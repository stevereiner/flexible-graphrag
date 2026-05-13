"""SPARQL chain builders — Fuseki/Oxigraph, GraphDB, Neptune RDF."""

import os
import logging
from typing import Any

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Namespace roots — single source of truth derived from KGToRDFConverter.
# All namespace URIs in prompts, prefix-injection, and schema strings are
# built from these two variables so a config change propagates everywhere.
# ---------------------------------------------------------------------------
from rdf.kg_to_rdf_converter import DEFAULT_BASE_NS, DEFAULT_ONTO_NS

_KG_NS   = DEFAULT_BASE_NS.rstrip("/") + "/"        # entity instance namespace
_KG_URI  = DEFAULT_BASE_NS.rstrip("/")              # named-graph URI (no trailing slash)
_ONTO_NS = DEFAULT_ONTO_NS.rstrip("#") + "#"        # ontology predicate/type namespace
_COMMON_NS = _ONTO_NS.replace("ontology#", "common#")  # common-world namespace

# ---------------------------------------------------------------------------
# Shared utilities: inject missing PREFIX declarations into SPARQL queries
# and fix structural issues in LLM-generated SPARQL.
# ---------------------------------------------------------------------------
_KNOWN_SPARQL_PREFIXES = {
    "kg:":       f"PREFIX kg:      <{_KG_NS}>",
    "onto:":     f"PREFIX onto:    <{_ONTO_NS}>",
    "company:":  "PREFIX company: <http://example.org/company/>",
    "common:":   f"PREFIX common:  <{_COMMON_NS}>",
    "rdfs:":     "PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>",
    "rdf:":      "PREFIX rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",
    "xsd:":      "PREFIX xsd:     <http://www.w3.org/2001/XMLSchema#>",
    "owl:":      "PREFIX owl:     <http://www.w3.org/2002/07/owl#>",
}


_SPARQL_STOPWORDS = frozenset({
    # question words
    "who", "what", "where", "when", "how", "why", "which",
    # auxiliary verbs / copulas
    "is", "are", "was", "were", "does", "did", "do", "can", "could",
    "has", "have", "had", "be", "been", "being", "will", "would", "may", "might",
    # prepositions / conjunctions / articles
    "for", "the", "a", "an", "at", "in", "of", "to", "and", "or",
    "by", "with", "from", "about", "between", "into", "its", "it", "this",
    "that", "these", "those", "each", "all", "any", "some", "no",
    # pronouns / filler
    "me", "us", "them", "their", "they", "he", "she", "we", "i", "you",
    "get", "list", "show", "find", "give", "tell", "let", "make",
    # ordinals / positions (not entity names)
    "first", "second", "third", "last", "latest", "recent", "current",
    "previous", "next", "earliest", "oldest", "newest",
    # generic structural words (not entity-specific)
    "department", "departments", "team", "teams", "group", "groups",
    "company", "companies", "corporation", "organization", "organizations",
    "member", "members", "employee", "employees", "person", "people",
    "project", "projects", "location", "locations", "office", "offices",
    "organized", "structured", "managed", "run", "work", "works", "working",
})

def _extract_keyword(question: str) -> str:
    """Return the most significant single keyword from a natural-language question.

    Entity names (Acme, CMIS, IBM) are typically short (3-8 chars).
    Question-specific words (organized, structured, introduced) are longer.
    We prefer the SHORTEST non-stopword candidate to pick proper entity names
    rather than question verbs/adjectives, which handles typos gracefully too.
    """
    import re as _re
    words = _re.sub(r"[^\w\s]", "", question.lower()).split()
    candidates = [w for w in words if w not in _SPARQL_STOPWORDS and len(w) > 2]
    if not candidates:
        candidates = [w for w in words if len(w) > 2]
    # Sort by length ascending — entity names (acme=4, cmis=4) beat
    # question-descriptor words (organized=9, structured=10).
    candidates.sort(key=len)
    return candidates[0] if candidates else (words[0] if words else "")


