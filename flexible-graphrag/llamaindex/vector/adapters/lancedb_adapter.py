"""LlamaIndex LanceDB vector store adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.vector.vector_store_factory import LlamaIndexVectorAdapter

logger = logging.getLogger(__name__)


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
                _schema = _t.schema
                _field_names = {f.name for f in _schema}
                if "doc_id" not in _field_names:
                    logger.info(
                        "LanceDB table '%s' missing 'doc_id' field "
                        "(created by a different backend) — dropping for fresh creation.",
                        table_name,
                    )
                    _db.drop_table(table_name)
        except Exception as _exc:
            logger.debug("LanceDB schema check skipped: %s", _exc)

        store = LanceDBVectorStore(
            uri=uri,
            table_name=table_name,
            vector_column_name=config.get("vector_column_name", "vector"),
            text_column_name=config.get("text_column_name", "text"),
        )
        super().__init__(store)
        logger.info("LlamaIndexLanceDBAdapter: uri=%s table=%s", uri, table_name)


__all__ = ["LlamaIndexLanceDBAdapter"]
