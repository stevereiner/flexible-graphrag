"""langchain.utils — Bridge utilities between LlamaIndex and LangChain.

These helpers are backend-agnostic and used across search, vector, and
graph sub-packages.
"""
from __future__ import annotations

import re
import uuid
from typing import List

from langchain_core.documents import Document as LCDocument


def _sanitize_metadata_key(key: str) -> str:
    """Normalise a metadata key for stores that reject spaces / special chars.

    Milvus, Weaviate, and others only accept ``[A-Za-z_][A-Za-z0-9_]*``-style
    field names.  LlamaIndex emits ``"modified at"`` (with a space) which
    breaks collection creation in these stores.

    Rules:
    - Replace runs of whitespace and hyphens with ``_``
    - Strip any remaining characters outside ``[A-Za-z0-9_]``
    - Prefix with ``_`` if the result starts with a digit
    """
    s = re.sub(r"[\s\-]+", "_", key)
    s = re.sub(r"[^A-Za-z0-9_]", "", s)
    if s and s[0].isdigit():
        s = "_" + s
    return s or "_unknown"


def llamaindex_nodes_to_langchain_docs(nodes_or_docs) -> List[LCDocument]:
    """Convert LlamaIndex ``TextNode`` / ``Document`` objects to LangChain ``Document`` objects.

    Copies ``text`` -> ``page_content`` and all metadata.  Metadata keys are
    sanitised to ``[A-Za-z0-9_]`` so Milvus / Weaviate / other strict stores
    do not reject field names containing spaces (e.g. LlamaIndex's
    ``"modified at"`` key).  ``ref_doc_id`` is preserved for delete-by-ref
    to work correctly across all LangChain adapters.
    """
    lc_docs: List[LCDocument] = []
    for node in nodes_or_docs:
        text = getattr(node, "text", None) or getattr(node, "get_content", lambda: "")()
        raw_meta = dict(getattr(node, "metadata", {}) or {})
        # Sanitise keys — replace spaces/hyphens → underscore, drop invalid chars
        metadata = {_sanitize_metadata_key(k): v for k, v in raw_meta.items()}
        ref_doc_id = (
            metadata.get("ref_doc_id")
            or getattr(node, "ref_doc_id", None)
            or getattr(node, "id_", None)
        )
        if ref_doc_id:
            metadata["ref_doc_id"] = str(ref_doc_id)
        lc_docs.append(LCDocument(page_content=text or "", metadata=metadata))
    return lc_docs


def sanitize_langchain_doc_metadata(lc_docs: List[LCDocument]) -> List[LCDocument]:
    """Return *new* LCDocument objects with sanitised metadata keys.

    Applies :func:`_sanitize_metadata_key` to every key in each document's
    metadata so stores that reject spaces / special chars (Milvus, Weaviate,
    Qdrant scalar filters) do not raise on ``add_documents``.

    Called by the full-LC pipeline in ``update_vector`` / ``update_search``
    before writing ``_last_lc_chunks`` directly to a LangChain store.
    """
    result: List[LCDocument] = []
    for doc in lc_docs:
        clean_meta = {_sanitize_metadata_key(k): v for k, v in (doc.metadata or {}).items()}
        result.append(LCDocument(page_content=doc.page_content, metadata=clean_meta))
    return result


def langchain_docs_to_llamaindex_nodes(lc_docs: List[LCDocument]) -> List:
    """Convert LangChain ``Document`` objects to thin LI ``TextNode`` objects.

    No embeddings are attached — this creates bridge nodes so KG-extraction
    and RDF-export consumers work unchanged when ``CHUNKER_BACKEND=langchain``
    and the vector store is LC-backed (handles its own embedding).

    Each output node carries:
    - ``text``      = ``page_content``
    - ``metadata``  = ``metadata`` (keys preserved as-is; caller sanitises)
    - ``id_``       = deterministic UUID derived from ``ref_doc_id`` + position + text prefix
    - ``ref_doc_id``= from metadata ``ref_doc_id`` or ``doc_id``
    """
    try:
        from llama_index.core.schema import TextNode
    except ImportError:
        return []

    nodes = []
    for i, doc in enumerate(lc_docs):
        meta = dict(doc.metadata or {})
        ref_doc_id = meta.get("ref_doc_id") or meta.get("doc_id", "")
        # Deterministic ID: ref_doc_id + chunk position + first 32 chars of text
        node_id = str(uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"{ref_doc_id}:{i}:{(doc.page_content or '')[:32]}",
        ))
        node = TextNode(
            text=doc.page_content or "",
            id_=node_id,
            metadata=meta,
        )
        nodes.append(node)
    return nodes


__all__ = [
    "llamaindex_nodes_to_langchain_docs",
    "langchain_docs_to_llamaindex_nodes",
    "sanitize_langchain_doc_metadata",
]
