"""
LangChain Retriever Wrapper for LlamaIndex Integration

Enables using LangChain graph database QA chains (Neptune, GraphDB, Fuseki,
Oxigraph, Neo4j, ArangoDB, etc.) within LlamaIndex's QueryFusionRetriever
for hybrid search.

Package precedence per store type:
  Neo4j     langchain_neo4j  > langchain_community
  Memgraph  langchain_memgraph > langchain_community
  Kuzu      langchain_kuzu   > langchain_community
  Neptune   langchain_aws    > langchain_community
  ArangoDB  langchain_community (chains) — NOT langchain_arangodb
  ArcadeDB  langchain_arcadedb (dedicated package, not in community)
  All others: langchain_community
"""

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from typing import List, Optional, Any, Callable
import logging
import os
import re as _re

_chain_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared utility: inject missing PREFIX declarations into a SPARQL query.
# The LLM often picks the correct predicate names but omits the corresponding
# PREFIX line, causing a 400 Bad Request from the SPARQL endpoint.
# ---------------------------------------------------------------------------
_KNOWN_SPARQL_PREFIXES = {
    "kg:":       "PREFIX kg:      <https://integratedsemantics.org/flexible-graphrag/kg/>",
    "onto:":     "PREFIX onto:    <https://integratedsemantics.org/flexible-graphrag/ontology#>",
    "company:":  "PREFIX company: <http://example.org/company/>",
    "common:":   "PREFIX common:  <https://integratedsemantics.org/flexible-graphrag/common#>",
    "rdfs:":     "PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>",
    "rdf:":      "PREFIX rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",
    "xsd:":      "PREFIX xsd:     <http://www.w3.org/2001/XMLSchema#>",
    "owl:":      "PREFIX owl:     <http://www.w3.org/2002/07/owl#>",
}


def _ensure_sparql_prefixes(sparql: str) -> str:
    """Inject any standard PREFIX declarations used but not declared in the query."""
    missing = []
    for prefix, decl in _KNOWN_SPARQL_PREFIXES.items():
        used = prefix in sparql
        declared = (f"PREFIX {prefix}" in sparql or f"prefix {prefix}" in sparql.lower())
        if used and not declared:
            missing.append(decl)
    if missing:
        _chain_logger.debug(
            "Injecting missing PREFIX declarations: %s",
            [m.split()[1] for m in missing],
        )
        sparql = "\n".join(missing) + "\n" + sparql
    return sparql


# ---------------------------------------------------------------------------
# Cypher property-name sanitizer.
# Neo4j property names that contain spaces must be backtick-quoted in Cypher.
# LlamaIndex stores metadata with keys like "modified at" (space) which get
# written to Neo4j and then the LLM generates unquoted `n.modified at` —
# causing CypherSyntaxError.  This regex fixes any `alias.word word` pattern
# that is NOT already backtick-quoted.
# ---------------------------------------------------------------------------

_CYPHER_KEYWORDS = _re.compile(
    r'\s+(?=AS|ASC|DESC|LIMIT|SKIP|WHERE|WITH|RETURN|ORDER|BY|MATCH|AND|OR|NOT|IN|IS|NULL\b)',
    _re.IGNORECASE,
)
_SPACED_PROP_RE = _re.compile(
    r'(?<![`\w])(\w+)\.([A-Za-z_]\w*(?:\s+\w+)*)(?![`\w])'
)
# Rewrite exact toLower equality to CONTAINS for partial name matching.
# e.g.  toLower(c.name) = toLower("Acme")  ->  toLower(c.name) CONTAINS toLower("Acme")
_TOLOWER_EQ_RE = _re.compile(
    r'(toLower\([^)]+\))\s*=\s*(toLower\([^)]+\))',
    _re.IGNORECASE,
)

# LLMs often confuse node label names with property names, e.g. writing
# `d.DEPARTMENT` or `d.department` instead of `d.name`.  This regex catches
# patterns like `alias.LABEL` where LABEL matches a known label name and
# rewrites them to `alias.name`.
_LABEL_AS_PROP_RE = _re.compile(
    r'\b(\w+)\.(COMPANY|PERSON|EMPLOYEE|DEPARTMENT|TOPIC|PROJECT|PRODUCT|'
    r'LOCATION|ADDRESS|PLACE|EVENT|ORGANIZATION|TECHNOLOGY|SKILL|ROLE)\b',
    _re.IGNORECASE,
)

# Matches a RETURN clause column expression: either  expr AS alias  or bare  expr
_RETURN_COL_RE = _re.compile(
    r'RETURN\s+(DISTINCT\s+)?(.+?)(?:\s+LIMIT\s+\d+)?\s*$',
    _re.IGNORECASE | _re.DOTALL,
)
_UNION_SPLIT_RE = _re.compile(r'\bUNION\b(?:\s+ALL\b)?', _re.IGNORECASE)


