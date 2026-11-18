"""LlamaIndex LanceDB vector store adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


def conform_metadata_rows(table: Any, data: Any, reported: set) -> Any:
    """Fit each row's ``metadata`` to the table's metadata struct before an append.

    LanceDB keeps a node's metadata as one Arrow struct column whose fields are fixed by the
    table's first insert, and it refuses a later row with a key that struct lacks ("Invalid input,
    field 'alfresco_id' does not exist in table schema") or a value of another type. So a second
    kind of source (Alfresco after local files, say) could not be added to the same table. Keys
    the struct lacks are left out of the struct only: the whole metadata is also in the row's
    ``_node_content`` JSON, which is what search results are rebuilt from. Keys the row lacks are
    stored as null, which LanceDB accepts.
    """
    if not isinstance(data, list):
        return data
    try:
        import pyarrow as pa

        struct = table.schema.field("metadata").type
    except Exception:
        return data
    if not pa.types.is_struct(struct):
        return data
    types = {struct.field(i).name: struct.field(i).type for i in range(struct.num_fields)}

    def fits(t, v) -> bool:
        if pa.types.is_null(t):
            return False
        if pa.types.is_boolean(t):
            return isinstance(v, bool)
        if pa.types.is_integer(t):
            return isinstance(v, int) and not isinstance(v, bool)
        if pa.types.is_floating(t):
            return isinstance(v, (int, float)) and not isinstance(v, bool)
        return True

    left_out = set()
    for row in data:
        md = row.get("metadata") if isinstance(row, dict) else None
        if not isinstance(md, dict):
            continue
        for key in list(md):
            t = types.get(key)
            if t is None:
                left_out.add(key)
                del md[key]
                continue
            v = md[key]
            if v is None:
                continue
            if pa.types.is_string(t) or pa.types.is_large_string(t):
                if not isinstance(v, str):
                    md[key] = str(v)
            elif not fits(t, v):
                md[key] = None
    new = left_out - reported
    if new:
        reported.update(new)
        logger.info(
            "LanceDB: metadata key(s) %s are not in the table's metadata columns (set by its first "
            "insert), so they are kept in each node's content only (not filterable).",
            ", ".join(sorted(new)),
        )
    return data


class LlamaIndexLanceDBAdapter(LlamaIndexVectorAdapter):
    """LlamaIndex vector store adapter backed by LanceDB.

    Configuration keys
    ------------------
    uri               LanceDB URI (default ``./lancedb``)
    table_name        Table name (default ``hybrid_search``)
    vector_column_name  Column for vector data (default ``vector``)
    text_column_name    Column for text content (default ``text``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.vector_stores.lancedb import LanceDBVectorStore
        import lancedb

        uri = config.get("uri", "./lancedb")
        table_name = config.get("table_name", "hybrid_search")

        # Drop the table if it exists but was created by a different backend
        # (e.g. LangChain) and is missing LlamaIndex's required 'doc_id' field.
        try:
            _db = lancedb.connect(uri)
            if table_name in _db.table_names():
                _t = _db.open_table(table_name)
                _field_names = {f.name for f in _t.schema}
                if "doc_id" not in _field_names:
                    logger.info(
                        "LanceDB table '%s' missing 'doc_id' field "
                        "(created by a different backend) — dropping for fresh creation.",
                        table_name,
                    )
                    _db.drop_table(table_name)
        except Exception as _exc:
            logger.debug("LanceDB schema check skipped: %s", _exc)

        # Stored for use by CocoIndexLanceDBVectorRetriever in retriever_setup.py:
        # when VECTOR_BACKEND=cocoindex the retriever reads these directly to open
        # the CocoIndex-written table without going through LanceDBVectorStore.
        self._lancedb_uri = uri
        self._lancedb_table_name = table_name
        # metadata keys already logged as left out of the table's metadata struct
        self._reported_keys: set = set()

        store = LanceDBVectorStore(
            uri=uri,
            table_name=table_name,
            vector_column_name=config.get("vector_column_name", "vector"),
            text_key=config.get("text_column_name", "text"),
            # create: lazy table creation on first add; append alone raises if missing
            mode="create",
        )
        super().__init__(store)
        self._install_mvcc_refresh_patch()
        logger.info("LlamaIndexLanceDBAdapter: uri=%s table=%s", uri, table_name)

    def _refresh_table(self) -> None:
        """Re-open the LanceDB table at the latest MVCC version."""
        try:
            conn = getattr(self._store, "_connection", None) or getattr(self._store, "client", None)
            table_name = getattr(self._store, "_table_name", None) or self._lancedb_table_name
            if conn is not None and table_name and table_name in conn.table_names():
                table = conn.open_table(table_name)
                orig_add = table.add

                def _add(data, *args, _orig=orig_add, _table=table, **kwargs):
                    return _orig(conform_metadata_rows(_table, data, self._reported_keys), *args, **kwargs)

                table.add = _add
                self._store._table = table
        except Exception as exc:
            logger.debug("LlamaIndexLanceDBAdapter: table refresh failed (non-fatal): %s", exc)

    def _install_mvcc_refresh_patch(self) -> None:
        """Refresh stale in-memory table handles before every read/write."""
        adapter = self
        store = self._store

        def _patch_method(method_name: str, is_async: bool) -> None:
            if not hasattr(store, method_name):
                return
            orig = getattr(store, method_name)
            if is_async:

                async def _async_wrapped(*args, _orig=orig, **kwargs):
                    adapter._refresh_table()
                    return await _orig(*args, **kwargs)

                wrapper = _async_wrapped
            else:

                def _sync_wrapped(*args, _orig=orig, **kwargs):
                    adapter._refresh_table()
                    return _orig(*args, **kwargs)

                wrapper = _sync_wrapped
            # Pydantic v2 models block setattr on undeclared attrs — bypass for method swap
            object.__setattr__(store, method_name, wrapper)

        _patch_method("add", is_async=False)
        _patch_method("async_add", is_async=True)
        _patch_method("aquery", is_async=True)
        logger.debug("LlamaIndexLanceDBAdapter: installed MVCC refresh patch on LanceDBVectorStore")


__all__ = ["LlamaIndexLanceDBAdapter"]
