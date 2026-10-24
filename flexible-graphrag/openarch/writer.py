"""Writes Flexible GraphRAG documents and their chunks into OpenArch.

Per source document:

- a ``SysFile`` with the ``CinRemote`` and ``SysHasEmbeddings`` mixins at
  ``<root>/<source key>/<source path>``, found again by ``cin_sourceId`` + ``cin_id``;
- its parsed text in ``cin_ingestProperties.fg_extractedText``: OpenArch copies the ingest
  property strings into the field ``sys_fulltext`` searches (a client can't set
  ``sys_fulltextBinary``, which only OpenArch's blob text extraction fills);
- its chunks as a Parquet blob (``id``, ``vector``, ``text``, ``location``) on a
  ``SysEmbeddings`` child named ``_e_<embedding type>``, which OpenArch explodes into its kNN index.

Flexible GraphRAG's doc ids (``<config_id>:<identity>``, one per data source) that refer to the
document are kept in ``fg_docIds``; removing the last one deletes the document, or only its
content (text, chunks) while data sources still keep their state on it (``FgDocState``, see
openarch/registry.py).
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from openarch.client import OpenArchClient, OpenArchError, hxql_literal, under
from openarch import source_system as ss

logger = logging.getLogger(__name__)

TEXT_KEY = "fg_extractedText"
DOC_IDS_KEY = "fg_docIds"
METADATA_KEY = "fg_metadata"
# Data sources' doc ids on a document that holds their state (FgDocState, openarch/registry.py)
STATE_DOC_IDS = "fg_docstate_docIds"

_WRITE_RETRIES = 8  # conditional updates of a document changed concurrently

# Ingest properties that describe the stored content: removed with it
_CONTENT_KEYS = (TEXT_KEY, DOC_IDS_KEY, METADATA_KEY, "fg_embeddingType", "fg_chunkCount", "fg_indexedAt")

# Document metadata worth keeping for search results (source attribution, open links)
_KEPT_METADATA = (
    "doc_id", "file_name", "file_path", "human_file_path", "stable_file_path", "source", "file_type",
    "content_type", "modified_at", "alfresco_id", "nuxeo_id", "cmis_id", "s3_uri", "s3_key", "bucket_name",
    "url", "source_url", "title", "page_id", "file id", "file_id", "box_file_id", "container", "name",
    "conversion_method",
)

_EMBEDDING_TYPE_CHARS = re.compile(r"[^a-z0-9._-]")


def embedding_type_name(kind: Optional[str], model: Optional[str], dimension: Optional[int]) -> str:
    """OpenArch embedding type of a model (the ``_e_<type>`` child name and the kNN filter):
    lowercase, ``[a-z0-9._-]``, at most 200 characters, like content-lake's resolver."""
    raw = "-".join(str(p) for p in ("fg", kind, model, dimension) if p)
    return _EMBEDDING_TYPE_CHARS.sub("-", raw.lower())[:200]


def doc_ids_of(props: Dict[str, Any]) -> List[str]:
    return [d for d in str(props.get(DOC_IDS_KEY) or "").split("\n") if d]


def create_source_document(client: OpenArchClient, root_path: str, source_type: str, system: str,
                           segments: List[str], body: Dict[str, Any]) -> Dict[str, Any]:
    """Create a source document at ``<root>/<source type>/<system>/<segments>`` (``body`` has
    its type, mixins and properties), creating the missing folders; returns the document."""
    parent = f"{root_path}/{ss.source_folder(source_type, system)}/" + "/".join(segments[:-1])
    client.ensure_folders(parent)
    name = segments[-1]
    try:
        return client.create(parent, dict(body, sys_name=name))
    except OpenArchError as e:
        if e.status_code != 409:
            raise
    # Another object of the source already has this name here (a non-hierarchical source,
    # or a rename): keep both, the second with its identity's hash in the name
    return client.create(parent, dict(body, sys_name=_unique_name(name, body["cin_id"])))


def _unique_name(name: str, identity: str) -> str:
    """``name`` with the identity's hash in it, for a second object of the source with that name."""
    suffix = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:8]
    stem, dot, ext = name.rpartition(".")
    return f"{stem}~{suffix}.{ext}" if dot and stem else f"{name}~{suffix}"


