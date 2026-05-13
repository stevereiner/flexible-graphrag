"""Cypher chain builders — Neo4j, Memgraph, FalkorDB, AGE, ArcadeDB, Neptune OpenCypher."""

import logging
import re as _re
from typing import Any

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared Cypher utilities
# ---------------------------------------------------------------------------

_CYPHER_KEYWORDS = _re.compile(
    r'\s+(?=AS|ASC|DESC|LIMIT|SKIP|WHERE|WITH|RETURN|ORDER|BY|MATCH|AND|OR|NOT|IN|IS|NULL|'
    r'SET|MERGE|CREATE|DELETE|UNWIND|CALL|FOREACH|REMOVE|OPTIONAL|DETACH|ON)\b',
    _re.IGNORECASE,
)
_SPACED_PROP_RE = _re.compile(
    r'(?<![`\w])(\w+)\.([A-Za-z_]\w*(?:\s+\w+)*)(?![`\w])'
)
# Rewrite exact toLower equality to CONTAINS for partial name matching.
_TOLOWER_EQ_RE = _re.compile(
    r'(toLower\([^)]+\))\s*=\s*(toLower\([^)]+\))',
    _re.IGNORECASE,
)
# LLMs often confuse node label names with property names.
_LABEL_AS_PROP_RE = _re.compile(
    r'\b(\w+)\.(COMPANY|PERSON|EMPLOYEE|DEPARTMENT|TOPIC|PROJECT|PRODUCT|'
    r'LOCATION|ADDRESS|PLACE|EVENT|ORGANIZATION|TECHNOLOGY|SKILL|ROLE)\b',
    _re.IGNORECASE,
)
_RETURN_COL_RE = _re.compile(
    r'\bRETURN\s+(DISTINCT\s+)?(.+?)(?=\s+ORDER\s+BY\b|\s+LIMIT\b|\s*$)',
    _re.IGNORECASE | _re.DOTALL,
)
# Strip markdown code fences that LLMs sometimes wrap around generated queries.
# Handles both the full ``` fence and the case where langchain_neo4j partially
# strips it (removes backticks but leaves the bare word "cypher" as a prefix).
_CODE_FENCE_OPEN  = _re.compile(
    r'^\s*(?:```(?:cypher)?\s*\n?|cypher\s*\n)',
    _re.IGNORECASE,
)
_CODE_FENCE_CLOSE = _re.compile(r'\n?```\s*$')
_UNION_SPLIT_RE = _re.compile(r'\bUNION\b(?:\s+ALL\b)?', _re.IGNORECASE)

# Neo4j 5+ rejects size(pattern_expr) for patterns; use COUNT { pattern } instead.
_SIZE_PATH_IN_PARENS = _re.compile(
    r"size\s*\(\s*("
    r"(?:\([^)]*\))"
    r"(?:"
    r"\s*-\[[^\]]+\]\s*->\s*"
    r"|"
    r"\s*<-\[[^\]]+\]\s*-\s*"
    r"|"
    r"\s*-\[[^\]]+\]\s*-\s*"
    r")"
    r"(?:\([^)]*\))"
    r")\s*\)",
    _re.IGNORECASE | _re.DOTALL,
)


