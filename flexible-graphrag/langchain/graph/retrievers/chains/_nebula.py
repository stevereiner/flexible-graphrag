"""NebulaGraph nGQL chain builder."""

import logging
from typing import Any

_logger = logging.getLogger(__name__)


def build_cypher_nebula(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """NebulaGraph nGQL QA chain with cleaned schema and custom prompt."""
    from langchain_community.chains.graph_qa.nebulagraph import NebulaGraphQAChain

    _nebula_skip_tags = {"Props__", "Chunk__", "Entity__", "Node__"}
    _nebula_skip_props = {
        "embedding", "_node_content", "_node_type", "ref_doc_id",
        "doc_id", "document_id", "triplet_source_id", "source",
        "conversion_method", "file_type", "file_name", "file_path",
        "file_size", "creation_date", "last_modified_date", "alfresco_id",
        "stable_file_path", "content_type", "modified_at",
    }
    try:
        raw_schema = graph.get_schema
        if callable(raw_schema):
            raw_schema = raw_schema()
    except Exception:
        raw_schema = getattr(graph, "schema", "") or ""

    # Collect named edge types via SHOW EDGES.
    # Note: langchain_community.graphs.NebulaGraph in this version only sets
    # graph.schema (a plain string) — structured_schema is never populated.
    # Query the live schema directly instead.
    _edge_labels: list = []
    try:
        for _ev in graph.execute("SHOW EDGES").column_values("Name"):
            _lbl = _ev.cast()
            if _lbl and _lbl not in ("Relation__",) and _lbl not in _edge_labels:
                _edge_labels.append(_lbl)
    except Exception as _ee:
        _logger.debug("NebulaGraph: could not query SHOW EDGES: %s", _ee)

    # If no named edge types found (e.g. fresh space with only Relation__),
    # query live Relation__.label values from ingested data as a fallback.
    _relation_labels: list = []
    if not _edge_labels:
        try:
            _lbl_result = graph.query(
                "MATCH ()-[e:Relation__]->() "
                "RETURN DISTINCT e.label AS lbl LIMIT 50"
            )
            for _row in (_lbl_result or []):
                _v = _row.get("lbl") if isinstance(_row, dict) else None
                if _v and _v not in _relation_labels:
                    _relation_labels.append(str(_v))
        except Exception as _qe:
            _logger.debug("NebulaGraph: could not query Relation__ labels: %s", _qe)

    # Build node tag list via SHOW TAGS + DESCRIBE TAG (structured_schema absent).
    _clean_lines: list = ["Node Tags (entity types):"]
    try:
        for _tv in graph.execute("SHOW TAGS").column_values("Name"):
            _tname = _tv.cast()
            if _tname in _nebula_skip_tags:
                continue
            try:
                _r = graph.execute(f"DESCRIBE TAG `{_tname}`")
                _kept = [
                    _f.cast()
                    for _f in _r.column_values("Field")
                    if _f.cast().lower() not in _nebula_skip_props
                ]
            except Exception:
                _kept = []
            if _kept:
                _clean_lines.append(f"  {_tname}: {', '.join(_kept)}")
            else:
                _clean_lines.append(f"  {_tname}: id, name")
    except Exception:
        for _ln in str(raw_schema).splitlines():
            if not any(_skip in _ln for _skip in _nebula_skip_tags):
                _clean_lines.append(_ln)

    _clean_lines.append("\nEdge types:")
    if _edge_labels:
        _clean_lines.append(f"  Named edge types (use directly): {', '.join(_edge_labels)}")
    if _relation_labels:
        _clean_lines.append(
            f"  Relation__ (fallback, filter by label property): "
            f"{', '.join(_relation_labels)}"
        )
    elif not _edge_labels:
        _clean_lines.append(
            "  Relation__ (only edge type — use e.Relation__.label to filter)"
        )
    cleaned_nebula_schema = "\n".join(_clean_lines)

    try:
        from langchain_core.prompts import PromptTemplate
        _NEBULA_TEMPLATE = """You are an expert NebulaGraph nGQL query writer.
Given the schema below, write an nGQL query to answer the question.

Schema:
{schema}

nGQL Rules:
- Vertex IDs (VIDs) ARE the entity names (e.g. VID "Acme Corporation" for that company).
  Use id(v) to read the VID. Use toLower(id(v)) CONTAINS toLower("search term") for matching.
- Access vertex tag properties with v.TagName.property syntax.
  Examples: v.Person.name, v.Organization.name, v.Person.hire_date
- For edge properties use e.property (NOT e.EdgeType.property).
  Example: e.label, e.doc_id  (NOT e.Relation__.label)
- If the schema shows named edge types (e.g. WORKS_FOR, HAS_DEPARTMENT), use them directly:
    MATCH (p:Person)-[:WORKS_FOR]->(o:Organization)
    WHERE toLower(id(o)) CONTAINS toLower("acme")
    RETURN id(p) AS name
- If relationships are stored under Relation__ with a label property, use:
    MATCH (p:Person)-[e:Relation__]->(o:Organization)
    WHERE e.label == "WORKS_FOR"
      AND toLower(id(o)) CONTAINS toLower("acme")
    RETURN id(p) AS name
- NEVER use OPTIONAL MATCH — NebulaGraph does not support it.
- NEVER write MATCH (v) without a tag label. Always specify the tag, e.g. MATCH (v:Organization).
  Untagged MATCH patterns will cause a syntax error when filtering on id(v).
- NEVER use properties(v) or labels(v) — these are not valid nGQL functions.
  Access properties directly: v.TagName.property  (e.g. v.Organization.name)
- When a question requires multiple relationship types (e.g. "how is X organized"),
  use UNION to combine queries — each sub-query MUST return the same column names:
    MATCH (org:Organization)-[e:Relation__]->(d:Department)
    WHERE e.label == "HAS_DEPARTMENT"
      AND toLower(id(org)) CONTAINS toLower("acme")
    RETURN "department" AS type, id(d) AS value
    UNION
    MATCH (org:Organization)-[e:Relation__]->(l:Location)
    WHERE e.label == "HAS_LOCATION"
      AND toLower(id(org)) CONTAINS toLower("acme")
    RETURN "location" AS type, id(l) AS value
- The schema shows which edge types and relationship labels are available — use ONLY those.
- ONLY use tag and edge type names that appear in the schema above.
- Output ONLY the raw nGQL query — no explanation, no markdown fences.

Question: {question}
nGQL query:"""
        nebula_prompt = PromptTemplate(
            input_variables=["schema", "question"],
            template=_NEBULA_TEMPLATE,
        )
        chain = NebulaGraphQAChain.from_llm(ngql_prompt=nebula_prompt, **common)
    except Exception:
        chain = NebulaGraphQAChain.from_llm(**common)

    try:
        graph.schema = cleaned_nebula_schema
        _logger.info(
            "NebulaGraph graph.schema cleaned (%d chars)", len(cleaned_nebula_schema)
        )
    except Exception as _ep:
        _logger.debug("Could not patch NebulaGraph graph.schema: %s", _ep)

    # Wrap query() to log generated nGQL, fix e.EdgeType.prop -> e.prop,
    # and convert column-oriented result dict to row-oriented list so that
    # CYPHER_QA_PROMPT receives [{'name': 'Alice'}, ...] instead of
    # {'name': ['Alice', 'Bob', ...]}, which confuses the synthesis LLM.
    _nebula_orig_query = graph.query

    def _col_to_rows(d: dict) -> list:
        if not isinstance(d, dict) or not d:
            return d
        cols = list(d.keys())
        list_cols = [k for k, v in d.items() if isinstance(v, list)]
        if not list_cols:
            return [d]
        n = max(len(d[k]) for k in list_cols)
        rows = []
        for i in range(n):
            row = {}
            for col in cols:
                val = d[col]
                row[col] = val[i] if isinstance(val, list) and i < len(val) else val
            rows.append(row)
        return rows

    def _nebula_logged_query(ngql: str, *args, **kwargs):
        import re as _re
        fixed = _re.sub(r'\be(\.\w+)\.(\w+)\b', r'e.\2', ngql)
        if fixed != ngql:
            _logger.debug("NebulaGraph: rewrote edge property access: %r -> %r", ngql, fixed)
            ngql = fixed
        _logger.info("NebulaGraph generated nGQL:\n%s", ngql)
        result = _nebula_orig_query(ngql, *args, **kwargs)
        rows = _col_to_rows(result)
        _logger.info("NebulaGraph nGQL result (%d rows): %r", len(rows) if isinstance(rows, list) else 1, rows)
        return rows

    graph.query = _nebula_logged_query

    return chain