def _build_broad_fallback_sparql(keyword: str, graph_uri: str = _KG_URI,
                                  onto_ns: str = _ONTO_NS) -> str:
    """Return a broad SPARQL that finds relationships involving entities matching keyword.

    Searches bi-directionally:
      - triples WHERE the matched entity is the SUBJECT  (?entity ?pred ?other)
      - triples WHERE the matched entity is the OBJECT   (?other ?pred ?entity)
    This ensures we capture both outbound (HAS_LOCATION, HAS_SKILL) and inbound
    (WORKS_FOR, PART_OF) relationships for organisational/structural questions.
    """
    return f"""\
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?entityLabel ?predName ?relatedLabel ?direction WHERE {{
  GRAPH <{graph_uri}> {{
    {{
      # Entity is SUBJECT — outbound relationships (HAS_LOCATION, HAS_SKILL, …)
      ?entity rdfs:label ?entityLabel FILTER(CONTAINS(LCASE(?entityLabel), "{keyword}")) .
      ?entity ?pred ?related .
      BIND("outbound" AS ?direction)
    }} UNION {{
      # Entity is OBJECT — inbound relationships (WORKS_FOR, PART_OF, EMPLOYED_BY, …)
      ?entity rdfs:label ?entityLabel FILTER(CONTAINS(LCASE(?entityLabel), "{keyword}")) .
      ?related ?pred ?entity .
      BIND("inbound" AS ?direction)
    }}
    BIND(REPLACE(REPLACE(STR(?pred), ".*#", ""), ".*/", "") AS ?predName)
    OPTIONAL {{ ?related rdfs:label ?relatedLabel }}
    FILTER(!STRSTARTS(STR(?pred), "http://www.w3.org/") &&
           !STRSTARTS(STR(?pred), "{onto_ns}"))
  }}
}} LIMIT 60
"""


def _ensure_sparql_prefixes(sparql: str) -> str:
    """Inject any standard PREFIX declarations used but not declared in the query."""
    missing = []
    for prefix, decl in _KNOWN_SPARQL_PREFIXES.items():
        used = prefix in sparql
        declared = (f"PREFIX {prefix}" in sparql or f"prefix {prefix}" in sparql.lower())
        if used and not declared:
            missing.append(decl)
    if missing:
        _logger.debug(
            "Injecting missing PREFIX declarations: %s",
            [m.split()[1] for m in missing],
        )
        sparql = "\n".join(missing) + "\n" + sparql
    return sparql


def _fix_sparql_structure(sparql: str) -> str:
    """Fix LLM-generated SPARQL where GRAPH{} appears as the outermost clause.

    LLMs frequently emit two broken patterns for named-graph queries:

    Pattern 1 — bare GRAPH block, no SELECT/WHERE:
        PREFIX ...
        GRAPH <uri> { ?s ?p ?o }

    Pattern 2 — SELECT trailing after the GRAPH block:
        PREFIX ...
        GRAPH <uri> { ?s ?p ?o }
        SELECT ?s ?p

    Both are rejected with HTTP 400 by Fuseki/GraphDB/Oxigraph.
    This function rewrites them to valid SPARQL:
        SELECT [* | ?vars] WHERE { GRAPH <uri> { ?s ?p ?o } }
    """
    import re as _re
    stripped = sparql.strip()

    prefix_lines = []
    body_lines = []
    in_prefixes = True
    for line in stripped.splitlines():
        ls = line.strip()
        if in_prefixes and (ls.upper().startswith("PREFIX") or ls == ""):
            prefix_lines.append(line)
        else:
            in_prefixes = False
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if not body:
        return sparql

    first_token = body.split()[0].upper()
    if first_token in ("SELECT", "ASK", "CONSTRUCT", "DESCRIBE"):
        return sparql
    if first_token != "GRAPH":
        return sparql

    last_brace = body.rfind("}")
    if last_brace == -1:
        return sparql

    graph_block = body[: last_brace + 1].strip()
    trailing = body[last_brace + 1 :].strip()

    if trailing.upper().startswith("SELECT"):
        new_body = f"{trailing}\nWHERE {{\n  {graph_block}\n}}"
    else:
        new_body = f"SELECT *\nWHERE {{\n  {graph_block}\n}}"

    prefix_str = "\n".join(line for line in prefix_lines if line.strip())
    result = (prefix_str + "\n" + new_body).strip() if prefix_str else new_body
    _logger.debug("Fixed SPARQL structure: wrapped bare GRAPH clause in SELECT...WHERE")
    return result


