"""LlamaIndex vector store over OpenArch's chunk (embeddings) index.

Query modes:

- DEFAULT: kNN over the chunks (``/api/query/embeddings``);
- HYBRID: kNN plus a match of the query terms in the chunk text, fused by OpenSearch's RRF
  pipeline inside OpenArch (``chunkFTS``);
- TEXT_SEARCH: keyword search: the chunks of the documents whose text (``sys_fulltext``)
  has a query term, ranked by how many query terms each chunk holds (content-lake's keyword
  leg: OpenArch's plain ``/api/query`` returns documents, not chunks).

A scope filter on ``doc_id`` (``IN`` / ``==``) becomes an HXQL ``cin_id IN (...)`` condition, so
scoped questions are filtered inside OpenArch, by the documents' source identities.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Set

from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.schema import BaseNode, NodeRelationship, RelatedNodeInfo, TextNode
from llama_index.core.vector_stores.types import (
    BasePydanticVectorStore,
    FilterOperator,
    MetadataFilters,
    VectorStoreQuery,
    VectorStoreQueryMode,
    VectorStoreQueryResult,
)

from openarch.client import OpenArchClient, hxql_literal
from openarch.source_system import document_identity
from openarch.writer import METADATA_KEY, OpenArchDocumentWriter, doc_ids_of

logger = logging.getLogger(__name__)

_STOP_WORDS = frozenset(
    "the and for are but not you all any can had her was one our out has him his how its may new now "
    "old see two who did get got let put say she too use what when where which while with this that "
    "from have they will would there their about into than then them these those been being some such "
    "only also does more most other over very just like each".split())
_TERM = re.compile(r"[\w'-]+", re.UNICODE)
_MAX_TERMS = 12


def query_terms(text: str) -> List[str]:
    """Search terms of a question: lowercase words of 3+ characters, stop words removed."""
    terms: List[str] = []
    for word in _TERM.findall((text or "").lower()):
        word = word.strip("'-")
        if len(word) >= 3 and word not in _STOP_WORDS and word not in terms:
            terms.append(word)
    return terms[:_MAX_TERMS]


class OpenArchVectorStore(BasePydanticVectorStore):
    """Chunks and embeddings in OpenArch, one source document per OpenArch document."""

    stores_text: bool = True
    flat_metadata: bool = False

    embedding_type: str
    write_concurrency: int = 4
    keyword_candidates: int = 75

    _client: OpenArchClient = PrivateAttr()
    _writer: OpenArchDocumentWriter = PrivateAttr()

    def __init__(self, client: OpenArchClient, embedding_type: str, root_path: str = "/fg-sources",
                 max_text_chars: int = 64000, write_concurrency: int = 4):
        super().__init__(embedding_type=embedding_type, write_concurrency=write_concurrency)
        self._client = client
        self._writer = OpenArchDocumentWriter(client, embedding_type, root_path, max_text_chars)

    @classmethod
    def class_name(cls) -> str:
        return "OpenArchVectorStore"

    @property
    def client(self) -> OpenArchClient:
        return self._client

    @property
    def writer(self) -> OpenArchDocumentWriter:
        return self._writer

    # ----- writes -----

    def add(self, nodes: List[BaseNode], **add_kwargs: Any) -> List[str]:
        """Write the nodes' documents; without the source documents at hand, a document's text
        is its chunks' text (``add_documents`` passes the parsed text instead)."""
        return self.add_documents([], nodes)

    def add_documents(self, documents: Iterable[Any], nodes: List[BaseNode],
                      source: Optional[tuple] = None) -> List[str]:
        """Write each document of ``nodes`` (grouped by ``ref_doc_id``) with all its chunks, its
        text and metadata taken from ``documents`` when one has the same id."""
        by_id = {getattr(d, "doc_id", None) or getattr(d, "id_", None): d for d in documents}
        groups: Dict[str, List[BaseNode]] = defaultdict(list)
        for node in nodes:
            groups[node.ref_doc_id or node.node_id].append(node)

        def write(item):
            ref, chunks = item
            doc = by_id.get(ref)
            if doc is not None:
                text, metadata = doc.text, dict(doc.metadata or {})
            else:
                text = "\n\n".join(c.get_content() for c in chunks)
                metadata = dict(chunks[0].metadata or {})
            metadata.setdefault("doc_id", ref)
            return self._writer.write(ref, text, metadata, chunks, source=source)

        # Copy the source system context into the worker threads
        ctx = contextvars.copy_context()
        with ThreadPoolExecutor(max_workers=max(1, self.write_concurrency)) as pool:
            list(pool.map(lambda item: ctx.copy().run(write, item), groups.items()))
        logger.info("OpenArch: wrote %d document(s), %d chunk(s)", len(groups), len(nodes))
        return [n.node_id for n in nodes]

    async def async_add_documents(self, documents: Iterable[Any], nodes: List[BaseNode]) -> List[str]:
        import asyncio
        return await asyncio.to_thread(self.add_documents, list(documents), nodes)

    def delete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
        self._writer.remove(ref_doc_id)

    # ----- queries -----

    def query(self, query: VectorStoreQuery, **kwargs: Any) -> VectorStoreQueryResult:
        if query.query_embedding is None:
            logger.warning("OpenArch query without a query embedding: no results")
            return VectorStoreQueryResult(nodes=[], similarities=[], ids=[])
        top_k = query.similarity_top_k or 10
        wanted = self._scope_doc_ids(query.filters)
        where = []
        if wanted is not None:
            if not wanted:
                return VectorStoreQueryResult(nodes=[], similarities=[], ids=[])
            identities = sorted({document_identity(d, {}) for d in wanted})
            where.append("cin_id IN (" + ", ".join(hxql_literal(i) for i in identities) + ")")

        if query.mode == VectorStoreQueryMode.TEXT_SEARCH:
            hits = self._keyword_hits(query, top_k, where)
        else:
            chunk_fts = None
            if query.mode == VectorStoreQueryMode.HYBRID:
                chunk_fts = " ".join(query_terms(query.query_str or "")) or None
            hits = self._client.query_embeddings(
                list(query.query_embedding), limit=top_k, embedding_type=self.embedding_type,
                hxql=self._hxql(where), chunk_fts=chunk_fts)
        return self._result(hits, wanted)

    def _keyword_hits(self, query: VectorStoreQuery, top_k: int, where: List[str]) -> List[Dict[str, Any]]:
        terms = query_terms(query.query_str or "")
        if not terms:
            return []
        fulltext = "(" + " OR ".join(f"sys_fulltext = {hxql_literal(t)}" for t in terms) + ")"
        candidates = self._client.query_embeddings(
            list(query.query_embedding), limit=max(top_k, self.keyword_candidates),
            embedding_type=self.embedding_type, hxql=self._hxql(where + [fulltext]))
        scored = []
        for hit in candidates:
            text = (hit.get("sysembed_text") or "").lower()
            matched = sum(1 for t in terms if t in text)
            if matched:
                occurrences = sum(text.count(t) for t in terms)
                hit = dict(hit, sysembed_score=matched / len(terms) + min(occurrences, 20) / 1000.0)
                scored.append(hit)
        scored.sort(key=lambda h: h["sysembed_score"], reverse=True)
        return scored[:top_k]

    def _hxql(self, where: List[str]) -> str:
        """The chunks' documents: in this store's tree, and matching ``where``."""
        return "SELECT * FROM SysFile WHERE " + " AND ".join([self._writer.in_root] + list(where))

    @staticmethod
    def _scope_doc_ids(filters: Optional[MetadataFilters]) -> Optional[Set[str]]:
        """The doc ids a ``doc_id`` filter keeps, or None without one. Other filters are left to
        the caller's post-filtering (ScopedRetriever)."""
        if not filters:
            return None
        wanted: Optional[Set[str]] = None
        for f in filters.filters:
            if getattr(f, "key", None) != "doc_id":
                logger.debug("OpenArch: filter on %s not applied in the store", getattr(f, "key", f))
                continue
            values = f.value if isinstance(f.value, (list, tuple, set)) else [f.value]
            if f.operator in (FilterOperator.IN, FilterOperator.EQ):
                ids = {str(v) for v in values}
                wanted = ids if wanted is None else wanted & ids
        return wanted

    def _result(self, hits: List[Dict[str, Any]], wanted: Optional[Set[str]]) -> VectorStoreQueryResult:
        parents = self._parents({h.get("sysembed_docId") for h in hits if h.get("sysembed_docId")})
        nodes, similarities, ids = [], [], []
        for hit in hits:
            parent = parents.get(hit.get("sysembed_docId")) or {}
            props = parent.get("cin_ingestProperties") or {}
            try:
                metadata = json.loads(props.get(METADATA_KEY) or "{}")
            except ValueError:
                metadata = {}
            doc_ids = doc_ids_of(props)
            if wanted:
                # The document may belong to several data sources: name the one asked about
                doc_id = next((d for d in doc_ids if d in wanted), None)
            else:
                doc_id = metadata.get("doc_id") if metadata.get("doc_id") in doc_ids else None
            doc_id = doc_id or (doc_ids[0] if doc_ids else hit.get("sysembed_docId"))
            metadata.update({"doc_id": doc_id, "openarch_id": hit.get("sysembed_docId"),
                             "openarch_path": parent.get("sys_path")})
            node = TextNode(id_=hit.get("sysembed_id"), text=hit.get("sysembed_text") or "", metadata=metadata)
            node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=doc_id)
            nodes.append(node)
            similarities.append(float(hit.get("sysembed_score") or 0.0))
            ids.append(node.node_id)
        return VectorStoreQueryResult(nodes=nodes, similarities=similarities, ids=ids)

    def _parents(self, ids: Set[str]) -> Dict[str, Dict[str, Any]]:
        if not ids:
            return {}
        hxql = "SELECT * FROM SysFile WHERE sys_id IN (" + ", ".join(hxql_literal(i) for i in sorted(ids)) + ")"
        docs = self._client.query(hxql, limit=len(ids), sync=False).get("documents") or []
        return {d["sys_id"]: d for d in docs}
