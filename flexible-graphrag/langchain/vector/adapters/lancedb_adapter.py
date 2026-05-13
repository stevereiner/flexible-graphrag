"""LangChain LanceDB vector store adapter.

Wraps ``langchain_community.vectorstores.LanceDB`` for local or remote
LanceDB-backed vector search.

API note
--------
``langchain_community.vectorstores.LanceDB`` changed its constructor between
0.0.x and 0.1.x.  The old ``connection=<table>`` positional argument was
replaced by ``uri`` + ``table_name`` keyword arguments.  We detect the
available API at runtime and call the appropriate form.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.vector.vector_store_adapter import LangChainVectorAdapter

logger = logging.getLogger(__name__)

try:
    from langchain_community.vectorstores import LanceDB
    _LANCEDB_AVAILABLE = True
except ImportError:
    _LANCEDB_AVAILABLE = False


def _build_lancedb_store(config: Dict[str, Any], embedding):
    """Construct a ``LanceDB`` LangChain store, handling both old and new APIs.

    New API (langchain-community >= 0.0.20 / lancedb >= 0.4):
        LanceDB(uri=..., table_name=..., embedding=..., vector_column_name=..., text_key=...)

    Old API (langchain-community < 0.0.20):
        LanceDB(connection=<table_or_db>, embedding=..., vector_column_name=..., text_key=...)

    We try the new API first.  If it raises ``TypeError`` (unexpected ``uri``
    kwarg) we fall back to the old connection-based form.
    """
    import inspect

    uri = config.get("uri", "./lancedb")
    table_name = config.get("table_name", "hybrid_search")
    vector_col = config.get("vector_column_name", "vector")
    text_key = config.get("text_column_name", "text")

    lancedb_init_params = set(inspect.signature(LanceDB.__init__).parameters.keys())

    if "uri" in lancedb_init_params:
        # New API — uri + table_name (langchain-community >= 0.0.20 / lancedb >= 0.4)
        # mode="append" is critical: the default "overwrite" replaces the entire table
        # on every add_documents() call, making previously indexed documents invisible.
        kwargs: Dict[str, Any] = dict(
            uri=uri,
            table_name=table_name,
            embedding=embedding,
            text_key=text_key,
            mode="append",
        )
        # vector_column_name was removed in some langchain-lancedb builds — only pass if accepted
        if "vector_column_name" in lancedb_init_params:
            kwargs["vector_column_name"] = vector_col
        return LanceDB(**kwargs)

    # Old API — pass a connection or table object
    import lancedb as _lancedb

    db = _lancedb.connect(uri)
    try:
        table = db.open_table(table_name)
        connection_obj = table
    except Exception:
        connection_obj = db

    old_kwargs: Dict[str, Any] = dict(
        connection=connection_obj,
        embedding=embedding,
        text_key=text_key,
        mode="append",
    )
    if "vector_column_name" in lancedb_init_params:
        old_kwargs["vector_column_name"] = vector_col
    return LanceDB(**old_kwargs)


class LanceDBVectorAdapter(LangChainVectorAdapter):
    """Vector store adapter backed by LanceDB.

    Uses ``langchain_community.vectorstores.LanceDB``.  Opens (or creates)
    a LanceDB table at the configured URI and wraps it in a LangChain
    VectorStore.

    Configuration keys
    ------------------
    uri               LanceDB data directory or remote URI (default ``./lancedb``)
    table_name        LanceDB table name (default ``hybrid_search``)
    vector_column_name  Column for the embedding vector (default ``vector``)
    text_column_name  Column for the text content (default ``text``)
    embedding         LangChain Embeddings instance (required for ingestion)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        delete_key: str = "ref_doc_id",
        embedding=None,
    ):
        if not _LANCEDB_AVAILABLE:
            raise ImportError(
                "langchain-community and lancedb required. "
                "Install: pip install langchain-community lancedb"
            )

        self._lancedb_uri = config.get("uri", "./lancedb")
        self._lancedb_table_name = config.get("table_name", "hybrid_search")

        store = _build_lancedb_store(config, embedding)

        super().__init__(store=store, delete_key=delete_key)
        # Install MVCC refresh shim on the raw store so that the LangChain retriever
        # (built via get_store() → lc_raw_store.as_retriever()) also sees the latest
        # table version on every search, not just the version at store-construction time.
        self._install_search_refresh_patch()
        logger.info(
            "LanceDBVectorAdapter: table=%s at %s",
            self._lancedb_uri,
            self._lancedb_table_name,
        )

    def _refresh_table(self) -> None:
        """Refresh the LanceDB store's internal table to the latest MVCC version.

        LanceDB uses MVCC — the LangChain store object holds a reference to the
        table at the version that existed when the store was created.  After new
        documents are added (each add creates a new manifest version), the old
        in-memory table reference is stale and similarity_search returns 0 results.

        We call ``get_table(set_default=True)`` which re-opens the table at the
        latest version and updates ``store._table`` in-place.  Because the
        LangChain retriever also holds a direct reference to ``self._store``, it
        picks up the same updated ``_table`` attribute automatically.
        """
        try:
            if hasattr(self._store, "get_table"):
                self._store.get_table(set_default=True)
            elif hasattr(self._store, "_table") and hasattr(self._store, "uri"):
                # Fallback: reopen table directly via lancedb
                import lancedb as _lancedb
                _db = _lancedb.connect(self._lancedb_uri)
                self._store._table = _db.open_table(self._lancedb_table_name)
        except Exception as exc:
            logger.debug("LanceDBVectorAdapter: table refresh failed (non-fatal): %s", exc)

    def _install_search_refresh_patch(self) -> None:
        """Monkey-patch the raw LangChain LanceDB store's similarity_search methods.

        ``retriever_setup.py`` creates the LangChain retriever from the raw store
        (``system.vector_store.get_store()``), bypassing the adapter's overridden
        ``similarity_search`` methods.  Without this patch, the retriever always
        queries the stale MVCC version of the table (the version at startup), so
        documents added after startup are invisible to search.
        """
        adapter = self  # capture for closure

        _orig_ss = self._store.similarity_search
        _orig_ss_score = self._store.similarity_search_with_score

        def _l2_to_sim(distance: float) -> float:
            # LanceDB returns L2/cosine distance (0 = perfect match, higher = worse).
            # Convert to similarity so that 0→1.0 and high→~0 to avoid the
            # zero-score filter in query_engine.py discarding the best matches.
            return 1.0 / (1.0 + max(0.0, distance))

        def _refreshing_search(query, k=4, **kwargs):
            adapter._refresh_table()
            return _orig_ss(query, k=k, **kwargs)

        def _refreshing_search_score(query, k=4, **kwargs):
            adapter._refresh_table()
            raw = _orig_ss_score(query, k=k, **kwargs)
            return [(doc, _l2_to_sim(score)) for doc, score in raw]

        # Patch directly on the instance — these take precedence over class methods
        self._store.similarity_search = _refreshing_search
        self._store.similarity_search_with_score = _refreshing_search_score
        logger.debug("LanceDBVectorAdapter: installed MVCC refresh patch on raw store")

    def add_documents(self, documents, **kwargs):
        """Override to log row count before/after for MVCC diagnostics."""
        import lancedb as _lancedb
        try:
            _db = _lancedb.connect(self._lancedb_uri)
            _tbl = _db.open_table(self._lancedb_table_name)
            before = len(_tbl.to_pandas())
        except Exception:
            before = -1
        result = self._store.add_documents(documents, **kwargs)
        try:
            _tbl2 = _db.open_table(self._lancedb_table_name)
            after = len(_tbl2.to_pandas())
        except Exception:
            after = -1
        logger.info(
            "LanceDBVectorAdapter: add_documents %d docs | rows before=%d after=%d",
            len(documents), before, after,
        )
        return result

    def similarity_search_with_score(self, query: str, k: int = 4, **kwargs):
        self._refresh_table()
        return self._store.similarity_search_with_score(query, k=k, **kwargs)

    def similarity_search(self, query: str, k: int = 4, **kwargs):
        self._refresh_table()
        return self._store.similarity_search(query, k=k, **kwargs)

    def delete(self, ref_doc_id: str) -> None:
        """Delete LanceDB rows matching ref_doc_id.

        LanceDB stores metadata as an Arrow struct — field access is metadata.field_name.
        Windows paths may be stored lowercase (c:\\...) but the engine passes the
        doc_id with the original casing from PostgreSQL document_state (C:\\...).
        We try both cases.

        LanceDB uses MVCC — a delete that races with a concurrent Overwrite raises
        ``Incompatible transaction``.  Retry up to 3 times with a short back-off.
        """
        import time
        import lancedb as _lancedb

        # Open table directly via lancedb — avoids relying on the LangChain store's
        # internal _table attribute which may be None for uri-based construction.
        try:
            db = _lancedb.connect(self._lancedb_uri)
            table = db.open_table(self._lancedb_table_name)
        except Exception as exc:
            logger.warning("LanceDBVectorAdapter: cannot open table for delete: %s", exc)
            return

        # Escape single quotes; try both original case and lowercase (Windows path normalisation)
        safe_id = ref_doc_id.replace("'", "''")
        safe_id_lower = safe_id.lower()

        predicates = [
            f"metadata.{self._delete_key} = '{safe_id}'",
            f"metadata.{self._delete_key} = '{safe_id_lower}'",
            f"metadata.ref_doc_id = '{safe_id}'",
            f"metadata.ref_doc_id = '{safe_id_lower}'",
            f"metadata.doc_id = '{safe_id}'",
            f"metadata.doc_id = '{safe_id_lower}'",
        ]

        for attempt in range(3):
            try:
                total_deleted = 0
                for pred in predicates:
                    try:
                        # Re-open the table for each predicate — LanceDB MVCC increments the
                        # table version after every delete, and a stale table handle may not
                        # see rows added by previous operations in the same process.
                        fresh_table = db.open_table(self._lancedb_table_name)
                        result = fresh_table.delete(pred)
                        n = getattr(result, "num_deleted_rows", None)
                        if n is None:
                            n = 0
                        total_deleted += n
                    except Exception as pred_exc:
                        logger.debug("LanceDBVectorAdapter: delete pred %r failed: %s", pred[:60], pred_exc)
                if total_deleted:
                    logger.info(
                        "LanceDBVectorAdapter: deleted %d row(s) for ref_doc_id=%s",
                        total_deleted, ref_doc_id,
                    )
                else:
                    logger.warning("LanceDBVectorAdapter: 0 rows matched for ref_doc_id=%s", ref_doc_id)
                return
            except Exception as exc:
                if "Incompatible transaction" in str(exc) and attempt < 2:
                    logger.debug(
                        "LanceDBVectorAdapter: Incompatible transaction on delete attempt %d, retrying...",
                        attempt + 1,
                    )
                    time.sleep(0.5 * (attempt + 1))
                else:
                    logger.warning("LanceDBVectorAdapter delete failed for %s: %s", ref_doc_id, exc)
                    return


__all__ = ["LanceDBVectorAdapter", "_LANCEDB_AVAILABLE"]
