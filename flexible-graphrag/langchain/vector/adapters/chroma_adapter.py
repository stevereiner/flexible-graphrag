"""LangChain Chroma vector store adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.vector.vector_store_adapter import LangChainVectorAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_chroma import Chroma
    _CHROMA_AVAILABLE = True
except ImportError:
    try:
        from langchain_community.vectorstores import Chroma  # type: ignore
        _CHROMA_AVAILABLE = True
    except ImportError:
        _CHROMA_AVAILABLE = False


class ChromaVectorAdapter(LangChainVectorAdapter):
    """Vector store adapter backed by Chroma.

    Configuration keys
    ------------------
    collection_name   Chroma collection (default ``hybrid_search``)
    persist_directory Path for persistent storage (optional; in-memory if omitted)
    embedding_function LangChain Embeddings instance (required for ingestion)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        delete_key: str = "ref_doc_id",
        embedding=None,
    ):
        if not _CHROMA_AVAILABLE:
            raise ImportError(
                "langchain-chroma required. Install: pip install langchain-chroma"
            )
        collection_name = config.get("collection_name", "hybrid_search")
        host = config.get("host")
        port = config.get("port", 8000)

        if host:
            # HTTP client mode — connects to a remote Chroma server
            try:
                import chromadb
                chroma_client = chromadb.HttpClient(host=host, port=int(port))
            except Exception as e:
                raise RuntimeError(
                    f"Cannot connect to Chroma HTTP server at {host}:{port}: {e}"
                ) from e
            store = Chroma(
                client=chroma_client,
                collection_name=collection_name,
                embedding_function=embedding,
            )
            logger.info("ChromaVectorAdapter (HTTP): collection=%s at %s:%s", collection_name, host, port)
        else:
            # Persistent (local) mode
            store = Chroma(
                collection_name=collection_name,
                persist_directory=config.get("persist_directory"),
                embedding_function=embedding,
            )
            logger.info(
                "ChromaVectorAdapter (local): collection=%s persist_dir=%s",
                collection_name,
                config.get("persist_directory"),
            )

        super().__init__(store=store, delete_key=delete_key)

    def delete(self, ref_doc_id: str) -> None:
        """Delete documents from Chroma by doc_id or ref_doc_id metadata field.

        The LC chunker path stores the stable ID under 'doc_id'; the LI path uses
        'ref_doc_id'.  Windows paths may also be stored lowercase — try both casings.
        """
        if self._store is None:
            return
        try:
            ref_lower = ref_doc_id.lower()
            # (key, value) pairs to try
            attempts = [
                ("doc_id", ref_doc_id),        # LC chunker path
                (self._delete_key, ref_doc_id),  # LI path
            ]
            if ref_lower != ref_doc_id:
                attempts += [
                    ("doc_id", ref_lower),
                    (self._delete_key, ref_lower),
                ]

            all_ids: list = []
            seen: set = set()
            for key, val in attempts:
                try:
                    results = self._store.get(where={key: val})
                    for doc_id in results.get("ids", []):
                        if doc_id not in seen:
                            seen.add(doc_id)
                            all_ids.append(doc_id)
                except Exception:
                    pass

            if all_ids:
                self._store.delete(ids=all_ids)
                logger.info("ChromaVectorAdapter: deleted %d docs for ref_doc_id=%s", len(all_ids), ref_doc_id)
            else:
                logger.debug("ChromaVectorAdapter: no docs found for ref_doc_id=%s", ref_doc_id)
        except Exception as exc:
            logger.warning("ChromaVectorAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["ChromaVectorAdapter", "_CHROMA_AVAILABLE"]