def _normalize_union_columns(cypher: str) -> str:
    """Ensure all UNION branches return identical column names.

    Two common LLM mistakes fixed here:

    1. Mismatched column counts / names across branches.
       e.g.  RETURN c.name, e.name AS name
             UNION
             RETURN p.name, t.name AS name
       Neo4j requires identical column lists across all UNION branches.
       Strategy: keep only the *first* column of the first branch as the
       canonical single-column RETURN, rewrite all other branches to match.

    2. ORDER BY referencing a variable not projected in a DISTINCT/aggregation
       RETURN.  e.g.  RETURN DISTINCT c.name AS name ORDER BY e.START_DATE
       Fix: strip ORDER BY clauses entirely when they reference variables
       not present in the RETURN column list.
    """
    if 'UNION' not in cypher.upper():
        # Still apply ORDER BY safety fix even on non-UNION queries
        cypher = _strip_invalid_order_by(cypher)
        return cypher

    parts = _UNION_SPLIT_RE.split(cypher)
    if len(parts) < 2:
        return cypher

    def _parse_return(branch: str):
        """Return (distinct_flag, list_of_col_exprs, suffix) for the RETURN clause."""
        ret_m = _RETURN_COL_RE.search(branch)
        if not ret_m:
            return None, [], ''
        distinct = bool(ret_m.group(1))
        cols_raw = ret_m.group(2).strip().rstrip(',').strip()
        cols = [c.strip() for c in cols_raw.split(',') if c.strip()]
        # Preserve ORDER BY / LIMIT suffix after the RETURN
        suffix_m = _re.search(r'(\s+(?:ORDER\s+BY|LIMIT)\b.*)$', cols_raw, _re.IGNORECASE | _re.DOTALL)
        if suffix_m:
            suffix_str = suffix_m.group(1)
            cols_raw2 = cols_raw[:suffix_m.start()].strip()
            cols = [c.strip() for c in cols_raw2.split(',') if c.strip()]
        else:
            suffix_str = ''
        return distinct, cols, suffix_str

    def _col_alias(col_expr: str) -> str:
        """Derive the alias / projected name for a single column expression."""
        col_expr = col_expr.strip()
        as_m = _re.search(r'\bAS\s+(\w+)\s*$', col_expr, _re.IGNORECASE)
        if as_m:
            return as_m.group(1)
        dot_m = _re.search(r'\.(\w+)\s*$', col_expr)
        if dot_m:
            return dot_m.group(1)
        return col_expr.split()[-1]

    def _set_return(branch: str, col_expr: str, alias: str) -> str:
        """Replace the RETURN clause in *branch* with  RETURN <col_expr> AS <alias>."""
        ret_m = _RETURN_COL_RE.search(branch)
        if not ret_m:
            return branch
        new_return = f"RETURN {col_expr} AS {alias}"
        return branch[:ret_m.start()] + new_return

    # Parse all branches
    parsed = [_parse_return(p) for p in parts]

    # Determine canonical single column + alias from first branch
    _, first_cols, _ = parsed[0]
    if not first_cols:
        return cypher
    first_col = first_cols[0]  # use the FIRST (most important) column only
    canonical_alias = _col_alias(first_col)
    # Strip existing AS from expression to get bare expr
    first_col_bare = _re.sub(r'\s+AS\s+\w+\s*$', '', first_col, flags=_re.IGNORECASE).strip()

    # Check whether normalisation is needed:
    # branches differ in column count OR in alias of first column
    needs_fix = False
    for _, cols, _ in parsed:
        if len(cols) != 1:
            needs_fix = True
            break
        if _col_alias(cols[0]) != canonical_alias:
            needs_fix = True
            break
    # Also check pure-alias mismatch when all single-column
    if not needs_fix:
        aliases = [_col_alias(c[0]) for _, c, _ in parsed if c]
        if len(set(a for a in aliases if a)) > 1:
            needs_fix = True

    if needs_fix:
        def _set_return_per_branch(branch: str, alias: str) -> str:
            """Replace RETURN in branch keeping its own first column, aliased to alias."""
            ret_m = _RETURN_COL_RE.search(branch)
            if not ret_m:
                return branch
            cols_raw = ret_m.group(2).strip().rstrip(',').strip()
            # Strip ORDER BY / LIMIT from cols_raw
            cols_raw_clean = _re.sub(r'\s+(?:ORDER\s+BY|LIMIT)\b.*$', '', cols_raw, flags=_re.IGNORECASE | _re.DOTALL).strip()
            cols = [c.strip() for c in cols_raw_clean.split(',') if c.strip()]
            if not cols:
                return branch
            first = _re.sub(r'\s+AS\s+\w+\s*$', '', cols[0], flags=_re.IGNORECASE).strip()
            new_return = f"RETURN {first} AS {alias}"
            return branch[:ret_m.start()] + new_return

        fixed_parts = [_set_return_per_branch(p, canonical_alias) for p in parts]
        separators = _UNION_SPLIT_RE.findall(cypher)
        result = fixed_parts[0]
        for sep, part in zip(separators, fixed_parts[1:]):
            result += f'\n{sep}\n' + part.lstrip('\n')
        _chain_logger.debug(
                "Normalized UNION column aliases to '%s' across %d branches",
                canonical_alias, len(parts),
            )
        cypher = result

    # Apply ORDER BY safety fix to the final cypher
    cypher = _strip_invalid_order_by(cypher)
    return cypher


def _strip_invalid_order_by(cypher: str) -> str:
    """Remove ORDER BY clauses that reference variables not in RETURN.

    Neo4j raises a SyntaxError when ORDER BY references a variable that is
    not projected in a DISTINCT or aggregation RETURN.  The safest fix is
    to remove the ORDER BY entirely when the referenced variable is not in
    the RETURN column list.
    """
    order_m = _re.search(r'\bORDER\s+BY\s+(\w+)\.', cypher, _re.IGNORECASE)
    if not order_m:
        return cypher
    order_var = order_m.group(1)
    # Find projected variable names in the RETURN clause (before ORDER BY / LIMIT)
    ret_m = _re.search(r'\bRETURN\b(.+?)(?:\bORDER\s+BY\b|\bLIMIT\b|$)', cypher, _re.IGNORECASE | _re.DOTALL)
    if not ret_m:
        return cypher
    return_text = ret_m.group(1)
    # Check using word-boundary so 'e' doesn't match inside 'name'
    if not _re.search(r'\b' + _re.escape(order_var) + r'\b', return_text):
        stripped = _re.sub(r'\s+ORDER\s+BY\s+[^\n]+', '', cypher, flags=_re.IGNORECASE)
        if stripped != cypher:
            _chain_logger.debug(
                "Stripped ORDER BY referencing out-of-scope variable '%s'", order_var
            )
        return stripped
    return cypher


def _fix_cypher_spaced_properties(cypher: str) -> str:
    """Backtick-quote Cypher property names that contain spaces.

    Transforms  ``n.modified at``  ->  ``n.`modified at` ``
    Leaves already-quoted references and ``p.name AS alias`` patterns untouched.
    """
    def _quote(m: "_re.Match") -> str:
        alias, prop = m.group(1), m.group(2)
        # Split off any trailing Cypher keyword (AS, ASC, DESC, etc.)
        parts = _CYPHER_KEYWORDS.split(prop, maxsplit=1)
        real_prop = parts[0].rstrip()
        rest = prop[len(real_prop):]
        if " " in real_prop:
            return f"{alias}.`{real_prop}`{rest}"
        return m.group(0)

    fixed = _SPACED_PROP_RE.sub(_quote, cypher)
    if fixed != cypher:
        _chain_logger.debug(
            "Fixed spaced property name(s) in Cypher query"
        )
    return fixed


