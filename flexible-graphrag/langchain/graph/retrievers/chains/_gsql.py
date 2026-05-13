"""TigerGraph GSQL interpreted-query chain builder."""

import logging
import re as _re
from typing import Any

_logger = logging.getLogger(__name__)


def build_gsql_tigergraph(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """TigerGraph custom GSQL interpreted-query chain (no NLQS required)."""
    _tg_conn = graph.conn if hasattr(graph, "conn") else None

    def _build_tg_schema(g) -> str:
        """Build a human-readable schema string from the TigerGraph connection."""
        raw = {}
        try:
            raw = g.conn.getSchema(force=True) or {}
        except Exception:
            try:
                raw = g.get_schema() or {}
            except Exception:
                pass
        if not raw:
            return "Schema not available."
        lines: list = []
        vtypes = raw.get("VertexTypes") or raw.get("vertex_types") or []
        for vt in vtypes:
            vname = vt.get("Name") or vt.get("name", "")
            pid = vt.get("PrimaryId", {})
            pid_name = pid.get("AttributeName", "id")
            attrs = vt.get("Attributes") or vt.get("attributes") or []
            anames = [pid_name] + [a.get("AttributeName") or a.get("name", "") for a in attrs]
            lines.append(f"Vertex: {vname}  properties: {', '.join(anames)}")
        etypes = raw.get("EdgeTypes") or raw.get("edge_types") or []
        for et in etypes:
            ename = et.get("Name") or et.get("name", "")
            pairs = et.get("EdgePairs") or []
            if pairs:
                frm = pairs[0].get("From", "")
                to  = pairs[0].get("To", "")
            else:
                frm = et.get("FromVertexTypeName") or et.get("from", "")
                to  = et.get("ToVertexTypeName") or et.get("to", "")
            attrs = et.get("Attributes") or []
            anames = [a.get("AttributeName") or a.get("name", "") for a in attrs]
            lines.append(
                f"Edge: ({frm})-[{ename}]->({to})"
                + (f"  properties: {', '.join(anames)}" if anames else "")
            )
        return "\n".join(lines) if lines else "Empty schema (no vertex/edge types yet)."

    _tg_schema_str = _build_tg_schema(graph)
    _logger.debug("TigerGraph schema for QA chain:\n%s", _tg_schema_str)

    _TG_GSQL_TEMPLATE = """\
You are a TigerGraph GSQL v1 expert.  Write a single interpreted GSQL query that answers the question.

Graph schema:
{schema}

CRITICAL RULES — follow every rule exactly or the query will fail:
1. The ONLY vertex type is __Entity__ (properties: id, name, node_type, source).
   NEVER use any other vertex type name (no Company, Person, Employee, etc.).
2. The ONLY edge type is __Relationship__ (properties: rel_type, source).
   NEVER use any other edge type name.
3. Use GSQL v1 syntax ONLY.  NEVER use MATCH, v2 patterns, or mix v1 and v2.
4. Vertex seed set:   Seed = {{__Entity__.*}};
5. Filter vertices:   Result = SELECT s FROM Seed:s WHERE lower(s.name) LIKE "%keyword%";
6. Edge traversal:    Related = SELECT t FROM Source:s -(__Relationship__:e)-> :t
                        WHERE e.rel_type == "REL_TYPE";
7. Filter by type:    Add  WHERE s.node_type == "TypeName"  (e.g. "Organization")
8. PRINT at least one variable at the end.
9. Wrap everything in:
   INTERPRET QUERY() FOR GRAPH MyGraph {{
     ...body...
     PRINT Result;
   }}
10. Emit ONLY the raw GSQL query — no markdown fences, no backticks, no explanation.

Examples:

Q: Who works for Acme?
A: INTERPRET QUERY() FOR GRAPH MyGraph {{
  Seed = {{__Entity__.*}};
  Acme = SELECT s FROM Seed:s WHERE lower(s.name) LIKE "%acme%";
  Workers = SELECT t FROM Acme:a -(__Relationship__:e)-> :t
              WHERE e.rel_type == "WORKS_FOR";
  PRINT Workers;
}}

Q: How is Acme organized? What departments does Acme have?
A: INTERPRET QUERY() FOR GRAPH MyGraph {{
  Seed = {{__Entity__.*}};
  Acme = SELECT s FROM Seed:s WHERE lower(s.name) LIKE "%acme%";
  Related = SELECT t FROM Acme:a -(__Relationship__:e)-> :t;
  PRINT Related;
}}

Q: What is the role of Alice at Acme?
A: INTERPRET QUERY() FOR GRAPH MyGraph {{
  Seed = {{__Entity__.*}};
  Alice = SELECT s FROM Seed:s WHERE lower(s.name) LIKE "%alice%";
  Roles = SELECT t FROM Alice:a -(__Relationship__:e)-> :t;
  PRINT Alice, Roles;
}}

Question: {question}
GSQL Query:"""

    from langchain_core.prompts import PromptTemplate as _PT
    _tg_prompt = _PT(template=_TG_GSQL_TEMPLATE, input_variables=["schema", "question"])

    _tg_graphname = "MyGraph"
    try:
        _tg_graphname = _tg_conn.graphname or "MyGraph"
    except Exception:
        pass

    class _TGGSQLChain:
        """Lightweight GSQL QA chain for local TigerGraph (no NLQS required)."""
        def __init__(self, llm, conn, graphname: str, schema: str, prompt):
            self._llm       = llm
            self._conn      = conn
            self._graphname = graphname
            self._schema    = schema
            self._prompt    = prompt

        def _run_query(self, gsql: str) -> list:
            gsql = gsql.strip()
            gsql = _re.sub(r"^```[a-zA-Z]*\n?", "", gsql)
            gsql = _re.sub(r"\n?```$", "", gsql.strip())
            gsql = _re.sub(
                r"FOR GRAPH\s+\w+",
                f"FOR GRAPH {self._graphname}",
                gsql, flags=_re.IGNORECASE,
            )
            if not gsql or "INTERPRET QUERY" not in gsql.upper():
                _logger.warning("TigerGraph: no valid GSQL generated: %r", gsql)
                return []
            _logger.info("TigerGraph GSQL query:\n%s", gsql)
            try:
                result = self._conn.runInterpretedQuery(gsql)
                return result if isinstance(result, list) else [result]
            except Exception as exc:
                _logger.warning("TigerGraph runInterpretedQuery error: %s\n%s", exc, gsql)
                return []

        def invoke(self, inputs: dict) -> dict:
            question = inputs.get("query") or inputs.get("question", "")
            prompt_val = self._prompt.format(schema=self._schema, question=question)
            gsql_raw = self._llm.invoke(prompt_val)
            gsql_text = gsql_raw.content if hasattr(gsql_raw, "content") else str(gsql_raw)
            rows = self._run_query(gsql_text)
            context = str(rows) if rows else "No results found."
            qa_prompt = (
                f"Given the following graph query results:\n{context}\n\n"
                f"Answer this question in a concise sentence: {question}"
            )
            answer_raw = self._llm.invoke(qa_prompt)
            answer = answer_raw.content if hasattr(answer_raw, "content") else str(answer_raw)
            return {"result": answer, "intermediate_steps": [{"query": gsql_text, "context": context}]}

        def __call__(self, inputs: dict) -> dict:
            return self.invoke(inputs)

    if _tg_conn is not None:
        chain = _TGGSQLChain(
            llm=common["llm"],
            conn=_tg_conn,
            graphname=_tg_graphname,
            schema=_tg_schema_str,
            prompt=_tg_prompt,
        )
        _logger.info("TigerGraph GSQL QA chain created (interpreted-query mode)")
        return chain  # type: ignore[return-value]

    # Fallback when conn not available
    _logger.warning("TigerGraph conn not available; falling back to cypher_generic")
    from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
    return GraphCypherQAChain.from_llm(**common)