def place_source_document(client: OpenArchClient, root_path: str, source_type: str, system: str,
                          segments: List[str], doc: Dict[str, Any]) -> Dict[str, Any]:
    """Move and / or rename an existing source document to ``<root>/<source type>/<system>/<segments>``
    after its source object was moved or renamed, so the tree follows the source. Returns the
    document at its new place. A rename is a move with the new name; a stock OpenArch's move takes
    no name (and an update ignores sys_name), so there the rename is a copy under the new name (its
    chunk children with it) and the old one's deletion -- a new document, with a new sys_id."""
    parent = "/" + (f"{root_path}/{ss.source_folder(source_type, system)}/" + "/".join(segments[:-1])).strip("/")
    name = segments[-1]
    unique = _unique_name(name, str(doc.get("cin_id") or ""))
    current_parent, _, current_name = str(doc.get("sys_path") or "").rpartition("/")
    if current_parent == parent and current_name in (name, unique):
        return doc
    old_path = doc.get("sys_path")
    if current_parent != parent:
        client.ensure_folders(parent)
    target = client.get_by_path(parent)
    placed = False
    for candidate in (name, unique):
        try:
            doc = client.move(doc["sys_id"], target["sys_id"], None if candidate == current_name else candidate)
        except OpenArchError as e:
            if e.status_code != 409:
                raise
            continue  # the name is taken there: the unique one
        current_name = str(doc.get("sys_path") or "").rpartition("/")[2]
        placed = current_name in (name, unique)  # False: the server ignored the name
        break
    if not placed:
        old_id = doc["sys_id"]
        try:
            copied = client.copy(old_id, target["sys_id"], name)
        except OpenArchError as e:
            if e.status_code != 409:
                raise
            copied = client.copy(old_id, target["sys_id"], unique)
        delete_with_chunks(client, old_id)
        doc = client.get(copied["sys_id"]) or copied
    logger.info("OpenArch: %s moved to %s (its source object was moved or renamed)", old_path, doc.get("sys_path"))
    return doc


def delete_chunks(client: OpenArchClient, doc_id: str) -> None:
    """Delete a document's chunk (SysEmbeddings) children."""
    for child in client.query_all(f"SELECT * FROM SysEmbeddings WHERE sys_parentId = {hxql_literal(doc_id)}"):
        client.delete(child["sys_id"])


def delete_with_chunks(client: OpenArchClient, doc_id: str) -> None:
    """Delete a document, its chunks first: their deletion with the parent is not guaranteed."""
    delete_chunks(client, doc_id)
    client.delete(doc_id)


