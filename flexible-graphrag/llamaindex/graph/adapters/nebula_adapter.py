"""LlamaIndex NebulaGraph property graph adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging
import re as _re

from llamaindex.graph.pg_adapter import LlamaIndexPGAdapter

logger = logging.getLogger(__name__)

_CUSTOM_PROPS_SCHEMA = (
    "`source` STRING, `conversion_method` STRING, `file_type` STRING, `file_name` STRING, "
    "`modified_at` STRING, "
    "`_node_content` STRING, `_node_type` STRING, `document_id` STRING, `doc_id` STRING, "
    "`ref_doc_id` STRING, `triplet_source_id` STRING, `file_path` STRING, `file_size` INT, "
    "`creation_date` STRING, `last_modified_date` STRING"
)

# Columns that only hold lists/dicts — skip them in Props__ (NebulaGraph
# doesn't support LIST/MAP types in tags).

def _install_dynamic_schema_patch(store) -> None:
    """Wrap store.structured_query to auto-add missing Props__ columns.

    When LlamaIndex writes entity properties (e.g. STREET_ADDRESS, CITY) to
    Props__, NebulaGraph raises "Unknown column `X' in schema" if that column
    was not declared in the CREATE TAG.  This wrapper:

    1. Parses ALL columns from the failing ``INSERT VERTEX Props__`` statement.
    2. Checks current ``Props__`` schema via DESCRIBE TAG.
    3. Issues ``ALTER TAG Props__ ADD`` for every missing column at once.
    4. Retries the original query with back-off sleep until storaged has
       propagated the schema change (storaged heartbeat default ~10 s).
       Up to MAX_RETRIES=8 attempts with RETRY_SLEEP=2s each (~16s max wait).
    """
    import time as _time
    MAX_RETRIES = 8
    RETRY_SLEEP = 2

    _orig_sq = store.structured_query
    _client = store._client  # SessionPool

    _known_cols: set = set()      # Props__ columns known to storaged
    _known_edge_cols: set = set() # Relation__ columns known to storaged
    _added: set = set()           # columns we've issued ALTER for this session

    def _add_missing_cols(cols: list, query: str = "") -> bool:
        """ALTER TAG Props__ or EDGE Relation__ for any missing cols.
        Returns True if altered (all string columns; values coerced beforehand).
        """
        is_edge = "INSERT EDGE" in (query or "") and "Relation__" in (query or "")
        if is_edge:
            cache = _known_edge_cols
            def _describe():
                res = _client.execute_parameter("DESCRIBE EDGE `Relation__`", {})
                for row in range(res.row_size()):
                    col = res.row_values(row)[0].cast()
                    if col:
                        cache.add(str(col))
            def _alter(col):
                _client.execute_parameter(
                    f"ALTER EDGE `Relation__` ADD (`{col}` STRING DEFAULT '')", {}
                )
        else:
            cache = _known_cols
            def _describe():
                res = _client.execute_parameter("DESCRIBE TAG `Props__`", {})
                for row in range(res.row_size()):
                    col = res.row_values(row)[0].cast()
                    if col:
                        cache.add(str(col))
            def _alter(col):
                _client.execute_parameter(
                    f"ALTER TAG `Props__` ADD (`{col}` STRING DEFAULT '')", {}
                )

        if not cache:
            try:
                _describe()
            except Exception:
                pass
        missing = [c for c in cols if c not in cache and c not in _added]
        if not missing:
            return False
        for col in missing:
            try:
                _alter(col)
                _added.add(col)
                cache.add(col)
                logger.info("NebulaGraph: added %s column '%s' dynamically",
                            "Relation__" if is_edge else "Props__", col)
            except Exception as _ae:
                _added.add(col)
                cache.add(col)
                logger.debug("NebulaGraph: ALTER ADD '%s': %s", col, _ae)
        return True

    def _cols_from_insert(query: str) -> list:
        """Extract column names from INSERT VERTEX/EDGE on Props__ or Relation__."""
        m = _re.search(r"INSERT\s+(?:VERTEX|EDGE)\s+`?(?:Props__|Relation__)`?\s*\(([^)]+)\)", query)
        if not m:
            return []
        return [c.strip().strip("`") for c in m.group(1).split(",")]

    def _is_schema_target(query: str) -> bool:
        return "Props__" in (query or "") or "Relation__" in (query or "")

    def _coerce_params_to_string(cols: list, param_map: dict) -> dict:
        """Convert non-string values in param_map to strings for Props__ inserts.

        Props__ columns are all declared as STRING; numeric values extracted by
        the ontology (e.g. SALARY=145000.0) must be stringified to avoid
        'data type does not meet requirements' errors.
        """
        result = {}
        for i, col in enumerate(cols):
            key = f"kv_{i}"
            if key in param_map:
                val = param_map[key]
                result[key] = str(val) if not isinstance(val, str) else val
            # keep other keys (not kv_N) unchanged
        for k, v in param_map.items():
            if k not in result:
                result[k] = v
        return result

    def _is_schema_error(msg: str, query: str) -> bool:
        return (
            ("Unknown column" in msg or "prop not found" in msg.lower()
             or "data type does not meet" in msg)
            and _is_schema_target(query)
        )

    def _patched_sq(query: str, param_map=None, **kwargs):
        # Coerce numeric params to string for Props__/Relation__ INSERTs.
        if query and "INSERT" in query and _is_schema_target(query) and param_map:
            cols = _cols_from_insert(query)
            if cols:
                param_map = _coerce_params_to_string(cols, param_map)

        # Pre-check: if INSERT references unknown cols, ALTER first.
        if query and "INSERT" in query and _is_schema_target(query):
            cols = _cols_from_insert(query)
            cache = _known_edge_cols if ("INSERT EDGE" in query and "Relation__" in query) else _known_cols
            if cols and cache and any(c not in cache for c in cols):
                _add_missing_cols(cols, query)

        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                return _orig_sq(query, param_map=param_map, **kwargs)
            except Exception as exc:
                msg = str(exc)
                last_exc = exc
                if _is_schema_error(msg, query):
                    cols = _cols_from_insert(query)
                    _add_missing_cols(cols, query)
                    if attempt < MAX_RETRIES - 1:
                        _time.sleep(RETRY_SLEEP)
                        continue
                raise
        raise last_exc  # pragma: no cover

    store.structured_query = _patched_sq


class LlamaIndexNebulaAdapter(LlamaIndexPGAdapter):
    """LlamaIndex property graph adapter backed by NebulaGraph.

    Configuration keys
    ------------------
    space / space_name  Graph space name (default ``flexible_graphrag``)
    url                 Full NebulaGraph URL (e.g. ``nebula://localhost:9669``)
    address / port      Host + port used when ``url`` is absent
    username            Username (default ``root``)
    password            Password (default ``nebula``)
    overwrite           Overwrite existing space (default ``True``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.graph_stores.nebula.nebula_property_graph import NebulaPropertyGraphStore

        space = config.get("space") or config.get("space_name", "flexible_graphrag")
        _host = config.get("address", "localhost")
        _port = int(config.get("port", 9669))
        _username = config.get("username", "root")
        _password = config.get("password", "nebula")

        if "url" in config:
            url = config["url"]
            # Extract host/port from nebula://host:port for _ensure_space_and_schema
            try:
                _netloc = config["url"].split("://", 1)[-1]
                _h, _p = _netloc.rsplit(":", 1)
                _host, _port = _h, int(_p)
            except Exception:
                pass
        else:
            url = f"nebula://{_host}:{_port}"

        # Ensure the space and minimal schema exist before LlamaIndex connects.
        # LlamaIndex's NebulaPropertyGraphStore(overwrite=True) also calls
        # CREATE SPACE, but it uses partition_num=100 (default) which can take
        # 60-120 s on a single-node Docker deployment. We pre-create with
        # partition_num=1 so the space is ready immediately.
        from langchain.graph.pg_store_adapters.nebula_adapter import NebulaGraphAdapter
        NebulaGraphAdapter._ensure_space_and_schema(_host, _port, _username, _password, space)

        store = NebulaPropertyGraphStore(
            space=space,
            username=_username,
            password=_password,
            url=url,
            overwrite=config.get("overwrite", True),
            props_schema=_CUSTOM_PROPS_SCHEMA,
        )
        _install_dynamic_schema_patch(store)
        super().__init__(store)
        logger.info("LlamaIndexNebulaAdapter: space=%s url=%s", space, url)


__all__ = ["LlamaIndexNebulaAdapter"]