# ---------------------------------------------------------------------------
# Chain builders
# ---------------------------------------------------------------------------

def build_sparql_neptune(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """Neptune RDF SPARQL chain with a fully custom prompt.

    ``extra_instructions`` on ``create_neptune_sparql_qa_chain`` is appended
    to the chain's built-in template but the LLM still primes toward ex:/org:
    prefixes from the base template and ignores the injected rules.

    Instead we replicate the _GenericSparqlQAChain approach: build our own
    ``GraphSparqlQAChain`` with a replacement SELECT prompt that puts the
    mandatory namespace rules first and leaves no room for hallucinated URIs.
    """
    try:
        from langchain_aws.chains import create_neptune_sparql_qa_chain  # noqa: F401 (kept for import check)
    except ImportError:
        raise ImportError(
            "langchain_aws is required for NeptuneRdfGraph. "
            "Install it with: pip install langchain-aws"
        )

    from langchain_community.chains.graph_qa.sparql import GraphSparqlQAChain
    from langchain_core.prompts import PromptTemplate

    # Read namespaces from config (AppSettings) when available.
    _cfg = common.get("config")
    _base_ns = (
        getattr(_cfg, "rdf_base_namespace", None) or DEFAULT_BASE_NS
    ).rstrip("/") + "/"
    _onto_ns = (
        getattr(_cfg, "rdf_ontology_namespace", None) or DEFAULT_ONTO_NS
    ).rstrip("#") + "#"
    _common_ns = _onto_ns.replace("ontology#", "common#")
    # Named-graph URI (no trailing slash) — triples are stored here
    _kg_uri = _base_ns.rstrip("/")

    _NEPTUNE_SELECT_TEMPLATE = f"""\
Task: Generate a SPARQL SELECT query to answer the following question from a Neptune RDF knowledge graph.

You are a SPARQL expert. ALWAYS declare and use EXACTLY these prefixes — no others:
  PREFIX kg:      <{_base_ns}>
  PREFIX onto:    <{_onto_ns}>
  PREFIX company: <http://example.org/company/>
  PREFIX common:  <{_common_ns}>
  PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
  PREFIX rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

FORBIDDEN prefixes — do NOT use: ex:, org:, foaf:, schema:, owl:

Entity URIs: kg:<EntityName_With_Underscores>  (spaces become underscores)
  Example: "Acme Corporation" -> kg:Acme_Corporation

Relation predicates: onto:<predicate> or company:<predicate>
  Example: onto:works_for, company:works_for, onto:has_department, onto:located_in

Triples are stored in a named graph <{_kg_uri}>.
Wrap all triple patterns in: GRAPH <{_kg_uri}> {{{{ ... }}}}

For entity lookups use FILTER with case-insensitive label matching:
  ?s rdfs:label ?label . FILTER(LCASE(?label) = "acme corporation")
OR match by URI slug:
  FILTER(LCASE(STRAFTER(STR(?s), "{_base_ns}")) = "acme_corporation")

Graph schema (available predicates and types):
{{schema}}

EXAMPLE 1 — who works for Acme:
PREFIX kg:      <{_base_ns}>
PREFIX onto:    <{_onto_ns}>
PREFIX company: <http://example.org/company/>
PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?name WHERE {{{{
  GRAPH <{_kg_uri}> {{{{
    {{{{ ?person onto:works_for ?org }}}} UNION {{{{ ?person company:works_for ?org }}}}
    ?org rdfs:label ?orgLabel . FILTER(LCASE(?orgLabel) = "acme corporation")
    OPTIONAL {{{{ ?person rdfs:label ?name }}}}
    BIND(COALESCE(?name, STRAFTER(STR(?person), "{_base_ns}")) AS ?name)
  }}}}
}}}}

EXAMPLE 2 — how is Acme organized:
PREFIX kg:      <{_base_ns}>
PREFIX onto:    <{_onto_ns}>
PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?deptName WHERE {{{{
  GRAPH <{_kg_uri}> {{{{
    ?org rdfs:label ?orgLabel . FILTER(LCASE(?orgLabel) = "acme corporation")
    {{{{ ?dept onto:part_of ?org }}}} UNION {{{{ ?org onto:has_department ?dept }}}}
    OPTIONAL {{{{ ?dept rdfs:label ?deptName }}}}
    BIND(COALESCE(?deptName, STRAFTER(STR(?dept), "{_base_ns}")) AS ?deptName)
  }}}}
}}}}

Output only the raw SPARQL query — no explanation, no markdown fences.

Question: {{prompt}}
SPARQL query:"""

    _neptune_select_prompt = PromptTemplate(
        input_variables=["schema", "prompt"],
        template=_NEPTUNE_SELECT_TEMPLATE,
    )

    # -----------------------------------------------------------------------
    # NeptuneRdfGraph is NOT a subclass of langchain_community's RdfGraph.
    # GraphSparqlQAChain has:  graph: RdfGraph = Field(...)
    # Pydantic enforces isinstance(graph, RdfGraph) and rejects NeptuneRdfGraph.
    #
    # Fix: wrap NeptuneRdfGraph in a thin proxy that inherits RdfGraph but
    # bypasses RdfGraph.__init__ (which fires a SPARQL COUNT query).
    # The proxy delegates query() and exposes get_schema so the chain works.
    # -----------------------------------------------------------------------
    from langchain_community.graphs.rdf_graph import RdfGraph as _RdfGraph

    class _NeptuneRdfGraphProxy(_RdfGraph):
        """Proxy that makes NeptuneRdfGraph pass isinstance(graph, RdfGraph).

        Inherits RdfGraph only for type-checking purposes. __init__ bypasses
        RdfGraph.__init__ via object.__init__ to avoid the SPARQL store setup.
        """

        def __init__(self, neptune_graph: Any) -> None:
            # Skip RdfGraph.__init__ — it fires a SPARQL COUNT and needs a store.
            object.__init__(self)
            self._neptune = neptune_graph
            # Minimal attributes that GraphSparqlQAChain may read
            self.query_endpoint = getattr(neptune_graph, "query_endpoint", "")
            self.update_endpoint = None
            self.standard = "rdf"
            self.local_copy = None
            self.schema: str = getattr(neptune_graph, "get_schema", "") or ""

        @property
        def get_schema(self) -> str:
            return getattr(self._neptune, "get_schema", "") or ""

        def load_schema(self) -> None:
            pass  # Already loaded by NeptuneRdfGraph

        def query(self, sparql_query: str):
            """Delegate SELECT to NeptuneRdfGraph and unwrap SPARQL JSON."""
            raw = self._neptune.query(sparql_query)
            # NeptuneRdfGraph returns SPARQL JSON Results dict
            if isinstance(raw, dict):
                bindings = raw.get("results", {}).get("bindings", [])
                return [{k: v.get("value", "") for k, v in b.items()} for b in bindings]
            return raw

    _proxy = _NeptuneRdfGraphProxy(graph)

    class _NeptuneSparqlQAChain(GraphSparqlQAChain):
        """GraphSparqlQAChain variant wired to NeptuneRdfGraph via proxy.

        Results from query() are already list-of-dicts (unwrapped by the proxy),
        so _format_results from the parent generic chain handles them cleanly.
        Falls back to a broad keyword SPARQL when the generated query returns 0 rows.
        """

        def _strip_backticks(self, text: str) -> str:
            lines = text.strip().splitlines()
            if lines and lines[0].strip().startswith("```"):
                inner = []
                for line in lines[1:]:
                    if line.strip() == "```":
                        break
                    inner.append(line)
                return "\n".join(inner).strip()
            return text

        def _format_results(self, results, question: str = "") -> str:
            if not results:
                return ""
            if isinstance(results, list) and results and isinstance(results[0], dict):
                _LABEL_KEYS = {"label", "name", "title", "value"}
                lines = []
                for row in results:
                    label_items = [(k, v) for k, v in row.items() if k.lower() in _LABEL_KEYS]
                    other_items = [(k, v) for k, v in row.items() if k.lower() not in _LABEL_KEYS]
                    display = label_items if label_items else other_items
                    parts = []
                    for _, v in display:
                        sv = str(v)
                        if sv.startswith("http"):
                            sv = sv.rstrip("/").split("/")[-1].split("#")[-1].replace("_", " ")
                        parts.append(sv)
                    if parts:
                        lines.append(", ".join(p for p in parts if p))
                return "\n".join(lines)
            return str(results)

        def _call(self, inputs, run_manager=None):
            from langchain_core.callbacks.manager import CallbackManagerForChainRun
            _run_manager = run_manager or CallbackManagerForChainRun.get_noop_manager()
            callbacks = _run_manager.get_child()
            prompt = inputs[self.input_key]

            schema = self.graph.get_schema if hasattr(self.graph, "get_schema") else ""
            _sparql_result = self.sparql_generation_select_chain.invoke(
                {"prompt": prompt, "schema": schema}, config={"callbacks": callbacks}
            )
            generated_sparql = self._strip_backticks(
                _sparql_result[self.sparql_generation_select_chain.output_key]
            )
            generated_sparql = _ensure_sparql_prefixes(generated_sparql)
            _logger.debug("Generated SPARQL:\n%s", generated_sparql)

            try:
                raw_results = self.graph.query(generated_sparql)
            except Exception as exc:
                _logger.error("Neptune SPARQL execution failed: %s\nQuery:\n%s", exc, generated_sparql)
                return {self.output_key: "", "generated_sparql": generated_sparql}

            row_count = len(raw_results) if hasattr(raw_results, "__len__") else 0
            _logger.debug("Neptune returned %s result rows", row_count)

            if not row_count:
                keyword = _extract_keyword(prompt)
                if keyword:
                    fallback_sparql = _build_broad_fallback_sparql(keyword, graph_uri=_kg_uri)
                    _logger.debug(
                        "SPARQL returned 0 rows — retrying with broad fallback (keyword=%r)", keyword
                    )
                    try:
                        fb_results = self.graph.query(fallback_sparql)
                        if fb_results:
                            raw_results = fb_results
                            generated_sparql = fallback_sparql
                            _logger.debug("Broad fallback returned %d rows", len(fb_results))
                    except Exception as _fb_exc:
                        _logger.debug("Broad fallback failed: %s", _fb_exc)

            context = self._format_results(raw_results, question=prompt)
            _logger.debug("Formatted context for QA:\n%s", context[:500])

            # If SPARQL returned no usable rows (primary + fallback both empty),
            # skip the QA chain entirely — calling it with empty context causes the
            # LLM to hallucinate a "no information available" answer that passes
            # through _is_no_result_answer and pollutes search results after deletion.
            if not context or not context.strip():
                _logger.debug(
                    "Neptune SPARQL: no results from primary or fallback — skipping QA chain"
                )
                return {self.output_key: "", "generated_sparql": generated_sparql}

            qa_result = self.qa_chain.invoke(
                {"prompt": prompt, "context": context}, config={"callbacks": callbacks}
            )
            return {
                self.output_key: qa_result[self.qa_chain.output_key],
                "generated_sparql": generated_sparql,
            }

    return _NeptuneSparqlQAChain.from_llm(
        sparql_select_prompt=_neptune_select_prompt,
        llm=llm,
        graph=_proxy,
        verbose=False,
        return_intermediate_steps=include_intermediate,
        allow_dangerous_requests=True,
    )


def build_sparql_graphdb(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """GraphDB (Ontotext) SPARQL chain."""
    from langchain_community.chains.graph_qa.ontotext_graphdb import OntotextGraphDBQAChain
    from langchain_core.callbacks.manager import CallbackManagerForChainRun

    _query_endpoint = None
    try:
        _query_endpoint = str(graph.graph.store.query_endpoint)
    except Exception:
        pass
    if not _query_endpoint:
        _query_endpoint = getattr(graph, "query_endpoint", None)
    _logger.info("GraphDB direct query endpoint: %s", _query_endpoint or "NOT FOUND")
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
            _logger.debug("Generated SPARQL:\n%s", generated_sparql)
            return generated_sparql

        def _execute_query(self, query: str):
            """POST query directly to GraphDB, bypassing rdflib SPARQLStore."""
            import requests as _requests
            endpoint = _query_endpoint
            if not endpoint:
                _logger.warning(
                    "No GraphDB endpoint available, falling back to rdflib store"
                )
                return super()._execute_query(query)
            _logger.debug("POSTing SPARQL directly to GraphDB: %s", endpoint)
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
                from collections import namedtuple
                rows = []
                for b in bindings:
                    keys = list(b.keys())
                    Row = namedtuple("Row", keys)
                    vals = [b[k].get("value", "") for k in keys]
                    rows.append(Row(*vals))
                _logger.debug("GraphDB returned %d result rows", len(rows))
                if rows:
                    _logger.debug("Sample row fields=%s values=%s", rows[0]._fields, list(rows[0]))
                return rows
            except _requests.HTTPError as e:
                _logger.error(
                    "GraphDB HTTP %s executing SPARQL:\n%s\nQuery:\n%s",
                    e.response.status_code, e.response.text[:500], query,
                )
                raise ValueError("Failed to execute the generated SPARQL query.") from e
            except Exception as e:
                _logger.error(
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
            names = "\n".join(lines)
            if question:
                text = f"SPARQL query results for '{question}':\n{names}"
            else:
                text = names
            _logger.debug("_format_results produced: %r", text[:300])
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
            generated_sparql = _fix_sparql_structure(generated_sparql)
            raw_results = self._execute_query(generated_sparql)
            if not raw_results:
                keyword = _extract_keyword(prompt)
                if keyword:
                    fallback_sparql = _build_broad_fallback_sparql(keyword)
                    _logger.debug(
                        "SPARQL returned 0 rows — retrying with broad fallback "
                        "(keyword=%r)", keyword
                    )
                    try:
                        raw_results = self._execute_query(fallback_sparql)
                        if raw_results:
                            generated_sparql = fallback_sparql
                            _logger.debug(
                                "Broad fallback returned %d rows", len(raw_results)
                            )
                    except Exception as _fb_exc:
                        _logger.debug("Broad fallback failed: %s", _fb_exc)
            # If both primary and fallback SPARQL returned 0 rows, return empty
            # so the LLM doesn't hallucinate an answer from its training data.
            if not raw_results:
                _logger.debug(
                    "GraphDB: no results from primary or fallback SPARQL — "
                    "returning empty to prevent LLM hallucination"
                )
                return {self.output_key: "", "generated_sparql": generated_sparql}
            context = self._format_results(raw_results, question=prompt)
            _logger.debug(
                "Formatted context for QA (%d rows):\n%s",
                len(raw_results), context[:500]
            )
            qa_result = self.qa_chain.invoke(
                {"prompt": prompt, "context": context}, callbacks=callbacks
            )
            return {
                self.output_key: qa_result[self.qa_chain.output_key],
                "generated_sparql": generated_sparql,
            }

    return _GraphDBQAChain.from_llm(**common)


def build_sparql_generic(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """Generic SPARQL chain for Fuseki/Oxigraph (via _HttpSparqlGraph or RdfGraph)."""
    from langchain_community.chains.graph_qa.sparql import GraphSparqlQAChain
    from langchain_core.prompts import PromptTemplate

    _GENERIC_SPARQL_SELECT_TEMPLATE = f"""\
Task: Generate a SPARQL SELECT query to answer the following question from a knowledge graph.

You are a SPARQL expert. The graph uses these named-graph namespaces:
  Knowledge-graph triples: GRAPH <{_KG_URI}>
  Ontology definitions   : GRAPH <{_KG_URI.replace("/kg", "/ontology")}>

Useful prefixes (declare any you use):
  PREFIX kg:      <{_KG_NS}>
  PREFIX onto:    <{_ONTO_NS}>
  PREFIX company: <http://example.org/company/>
  PREFIX common:  <{_COMMON_NS}>
  PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
  PREFIX rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
  PREFIX xsd:     <http://www.w3.org/2001/XMLSchema#>
  PREFIX owl:     <http://www.w3.org/2002/07/owl#>

Graph schema (available predicates and types):
{{schema}}

Rules:
- Always wrap triple patterns in GRAPH <{_KG_URI}> {{{{ ... }}}}
- Use FILTER(CONTAINS(LCASE(?label), "keyword")) for case-insensitive partial matching.
- Use rdfs:label to look up entity names.
- FORBIDDEN: Do NOT use any predicate not visible in the schema above.
  The schema may list predicates from an OWL ontology file; only use those
  that actually appear as triples in the store. If unsure, use the broad fallback.
- Output only the raw SPARQL query — no explanation, no markdown fences.

Broad fallback (when no specific predicate fits):
  SELECT DISTINCT ?entity ?label WHERE {{{{
    GRAPH <{_KG_URI}> {{{{
      ?entity ?pred ?related .
      ?related rdfs:label ?relLabel FILTER(CONTAINS(LCASE(?relLabel), "keyword")) .
      OPTIONAL {{{{ ?entity rdfs:label ?label }}}}
    }}}}
  }}}}

Question: {{prompt}}
SPARQL query:"""

    _GENERIC_SPARQL_SELECT_PROMPT = PromptTemplate(
        input_variables=["schema", "prompt"],
        template=_GENERIC_SPARQL_SELECT_TEMPLATE,
    )

    class _GenericSparqlQAChain(GraphSparqlQAChain):
        """Overrides _call so that results from _HttpSparqlGraph (list-of-dicts
        returned by requests) are formatted cleanly for the QA LLM, and
        strips any backtick fences the LLM may still add despite instructions.
        """

        def _strip_backticks(self, text: str) -> str:
            """Remove ```sparql ... ``` or ``` ... ``` fences if present."""
            lines = text.strip().splitlines()
            if lines and lines[0].strip().startswith("```"):
                inner = []
                for line in lines[1:]:
                    if line.strip() == "```":
                        break
                    inner.append(line)
                return "\n".join(inner).strip()
            return text

        def _format_results(self, results, question: str = "") -> str:
            if not results:
                return ""
            if isinstance(results, list) and results and isinstance(results[0], dict):
                _LABEL_KEYS = {"label", "name", "title", "value"}
                lines = []
                for row in results:
                    label_items = [(k, v) for k, v in row.items() if k.lower() in _LABEL_KEYS]
                    uri_items   = [(k, v) for k, v in row.items() if k.lower() not in _LABEL_KEYS]
                    display_items = label_items if label_items else uri_items
                    parts = []
                    for k, v in display_items:
                        sv = str(v)
                        if sv.startswith("http"):
                            sv = sv.rstrip("/").split("/")[-1].split("#")[-1].replace("_", " ")
                        parts.append(sv)
                    if parts:
                        lines.append(", ".join(p for p in parts if p))
                return "\n".join(lines)
            if isinstance(results, list):
                return "\n".join(str(r) for r in results)
            return str(results)

        def _call(self, inputs, run_manager=None):
            """Override to strip backtick fences and handle empty results."""
            from langchain_core.callbacks.manager import CallbackManagerForChainRun
            _run_manager = run_manager or CallbackManagerForChainRun.get_noop_manager()
            callbacks = _run_manager.get_child()
            prompt = inputs[self.input_key]

            _intent_result = self.sparql_intent_chain.invoke({"prompt": prompt}, config={"callbacks": callbacks})
            intent = _intent_result[self.sparql_intent_chain.output_key].strip()
            if "SELECT" in intent and "UPDATE" not in intent:
                sparql_gen_chain = self.sparql_generation_select_chain
                intent = "SELECT"
            elif "UPDATE" in intent and "SELECT" not in intent:
                # This retriever is read-only — we never execute SPARQL UPDATE.
                # The LLM occasionally classifies retrieval questions that contain
                # words like "deleted", "removed", etc. as UPDATE intent.
                # Force SELECT: use the SELECT chain and override intent.
                _logger.debug(
                    "SPARQL intent chain returned UPDATE for retrieval query; "
                    "forcing SELECT (this chain is read-only)."
                )
                sparql_gen_chain = self.sparql_generation_select_chain
                intent = "SELECT"
            else:
                # Intent is ambiguous — default to SELECT (read-only retrieval)
                _logger.debug(
                    "SPARQL intent ambiguous (%r) — defaulting to SELECT.", intent
                )
                sparql_gen_chain = self.sparql_generation_select_chain
                intent = "SELECT"

            schema = self.graph.get_schema if hasattr(self.graph, "get_schema") else self.graph.schema
            _sparql_result = sparql_gen_chain.invoke(
                {"prompt": prompt, "schema": schema}, config={"callbacks": callbacks}
            )
            generated_sparql = self._strip_backticks(
                _sparql_result[sparql_gen_chain.output_key]
            )
            generated_sparql = _ensure_sparql_prefixes(generated_sparql)
            generated_sparql = _fix_sparql_structure(generated_sparql)
            _logger.debug("Generated SPARQL:\n%s", generated_sparql)

            if intent == "SELECT":
                try:
                    raw_results = self.graph.query(generated_sparql)
                    row_count = len(raw_results) if hasattr(raw_results, "__len__") else "?"
                    _logger.debug(
                        "Endpoint returned %s result rows from %s",
                        row_count,
                        getattr(self.graph, "_clean_endpoint", "?"),
                    )
                except Exception as exc:
                    _logger.error("SPARQL execution failed: %s", exc)
                    return {self.output_key: ""}

                if not raw_results or (hasattr(raw_results, "__len__") and len(raw_results) == 0):
                    keyword = _extract_keyword(prompt)
                    if keyword:
                        fallback_sparql = _build_broad_fallback_sparql(keyword)
                        _logger.debug(
                            "SPARQL returned 0 rows — retrying with broad fallback "
                            "(keyword=%r)", keyword
                        )
                        try:
                            fb_results = self.graph.query(fallback_sparql)
                            if fb_results and (not hasattr(fb_results, "__len__") or len(fb_results) > 0):
                                raw_results = fb_results
                                generated_sparql = fallback_sparql
                                _logger.debug(
                                    "Broad fallback returned %d rows",
                                    len(raw_results) if hasattr(raw_results, "__len__") else "?",
                                )
                        except Exception as _fb_exc:
                            _logger.debug("Broad fallback failed: %s", _fb_exc)

                # If both primary and fallback returned 0 rows, return empty
                # so the LLM doesn't hallucinate an answer from its training data.
                _result_count = len(raw_results) if hasattr(raw_results, "__len__") else 1
                if not raw_results or _result_count == 0:
                    _logger.debug(
                        "SPARQL: no results from primary or fallback — "
                        "returning empty to prevent LLM hallucination"
                    )
                    return {self.output_key: "", "generated_sparql": generated_sparql}

                context = self._format_results(raw_results, question=prompt)
                _logger.debug(
                    "Formatted context for QA (%s rows):\n%s",
                    _result_count,
                    context[:500],
                )
                result = self.qa_chain.invoke(
                    {"prompt": prompt, "context": context},
                    config={"callbacks": callbacks},
                )
                res = result[self.qa_chain.output_key]
            elif intent == "UPDATE":
                # Should never reach here — intent is always forced to SELECT above.
                # Kept as a safety net: try SELECT, ignore any error.
                try:
                    raw_results = self.graph.query(generated_sparql)
                    context = self._format_results(raw_results, question=prompt)
                    result = self.qa_chain.invoke(
                        {"prompt": prompt, "context": context},
                        config={"callbacks": callbacks},
                    )
                    res = result[self.qa_chain.output_key]
                except Exception:
                    res = ""
            else:
                raise ValueError("Unsupported SPARQL query type.")

            chain_result = {self.output_key: res, "generated_sparql": generated_sparql}
            if self.return_sparql_query:
                chain_result[self.sparql_query_key] = generated_sparql
            return chain_result

    return _GenericSparqlQAChain.from_llm(
        sparql_select_prompt=_GENERIC_SPARQL_SELECT_PROMPT,
        **common,
    )
