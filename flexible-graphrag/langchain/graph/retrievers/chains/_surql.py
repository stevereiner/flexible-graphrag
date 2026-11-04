"""SurrealQL chain builder — SurrealDB."""

import asyncio
import logging
from typing import Any

from ..query_guard import refuse_writes

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LangChain-backend SurrealDB QA chain (per-type schema)
# ---------------------------------------------------------------------------

class _LCSurrealDBChain:
    """Self-contained QA chain for the LangChain SurrealDBAdapter per-type schema.

    LangChain ``SurrealDBAdapter`` / ``SurrealDBGraph`` writes:
    - ``graph_{Type}`` tables (e.g. ``graph_Company``, ``graph_Person``)
      — each record has ``name``, ``type``, and entity properties
    - ``relation_{PREDICATE}`` edge tables (uppercase), e.g. ``relation_WORKS_FOR``
      — each edge links two ``graph_*`` records

    This chain uses the existing ``SurrealDBGraph.connection`` (already
    authenticated) to avoid re-connecting and bypasses ``langchain_surrealdb``'s
    ``SurrealDBGraphQAChain``, which has a fragile custom prompt API.
    """

    output_key = "result"

    def __init__(self, graph: Any, llm: Any, include_intermediate: bool = False) -> None:
        self._graph = graph
        self._llm = llm
        self._include_intermediate = include_intermediate
        self._schema_str = self._build_schema_str()

    @property
    def graph_schema(self) -> str:
        """Expose schema so LCGraphQARetriever._graph_is_empty() treats us as non-empty."""
        return self._schema_str

    # ------------------------------------------------------------------
    # Low-level DB helper — reuse existing SurrealDBGraph.connection
    # ------------------------------------------------------------------

    def _safe_query(self, surql: str) -> list:
        try:
            result = self._graph.query(surql)
            if isinstance(result, list):
                return result
            return [result] if result is not None else []
        except Exception as exc:  # noqa: BLE001
            _logger.debug("LCSurrealDB query error: %s | SurrealQL: %s", exc, surql)
            return []

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    def _build_schema_str(self) -> str:
        """Introspect per-type tables and relation tables from the live DB."""
        node_tables: list[str] = []
        rel_tables: list[str] = []
        try:
            info = self._safe_query("INFO FOR DB")
            if info and isinstance(info[0], dict):
                tables = info[0].get("tables", {})
                for t in tables:
                    ts = str(t)
                    if ts.startswith("graph_"):
                        node_tables.append(ts)
                    elif ts.startswith("relation_"):
                        rel_tables.append(ts)
        except Exception:  # noqa: BLE001
            pass

        parts = [
            "LangChain SurrealDB schema (per-type tables):",
        ]
        if node_tables:
            parts.append(f"Node tables: {', '.join(sorted(node_tables))}")
            parts.append("Each node table has: name (string), type (string), [entity properties]")
        else:
            parts.append(
                "Node tables: graph_COMPANY, graph_PERSON, graph_DEPARTMENT, graph_LOCATION, "
                "graph_PROJECT, graph_EVENT, graph_PRODUCT "
                "(examples — CASE-SENSITIVE, actual names from DB may differ)"
            )
            parts.append("Each node table has: name (string), type (string), [entity properties]")
        if rel_tables:
            parts.append(f"Relation tables: {', '.join(sorted(rel_tables))}")
        else:
            parts.append(
                "Relation tables: relation_WORKS_FOR, relation_HAS_DEPARTMENT, "
                "relation_HAS_LOCATION, relation_ASSIGNED_TO, relation_PART_OF (examples)"
            )
        parts.append(
            "Relation tables link two graph_* records: "
            "<-relation_PREDICATE<- (incoming) or ->relation_PREDICATE-> (outgoing)"
        )
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Query generation + answering
    # ------------------------------------------------------------------

    _SURQL_GEN_TEMPLATE = """\
You are a SurrealDB expert querying a LangChain knowledge-graph.

Schema:
{schema}

CRITICAL RULES — follow every rule or the query will return no results:
1. TABLE NAMES ARE CASE-SENSITIVE. Copy node and relation table names EXACTLY as they
   appear in the Schema above — do NOT change capitalisation.
   If the schema says "graph_COMPANY", write "graph_COMPANY", NOT "graph_Company".
2. Node tables are per-type: graph_COMPANY, graph_PERSON, graph_DEPARTMENT, etc.
   There is NO single 'graph_entity' table — use the specific type table from the schema.
3. Relation table names are UPPERCASE predicates: relation_WORKS_FOR, relation_HAS_DEPARTMENT.
4. ALWAYS use partial, case-insensitive matching on name:
       WHERE string::lowercase(name) CONTAINS "keyword"
   Use only lowercase in the keyword string. NEVER use exact = equality on names.
5. Use array::distinct() on every traversal to remove duplicates.
6. Incoming edge (who points TO entity): <-relation_WORKS_FOR<-graph_PERSON
   Outgoing edge (entity points TO what): ->relation_HAS_DEPARTMENT->graph_DEPARTMENT
7. Return ONLY the SELECT query — no explanation, no markdown fences.
8. DO NOT generate DELETE or UPDATE statements.

Examples (node/relation names here match typical UPPERCASE output — always verify against Schema):

Q: Who works for Acme?
A: SELECT array::distinct(<-relation_WORKS_FOR<-graph_PERSON) AS workers
   FROM graph_COMPANY WHERE string::lowercase(name) CONTAINS "acme";

Q: What departments does Acme have?
A: SELECT array::distinct(->relation_HAS_DEPARTMENT->graph_DEPARTMENT) AS departments
   FROM graph_COMPANY WHERE string::lowercase(name) CONTAINS "acme";

Q: What locations or offices does Acme have?
A: SELECT array::distinct(->relation_HAS_LOCATION->graph_LOCATION) AS locations
   FROM graph_COMPANY WHERE string::lowercase(name) CONTAINS "acme";

Q: How is Acme organized?
A: SELECT
     array::distinct(->relation_HAS_DEPARTMENT->graph_DEPARTMENT) AS departments,
     array::distinct(<-relation_WORKS_FOR<-graph_PERSON) AS employees
   FROM graph_COMPANY WHERE string::lowercase(name) CONTAINS "acme";

Q: Who works in Engineering?
A: SELECT array::distinct(<-relation_WORKS_IN_DEPARTMENT<-graph_PERSON) AS staff
   FROM graph_DEPARTMENT WHERE string::lowercase(name) CONTAINS "engineering";

Q: Who supported CMIS?
A: SELECT array::distinct(<-relation_SUPPORTS<-graph_ORGANIZATION) AS supporters
   FROM graph_STANDARD WHERE string::lowercase(name) CONTAINS "cmis";

User question: {question}

SurrealQL query:"""

    _QA_TEMPLATE = """\
Use the following graph query results to answer the question.
If the results do not contain sufficient information, say you don't know.

Context:
{context}

Question: {question}
Answer:"""

    def _generate_surql(self, question: str) -> str:
        from langchain_core.prompts import PromptTemplate  # noqa: PLC0415
        prompt = PromptTemplate(
            input_variables=["schema", "question"],
            template=self._SURQL_GEN_TEMPLATE,
        )
        chain = prompt | self._llm
        try:
            resp = chain.invoke({"schema": self._schema_str, "question": question})
            raw = resp.content if hasattr(resp, "content") else str(resp)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0]
            return raw.strip()
        except Exception as exc:  # noqa: BLE001
            _logger.debug("LCSurrealDB SurrealQL generation error: %s", exc)
            kw = question[:20].lower().replace('"', "")
            return (
                f"SELECT * FROM type::any "
                f"WHERE string::lowercase(name) CONTAINS \"{kw}\" LIMIT 10"
            )

    def _format_context(self, results: list) -> str:
        parts: list[str] = []
        for row in results[:20]:
            if not isinstance(row, dict):
                continue
            for k, v in row.items():
                if v is None:
                    continue
                if isinstance(v, list):
                    names = []
                    for item in v[:20]:
                        if isinstance(item, dict):
                            names.append(item.get("name") or item.get("id") or str(item))
                        else:
                            names.append(str(item))
                    if names:
                        parts.append(f"{k}: {', '.join(names)}")
                elif isinstance(v, dict):
                    parts.append(f"{k}: {v.get('name') or v.get('id') or str(v)}")
                else:
                    parts.append(f"{k}: {v}")
        return "\n".join(parts)

    def _generate_answer(self, question: str, context: str) -> str:
        if not context or not context.strip():
            return ""
        from langchain_core.prompts import PromptTemplate  # noqa: PLC0415
        prompt = PromptTemplate(
            input_variables=["context", "question"],
            template=self._QA_TEMPLATE,
        )
        chain = prompt | self._llm
        try:
            resp = chain.invoke({"context": context, "question": question})
            return resp.content if hasattr(resp, "content") else str(resp)
        except Exception as exc:  # noqa: BLE001
            _logger.debug("LCSurrealDB answer generation error: %s", exc)
            return context

    # ------------------------------------------------------------------
    # Public chain interface
    # ------------------------------------------------------------------

    def invoke(self, inputs: Any) -> dict:
        if isinstance(inputs, dict):
            question = (
                inputs.get("query") or inputs.get("question") or
                inputs.get("input") or str(inputs)
            )
        else:
            question = str(inputs)
        surql = self._generate_surql(question)
        _logger.debug("LCSurrealDB generated SurrealQL: %s", surql)
        refuse_writes(surql, "surql")
        results = self._safe_query(surql)
        context = self._format_context(results)
        answer = self._generate_answer(question, context)
        out: dict = {
            self.output_key: answer,
            "generated_surql": surql,
            # "generated_query" is what LCGraphQARetriever._result_to_docs() looks for
            "generated_query": surql,
        }
        if self._include_intermediate:
            out["intermediate_steps"] = [{"surql": surql, "results": results, "context": context}]
        return out

    async def ainvoke(self, inputs: Any) -> dict:
        return await asyncio.to_thread(self.invoke, inputs)


