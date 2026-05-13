"""LangChain Milvus vector store adapter.

Wraps ``langchain_milvus.Milvus`` (first-party, preferred) falling back to
``langchain_community.vectorstores.Milvus``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.vector.vector_store_adapter import LangChainVectorAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_milvus import Milvus
    _MILVUS_AVAILABLE = True
    _MILVUS_SOURCE = "langchain_milvus"
except ImportError:
    try:
        from langchain_community.vectorstores import Milvus  # type: ignore
        _MILVUS_AVAILABLE = True
        _MILVUS_SOURCE = "langchain_community"
    except ImportError:
        Milvus = None  # type: ignore[assignment,misc]
        _MILVUS_AVAILABLE = False
        _MILVUS_SOURCE = None


def _build_milvus_connection_args(config: Dict[str, Any]) -> Dict[str, Any]:
    """Build pymilvus connection_args from config.

    ``langchain_milvus.Milvus`` now uses ``MilvusClient`` internally, which
    requires a ``uri`` kwarg rather than the legacy ``host``/``port`` form.
    Passing ``host``/``port`` only lands in ``**kwargs`` and is silently ignored,
    leaving the internal alias in an undefined state (causes
    ``ConnectionNotExistException`` on the first ``add_documents`` call).

    Rules:
    - If ``uri`` is given explicitly, use it as-is (Zilliz Cloud HTTPS endpoint).
    - Otherwise build ``http://{host}:{port}`` — valid for Milvus 2.3+ standalone
      which serves both gRPC and REST on port 19530.
    """
    if config.get("uri"):
        args: Dict[str, Any] = {"uri": config["uri"]}
    else:
        host = config.get("host", "localhost")
        port = config.get("port", 19530)
        args = {"uri": f"http://{host}:{port}"}
    if config.get("token"):
        args["token"] = config["token"]
    if config.get("username") and config.get("password"):
        args["user"] = config["username"]
        args["password"] = config["password"]
    return args


class _MilvusPatch(Milvus if _MILVUS_AVAILABLE else object):  # type: ignore[misc]
    """Subclass of langchain_milvus.Milvus that bridges the new/old pymilvus APIs.

    ``langchain_milvus.Milvus`` creates a ``MilvusClient`` (new API) internally and
    stores ``self.alias = f"cm-{id(self._milvus_client._handler)}"`` for legacy
    compatibility.  However ``MilvusClient`` never registers that alias in the global
    ``pymilvus.connections`` singleton, so every subsequent call to the old ORM
    ``Collection(..., using=self.alias)`` raises ``ConnectionNotExistException``.

    This subclass overrides ``_init`` to register a proper ``GrpcHandler`` under the
    same alias *before* the parent's ``_init`` logic runs, which eliminates the error.
    """

    def _init(self, *args, **kwargs):
        try:
            from pymilvus import connections as _pmc
            if self.alias not in _pmc._alias_handlers:
                ca = getattr(self, "_connection_args", {}) or {}
                uri = ca.get("uri")
                if uri:
                    _pmc.connect(self.alias, uri=uri)
                else:
                    _pmc.connect(
                        self.alias,
                        host=ca.get("host", "localhost"),
                        port=int(ca.get("port", 19530)),
                    )
                logger.debug("Milvus: registered legacy alias %s in connections", self.alias)
        except Exception as _exc:
            logger.debug("Milvus legacy alias registration skipped: %s", _exc)
        return super()._init(*args, **kwargs)


def _l2_to_similarity(distance: float) -> float:
    """Convert an L2 distance (0 = perfect match, ∞ = worst) to a similarity score.

    Milvus's default AUTOINDEX/FLAT uses L2 metric and returns raw squared-L2
    distance in the ``distance`` field.  The value is 0 for an identical vector
    and grows with dissimilarity.  Our retrieval stack uses the returned score as
    a *similarity* (higher = better) and filters out scores ≤ 0, so a perfectly
    matching document (L2 = 0.0) would be discarded.

    Transformation: ``1 / (1 + distance)`` maps [0, ∞) → (0, 1] with
    0 → 1.0 (perfect) and large values → 0 (worst).  This makes the score safe
    for use alongside cosine-similarity scores from other stores.
    """
    return 1.0 / (1.0 + max(0.0, distance))


class MilvusVectorAdapter(LangChainVectorAdapter):
    """Vector store adapter backed by Milvus / Zilliz Cloud.

    Uses ``langchain_milvus.Milvus`` (first-party) falling back to
    ``langchain_community``.

    Configuration keys
    ------------------
    host             Milvus host (default ``localhost``)
    port             Milvus gRPC port (default ``19530``)
    uri              Full URI — overrides host/port when given (e.g. Zilliz Cloud HTTPS endpoint)
    token            API token for Zilliz Cloud (optional)
    username         Username for auth (optional)
    password         Password for auth (optional)
    collection_name  Collection to use (default ``hybrid_search``)
    embedding_field  Field for the vector (default ``vector``)
    text_field       Field for text content (default ``text``)
    embedding        LangChain Embeddings instance (required for ingestion)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        delete_key: str = "ref_doc_id",
        embedding=None,
    ):
        if not _MILVUS_AVAILABLE:
            raise ImportError(
                "langchain-milvus required. Install: pip install langchain-milvus"
            )

        connection_args = _build_milvus_connection_args(config)
        collection_name = config.get("collection_name", "hybrid_search")

        store = _MilvusPatch(
            embedding_function=embedding,
            collection_name=collection_name,
            connection_args=connection_args,
            vector_field=config.get("embedding_field", "vector"),
            text_field=config.get("text_field", "text"),
            auto_id=True,
            drop_old=False,
        )
        super().__init__(store=store, delete_key=delete_key)
        self._patch_l2_scores(store)
        endpoint = config.get("uri") or f"http://{config.get('host', 'localhost')}:{config.get('port', 19530)}"
        logger.info(
            "MilvusVectorAdapter (%s): collection=%s at %s",
            _MILVUS_SOURCE,
            collection_name,
            endpoint,
        )

    def _patch_l2_scores(self, store) -> None:
        """Monkey-patch ``similarity_search_with_score`` to convert L2 distances.

        Milvus returns raw L2 distances (0 = perfect match, higher = worse).
        Our retrieval stack treats the returned value as a similarity score
        (higher = better) and filters out results with score ≤ 0.  A perfectly
        matching document (distance = 0.0) would be silently dropped.

        We wrap the method to apply ``_l2_to_similarity`` to each raw distance
        before it reaches the upstream callers.
        """
        _orig = store.similarity_search_with_score

        def _patched(query, k=4, **kwargs):
            results = _orig(query, k=k, **kwargs)
            return [(doc, _l2_to_similarity(raw_score)) for doc, raw_score in results]

        store.similarity_search_with_score = _patched
        logger.debug("MilvusVectorAdapter: installed L2→similarity score patch")

    def delete(self, ref_doc_id: str) -> None:
        """Delete Milvus entities matching ref_doc_id in metadata.

        Backslashes in ref_doc_id (Windows paths) must be double-escaped in the
        Milvus expression parser — ``\n``, ``\t`` etc. are treated as escape seqs.
        We use MilvusClient.delete() which also supports a filter expression.
        """
        if self._store is None:
            return
        try:
            # Escape backslashes so Milvus expression parser doesn't interpret them
            escaped = ref_doc_id.replace("\\", "\\\\")

            # Try pymilvus MilvusClient path (new API) — most reliable
            connection_args = getattr(self._store, "connection_args", None) or {}
            uri = connection_args.get("uri") or f"http://localhost:19530"
            collection_name = getattr(self._store, "collection_name", "hybrid_search")

            from pymilvus import MilvusClient
            client = MilvusClient(uri=uri)
            # Milvus stores metadata as FLAT top-level fields (not a struct/JSON column).
            # Try ref_doc_id first, then doc_id — both are flat string columns.
            for field_expr in [
                f'ref_doc_id == "{escaped}"',
                f'doc_id == "{escaped}"',
            ]:
                try:
                    result = client.delete(collection_name=collection_name, filter=field_expr)
                    deleted = len(result) if isinstance(result, list) else (result.get("delete_count", 0) if isinstance(result, dict) else 0)
                    if deleted:
                        logger.info("MilvusVectorAdapter: deleted %s doc(s) for ref_doc_id=%s (expr=%s)",
                                    deleted, ref_doc_id, field_expr)
                        return
                except Exception:
                    pass
            logger.warning("MilvusVectorAdapter: 0 docs deleted for ref_doc_id=%s", ref_doc_id)
        except Exception as exc:
            logger.warning("MilvusVectorAdapter delete failed for %s: %s", ref_doc_id, exc)


__all__ = ["MilvusVectorAdapter", "_MILVUS_AVAILABLE"]