def _clean_neo4j_schema_for_chain(
    schema: str, skip_labels: set, skip_props: set
) -> str:
    """Clean a Neo4j schema string for use in the Cypher generation prompt.

    Removes LlamaIndex-internal node types (__Node__, __Entity__, Chunk) and
    their internal properties (embedding, ref_doc_id, etc.) so the LLM sees
    only semantic entity types and their meaningful properties.  Also strips
    relationship lines where __Node__ or Chunk appear as source/target.
    """
    lines = schema.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        # Drop relationship lines involving infrastructure labels
        if stripped.startswith("("):
            if "__Node__" in stripped or "(:Chunk)" in stripped:
                continue
        # Filter node/rel property lines
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
# graph-class-name substring  ->  chain_key mapping table.
# Matched against type(langchain_graph).__name__; first match wins.
# More-specific substrings must come before shorter/broader ones.
# ---------------------------------------------------------------------------
_GRAPH_CHAIN_MAP = [
    # ---- RDF / SPARQL -------------------------------------------------------
    ("NeptuneRdf",       "sparql_neptune"),       # langchain_aws NeptuneRdfGraph
    ("OntotextGraphDB",  "sparql_graphdb"),       # langchain_community OntotextGraphDBGraph
    ("_LazyRdf",         "sparql_generic"),       # _LazyRdfGraph subclass (Fuseki/Oxigraph)
    ("RdfGraph",         "sparql_generic"),       # langchain_community RdfGraph (Fuseki/Oxigraph)
    ("RDF",              "sparql_generic"),       # belt-and-suspenders
    ("Rdf",              "sparql_generic"),       # belt-and-suspenders

    # ---- Neptune property graph (OpenCypher) --------------------------------
    ("NeptuneAnalytics", "opencypher_neptune"),   # langchain_aws NeptuneAnalyticsGraph
    ("Neptune",          "opencypher_neptune"),   # langchain_aws NeptuneGraph (also community)

    # ---- ArcadeDB -----------------------------------------------------------
    ("ArcadeDB",         "cypher_arcadedb"),      # langchain_arcadedb

    # ---- Cypher property graphs ---------------------------------------------
    ("Neo4j",            "cypher_neo4j"),         # langchain_neo4j > community
    ("Memgraph",         "cypher_memgraph"),      # langchain_memgraph > community
    ("Kuzu",             "cypher_kuzu"),          # langchain_kuzu > community
    ("FalkorDB",         "cypher_falkordb"),      # community FalkorDBQAChain
    ("AGE",              "cypher_generic"),       # community AGEGraph + GraphCypherQAChain
    ("Tiger",            "cypher_generic"),       # community TigerGraph + GraphCypherQAChain
    ("Spanner",          "cypher_generic"),       # langchain_google_spanner + GraphCypherQAChain

    # ---- HugeGraph (its own class, not GremlinGraph) ------------------------
    ("HugeGraph",        "gremlin_hugegraph"),    # community HugeGraph + HugeGraphQAChain

    # ---- Generic Gremlin (GremlinGraph, CosmosDBGremlinGraph, etc.) ---------
    ("Gremlin",          "gremlin_generic"),      # community GremlinQAChain
    ("CosmosDB",         "gremlin_generic"),      # community CosmosDBGremlinGraph

    # ---- AQL (ArangoDB) -----------------------------------------------------
    ("Arango",           "aql_arangodb"),         # community ArangoGraphQAChain

    # ---- NebulaGraph --------------------------------------------------------
    ("Nebula",           "cypher_nebula"),        # community NebulaGraphQAChain
]