def _strip_code_fences(cypher: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap around Cypher queries.

    Handles ` ```cypher\\nQUERY\\n``` ` and ` ```\\nQUERY\\n``` `.
    """
    cypher = _CODE_FENCE_OPEN.sub("", cypher)
    cypher = _CODE_FENCE_CLOSE.sub("", cypher)
    return cypher.strip()


def _fix_size_pattern_to_count(cypher: str) -> str:
    """Neo4j 5+ rejects size((pattern)); use COUNT { pattern } instead."""
    def _repl(m: "_re.Match") -> str:
        inner = m.group(1).strip()
        _logger.debug("Rewrote size(pattern) -> COUNT { pattern } for Neo4j 5+")
        return f"COUNT {{ {inner} }}"

    fixed, n = _SIZE_PATH_IN_PARENS.subn(_repl, cypher)
    if n:
        return fixed
    return cypher


def _strip_invalid_order_by(cypher: str) -> str:
    """Remove ORDER BY clauses that reference variables not in RETURN."""
    order_m = _re.search(r'\bORDER\s+BY\s+(\w+)\.', cypher, _re.IGNORECASE)
    if not order_m:
        return cypher
    order_var = order_m.group(1)
    ret_m = _re.search(r'\bRETURN\b(.+?)(?:\bORDER\s+BY\b|\bLIMIT\b|$)', cypher, _re.IGNORECASE | _re.DOTALL)
    if not ret_m:
        return cypher
    return_text = ret_m.group(1)
    if not _re.search(r'\b' + _re.escape(order_var) + r'\b', return_text):
        stripped = _re.sub(r'\s+ORDER\s+BY\s+[^\n]+', '', cypher, flags=_re.IGNORECASE)
        if stripped != cypher:
            _logger.debug(
                "Stripped ORDER BY referencing out-of-scope variable '%s'", order_var
            )
        return stripped
    return cypher


def _normalize_union_columns(cypher: str) -> str:
    """Ensure all UNION branches return identical column names."""
    if 'UNION' not in cypher.upper():
        cypher = _strip_invalid_order_by(cypher)
        return cypher

    parts = _UNION_SPLIT_RE.split(cypher)
    if len(parts) < 2:
        return cypher

    def _parse_return(branch: str):
        ret_m = _RETURN_COL_RE.search(branch)
        if not ret_m:
            return None, [], ''
        distinct = bool(ret_m.group(1))
        cols_raw = ret_m.group(2).strip().rstrip(",").strip()
        cols = [c.strip() for c in cols_raw.split(",") if c.strip()]
        suffix_str = branch[ret_m.end():]
        return distinct, cols, suffix_str

    def _col_alias(col_expr: str) -> str:
        col_expr = col_expr.strip()
        as_m = _re.search(r'\bAS\s+(\w+)\s*$', col_expr, _re.IGNORECASE)
        if as_m:
            return as_m.group(1)
        dot_m = _re.search(r'\.(\w+)\s*$', col_expr)
        if dot_m:
            return dot_m.group(1)
        return col_expr.split()[-1]

    parsed = [_parse_return(p) for p in parts]

    _, first_cols, _ = parsed[0]
    if not first_cols:
        return cypher
    first_col = first_cols[0]
    canonical_alias = _col_alias(first_col)
    first_col_bare = _re.sub(r'\s+AS\s+\w+\s*$', '', first_col, flags=_re.IGNORECASE).strip()

    needs_fix = False
    for _, cols, _ in parsed:
        if len(cols) != 1:
            needs_fix = True
            break
        if _col_alias(cols[0]) != canonical_alias:
            needs_fix = True
            break
    if not needs_fix:
        aliases = [_col_alias(c[0]) for _, c, _ in parsed if c]
        if len(set(a for a in aliases if a)) > 1:
            needs_fix = True

    if needs_fix:
        def _set_return_per_branch(branch: str, alias: str) -> str:
            ret_m = _RETURN_COL_RE.search(branch)
            if not ret_m:
                return branch
            cols_raw = ret_m.group(2).strip().rstrip(",").strip()
            cols = [c.strip() for c in cols_raw.split(",") if c.strip()]
            if not cols:
                return branch
            first = _re.sub(r"\s+AS\s+\w+\s*$", "", cols[0], flags=_re.IGNORECASE).strip()
            new_return = f"RETURN {first} AS {alias}"
            rest = branch[ret_m.end():]
            return branch[:ret_m.start()] + new_return + rest

        fixed_parts = [_set_return_per_branch(p, canonical_alias) for p in parts]
        separators = _UNION_SPLIT_RE.findall(cypher)
        result = fixed_parts[0]
        for sep, part in zip(separators, fixed_parts[1:]):
            result += f'\n{sep}\n' + part.lstrip('\n')
        _logger.debug(
            "Normalized UNION column aliases to '%s' across %d branches",
            canonical_alias, len(parts),
        )
        cypher = result

    cypher = _strip_invalid_order_by(cypher)
    return cypher


def _fix_cypher_spaced_properties(cypher: str) -> str:
    """Backtick-quote Cypher property names that contain spaces."""
    def _quote(m: "_re.Match") -> str:
        alias, prop = m.group(1), m.group(2)
        parts = _CYPHER_KEYWORDS.split(prop, maxsplit=1)
        real_prop = parts[0].rstrip()
        rest = prop[len(real_prop):]
        if " " in real_prop:
            return f"{alias}.`{real_prop}`{rest}"
        return m.group(0)

    fixed = _SPACED_PROP_RE.sub(_quote, cypher)
    if fixed != cypher:
        _logger.debug("Fixed spaced property name(s) in Cypher query")
    return fixed


def _format_falkordb_schema(raw: str, skip_labels: set, skip_props: set) -> str:
    """Reformat FalkorDB's Python OrderedDict repr schema into clean LLM-readable text."""
    import ast as _ast

    def _parse_section(text: str) -> list:
        text = text.strip()
        if not text or text in ("[]", "[[]]"):
            return []
        try:
            return _ast.literal_eval(text)
        except Exception:
            return []

    node_section = ""
    rel_section  = ""
    try:
        np_start = raw.index("Node properties:")
        np_end   = raw.index("Relationships:") if "Relationships:" in raw else len(raw)
        node_section = raw[np_start + len("Node properties:"):np_end].strip()
        rel_section  = raw[np_end + len("Relationships:"):].strip()
    except (ValueError, IndexError):
        return raw

    node_items = _parse_section(node_section)
    rel_items  = _parse_section(rel_section)

    lines = ["Node properties:"]
    for outer in node_items:
        if isinstance(outer, list):
            items = outer
        else:
            items = [outer]
        for item in items:
            if not isinstance(item, dict):
                continue
            label = item.get("label") or item.get("name", "")
            if label in skip_labels:
                continue
            keys = item.get("keys") or item.get("properties") or []
            kept = [
                k.split("(")[0].strip()
                for k in keys
                if k.split("(")[0].strip().lower() not in {p.lower() for p in skip_props}
            ]
            lines.append(f"  {label}: {', '.join(kept)}" if kept else f"  {label}: (no properties)")

    lines.append("Relationships:")
    for outer in rel_items:
        if isinstance(outer, list):
            items = outer
        else:
            items = [outer]
        for item in items:
            if not isinstance(item, dict):
                continue
            start = item.get("start", "")
            end   = item.get("end", "")
            rtype = item.get("type", "")
            if not rtype:
                continue
            lines.append(f"  (:{start})-[:{rtype}]->(:{end})")

    return "\n".join(lines)


def _clean_neo4j_schema_for_chain(
    schema: str, skip_labels: set, skip_props: set
) -> str:
    """Clean a Neo4j schema string for use in the Cypher generation prompt."""
    lines = schema.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("("):
            if "__Node__" in stripped or "(:Chunk)" in stripped:
                continue
        m = _re.match(r'^(\w+)\s*\{(.+)\}$', stripped)
        if m:
            label = m.group(1)
            if label in skip_labels:
                continue
            props_raw = m.group(2)
            kept = [
                p.strip() for p in props_raw.split(", ")
                if p.split(":")[0].strip() not in skip_props
            ]
            if kept:
                result.append(f"{label} " + "{" + ", ".join(kept) + "}")
            continue
        result.append(line)
    return "\n".join(result)


# ---------------------------------------------------------------------------
# Chain builders
# ---------------------------------------------------------------------------

_NEPTUNE_CYPHER_TEMPLATE = """You are an expert Amazon Neptune OpenCypher query writer.
Given the schema below, write an OpenCypher query to answer the question.

Schema:
{schema}

Rules:
- Every entity node carries the label `__Entity__` PLUS its type label (e.g. `__Entity__:Company`).
  Always include `__Entity__` when matching entity nodes.
- The primary identifier property is `id` (stores the full entity name, e.g. "Acme Corporation").
  Nodes may also have a `name` property that mirrors `id`; prefer `id` for matching.
- ALWAYS use case-insensitive PARTIAL matching for user-supplied strings:
    WHERE toLower(n.id) CONTAINS toLower("keyword")
  Never use exact equality for entity names.
- FORBIDDEN: Do NOT use APOC procedures — Neptune does not support them.
- For "who works for / at <company>" questions:
    MATCH (p:__Entity__)-[:WORKS_FOR]->(c:__Entity__)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    RETURN p.id AS name
    UNION
    MATCH (c:__Entity__)-[:EMPLOYS]->(p:__Entity__)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    RETURN p.id AS name
- For "how is <company> organized" / "departments at <company>" questions,
  use a UNION covering forward, reverse, and employee-path directions:
    MATCH (d:__Entity__)-[:PART_OF]->(c:__Entity__)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    RETURN DISTINCT d.id AS name, "dept_part_of" AS rel
    UNION
    MATCH (c:__Entity__)-[:HAS_DEPARTMENT]->(d:__Entity__)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    RETURN DISTINCT d.id AS name, "dept_has" AS rel
    UNION
    MATCH (p:__Entity__)-[:WORKS_FOR]->(c:__Entity__)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    WITH p, c
    MATCH (p)-[:WORKS_IN_DEPARTMENT]->(d:__Entity__)
    RETURN DISTINCT d.id AS name, "dept_via_employee" AS rel
- Every UNION branch MUST return the same column names.
- Return only the Cypher query with no explanation, no markdown fences.

Question: {question}
Cypher query:"""


_NEPTUNE_QA_TEMPLATE = """You are an assistant that answers questions using graph database results.

The query results below are rows returned from the graph. Each row is a dict with field names
as keys. Use ALL rows to form a complete, human-readable answer.
If the results are empty, say you don't know.

Results:
{context}

Question: {question}
Answer:"""


def build_opencypher_neptune(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """Neptune OpenCypher chain with custom id-aware prompt (langchain_aws)."""
    from langchain_core.prompts import PromptTemplate

    cypher_prompt = PromptTemplate(
        input_variables=["schema", "question"],
        template=_NEPTUNE_CYPHER_TEMPLATE,
    )

    qa_prompt = PromptTemplate(
        input_variables=["context", "question"],
        template=_NEPTUNE_QA_TEMPLATE,
    )

    # Always patch the real langchain-aws graph object — not a write-wrapper that
    # forwards to .query (otherwise _original_query -> ._graph.query loops).
    # Guard against double-patching: if raw.query is already our sentinel wrapper,
    # retrieve the original underneath it.
    raw = getattr(graph, "_graph", graph)
    _original_neptune_query = getattr(raw, "_neptune_original_query", raw.query)

    def _inject_union(cypher: str) -> str:
        """Insert UNION between consecutive MATCH blocks separated by a bare RETURN.

        The LLM sometimes omits UNION when producing multi-branch queries:
          MATCH ... RETURN ...
          MATCH ... RETURN ...
        Neptune rejects the second MATCH after RETURN. Insert UNION before each
        orphaned MATCH that follows a RETURN line.
        """
        import re as _re
        # Split on line boundaries so we can inspect each line.
        lines = cypher.splitlines()
        out: list[str] = []
        prev_was_return = False
        for line in lines:
            stripped = line.strip().upper()
            if prev_was_return and _re.match(r'^MATCH\b', stripped):
                out.append("UNION")
            out.append(line)
            prev_was_return = _re.match(r'^RETURN\b', stripped) is not None
        return "\n".join(out)

    def _clean_query(cypher: str, *args, **kwargs):
        cypher = _strip_code_fences(cypher)
        cypher = _inject_union(cypher)
        rewritten = _TOLOWER_EQ_RE.sub(r'\1 CONTAINS \2', cypher)
        if rewritten != cypher:
            _logger.debug("Neptune: rewrote toLower equality to CONTAINS")
        _logger.debug("Neptune Cypher: %s", rewritten)
        return _original_neptune_query(rewritten, *args, **kwargs)

    # Stamp the original so subsequent calls can find it (avoids re-wrap recursion).
    if not hasattr(raw, "_neptune_original_query"):
        raw._neptune_original_query = _original_neptune_query
    raw.query = _clean_query

    try:
        from langchain_aws.chains.graph_qa.neptune_cypher import (
            create_neptune_opencypher_qa_chain,
        )
        return create_neptune_opencypher_qa_chain(
            llm=llm,
            graph=raw,
            qa_prompt=qa_prompt,
            cypher_prompt=cypher_prompt,
            return_intermediate_steps=include_intermediate,
            allow_dangerous_requests=True,
        )
    except ImportError:
        from langchain_community.chains.graph_qa.neptune_cypher import (
            NeptuneOpenCypherQAChain,
        )
        return NeptuneOpenCypherQAChain.from_llm(
            **{**common, "cypher_prompt": cypher_prompt}
        )


_ARCADEDB_CYPHER_TEMPLATE = """You are an expert ArcadeDB OpenCypher query writer.
Given the schema below, write a Cypher query to answer the question.

Schema:
{schema}

Rules:
- CRITICAL: Node labels in ArcadeDB are CASE SENSITIVE. Always copy label names EXACTLY
  as they appear in the Schema above (e.g. Company, Person, Department — never
  COMPANY, PERSON, DEPARTMENT or company, person, department).
- ALWAYS use case-insensitive PARTIAL matching for string comparisons.
  Use: toLower(n.id) CONTAINS toLower("value")
  The primary property for every node is `id` which stores the entity name.
  Nodes also have a `name` property (copy of id); use `id` for matching to be safe.
  Never use exact equality (= or {{id: "value"}}) for user-supplied strings.
- Every UNION branch MUST return the same column names.
- For "who works for / at / with <company>" questions:
    MATCH (p:Person)-[:WORKS_FOR]->(c:Company)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    RETURN p.id AS name
    UNION
    MATCH (c:Company)-[:EMPLOYS]->(p:Person)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    RETURN p.id AS name
- For "what departments are at <company>" questions:
    MATCH (c:Company)-[:HAS_DEPARTMENT]->(d:Department)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    RETURN d.id AS name
    UNION
    MATCH (d:Department)-[:PART_OF]->(c:Company)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    RETURN d.id AS name
- For "how is <company> organized" / "structure of <company>" / "departments at <company>" questions,
  departments may be linked via PART_OF (reverse), HAS_DEPARTMENT (forward), or through employees.
  CRITICAL: each MATCH must have its own WHERE; NEVER reference unbound variables in RETURN.
    MATCH (d:Department)-[:PART_OF]->(c:Company)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    RETURN DISTINCT d.id AS name, "dept_part_of" AS rel
    UNION
    MATCH (c:Company)-[:HAS_DEPARTMENT]->(d:Department)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    RETURN DISTINCT d.id AS name, "dept_has" AS rel
    UNION
    MATCH (p:Person)-[:WORKS_FOR]->(c:Company)
    WHERE toLower(c.id) CONTAINS toLower("Acme")
    OPTIONAL MATCH (p)-[:WORKS_IN_DEPARTMENT]->(d:Department)
    WITH DISTINCT d WHERE d IS NOT NULL
    RETURN d.id AS name, "dept_via_employee" AS rel

Question: {question}
Cypher query:"""


def build_cypher_arcadedb(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """ArcadeDB OpenCypher chain with custom prompt for id-based partial matching."""
    try:
        from langchain_neo4j import GraphCypherQAChain
    except ImportError:
        from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain

    # Apply the same query rewrites as Neo4j so typo'd exact-equality queries
    # still work when the LLM ignores the CONTAINS instruction.
    _original_query = graph.query

    def _sanitized_query(cypher: str, *args, **kwargs):
        cypher = _strip_code_fences(cypher)
        cypher = _fix_cypher_spaced_properties(cypher)
        rewritten = _TOLOWER_EQ_RE.sub(r'\1 CONTAINS \2', cypher)
        if rewritten != cypher:
            _logger.debug("ArcadeDB: rewrote toLower equality to CONTAINS")
            cypher = rewritten
        _logger.debug("ArcadeDB Cypher: %s", cypher)
        return _original_query(cypher, *args, **kwargs)

    graph.query = _sanitized_query

    try:
        from langchain_core.prompts import PromptTemplate
        cypher_prompt = PromptTemplate(
            input_variables=["schema", "question"],
            template=_ARCADEDB_CYPHER_TEMPLATE,
        )
        common["cypher_prompt"] = cypher_prompt
    except Exception:
        pass

    return GraphCypherQAChain.from_llm(**common)


def build_cypher_neo4j(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """Neo4j Cypher chain with sanitized query and cleaned schema."""
    try:
        from langchain_neo4j import GraphCypherQAChain
    except ImportError:
        from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain

    _original_query = graph.query

    _ORDER_BY_RE = _re.compile(r'\s*ORDER\s+BY\s+[^\n;]+', _re.IGNORECASE)

    def _sanitized_query(cypher: str, *args, **kwargs):
        # Skip all fixups for internal import queries from add_graph_documents.
        # These use fixed Cypher templates (not LLM-generated) and must not be modified.
        if '$document.page_content' in cypher or 'apoc.create.addLabels' in cypher:
            return _original_query(cypher, *args, **kwargs)
        cypher = _fix_cypher_spaced_properties(cypher)
        rewritten = _TOLOWER_EQ_RE.sub(r'\1 CONTAINS \2', cypher)
        if rewritten != cypher:
            _logger.debug("Rewrote toLower equality to CONTAINS for partial matching")
            cypher = rewritten
        fixed_labels = _LABEL_AS_PROP_RE.sub(
            lambda m: f"{m.group(1)}.name", cypher
        )
        if fixed_labels != cypher:
            _logger.debug(
                "Fixed label-as-property references in Cypher (e.g. d.DEPARTMENT -> d.name)"
            )
            cypher = fixed_labels
        cypher = _fix_size_pattern_to_count(cypher)
        cypher = _normalize_union_columns(cypher)
        _logger.debug("Generated Cypher: %s", cypher)
        try:
            return _original_query(cypher, *args, **kwargs)
        except Exception as exc:
            # If a SyntaxError mentions ORDER BY, strip it and retry once.
            # The LLM sometimes inserts "ORDER BY <unbound_var>" which Neo4j rejects.
            exc_str = str(exc)
            if "SyntaxError" in exc_str and _ORDER_BY_RE.search(cypher):
                stripped = _ORDER_BY_RE.sub("", cypher).strip()
                if stripped != cypher.strip():
                    _logger.info(
                        "Cypher SyntaxError on ORDER BY clause — retrying without it. "
                        "Error: %s", exc_str[:120]
                    )
                    return _original_query(stripped, *args, **kwargs)
            raise

    graph.query = _sanitized_query

    try:
        from langchain_core.prompts import PromptTemplate
        _NEO4J_CYPHER_TEMPLATE = """You are an expert Neo4j Cypher query writer.
Given the schema below, write a Cypher query to answer the question.

Schema:
{schema}

Rules:
- CRITICAL: Node labels in Neo4j are CASE SENSITIVE. Always copy label names EXACTLY
  as they appear in the Schema above (e.g. Company, Person, Department — never
  COMPANY, PERSON, DEPARTMENT or company, person, department).
- Target Neo4j 5+ Cypher: do NOT use size((pattern)) for pattern counts; use COUNT {{ (pattern) }} instead.
- Every UNION branch MUST return the same column names (e.g. use `AS name` on each RETURN column).
- ALWAYS use case-insensitive PARTIAL matching for string comparisons on name fields.
  Use: toLower(n.name) CONTAINS toLower("value")
  This ensures "Acme" matches "Acme Corporation", "ACME Inc", etc.
  Never use exact equality (= or {{name: "value"}}) for user-supplied strings.
- ALWAYS use the `name` property to reference a node's value.
  For Department nodes use d.name (NOT d.Department or d.DEPARTMENT).
  For Company nodes use c.name (NOT c.Company). Same rule for all labels.
- For "who works for / at / with <company>" questions:
    MATCH (p:Person)-[:WORKS_FOR]->(c:Company)
    WHERE toLower(c.name) CONTAINS toLower("Alfresco")
    RETURN p.name
    UNION
    MATCH (c:Company)-[:EMPLOYS]->(p:Person)
    WHERE toLower(c.name) CONTAINS toLower("Alfresco")
    RETURN p.name
- For "what departments are at <company>" questions:
    MATCH (d:Department)-[:PART_OF]->(c:Company)
    WHERE toLower(c.name) CONTAINS toLower("Acme")
    RETURN d.name
    UNION
    MATCH (c:Company)-[:HAS_DEPARTMENT]->(d:Department)
    WHERE toLower(c.name) CONTAINS toLower("Acme")
    RETURN d.name
- For "how is <company> organized" / "structure of <company>" / "departments at <company>" questions,
  departments may be connected via PART_OF (reverse), HAS_DEPARTMENT (forward), or discovered
  through employee WORKS_IN_DEPARTMENT relationships.  Try ALL three and UNION the results.
  CRITICAL: The WHERE clause filtering on company name MUST appear in every MATCH branch.
  NEVER put RETURN columns that reference unbound variables (e.g. loc when there is no MATCH for loc).
    MATCH (d:Department)-[:PART_OF]->(c:Company)
    WHERE toLower(c.name) CONTAINS toLower("Acme")
    RETURN DISTINCT d.name AS name, "dept_part_of" AS rel
    UNION
    MATCH (c:Company)-[:HAS_DEPARTMENT]->(d:Department)
    WHERE toLower(c.name) CONTAINS toLower("Acme")
    RETURN DISTINCT d.name AS name, "dept_has" AS rel
    UNION
    MATCH (p:Person)-[:WORKS_FOR]->(c:Company)
    WHERE toLower(c.name) CONTAINS toLower("Acme")
    OPTIONAL MATCH (p)-[:WORKS_IN_DEPARTMENT]->(d:Department)
    WITH DISTINCT d WHERE d IS NOT NULL
    RETURN d.name AS name, "dept_via_employee" AS rel
- For "who is in <department>" questions:
    MATCH (p:Person)-[:WORKS_IN_DEPARTMENT]->(d:Department)
    WHERE toLower(d.name) CONTAINS toLower("Engineering")
    RETURN p.name
- For "who endorsed / supported / backed / was involved in <topic>" questions,
  use HAS_SKILL (company expertise), ANNOUNCED (company announced an event),
  and AFFILIATED_WITH (company partnership network).
  ALL UNION branches MUST return the same column name.
  Example — "what companies endorsed the CMIS spec":
    MATCH (c:Company)-[:HAS_SKILL]->(t:Topic)
    WHERE toLower(t.name) CONTAINS toLower("CMIS")
    RETURN DISTINCT c.name AS name
    UNION
    MATCH (hub:Company)-[:HAS_SKILL]->(t:Topic)
    WHERE toLower(t.name) CONTAINS toLower("CMIS")
    MATCH (hub)-[:AFFILIATED_WITH]->(partner:Company)
    RETURN DISTINCT partner.name AS name
    UNION
    MATCH (c:Company)-[:ANNOUNCED]->(e:Event)
    WHERE toLower(e.name) CONTAINS toLower("CMIS")
    RETURN DISTINCT c.name AS name
- For "who was first / announced / introduced / released <topic>" questions,
  match ANY node type related to the keyword — no label constraints on the target node.
  Use a single MATCH with OPTIONAL MATCH for extra context.
  ALWAYS use .name — never .text (graph nodes have no .text property):
    MATCH (c)-[r]->(e)
    WHERE toLower(e.name) CONTAINS toLower("CMIS")
    RETURN DISTINCT c.name AS name, type(r) AS relationship, e.name AS item
- NEVER use `.text` on any node — graph entity nodes have `name`, `id`, or `description` properties only.
- Only use node labels and relationship types present in the schema.
- Return only the most relevant properties (especially name), not entire nodes.
- NEVER use ORDER BY — it frequently references unbound variables and is not needed.
- Output ONLY the raw Cypher query — no explanation, no markdown fences.

Question: {question}
Cypher query:"""
        cypher_prompt = PromptTemplate(
            input_variables=["schema", "question"],
            template=_NEO4J_CYPHER_TEMPLATE,
        )
        chain = GraphCypherQAChain.from_llm(
            cypher_prompt=cypher_prompt,
            **common,
        )
    except Exception:
        chain = GraphCypherQAChain.from_llm(**common)

    _SKIP_LABELS = {"__Node__", "__Entity__", "Chunk"}
    _SKIP_PROPS = {
        "embedding", "_node_content", "_node_type", "ref_doc_id",
        "doc_id", "document_id", "triplet_source_id", "source",
        "conversion_method", "file_type", "file_name", "file_path",
        "modified at", "id",
    }
    try:
        cleaned = _clean_neo4j_schema_for_chain(
            chain.graph_schema, _SKIP_LABELS, _SKIP_PROPS
        )
        chain.graph_schema = cleaned
        _logger.info(
            "Cleaned chain.graph_schema (%d -> %d chars)",
            len(chain.graph_schema), len(cleaned),
        )
    except Exception as _e:
        _logger.warning("Could not clean chain.graph_schema: %s", _e)

    return chain


def build_cypher_memgraph(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """Memgraph Cypher chain — same treatment as Neo4j."""
    from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain as _MGChain

    _mg_original_query = graph.query

    def _mg_sanitized_query(cypher: str, *args, **kwargs):
        cypher = _fix_cypher_spaced_properties(cypher)
        rewritten = _TOLOWER_EQ_RE.sub(r'\1 CONTAINS \2', cypher)
        if rewritten != cypher:
            _logger.debug("Memgraph: rewrote toLower equality to CONTAINS")
            cypher = rewritten
        fixed_labels = _LABEL_AS_PROP_RE.sub(lambda m: f"{m.group(1)}.name", cypher)
        if fixed_labels != cypher:
            _logger.debug("Memgraph: fixed label-as-property in Cypher")
            cypher = fixed_labels
        cypher = _fix_size_pattern_to_count(cypher)
        cypher = _normalize_union_columns(cypher)
        _logger.debug("Generated cypher query:\n%s", cypher)
        return _mg_original_query(cypher, *args, **kwargs)

    graph.query = _mg_sanitized_query

    try:
        from langchain_core.prompts import PromptTemplate
        _MG_CYPHER_TEMPLATE = """You are an expert Memgraph Cypher query writer.
Given the schema below, write a Cypher query to answer the question.

Schema:
{schema}

Rules:
- CRITICAL: Node labels are CASE SENSITIVE. Copy label names EXACTLY as shown in the schema.
- Use ONLY the node labels and relationship types present in the schema — never invent synonyms.
- ALWAYS use case-insensitive PARTIAL matching for string comparisons:
  Use: toLower(n.name) CONTAINS toLower("value")
  Never use exact equality (= or {{name: "value"}}) for user-supplied strings.
- The `name` property holds the entity's display name. Use n.name (not n.id, n.LABEL, etc.).
- For "who works for <company>" questions use labels from the schema, e.g.:
    MATCH (p:Employee)-[:WORKS_FOR]->(c:Company)
    WHERE toLower(c.name) CONTAINS toLower("acme")
    RETURN p.name
    UNION
    MATCH (c:Company)-[:EMPLOYS]->(p:Employee)
    WHERE toLower(c.name) CONTAINS toLower("acme")
    RETURN p.name
- For "how is <company> organized" / "structure of <company>" questions,
  try PART_OF (reverse), HAS_DEPARTMENT, and employee-based discovery:
    MATCH (d:Department)-[:PART_OF]->(c:Company)
    WHERE toLower(c.name) CONTAINS toLower("acme")
    RETURN DISTINCT d.name AS name, "dept_part_of" AS rel
    UNION
    MATCH (c:Company)-[:HAS_DEPARTMENT]->(d:Department)
    WHERE toLower(c.name) CONTAINS toLower("acme")
    RETURN DISTINCT d.name AS name, "dept_has" AS rel
    UNION
    MATCH (p:Person)-[:WORKS_FOR]->(c:Company)
    WHERE toLower(c.name) CONTAINS toLower("acme")
    OPTIONAL MATCH (p)-[:WORKS_IN_DEPARTMENT]->(d:Department)
    WITH DISTINCT d WHERE d IS NOT NULL
    RETURN d.name AS name, "dept_via_employee" AS rel
- Return only the most relevant properties (especially name), not entire nodes.
- NEVER use ORDER BY — it frequently references unbound variables and is not needed.
- Output ONLY the raw Cypher query — no explanation, no markdown fences.

Question: {question}
Cypher query:"""
        cypher_prompt = PromptTemplate(
            input_variables=["schema", "question"],
            template=_MG_CYPHER_TEMPLATE,
        )
        chain = _MGChain.from_llm(cypher_prompt=cypher_prompt, **common)
    except Exception:
        chain = _MGChain.from_llm(**common)

    _SKIP_LABELS_MG = {"__Node__", "__Entity__", "Chunk"}
    _SKIP_PROPS_MG = {
        "embedding", "_node_content", "_node_type", "ref_doc_id",
        "doc_id", "document_id", "triplet_source_id", "source",
        "conversion_method", "file_type", "file_name", "file_path",
        "modified at", "id",
    }
    try:
        cleaned_mg = _clean_neo4j_schema_for_chain(
            chain.graph_schema, _SKIP_LABELS_MG, _SKIP_PROPS_MG,
        )
        chain.graph_schema = cleaned_mg
        _logger.info(
            "Memgraph schema cleaned (%d -> %d chars)",
            len(chain.graph_schema), len(cleaned_mg),
        )
    except Exception as _mge:
        _logger.warning("Could not clean Memgraph chain.graph_schema: %s", _mge)

    # If the schema is too short to be useful (<200 chars), query the live graph
    # directly for node labels and relationship types.  MemgraphGraph.refresh_schema()
    # uses CALL schema.node_type_properties() which may silently fail on community
    # Memgraph images without MAGE, leaving an empty/minimal schema string.
    if len(chain.graph_schema.strip()) < 200:
        try:
            label_rows = graph.query(
                "MATCH (n) RETURN DISTINCT labels(n)[0] AS label LIMIT 100"
            )
            rel_rows = graph.query(
                "MATCH ()-[r]->() RETURN DISTINCT type(r) AS reltype LIMIT 100"
            )
            labels = sorted({r["label"] for r in label_rows if r.get("label")} - _SKIP_LABELS_MG)
            reltypes = sorted({r["reltype"] for r in rel_rows if r.get("reltype")})
            if labels or reltypes:
                rebuilt = (
                    "Node labels: " + ", ".join(labels) + "\n"
                    "Relationship types: " + ", ".join(reltypes)
                )
                _logger.info(
                    "Memgraph schema rebuilt from live graph (%d chars): %s",
                    len(rebuilt), rebuilt[:200],
                )
                chain.graph_schema = rebuilt
        except Exception as _schema_err:
            _logger.warning("Memgraph live schema rebuild failed: %s", _schema_err)

    return chain


def build_cypher_falkordb(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """FalkorDB Cypher chain with schema reformatting."""
    _SKIP_LABELS_FK = {"__Entity__", "__Node__", "Chunk"}
    _SKIP_PROPS_FK = {
        "embedding", "_node_content", "_node_type", "ref_doc_id",
        "doc_id", "document_id", "triplet_source_id",
    }
    _logger.debug("FalkorDB raw graph.schema:\n%s", getattr(graph, "schema", "(none)"))
    cleaned_fk = ""
    try:
        raw_schema = getattr(graph, "schema", "") or ""
        if raw_schema:
            cleaned_fk = _format_falkordb_schema(raw_schema, _SKIP_LABELS_FK, _SKIP_PROPS_FK)
            _logger.info(
                "FalkorDB schema reformatted (%d -> %d chars):\n%s",
                len(raw_schema), len(cleaned_fk), cleaned_fk,
            )
    except Exception as _fe:
        _logger.debug("Could not reformat FalkorDB graph.schema: %s", _fe)

    from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain as _FKChain

    def _to_compat(raw: dict) -> dict:
        def _props(keys):
            return [
                {"property": k.split("(")[0].strip(), "type": "STRING"}
                for k in (keys or [])
            ]
        return {
            "node_props": {lbl: _props(ks) for lbl, ks in (raw.get("node_props") or {}).items()},
            "rel_props": {rt: _props(ks) for rt, ks in (raw.get("rel_props") or {}).items()},
            "relationships": raw.get("relationships", []),
        }

    _orig_ss = getattr(graph, "structured_schema", {})
    try:
        graph.structured_schema = _to_compat(_orig_ss)
        chain = _FKChain.from_llm(**common)
    finally:
        graph.structured_schema = _orig_ss
    if cleaned_fk:
        try:
            _fk_hint = (
                "Important:\n"
                "1. Use ONLY the exact node labels shown in the schema below. "
                "Do NOT substitute synonyms (e.g. if the schema shows 'Organization', "
                "never write 'Company'; if it shows 'Technology', never write 'Skill').\n"
                "2. The `id` property stores the full entity name "
                "(e.g. 'Acme Corporation'). Always use case-insensitive substring "
                "matching: toLower(n.id) CONTAINS toLower('search term')\n\n"
            )
            chain.graph_schema = _fk_hint + cleaned_fk
            _logger.info(
                "FalkorDB chain.graph_schema patched (%d chars)", len(cleaned_fk)
            )
        except Exception as _ep:
            _logger.debug("Could not patch chain.graph_schema: %s", _ep)
    return chain


def build_cypher_age(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """Apache AGE Cypher chain (langchain-age)."""
    try:
        from langchain_age.chains.graph_cypher_qa_chain import AGEGraphCypherQAChain
        from langchain_core.prompts import ChatPromptTemplate

        _age_cypher_prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are an expert in Apache AGE graph database and Cypher query language.\n"
                "Given a graph schema and a user question, generate a valid Cypher query.\n\n"
                "IMPORTANT AGE-specific rules:\n"
                "- Use standard openCypher syntax only — no APOC, no Neo4j-specific functions.\n"
                "- Do NOT wrap the query in SQL (handled automatically).\n"
                "- EVERY expression in the RETURN clause MUST have an explicit AS alias:\n"
                "    RETURN n.id AS name, count(*) AS cnt   (never bare RETURN n.id or RETURN 1)\n"
                "- To return a node's name use: n.id AS name\n"
                "  (nodes are stored with 'id' as the canonical identifier — always present)\n"
                "- ALWAYS use case-insensitive partial matching for any name from the question:\n"
                "    WHERE toLower(n.id) CONTAINS toLower('value')\n"
                "  Never use exact string equality (=) for names supplied by the user.\n"
                "- Variable-length paths: use [*] or [*..N], NEVER [*1..N] or [*N..].\n"
                "  AGE does not accept an explicit minimum hop count.\n"
                "- Safe clauses: MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, LIMIT.\n"
                "- Do NOT add LIMIT to your query unless the user explicitly asks for a specific\n"
                "  number of results. Return all matching data — LIMIT hides relevant rows.\n"
                "- Avoid: COLLECT with nested map literals {{k: v}}, path comprehensions,\n"
                "  CALL procedures, subqueries, and arithmetic in RETURN without an alias.\n"
                "- When counting, use alias 'cnt' not 'count' ('count' is a reserved word in AGE).\n\n"
                "Graph schema:\n{schema}\n\n"
                "Generate ONLY the Cypher query — no explanation, no markdown fences."
            )),
            ("human", "Question: {question}"),
        ])

        return AGEGraphCypherQAChain.from_llm(
            **common,
            cypher_prompt=_age_cypher_prompt,
        )
    except ImportError:
        from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
        return GraphCypherQAChain.from_llm(**common)


def build_cypher_generic(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """Generic Cypher chain — Spanner and other openCypher stores."""
    from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
    return GraphCypherQAChain.from_llm(**common)


_LADYBUG_CYPHER_TEMPLATE = """Task: Generate a Ladybug Cypher statement to query a graph database.

Schema:
{schema}

CRITICAL RULE — Entity ids vs. abbreviations:
  Entity ids come directly from the source text and may be FULL names, not abbreviations.
  Example: the question uses "CMIS" but the graph stores "Content Management Interoperability Services".
  When a question uses an acronym, abbreviation, or short product name, DO NOT rely on matching
  entity ids alone — search the Chunk text instead, which preserves the original wording.

Instructions:
1. Always use the explicit relationship pattern ()-[]->() — never omit the brackets.
2. PREFERRED pattern for "who supported / developed / was involved with X" questions
   or any question using an acronym or short product name:
   Search Chunk text (the raw source text always contains the original abbreviation):
   MATCH (c:Chunk)-[:MENTIONS]->(e:Organization)
   WHERE toLower(c.text) CONTAINS toLower('cmis')
   RETURN DISTINCT e.id AS organization
   — Change the node label (Organization / Person / Company / etc.) to match what the question asks for.
   — To return context as well: RETURN DISTINCT e.id AS entity, c.text AS context
3. For relationship-structure questions where the subject is a well-known proper noun
   (e.g. "who works for Acme Corporation"):
   MATCH (p:Person)-[:WORKS_FOR]->(co:Company)
   WHERE toLower(co.id) CONTAINS toLower('acme')
   RETURN p.id AS person
4. When unsure whether the entity id matches, use a broad Chunk text search:
   MATCH (c:Chunk)-[:MENTIONS]->(e)
   WHERE toLower(c.text) CONTAINS toLower('keyword')
   RETURN DISTINCT e.id AS entity
5. Return only the Cypher statement — no explanations, no backticks, no comments.
6. Use only relationship types and node labels from the schema above.

The question is:
{question}"""

_LADYBUG_CYPHER_PROMPT = None  # lazy-init to avoid import cost at module load


def _get_ladybug_prompt():
    global _LADYBUG_CYPHER_PROMPT
    if _LADYBUG_CYPHER_PROMPT is None:
        from langchain_core.prompts import PromptTemplate
        _LADYBUG_CYPHER_PROMPT = PromptTemplate(
            input_variables=["schema", "question"],
            template=_LADYBUG_CYPHER_TEMPLATE,
        )
    return _LADYBUG_CYPHER_PROMPT


def build_cypher_ladybug(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """LadybugQAChain for the LadybugDB embedded graph database.

    Uses a custom Cypher generation prompt that enforces:
    - Ladybug dialect (explicit ()-[]->() relationship patterns)
    - Case-insensitive partial entity matching via toLower CONTAINS
    - Optional Chunk-text traversal via MENTIONS edges

    ``return_intermediate_steps`` is not forwarded because ``LadybugQAChain``
    does not support it — ``LCGraphQARetriever`` handles the missing key
    gracefully (empty intermediate_steps list).
    """
    from langchain_ladybug import LadybugQAChain
    return LadybugQAChain.from_llm(
        llm=llm,
        graph=graph,
        cypher_prompt=_get_ladybug_prompt(),
        verbose=False,
        allow_dangerous_requests=True,
    )