def build_surql_surrealdb(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """SurrealDB graph QA chain using SurrealQL (LangChain per-type schema).

    Primary: ``SurrealDBGraphQAChain`` from ``langchain_surrealdb`` with a custom
    prompt tuned for the per-type schema written by ``SurrealDBAdapter``.
    The prompt uses exactly the three variables the chain passes internally:
    ``{surql_schema}``, ``{surql_examples}``, ``{user_input}``.

    Fallback: ``_LCSurrealDBChain`` — our own self-contained chain that reuses the
    ``SurrealDBGraph.query()`` connection directly, used when ``langchain_surrealdb``
    is not installed or fails to construct.

    Note: ``_graph_is_empty()`` in ``LCGraphQARetriever`` must return ``False`` for
    ``SurrealDBGraphQAChain`` (which has no ``graph_schema`` attribute) so the LLM
    is actually invoked.  That fix lives in ``lc_graph_retriever.py``.
    """
    try:
        from langchain_surrealdb.experimental.graph_qa.chain import SurrealDBGraphQAChain  # noqa: PLC0415
        from langchain_core.prompts import PromptTemplate  # noqa: PLC0415

        _SURQL_GEN_TEMPLATE = """\
Task: Generate a SurrealDB (SurrealQL) query from a User Input.

You are a SurrealDB expert.  Translate the User Input into a single SELECT query.

Graph Schema:
{surql_schema}

CRITICAL RULES — follow every rule or the query will return no results:
1. TABLE NAMES ARE CASE-SENSITIVE. Copy node and relation table names EXACTLY as they appear
   in the Graph Schema above — do NOT change capitalisation.
   If the schema lists "graph_COMPANY", write "graph_COMPANY", NOT "graph_Company".
   If the schema lists "graph_PERSON", write "graph_PERSON", NOT "graph_Person".
2. NEVER use exact equality for names: do NOT write `WHERE name = "acme"`.
3. ALWAYS use partial, case-insensitive matching:
       WHERE string::lowercase(name) CONTAINS "keyword"
   Use only lowercase in the keyword string.
4. ALWAYS wrap every traversal result in array::distinct() to remove duplicates:
       SELECT array::distinct(<-relation_EDGE_NAME<-graph_NODETYPE) AS alias
5. Incoming edge traversal (who/what points TO the node):
       SELECT array::distinct(<-relation_EDGE_NAME<-graph_NODETYPE) AS alias
       FROM graph_SOURCETYPE WHERE string::lowercase(name) CONTAINS "keyword";
6. Outgoing edge traversal (what the node points TO):
       SELECT array::distinct(->relation_EDGE_NAME->graph_NODETYPE) AS alias
       FROM graph_SOURCETYPE WHERE string::lowercase(name) CONTAINS "keyword";
7. Generate ONLY the SELECT query — no explanation, no markdown fences.
8. Do NOT generate any DELETE or UPDATE statements.

{surql_examples}

Examples (node/relation names here are illustrative — always use the EXACT names from the Schema):

Q: Who works for Acme?
A: SELECT array::distinct(<-relation_WORKS_FOR<-graph_PERSON) AS workers
   FROM graph_COMPANY WHERE string::lowercase(name) CONTAINS "acme";

Q: What departments does Acme have?
A: SELECT array::distinct(->relation_HAS_DEPARTMENT->graph_DEPARTMENT) AS departments
   FROM graph_COMPANY WHERE string::lowercase(name) CONTAINS "acme";

Q: What projects is Alice working on?
A: SELECT array::distinct(->relation_ASSIGNED_TO->graph_PROJECT) AS projects
   FROM graph_PERSON WHERE string::lowercase(name) CONTAINS "alice";

Q: What offices or locations does Acme have?
A: SELECT array::distinct(->relation_HAS_LOCATION->graph_LOCATION) AS locations
   FROM graph_COMPANY WHERE string::lowercase(name) CONTAINS "acme";

Q: Who works in the Engineering department?
A: SELECT array::distinct(<-relation_WORKS_IN_DEPARTMENT<-graph_PERSON) AS staff
   FROM graph_DEPARTMENT WHERE string::lowercase(name) CONTAINS "engineering";

Q: How is Acme organized?
A: SELECT
     array::distinct(->relation_HAS_DEPARTMENT->graph_DEPARTMENT) AS departments,
     array::distinct(<-relation_WORKS_FOR<-graph_PERSON) AS employees
   FROM graph_COMPANY WHERE string::lowercase(name) CONTAINS "acme";

User Input:
{user_input}

SurrealDB Query:"""

        _surql_gen_prompt = PromptTemplate(
            input_variables=["surql_schema", "surql_examples", "user_input"],
            template=_SURQL_GEN_TEMPLATE,
        )
        return SurrealDBGraphQAChain.from_llm(
            llm=llm,
            graph=graph,
            surql_generation_prompt=_surql_gen_prompt,
            verbose=False,
            return_intermediate_steps=include_intermediate,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "SurrealDBGraphQAChain unavailable (%s) — falling back to direct SurrealQL chain",
            exc,
        )
        return _LCSurrealDBChain(graph=graph, llm=llm, include_intermediate=include_intermediate)