def _build_qa_chain(graph: Any, llm: Any, include_intermediate: bool = True) -> Any:
    """Build the correct LangChain QA chain for *graph* by matching its class name
    against _GRAPH_CHAIN_MAP.  Raises ValueError if no match is found.

    Each chain_key tries the dedicated first-party package first and falls back
    to langchain_community where available, so the code works whether or not the
    optional packages are installed.
    """
    name = type(graph).__name__
    logger = logging.getLogger(__name__)

    chain_key = None
    for substr, key in _GRAPH_CHAIN_MAP:
        if substr in name:
            chain_key = key
            break

    # Fallback: check MRO class names so subclasses are matched automatically
    if chain_key is None:
        for cls in type(graph).__mro__:
            for substr, key in _GRAPH_CHAIN_MAP:
                if substr in cls.__name__:
                    chain_key = key
                    logger.debug(
                        "Matched graph class '%s' via MRO class '%s' -> chain_key '%s'",
                        name, cls.__name__, key,
                    )
                    break
            if chain_key is not None:
                break

    if chain_key is None:
        raise ValueError(
            f"No QA chain mapping found for graph class '{name}'. "
            "Pass qa_chain_factory= to TextToGraphQueryRetriever to use a custom chain."
        )

    logger.info("Building QA chain '%s' for graph class '%s'", chain_key, name)

    # allow_dangerous_requests=True is required by all langchain-community graph
    # QA chains since langchain-community 0.3.x as a security acknowledgement.
    # We surface it here centrally rather than repeating it on every call.
    common = dict(
        llm=llm,
        graph=graph,
        verbose=False,
        return_intermediate_steps=include_intermediate,
        allow_dangerous_requests=True,
    )

    # ---- RDF / SPARQL -------------------------------------------------------
    if chain_key == "sparql_neptune":
        from langchain_aws.chains.graph_qa.neptune_sparql import NeptuneSparqlQAChain
        return NeptuneSparqlQAChain.from_llm(**common)

    if chain_key == "sparql_graphdb":
        from langchain_community.chains.graph_qa.ontotext_graphdb import OntotextGraphDBQAChain
        from langchain_core.callbacks.manager import CallbackManagerForChainRun

        # Grab the GraphDB query endpoint from the graph object for direct HTTP queries
        # OntotextGraphDBGraph wraps an rdflib.Graph whose store is a SPARQLStore.
        # SPARQLStore exposes .query_endpoint (not .endpoint).
        _query_endpoint = None
        try:
            _query_endpoint = str(graph.graph.store.query_endpoint)
        except Exception:
            pass
        if not _query_endpoint:
            _query_endpoint = getattr(graph, "query_endpoint", None)
        _chain_logger.info("GraphDB direct query endpoint: %s", _query_endpoint or "NOT FOUND")
        _auth = None
        _gdb_username = os.environ.get("GRAPHDB_USERNAME")
        _gdb_password = os.environ.get("GRAPHDB_PASSWORD")
        if _gdb_username and _gdb_password:
            _auth = (_gdb_username, _gdb_password)

        class _GraphDBQAChain(OntotextGraphDBQAChain):
            """Subclass that skips rdflib prepareQuery validation and executes
            SPARQL directly against GraphDB via HTTP POST instead of going
            through rdflib's SPARQLStore.

            rdflib SPARQLStore prepends its own PREFIX declarations to every
            query it sends, which causes HTTP 400 (duplicate PREFIX) when the
            LLM-generated query already includes PREFIX lines.

            rdflib's parser also rejects GRAPH <uri> { } named-graph clauses,
            so we skip local validation entirely.
            """
            def _prepare_sparql_query(
                self,
                _run_manager: CallbackManagerForChainRun,
                generated_sparql: str,
            ) -> str:
                self._log_prepared_sparql_query(_run_manager, generated_sparql)
                _chain_logger.debug("Generated SPARQL:\n%s", generated_sparql)
                return generated_sparql

            def _execute_query(self, query: str):
                """POST query directly to GraphDB, bypassing rdflib SPARQLStore."""
                import requests as _requests
                endpoint = _query_endpoint
                if not endpoint:
                    _chain_logger.warning(
                        "No GraphDB endpoint available, falling back to rdflib store"
                    )
                    return super()._execute_query(query)
                _chain_logger.debug("POSTing SPARQL directly to GraphDB: %s", endpoint)
                try:
                    resp = _requests.post(
                        endpoint,
                        data=query.encode("utf-8"),
                        headers={
                            "Content-Type": "application/sparql-query; charset=UTF-8",
                            "Accept": "application/sparql-results+json",
                        },
                        auth=_auth,
                        timeout=60,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    bindings = data.get("results", {}).get("bindings", [])
                    # Convert to plain-string named tuples so the QA prompt
                    # receives readable text (e.g. "Sarah Chen") rather than
                    # rdflib URIRef/Literal reprs that confuse the answer LLM.
                    from collections import namedtuple
                    rows = []
                    for b in bindings:
                        keys = list(b.keys())
                        Row = namedtuple("Row", keys)
                        vals = [b[k].get("value", "") for k in keys]
                        rows.append(Row(*vals))
                    _chain_logger.debug(
                        "GraphDB returned %d result rows", len(rows)
                    )
                    if rows:
                        _chain_logger.debug("Sample row fields=%s values=%s", rows[0]._fields, list(rows[0]))
                    return rows
                except _requests.HTTPError as e:
                    _chain_logger.error(
                        "GraphDB HTTP %s executing SPARQL:\n%s\nQuery:\n%s",
                        e.response.status_code, e.response.text[:500], query,
                    )
                    raise ValueError("Failed to execute the generated SPARQL query.") from e
                except Exception as e:
                    _chain_logger.error(
                        "GraphDB SPARQL execution failed: %s\nQuery:\n%s", e, query
                    )
                    raise ValueError("Failed to execute the generated SPARQL query.") from e

            def _format_results(self, results, question: str = "") -> str:
                """Convert result rows to clean readable text for the QA prompt."""
                if not results:
                    return ""
                lines = []
                for row in results:
                    if hasattr(row, "_fields"):
                        vals = []
                        for f in row._fields:
                            v = str(getattr(row, f))
                            if v.startswith("http"):
                                local = v.rstrip("/").split("/")[-1].split("#")[-1].replace("_", " ")
                                vals.append(local)
                            else:
                                vals.append(v)
                        lines.append(", ".join(v for v in vals if v))
                    else:
                        lines.append(str(row))
                # Wrap with context so the LLM understands what the results mean
                names = "\n".join(lines)
                if question:
                    text = f"SPARQL query results for '{question}':\n{names}"
                else:
                    text = names
                _chain_logger.debug("_format_results produced: %r", text[:300])
                return text

            def _call(self, inputs, run_manager=None):
                """Override to format SPARQL results as readable text before QA."""
                from langchain_core.callbacks.manager import CallbackManagerForChainRun
                _run_manager = run_manager or CallbackManagerForChainRun.get_noop_manager()
                callbacks = _run_manager.get_child()
                prompt = inputs[self.input_key]
                ontology_schema = self.graph.get_schema
                sparql_result = self.sparql_generation_chain.invoke(
                    {"prompt": prompt, "schema": ontology_schema}, callbacks=callbacks
                )
                generated_sparql = sparql_result[self.sparql_generation_chain.output_key]
                generated_sparql = self._get_prepared_sparql_query(
                    _run_manager, callbacks, generated_sparql, ontology_schema
                )
                generated_sparql = _ensure_sparql_prefixes(generated_sparql)
                raw_results = self._execute_query(generated_sparql)
                context = self._format_results(raw_results, question=prompt)
                _chain_logger.debug(
                    "Formatted context for QA (%d rows):\n%s",
                    len(raw_results), context[:500]
                )
                qa_result = self.qa_chain.invoke(
                    {"prompt": prompt, "context": context}, callbacks=callbacks
                )
                return {self.output_key: qa_result[self.qa_chain.output_key]}

        return _GraphDBQAChain.from_llm(**common)

    if chain_key == "sparql_generic":
        from langchain_community.chains.graph_qa.sparql import GraphSparqlQAChain
        from langchain_core.prompts import PromptTemplate

        # Custom SELECT prompt: no backtick examples (the stock prompt shows
        # backtick-wrapped examples which causes the LLM to return backtick-
        # wrapped queries).  Also inject our kg:/onto:/company: namespaces so
        # the LLM doesn't invent arbitrary prefixes.
        _GENERIC_SPARQL_SELECT_TEMPLATE = """\
Task: Generate a SPARQL SELECT query for a graph database.

CRITICAL RULES:
- Output ONLY the raw SPARQL query — no backticks, no markdown, no explanation.
- Use ONLY the predicates listed in the schema below — copy them EXACTLY as full URIs or use the declared PREFIX.
- Data lives in a named graph — ALWAYS wrap the WHERE body with:
  GRAPH <https://integratedsemantics.org/flexible-graphrag/kg> {{ ... }}
- Entity instances use the kg: prefix:
  PREFIX kg: <https://integratedsemantics.org/flexible-graphrag/kg/>
- To find an entity by name, use rdfs:label with CONTAINS/LCASE:
  ?x rdfs:label ?label . FILTER(CONTAINS(LCASE(?label), "acme"))
- Do NOT invent predicates — only use what is listed in the schema.
- The employment relationship predicate is company:works_for (not worksAt, not employs).

Schema (contains actual namespaces and predicates in the store):
{schema}

Question: {prompt}
SPARQL query (raw, no backticks):"""

        _GENERIC_SPARQL_SELECT_PROMPT = PromptTemplate(
            input_variables=["schema", "prompt"],
            template=_GENERIC_SPARQL_SELECT_TEMPLATE,
        )

        class _GenericSparqlQAChain(GraphSparqlQAChain):
            """
            Overrides _call so that results from _LazyRdfGraph (list-of-dicts
            returned by requests) are formatted cleanly for the QA LLM, and
            strips any backtick fences the LLM may still add despite instructions.
            """

            @staticmethod
            def _strip_backticks(sparql: str) -> str:
                """Remove markdown code fences the LLM may add around the query."""
                s = sparql.strip()
                if s.startswith("```"):
                    lines = s.splitlines()
                    inner = []
                    for line in lines[1:]:
                        if line.strip() == "```":
                            break
                        inner.append(line)
                    s = "\n".join(inner).strip()
                return s

            def _format_results(self, results, question: str = "") -> str:
                if not results:
                    return ""
                if isinstance(results, list) and results and isinstance(results[0], dict):
                    # Label columns take priority over URI columns — avoids duplicates
                    # when the query returns both ?entity (URI) and ?label (literal).
                    _LABEL_KEYS = {"label", "name", "title", "value"}

                    names = []
                    for row in results:
                        keys = [k.lower() for k in row]
                        label_keys = [k for k in row if any(lk in k.lower() for lk in _LABEL_KEYS)]
                        use_keys = label_keys if label_keys else list(row.keys())
                        for k in use_keys:
                            val = row[k]
                            s = str(val)
                            if s.startswith("http"):
                                s = s.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
                            s = s.replace("_", " ").strip()
                            if s:
                                names.append(s)
                    # Deduplicate preserving order
                    seen = set()
                    unique = []
                    for n in names:
                        key = n.lower()
                        if key not in seen:
                            seen.add(key)
                            unique.append(n)
                    body = "\n".join(unique)
                else:
                    body = str(results)
                if question:
                    return f"SPARQL query results for '{question}':\n{body}"
                return body

            def _call(self, inputs, run_manager=None):
                from langchain_core.callbacks import CallbackManagerForChainRun
                _run_manager = run_manager or CallbackManagerForChainRun.get_noop_manager()
                callbacks = _run_manager.get_child()
                prompt = inputs[self.input_key]

                # Intent detection (SELECT vs UPDATE)
                _intent_result = self.sparql_intent_chain.invoke({"prompt": prompt}, config={"callbacks": callbacks})
                intent = _intent_result[self.sparql_intent_chain.output_key].strip()
                if "SELECT" in intent and "UPDATE" not in intent:
                    sparql_gen_chain = self.sparql_generation_select_chain
                    intent = "SELECT"
                elif "UPDATE" in intent and "SELECT" not in intent:
                    sparql_gen_chain = self.sparql_generation_update_chain
                    intent = "UPDATE"
                else:
                    raise ValueError(
                        "Prompt fits neither SELECT nor UPDATE SPARQL query types."
                    )

                # Generate SPARQL
                schema = self.graph.get_schema if hasattr(self.graph, "get_schema") else self.graph.schema
                _sparql_result = sparql_gen_chain.invoke(
                    {"prompt": prompt, "schema": schema}, config={"callbacks": callbacks}
                )
                generated_sparql = self._strip_backticks(
                    _sparql_result[sparql_gen_chain.output_key]
                )
                generated_sparql = _ensure_sparql_prefixes(generated_sparql)
                _chain_logger.debug("Generated SPARQL:\n%s", generated_sparql)

                if intent == "SELECT":
                    try:
                        raw_results = self.graph.query(generated_sparql)
                        row_count = len(raw_results) if hasattr(raw_results, "__len__") else "?"
                        _chain_logger.debug(
                            "Endpoint returned %s result rows from %s",
                            row_count,
                            getattr(self.graph, "_clean_endpoint", "?"),
                        )
                    except Exception as exc:
                        _chain_logger.error("SPARQL execution failed: %s", exc)
                        return {self.output_key: ""}

                    context = self._format_results(raw_results, question=prompt)
                    _chain_logger.debug(
                        "Formatted context for QA (%s rows):\n%s",
                        len(raw_results) if hasattr(raw_results, "__len__") else "?",
                        context[:500],
                    )
                    result = self.qa_chain.invoke(
                        {"prompt": prompt, "context": context},
                        config={"callbacks": callbacks},
                    )
                    res = result[self.qa_chain.output_key]
                elif intent == "UPDATE":
                    self.graph.update(generated_sparql)
                    res = "Successfully inserted triples into the graph."
                else:
                    raise ValueError("Unsupported SPARQL query type.")

                chain_result = {self.output_key: res}
                if self.return_sparql_query:
                    chain_result[self.sparql_query_key] = generated_sparql
                return chain_result

        return _GenericSparqlQAChain.from_llm(
            sparql_select_prompt=_GENERIC_SPARQL_SELECT_PROMPT,
            **common,
        )

    # ---- Neptune OpenCypher -------------------------------------------------
    if chain_key == "opencypher_neptune":
        try:
            from langchain_aws.chains.graph_qa.neptune_cypher import (
                create_neptune_opencypher_qa_chain,
            )
            return create_neptune_opencypher_qa_chain(
                llm=llm, graph=graph,
                return_intermediate_steps=include_intermediate,
                allow_dangerous_requests=True,
            )
        except ImportError:
            from langchain_community.chains.graph_qa.neptune_cypher import (
                NeptuneOpenCypherQAChain,
            )
            return NeptuneOpenCypherQAChain.from_llm(**common)

    # ---- ArcadeDB -----------------------------------------------------------
    if chain_key == "cypher_arcadedb":
        from langchain_arcadedb import ArcadeDBQAChain
        return ArcadeDBQAChain.from_llm(**common)

    # ---- Neo4j --------------------------------------------------------------
    if chain_key == "cypher_neo4j":
        try:
            from langchain_neo4j import GraphCypherQAChain
        except ImportError:
            from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain

        # Wrap graph.query to sanitize LLM-generated Cypher before execution.
        # Neo4j property names with spaces (e.g. "modified at") must be
        # backtick-quoted; the LLM often omits the backticks causing a
        # CypherSyntaxError.
        _original_query = graph.query

        def _sanitized_query(cypher: str, *args, **kwargs):
            cypher = _fix_cypher_spaced_properties(cypher)
            # Rewrite exact toLower equality to CONTAINS so partial names like
            # "Acme" match "Acme Corporation" stored in the graph.
            rewritten = _TOLOWER_EQ_RE.sub(r'\1 CONTAINS \2', cypher)
            if rewritten != cypher:
                _chain_logger.debug("Rewrote toLower equality to CONTAINS for partial matching")
                cypher = rewritten
            # Rewrite n.LABEL_NAME -> n.name (LLMs confuse label names with
            # property names, e.g. d.DEPARTMENT instead of d.name).
            fixed_labels = _LABEL_AS_PROP_RE.sub(
                lambda m: f"{m.group(1)}.name", cypher
            )
            if fixed_labels != cypher:
                _chain_logger.debug(
                    "Fixed label-as-property references in Cypher (e.g. d.DEPARTMENT -> d.name)"
                )
                cypher = fixed_labels
            # Normalize UNION column aliases so all branches use the same name.
            cypher = _normalize_union_columns(cypher)
            _chain_logger.debug("Generated Cypher: %s", cypher)
            return _original_query(cypher, *args, **kwargs)

        graph.query = _sanitized_query

        # Custom Cypher generation prompt: instructs the LLM to use
        # case-insensitive matching so queries like {name: "acme"} still
        # match nodes stored as "Acme Corporation".
        try:
            from langchain_core.prompts import PromptTemplate
            _NEO4J_CYPHER_TEMPLATE = """You are an expert Neo4j Cypher query writer.
Given the schema below, write a Cypher query to answer the question.

Schema:
{schema}

Rules:
- ALWAYS use case-insensitive PARTIAL matching for string comparisons on name fields.
  Use: toLower(n.name) CONTAINS toLower("value")
  This ensures "Acme" matches "Acme Corporation", "ACME Inc", etc.
  Never use exact equality (= or {{name: "value"}}) for user-supplied strings.
- ALWAYS use the `name` property to reference a node's value.
  For DEPARTMENT nodes use d.name (NOT d.DEPARTMENT or d.department).
  For COMPANY nodes use c.name (NOT c.COMPANY). Same rule for all labels.
- For "who works for / at / with COMPANY" questions:
    MATCH (p:PERSON)-[:WORKS_FOR]->(c:COMPANY)
    WHERE toLower(c.name) CONTAINS toLower("Alfresco")
    RETURN p.name
    UNION
    MATCH (c:COMPANY)-[:EMPLOYS]->(p:PERSON)
    WHERE toLower(c.name) CONTAINS toLower("Alfresco")
    RETURN p.name
- For "what departments are at COMPANY" questions:
    MATCH (d:DEPARTMENT)-[:PART_OF]->(c:COMPANY)
    WHERE toLower(c.name) CONTAINS toLower("Acme")
    RETURN d.name
    UNION
    MATCH (c:COMPANY)-[:HAS_DEPARTMENT]->(d:DEPARTMENT)
    WHERE toLower(c.name) CONTAINS toLower("Acme")
    RETURN d.name
- For "who is in DEPARTMENT" questions:
    MATCH (p:PERSON)-[:WORKS_IN_DEPARTMENT]->(d:DEPARTMENT)
    WHERE toLower(d.name) CONTAINS toLower("Engineering")
    RETURN p.name
- For "who endorsed / supported / backed / was involved in TOPIC" questions,
  use HAS_SKILL (company expertise), ANNOUNCED (company announced an event),
  and AFFILIATED_WITH (company partnership network).
  ALL UNION branches MUST return the same column name.
  Example — "what companies endorsed the CMIS spec":
    MATCH (c:COMPANY)-[:HAS_SKILL]->(t:TOPIC)
    WHERE toLower(t.name) CONTAINS toLower("CMIS")
    RETURN DISTINCT c.name AS name
    UNION
    MATCH (hub:COMPANY)-[:HAS_SKILL]->(t:TOPIC)
    WHERE toLower(t.name) CONTAINS toLower("CMIS")
    MATCH (hub)-[:AFFILIATED_WITH]->(partner:COMPANY)
    RETURN DISTINCT partner.name AS name
    UNION
    MATCH (c:COMPANY)-[:ANNOUNCED]->(e:EVENT)
    WHERE toLower(e.name) CONTAINS toLower("CMIS")
    RETURN DISTINCT c.name AS name
- For "who was first / announced / introduced TOPIC" questions:
    MATCH (c:COMPANY)-[:ANNOUNCED]->(e:EVENT)
    WHERE toLower(e.name) CONTAINS toLower("CMIS")
    RETURN c.name, e.name
    UNION
    MATCH (p:PERSON)-[:RELATED_TO]->(t:TOPIC)
    WHERE toLower(t.name) CONTAINS toLower("CMIS")
    RETURN p.name, t.name
- Only use node labels and relationship types present in the schema.
- Return only the most relevant properties (especially name), not entire nodes.
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
            # Fallback: no custom prompt
            chain = GraphCypherQAChain.from_llm(**common)

        # Override graph_schema on the chain itself — GraphCypherQAChain uses
        # graph.get_structured_schema internally (not graph.schema) to build
        # graph_schema, so patching graph.schema alone has no effect.
        # We clean the schema here to remove LlamaIndex-internal labels (__Node__,
        # Chunk) and noise properties so the LLM only sees semantic entity types.
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
            _chain_logger.info(
                "Cleaned chain.graph_schema (%d -> %d chars)",
                len(chain.graph_schema), len(cleaned),
            )
        except Exception as _e:
            _chain_logger.warning("Could not clean chain.graph_schema: %s", _e)

        return chain

    # ---- Memgraph -----------------------------------------------------------
    if chain_key == "cypher_memgraph":
        try:
            from langchain_memgraph import MemgraphQAChain
        except ImportError:
            from langchain_community.chains.graph_qa.memgraph import MemgraphQAChain
        return MemgraphQAChain.from_llm(**common)

    # ---- Kuzu ---------------------------------------------------------------
    if chain_key == "cypher_kuzu":
        try:
            from langchain_kuzu import KuzuQAChain
        except ImportError:
            from langchain_community.chains.graph_qa.kuzu import KuzuQAChain
        return KuzuQAChain.from_llm(**common)

    # ---- FalkorDB -----------------------------------------------------------
    if chain_key == "cypher_falkordb":
        from langchain_community.chains.graph_qa.falkordb import FalkorDBQAChain
        return FalkorDBQAChain.from_llm(**common)

    # ---- Generic Cypher (AGE, TigerGraph, Spanner) --------------------------
    if chain_key == "cypher_generic":
        from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
        return GraphCypherQAChain.from_llm(**common)

    # ---- NebulaGraph --------------------------------------------------------
    if chain_key == "cypher_nebula":
        from langchain_community.chains.graph_qa.nebulagraph import NebulaGraphQAChain
        return NebulaGraphQAChain.from_llm(**common)

    # ---- HugeGraph ----------------------------------------------------------
    if chain_key == "gremlin_hugegraph":
        from langchain_community.chains.graph_qa.hugegraph import HugeGraphQAChain
        return HugeGraphQAChain.from_llm(**common)

    # ---- Generic Gremlin (GremlinGraph, CosmosDBGremlinGraph) ---------------
    if chain_key == "gremlin_generic":
        from langchain_community.chains.graph_qa.gremlin import GremlinQAChain
        return GremlinQAChain.from_llm(**common)

    # ---- ArangoDB (community chain — NOT langchain_arangodb) ----------------
    if chain_key == "aql_arangodb":
        from langchain_community.chains.graph_qa.arangodb import ArangoGraphQAChain
        return ArangoGraphQAChain.from_llm(**common)

    raise ValueError(f"Unhandled chain_key '{chain_key}' for '{name}'")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def detect_query_type(query: str) -> str:
    """Detect the query language from a generated query string."""
    if not query:
        return "unknown"
    q = query.upper()
    if any(kw in q for kw in ("SELECT", "CONSTRUCT", "ASK", "DESCRIBE")):
        return "sparql"
    if "g.V(" in query or "g.E(" in query:
        return "gremlin"
    if "FOR " in q and " RETURN " in q:
        return "aql"
    if any(kw in q for kw in ("MATCH", "CREATE", "MERGE", "OPTIONAL MATCH")):
        return "cypher"
    return "unknown"


# ---------------------------------------------------------------------------
# LlamaIndex retriever wrappers
# ---------------------------------------------------------------------------

class TextToGraphQueryRetriever(BaseRetriever):
    """Wrap any LangChain graph QA chain as a LlamaIndex BaseRetriever.

    Supports every graph store / QA chain pair in langchain_community and
    langchain_aws via automatic class-name detection.  Pass
    ``qa_chain_factory`` to override for custom chains.

    Supported graph stores (auto-detected):
        RDF/SPARQL  : RdfGraph, OntotextGraphDBGraph, NeptuneRdfGraph
        OpenCypher  : NeptuneGraph, NeptuneAnalyticsGraph
        Cypher      : Neo4jGraph, MemgraphGraph, KuzuGraph, FalkorDBGraph,
                      AGEGraph, TigerGraph
        Gremlin     : GremlinGraph, HugeGraph, CosmosDBGremlinGraph
        AQL         : ArangoGraph
        Other       : NebulaGraph, SpannerGraphStore
    """

    def __init__(
        self,
        langchain_graph: Any,
        llm: Any,
        qa_chain_factory: Optional[Callable] = None,
        top_k: int = 5,
        include_intermediate_steps: bool = True,
        **kwargs,
    ):
        """
        Args:
            langchain_graph: Any LangChain graph store object.
            llm: LangChain LLM (ChatOpenAI, ChatAnthropic, ChatOllama, etc.)
            qa_chain_factory: Optional ``(llm, graph) -> chain`` callable to
                override auto-detection.
            top_k: Maximum nodes to return.
            include_intermediate_steps: Surface raw query results as extra
                context nodes with decaying scores.
        """
        super().__init__(**kwargs)
        self.langchain_graph = langchain_graph
        self.llm = llm
        self.top_k = top_k
        self.include_intermediate_steps = include_intermediate_steps
        self.logger = logging.getLogger(__name__)

        if qa_chain_factory:
            self.qa_chain = qa_chain_factory(llm, langchain_graph)
        else:
            self.qa_chain = _build_qa_chain(
                langchain_graph, llm, include_intermediate_steps
            )

        self.logger.info(
            "TextToGraphQueryRetriever ready for %s",
            type(langchain_graph).__name__,
        )

    # ------------------------------------------------------------------

    # Phrases that indicate the graph QA chain found no relevant data.
    # Nodes whose text starts with (case-insensitive) any of these are dropped
    # so they don't pollute the fusion context and degrade the final LLM answer.
    _NO_RESULT_PHRASES = (
        "i don't have",
        "i do not have",
        "no information",
        "not enough information",
        "cannot find",
        "could not find",
        "no results",
        "i don't know",
        "i do not know",
        "i couldn't find",
        "i could not find",
        "no data",
        "not found",
        "unable to find",
        "unable to answer",
        "i'm sorry, but i don't",
        "i'm sorry, but i do not",
        "i'm sorry, i don't",
        "i'm sorry, i do not",
        "i am sorry, but i don't",
        "i am sorry, but i do not",
    )

    @classmethod
    def _is_no_result_answer(cls, text: str) -> bool:
        """Return True if *text* is a 'I don't know / no data' LLM response."""
        t = text.strip().lower()
        return any(t.startswith(p) for p in cls._NO_RESULT_PHRASES)

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        query_str = query_bundle.query_str
        try:
            # Use .invoke() — calling a chain as callable is deprecated in LangChain 0.2+
            result = self.qa_chain.invoke({"query": query_str})

            answer = result.get("result", "")
            generated_query = (
                result.get("generated_sparql")
                or result.get("generated_cypher")
                or result.get("generated_query", "")
            )
            intermediate_steps = result.get("intermediate_steps", [])

            if generated_query:
                self.logger.debug(
                    "Generated %s query:\n%s",
                    detect_query_type(generated_query),
                    generated_query[:500],
                )

            nodes: List[NodeWithScore] = []

            no_data = not answer or not answer.strip() or self._is_no_result_answer(answer)

            if answer and answer.strip():
                if no_data:
                    self.logger.info(
                        "Graph QA returned a 'no data' answer — suppressing node "
                        "to avoid polluting fusion context. Answer was: %s",
                        answer[:200],
                    )
                else:
                    node = TextNode(
                        text=answer,
                        metadata={
                            "source": "langchain_graph_qa",
                            "graph_type": type(self.langchain_graph).__name__,
                            "generated_query": generated_query,
                            "query_type": detect_query_type(generated_query),
                            "original_query": query_str,
                        },
                    )
                    nodes.append(NodeWithScore(node=node, score=1.0))

            # Only surface intermediate steps when the chain produced a real answer.
            # When the answer is "I don't know" the intermediate steps are just the
            # raw Cypher and an empty context string — leaking them as "Source: Unknown"
            # nodes into the fusion retriever adds noise without value.
            if not no_data and self.include_intermediate_steps and intermediate_steps:
                for idx, step in enumerate(intermediate_steps[: self.top_k - 1]):
                    text = _format_step(step)
                    if text and not self._is_no_result_answer(text):
                        node = TextNode(
                            text=text,
                            metadata={
                                "source": "langchain_graph_intermediate",
                                "step_index": idx,
                                "graph_type": type(self.langchain_graph).__name__,
                            },
                        )
                        score = max(0.8 - idx * 0.1, 0.3)
                        nodes.append(NodeWithScore(node=node, score=score))

            self.logger.debug(
                "TextToGraphQueryRetriever returned %d nodes", len(nodes)
            )
            for i, nws in enumerate(nodes[:3]):
                self.logger.debug(
                    "  RDF node[%d] score=%.3f text=%r",
                    i, nws.score, nws.node.text[:150],
                )
            return nodes[: self.top_k]

        except Exception as e:
            self.logger.error("LangChain graph retrieval error: %s", e, exc_info=True)
            return []

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """Async — runs sync in executor to avoid blocking the event loop."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._retrieve, query_bundle)


# ---------------------------------------------------------------------------

class LangChainVectorRetrieverWrapper(BaseRetriever):
    """Wrap any LangChain vector store retriever as a LlamaIndex BaseRetriever."""

    def __init__(
        self,
        langchain_retriever: Any,
        fallback_score: float = 0.7,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.langchain_retriever = langchain_retriever
        self.fallback_score = fallback_score
        self.logger = logging.getLogger(__name__)

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        query_str = query_bundle.query_str
        try:
            # invoke() is the non-deprecated path in LangChain 0.2+
            if hasattr(self.langchain_retriever, "invoke"):
                docs = self.langchain_retriever.invoke(query_str)
            else:
                docs = self.langchain_retriever.get_relevant_documents(query_str)  # type: ignore[attr-defined]
            if not docs:
                return []

            nodes: List[NodeWithScore] = []
            for doc in docs:
                meta = doc.metadata.copy() if doc.metadata else {}
                meta["source_framework"] = "langchain"
                meta["retriever_type"] = type(self.langchain_retriever).__name__
                node = TextNode(text=doc.page_content or "", metadata=meta)
                score = float(
                    getattr(doc, "score", None)
                    or meta.get("score")
                    or meta.get("relevance_score")
                    or self.fallback_score
                )
                nodes.append(NodeWithScore(node=node, score=score))

            self.logger.info(
                "LangChainVectorRetrieverWrapper returned %d nodes", len(nodes)
            )
            return nodes

        except Exception as e:
            self.logger.error("LangChain vector retrieval error: %s", e, exc_info=True)
            return []

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        query_str = query_bundle.query_str
        # ainvoke() is preferred; fall back to aget_relevant_documents, then sync
        if hasattr(self.langchain_retriever, "ainvoke"):
            try:
                docs = await self.langchain_retriever.ainvoke(query_str)
                nodes: List[NodeWithScore] = []
                for doc in docs:
                    meta = doc.metadata.copy() if doc.metadata else {}
                    meta["source_framework"] = "langchain"
                    node = TextNode(text=doc.page_content or "", metadata=meta)
                    score = float(
                        getattr(doc, "score", None)
                        or meta.get("score")
                        or meta.get("relevance_score")
                        or self.fallback_score
                    )
                    nodes.append(NodeWithScore(node=node, score=score))
                return nodes
            except Exception as e:
                self.logger.warning("Async ainvoke failed, falling back to sync: %s", e)
        elif hasattr(self.langchain_retriever, "aget_relevant_documents"):
            try:
                docs = await self.langchain_retriever.aget_relevant_documents(query_str)  # type: ignore[attr-defined]
                nodes = []
                for doc in docs:
                    meta = doc.metadata.copy() if doc.metadata else {}
                    meta["source_framework"] = "langchain"
                    node = TextNode(text=doc.page_content or "", metadata=meta)
                    score = float(
                        getattr(doc, "score", None)
                        or meta.get("score")
                        or meta.get("relevance_score")
                        or self.fallback_score
                    )
                    nodes.append(NodeWithScore(node=node, score=score))
                return nodes
            except Exception as e:
                self.logger.warning("Async retrieval failed, falling back to sync: %s", e)
        return self._retrieve(query_bundle)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_step(step: Any) -> str:
    if isinstance(step, str):
        return step
    if isinstance(step, dict):
        return "\n".join(
            f"{k}: {', '.join(str(v) for v in val) if isinstance(val, (list, tuple)) else val}"
            for k, val in step.items()
        )
    if isinstance(step, (list, tuple)):
        return "\n".join(str(item) for item in step)
    return str(step)