class OpenArchDocumentWriter:
    """Creates, updates and removes source documents and their embeddings in OpenArch."""

    def __init__(self, client: OpenArchClient, embedding_type: str, root_path: str = "/fg-sources",
                 max_text_chars: int = 64000):
        self.client = client
        self.embedding_type = embedding_type
        self.root_path = "/" + root_path.strip("/")
        self.in_root = under(self.root_path)  # lookups stay in this tree
        self.max_text_chars = max_text_chars

    # ----- lookups -----

    def find(self, cin_source_id: Optional[str], identity: str) -> Optional[Dict[str, Any]]:
        """The document of a source object, from the repository (consistent with the last writes)."""
        where = f"cin_id = {hxql_literal(identity)} AND {self.in_root}"
        if cin_source_id:
            where += f" AND cin_sourceId = {hxql_literal(cin_source_id)}"
        docs = self.client.query(f"SELECT * FROM SysFile WHERE {where}", limit=10).get("documents") or []
        return docs[0] if docs else None

    def find_by_doc_id(self, fg_doc_id: str) -> Optional[Dict[str, Any]]:
        """The document a Flexible GraphRAG doc id refers to (any source system)."""
        if ss.is_data_source_doc_id(fg_doc_id):
            identity = ss.document_identity(fg_doc_id, {})
            docs = self.client.query(f"SELECT * FROM SysFile WHERE cin_id = {hxql_literal(identity)} AND {self.in_root}",
                                     limit=50).get("documents") or []
        else:
            # An ad-hoc ingest's id, the document's only doc id. Keys inside cin_ingestProperties
            # can only be queried on OpenSearch (the repository query validates the schema)
            docs = self.client.query(
                f"SELECT * FROM SysFile WHERE cin_ingestProperties.{DOC_IDS_KEY} = {hxql_literal(fg_doc_id)} "
                f"AND {self.in_root}", limit=50, sync=False).get("documents") or []
        for doc in docs:
            if fg_doc_id in doc_ids_of(doc.get("cin_ingestProperties") or {}):
                return doc
        return None

    # ----- writes -----

    def write(self, doc_id: str, text: str, metadata: Dict[str, Any], chunks: List[Any],
              source: Optional[tuple] = None) -> str:
        """Create or update one source document with its text and chunks; returns its OpenArch id.

        ``chunks`` are LlamaIndex nodes with their embeddings; ``source`` is the
        ``(source type, source system)`` of the ingest job.
        """
        source_type, system = source or ss.current_source_system() or (
            str(metadata.get("source") or "filesystem"), "default")
        identity = ss.document_identity(doc_id, metadata)
        cin_source = ss.cin_source_id(source_type, system)

        kept = {k: str(v) for k, v in metadata.items() if k in _KEPT_METADATA and v not in (None, "")}
        if doc_id:
            kept["doc_id"] = doc_id
        segments = ss.document_path(source_type, identity, metadata)

        def body_for(existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            props = dict((existing or {}).get("cin_ingestProperties") or {})
            # Data sources' doc ids accumulate (each one's removal is tracked); an ad-hoc
            # ingest's random id only lasts until the next write
            doc_ids = [d for d in doc_ids_of(props) if ss.is_data_source_doc_id(d)]
            if doc_id and doc_id not in doc_ids:
                doc_ids.append(doc_id)
            props.update({
                TEXT_KEY: (text or "")[: self.max_text_chars],
                DOC_IDS_KEY: "\n".join(doc_ids),
                METADATA_KEY: json.dumps(kept, ensure_ascii=False),
                "source_type": source_type,
                "source_path": str(metadata.get("human_file_path") or metadata.get("file_path") or identity),
                "source_mimeType": str(metadata.get("content_type") or metadata.get("file_type") or ""),
                "source_modifiedAt": str(metadata.get("modified_at") or ""),
                "fg_embeddingType": self.embedding_type,
                "fg_chunkCount": str(len(chunks)),
                "fg_indexedAt": datetime.now(timezone.utc).isoformat(),
            })
            body = {
                "sys_title": str(metadata.get("file_name") or metadata.get("title") or segments[-1]),
                "cin_id": identity,
                "cin_sourceId": cin_source,
                "cin_paths": [props["source_path"]],
                "cin_ingestProperties": props,
                "cin_ingestPropertyNames": sorted(props),
            }
            if existing:
                mixins = list(existing.get("sys_mixinTypes") or [])
                for mixin in ("CinRemote", "SysHasEmbeddings"):
                    if mixin not in mixins:
                        mixins.append(mixin)
                body["sys_mixinTypes"] = mixins
            return body

        existing = self.find(cin_source, identity)
        if existing is None:
            oa_id = self._create(source_type, system, segments, body_for(None))
        else:
            # Conditional on the version read: the mixins and fg_docIds are read-modify-write,
            # and data sources' state (openarch/registry.py) is written on the same document
            for attempt in range(_WRITE_RETRIES):
                try:
                    body = body_for(existing)
                    updated = self.client.update(existing["sys_id"], body,
                                                 condition=f"sys_ugen = {int(existing.get('sys_ugen') or 0)}")
                    oa_id = updated["sys_id"]
                    # where its source object now is (moved or renamed), or where the naming rules
                    # put it: a no-op when it is already there
                    oa_id = place_source_document(self.client, self.root_path, source_type, system,
                                                  segments, updated)["sys_id"]
                    break
                except OpenArchError as e:
                    if e.status_code not in (409, 412) or attempt == _WRITE_RETRIES - 1:
                        raise
                existing = self.client.get(existing["sys_id"]) or existing

        if chunks:
            self._write_embeddings(oa_id, chunks)
        logger.info("OpenArch: wrote %s (%d chunks) as %s", identity, len(chunks), oa_id)
        return oa_id

    def _create(self, source_type: str, system: str, segments: List[str], body: Dict[str, Any]) -> str:
        body = dict(body, sys_primaryType="SysFile", sys_mixinTypes=["CinRemote", "SysHasEmbeddings"])
        return create_source_document(self.client, self.root_path, source_type, system, segments, body)["sys_id"]

    def _write_embeddings(self, oa_id: str, chunks: List[Any]) -> None:
        data = parquet_bytes(chunks, self.embedding_type)
        upload_id = self.client.upload(data, "embeddings.parquet", "application/x-parquet")
        name = f"_e_{self.embedding_type}"
        child = self._embeddings_child(oa_id)
        if child:
            self.client.update(child["sys_id"], {"sysemb_embeddings": {"uploadId": upload_id}})
        else:
            self.client.create_child(oa_id, {"sys_primaryType": "SysEmbeddings", "sys_name": name,
                                             "sys_title": "Embeddings",
                                             "sysemb_embeddings": {"uploadId": upload_id}})

    def _embeddings_child(self, oa_id: str) -> Optional[Dict[str, Any]]:
        name = f"_e_{self.embedding_type}"
        children = self.client.query(
            f"SELECT * FROM SysEmbeddings WHERE sys_parentId = {hxql_literal(oa_id)}", limit=50
        ).get("documents") or []
        return next((c for c in children if c.get("sys_name") == name), None)

    # ----- removal -----

    def remove(self, fg_doc_id: str) -> bool:
        """Remove a data source's reference to a document; the document (and its chunks) goes
        when no data source refers to it any more -- only its content while data sources keep
        their state on it. Returns whether anything was found."""
        doc = self.find_by_doc_id(fg_doc_id)
        if doc is None:
            return False
        props = dict(doc.get("cin_ingestProperties") or {})
        remaining = [d for d in doc_ids_of(props) if d != fg_doc_id]
        if remaining:
            props[DOC_IDS_KEY] = "\n".join(remaining)
            self.client.update(doc["sys_id"], {"cin_ingestProperties": props,
                                               "cin_ingestPropertyNames": sorted(props)})
            logger.info("OpenArch: %s no longer refers to %s (%d other(s) still do)",
                        fg_doc_id, doc["sys_id"], len(remaining))
            return True
        if doc.get(STATE_DOC_IDS) or doc.get("fg_rule_path"):
            # Data sources keep their state on it, or a scope rule (openarch/scope.py): the
            # state store deletes it with the last one
            delete_chunks(self.client, doc["sys_id"])
            for key in _CONTENT_KEYS:
                props.pop(key, None)
            self.client.update(doc["sys_id"], {"cin_ingestProperties": props,
                                               "cin_ingestPropertyNames": sorted(props)})
            logger.info("OpenArch: removed the content of %s (%s), kept its data source state",
                        doc["sys_id"], fg_doc_id)
            return True
        delete_with_chunks(self.client, doc["sys_id"])
        logger.info("OpenArch: deleted %s (%s)", doc["sys_id"], fg_doc_id)
        return True


def parquet_bytes(chunks: Iterable[Any], embedding_type: str) -> bytes:
    """The chunks as the Parquet file OpenArch's embeddings parser reads: ``id`` (a UUID is kept
    as the chunk's id in the index), ``vector``, ``text``, ``location`` (JSON)."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [c for c in chunks if getattr(c, "embedding", None)]
    schema = pa.schema([
        pa.field("id", pa.string(), nullable=False),
        pa.field("type", pa.string()),
        pa.field("vector", pa.list_(pa.float64())),
        pa.field("text", pa.string()),
        pa.field("blobref", pa.string()),
        pa.field("location", pa.string()),
    ])
    table = pa.table({
        "id": [c.node_id for c in rows],
        "type": [embedding_type] * len(rows),
        "vector": [[float(x) for x in c.embedding] for c in rows],
        "text": [c.get_content() for c in rows],
        "blobref": [None] * len(rows),
        "location": [json.dumps({"text": {"paragraph": i}}) for i in range(len(rows))],
    }, schema=schema)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    return buf.getvalue()
