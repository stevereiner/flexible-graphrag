"""
langchain.graph.retrievers.lc_graph_retriever
=============================================

Pure LangChain BaseRetriever wrapping any graph QA chain.

LCGraphQARetriever
    Layer-0 LC retriever: invokes the chain, suppresses no-data answers,
    and converts intermediate steps into additional context Documents.
    Returns ``List[Document]`` — no LlamaIndex dependency.

    Use ``LCGraphQARetriever.from_graph(graph, llm, ...)`` to auto-detect
    the right chain from the graph class name via ``_GRAPH_CHAIN_MAP``.

See ``li_graph_query_retriever.py`` for the LlamaIndex wrapper (Layer 1).
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar, List, Optional, Self, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph class -> chain_key dispatch table
# ---------------------------------------------------------------------------

_GRAPH_CHAIN_MAP = [
    # ---- RDF / SPARQL -------------------------------------------------------
    ("NeptuneRdf",       "sparql_neptune"),
    ("OntotextGraphDB",  "sparql_graphdb"),
    ("_HttpSparql",      "sparql_generic"),
    ("RdfGraph",         "sparql_generic"),
    ("RDF",              "sparql_generic"),
    ("Rdf",              "sparql_generic"),
    # ---- Neptune property graph (OpenCypher) --------------------------------
    ("NeptuneAnalytics", "opencypher_neptune"),
    ("Neptune",          "opencypher_neptune"),
    # ---- ArcadeDB -----------------------------------------------------------
    ("ArcadeDB",         "cypher_arcadedb"),
    # ---- Cypher property graphs ---------------------------------------------
    ("Neo4j",            "cypher_neo4j"),
    ("Memgraph",         "cypher_memgraph"),
    ("FalkorDB",         "cypher_falkordb"),
    ("AGE",              "cypher_age"),
    ("Tiger",            "gsql_tigergraph"),
    ("Spanner",          "cypher_generic"),
    ("HugeGraph",        "cypher_hugegraph"),
    # ---- Generic Gremlin ----------------------------------------------------
    ("Gremlin",          "gremlin_generic"),
    ("CosmosDB",         "gremlin_generic"),
    # ---- AQL (ArangoDB) -----------------------------------------------------
    ("Arango",           "aql_arangodb"),
    # ---- SurrealQL ----------------------------------------------------------
    ("SurrealDB",        "surql_surrealdb"),
    # ---- NebulaGraph --------------------------------------------------------
    ("Nebula",           "cypher_nebula"),
    # ---- LadybugDB (embedded, Kùzu-based) -----------------------------------
    ("Ladybug",          "cypher_ladybug"),
]


def _resolve_chain_key(graph: Any) -> str:
    """Return the chain_key for *graph* by matching its class name against
    ``_GRAPH_CHAIN_MAP``.  Falls back to MRO walk.  Raises ``ValueError``
    if no match is found.
    """
    name = type(graph).__name__
    for substr, key in _GRAPH_CHAIN_MAP:
        if substr in name:
            return key
    for cls in type(graph).__mro__:
        for substr, key in _GRAPH_CHAIN_MAP:
            if substr in cls.__name__:
                logger.debug(
                    "Matched graph class '%s' via MRO class '%s' -> '%s'",
                    name, cls.__name__, key,
                )
                return key
    raise ValueError(
        f"No QA chain mapping found for graph class '{name}'. "
        "Pass qa_chain_factory= to override."
    )


def _build_qa_chain(graph: Any, llm: Any, include_intermediate: bool = True, config: Any = None) -> Any:
    """Build the correct LangChain QA chain for *graph*.

    ``config`` (AppSettings or any object) is forwarded inside ``common`` so
    individual chain builders can read namespace / store configuration without
    hardcoding defaults.  Pass ``None`` to use builder defaults.
    """
    chain_key = _resolve_chain_key(graph)
    logger.info("Building QA chain '%s' for graph class '%s'", chain_key, type(graph).__name__)
    common = dict(
        llm=llm,
        graph=graph,
        verbose=False,
        return_intermediate_steps=include_intermediate,
        allow_dangerous_requests=True,
        config=config,
    )
    from .chains import CHAIN_BUILDERS
    if chain_key in CHAIN_BUILDERS:
        return CHAIN_BUILDERS[chain_key](graph, llm, include_intermediate, common)
    raise ValueError(f"Unhandled chain_key '{chain_key}' for '{type(graph).__name__}'")


# ---------------------------------------------------------------------------
# Shared utilities (query language detection, result formatting)
# ---------------------------------------------------------------------------

def detect_query_type(query: Any) -> str:
    """Detect the query language from a generated query string."""
    if not query:
        return "unknown"
    if hasattr(query, "content"):
        query = str(query.content)
    if not isinstance(query, str):
        query = str(query)
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


def _format_step(step: Any) -> tuple:
    """Format a graph QA chain intermediate step as readable entity text.

    Returns ``(text, extra_files)`` where *extra_files* is a list of any
    ``file_name`` values found in the context rows.
    """
    if isinstance(step, str):
        return step, []

    if isinstance(step, dict):
        if "context" in step:
            body, files = _extract_entities_from_context(step["context"])
            return (f"Graph results: {body}", files) if body else ("", files)
        context_val = step.get("context") or step.get("result") or step.get("output")
        if context_val is not None:
            body, files = _extract_entities_from_context(context_val)
            return (f"Graph results: {body}", files) if body else ("", files)
        lines = []
        for k, val in step.items():
            if k in ("query", "generated_cypher", "generated_sparql", "aql_query"):
                continue
            lines.append(
                f"{k}: {', '.join(str(v) for v in val) if isinstance(val, (list, tuple)) else val}"
            )
        body = "\n".join(lines)
        return (f"Graph results: {body}", []) if body else ("", [])

    if isinstance(step, (list, tuple)):
        body, files = _extract_entities_from_context(step)
        return (f"Graph results: {body}", files) if body else ("", files)

    return str(step), []


def _extract_entities_from_context(context: Any) -> tuple:
    """Convert raw graph query results into readable 'Name (type)' lines.

    Returns ``(text, file_names)``.
    """
    import ast, json as _json

    if isinstance(context, str):
        ctx = context.strip()
        if ctx in ("", "No results found."):
            return "", []
        try:
            context = ast.literal_eval(ctx)
        except Exception:
            try:
                context = _json.loads(ctx)
            except Exception:
                return ctx, []

    lines: list = []
    files: list = []

    def _vertex_line(v: dict) -> str:
        attrs = v.get("attributes") or v
        name  = attrs.get("name") or attrs.get("id") or v.get("v_id", "")
        ntype = attrs.get("node_type") or attrs.get("type") or attrs.get("label", "")
        fn = attrs.get("file_name") or v.get("file_name", "")
        if fn and fn not in files:
            files.append(fn)
        if name and ntype:
            return f"{name} ({ntype})"
        return name or str(v)

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            fn = obj.get("file_name", "")
            if fn and fn not in files:
                files.append(fn)
            if "v_id" in obj or "v_type" in obj:
                line = _vertex_line(obj)
                if line:
                    lines.append(line)
                return
            if "name" in obj or "id" in obj:
                line = _vertex_line(obj)
                if line:
                    lines.append(line)
                return
            for val in obj.values():
                _walk(val)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)

    _walk(context)
    text = "\n".join(lines) if lines else str(context)[:400]
    return text, files


# ---------------------------------------------------------------------------
# LCGraphQARetriever — Layer 0 pure LC retriever
# ---------------------------------------------------------------------------

try:
    from langchain_core.retrievers import BaseRetriever as _LCBase
    from langchain_core.documents import Document as _LCDoc
    from langchain_core.callbacks.manager import (
        CallbackManagerForRetrieverRun,
        AsyncCallbackManagerForRetrieverRun,
    )
    from pydantic import ConfigDict

    class LCGraphQARetriever(_LCBase):  # pyright: ignore[reportRedeclaration]
        """Pure LC BaseRetriever wrapping any LangChain graph QA chain.

        Invokes the chain, suppresses no-data answers, and surfaces
        intermediate steps as additional context Documents.

        Use ``from_graph(graph, llm, ...)`` to auto-detect the chain type.
        Chain logic (prompts, schema cleaning, query sanitizers) lives in
        ``chains/_cypher.py``, ``chains/_sparql.py``, etc.
        """

        model_config = ConfigDict(arbitrary_types_allowed=True)

        # Phrases that indicate the chain found no relevant data
        _NO_RESULT_PHRASES: ClassVar[Tuple[str, ...]] = (
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
            "the information provided does not",
            "the provided information does not",
            "the context does not",
            "the data does not",
            "based on the information provided, i cannot",
            "based on the provided information, i cannot",
            "i'm sorry, but i don't",
            "i'm sorry, but i do not",
            "i'm sorry, i don't",
            "i'm sorry, i do not",
            "i am sorry, but i don't",
            "i am sorry, but i do not",
        )
        _NO_RESULT_CONTAINS: ClassVar[Tuple[str, ...]] = (
            "unable to determine",
            "unable to specify",
            "cannot be determined",
            "does not specify who",
            "does not mention who",
            "does not contain information",
            "no relevant information",
            "not mentioned in the",
            "not specified in the",
        )

        def __init__(
            self,
            chain: Any,
            graph: Any,
            top_k: int = 5,
            include_intermediate: bool = True,
            source_files: Optional[List[str]] = None,
        ):
            super().__init__()
            self._chain = chain
            self._graph = graph
            self._top_k = top_k
            self._include_intermediate = include_intermediate
            self._source_files: List[str] = [f for f in (source_files or []) if f]

        @classmethod
        def from_graph(
            cls,
            graph: Any,
            llm: Any,
            top_k: int = 5,
            include_intermediate_steps: bool = True,
            source_files: Optional[List[str]] = None,
            config: Any = None,
        ) -> "Self":
            """Factory: auto-detect chain type and return an LCGraphQARetriever.

            ``config`` (AppSettings) is forwarded to chain builders so they can
            read namespace and store settings from the application config.
            """
            chain = _build_qa_chain(graph, llm, include_intermediate_steps, config=config)
            return cls(
                chain=chain,
                graph=graph,
                top_k=top_k,
                include_intermediate=include_intermediate_steps,
                source_files=source_files,
            )

        @classmethod
        def _is_no_result_answer(cls, text: str) -> bool:
            t = text.strip().lower()
            if any(t.startswith(p) for p in cls._NO_RESULT_PHRASES):
                return True
            return any(p in t for p in cls._NO_RESULT_CONTAINS)

        def _result_to_docs(self, result: dict, query: str) -> List[_LCDoc]:
            """Convert a chain result dict to a list of LC Documents."""
            answer = result.get("result", "")
            if hasattr(answer, "content"):
                answer = answer.content
            if not isinstance(answer, str):
                answer = str(answer) if answer else ""

            # If the AQL/graph query returned no data, suppress the LLM answer even
            # if the LLM hallucinated a response mentioning entity names from the query.
            # aql_result is present when return_aql_result=True (ArangoDB chain).
            aql_result = result.get("aql_result")
            if aql_result is not None and not aql_result:
                logger.info(
                    "Graph QA (AQL): empty result set — suppressing LLM answer to "
                    "prevent hallucination about deleted/absent entities."
                )
                return []

            generated_query = (
                result.get("generated_sparql")
                or result.get("generated_cypher")
                or result.get("aql_query")
                or result.get("generated_query", "")
            )
            if hasattr(generated_query, "content"):
                generated_query = str(generated_query.content)
            elif not isinstance(generated_query, str):
                generated_query = str(generated_query) if generated_query else ""

            intermediate_steps = result.get("intermediate_steps", [])
            if not generated_query and intermediate_steps:
                for step in intermediate_steps:
                    if isinstance(step, dict) and "query" in step:
                        generated_query = step["query"]
                        break

            if generated_query:
                logger.debug(
                    "Generated %s query:\n%s",
                    detect_query_type(generated_query),
                    generated_query[:500],
                )

            no_data = not answer or not answer.strip() or self._is_no_result_answer(answer)
            docs: List[_LCDoc] = []

            if answer and answer.strip():
                if no_data:
                    logger.info(
                        "Graph QA returned a no-data answer -- suppressing node. Answer: %s",
                        answer[:200],
                    )
                else:
                    docs.append(_LCDoc(
                        page_content=answer,
                        metadata={
                            "source": "langchain_graph_qa",
                            "graph_type": type(self._graph).__name__,
                            "generated_query": generated_query,
                            "query_type": detect_query_type(generated_query),
                            "original_query": query,
                            "source_files": self._source_files,
                        },
                    ))

            if not no_data and self._include_intermediate and intermediate_steps:
                for idx, step in enumerate(intermediate_steps[: self._top_k - 1]):
                    text, extra_files = _format_step(step)
                    if text and not self._is_no_result_answer(text):
                        merged_files = list(dict.fromkeys(
                            self._source_files
                            + [f for f in extra_files if f not in self._source_files]
                        ))
                        docs.append(_LCDoc(
                            page_content=text,
                            metadata={
                                "source": "langchain_graph_intermediate",
                                "step_index": idx,
                                "graph_type": type(self._graph).__name__,
                                "source_files": merged_files,
                                "_intermediate_score": max(0.8 - idx * 0.1, 0.3),
                            },
                        ))

            return docs[: self._top_k]

        def _graph_is_empty(self) -> bool:
            """Return True when the graph schema is trivially empty.

            An empty Neo4j / property-graph schema looks like
            ``"Node properties:\n\nRelationship properties:\n\nThe relationships:\n"``
            (~60 chars, no actual node labels).  Calling the LLM chain against an
            empty graph wastes a full LLM round-trip (200+ s for slow providers)
            and always returns a no-data answer anyway.
            """
            schema: str = getattr(self._chain, "graph_schema", "") or ""
            if not schema:
                return True
            # Heuristic: meaningful schemas have at least one label in the node
            # properties section.  An empty one has only the section headers.
            _EMPTY_MARKERS = ("node properties:\n\nrelationship", "node properties: none")
            return any(m in schema.lower() for m in _EMPTY_MARKERS)

        def _get_relevant_documents(
            self,
            query: str,
            *,
            run_manager: CallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            if self._graph_is_empty():
                logger.debug("LCGraphQARetriever: graph schema is empty — skipping LLM chain call")
                return []
            try:
                result = self._chain.invoke({"query": query})
                return self._result_to_docs(result, query)
            except Exception as exc:
                logger.error("LCGraphQARetriever error: %s", exc, exc_info=True)
                return []

        async def _aget_relevant_documents(
            self,
            query: str,
            *,
            run_manager: AsyncCallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            if self._graph_is_empty():
                logger.debug("LCGraphQARetriever: graph schema is empty — skipping LLM chain call")
                return []
            try:
                result = await self._chain.ainvoke({"query": query})
                return self._result_to_docs(result, query)
            except Exception as exc:
                logger.error("LCGraphQARetriever async error: %s", exc, exc_info=True)
                return []

except ImportError as _lc_import_err:
    class LCGraphQARetriever:  # type: ignore[no-redef]  # pyright: ignore[reportRedeclaration]
        """Stub when langchain_core is not installed."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                f"langchain_core is required for LCGraphQARetriever: {_lc_import_err}"
            )


__all__ = [
    "LCGraphQARetriever",
    "_GRAPH_CHAIN_MAP",
    "_resolve_chain_key",
    "_build_qa_chain",
    "detect_query_type",
    "_format_step",
    "_extract_entities_from_context",
]
