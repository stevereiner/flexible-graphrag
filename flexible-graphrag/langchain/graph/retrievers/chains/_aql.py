"""AQL chain builder — ArangoDB."""

import logging
from typing import Any

_logger = logging.getLogger(__name__)


def build_aql_arangodb(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """ArangoDB AQL QA chain (langchain_arangodb)."""
    from langchain_arangodb import ArangoGraphQAChain
    from langchain_arangodb.chains.graph_qa.prompts import (
        AQL_GENERATION_PROMPT, AQL_QA_PROMPT,
    )

    # Extend the default QA summary prompt to always respond in English.
    try:
        from langchain_core.prompts import PromptTemplate
        _AQL_QA_TEMPLATE = AQL_QA_PROMPT.template.replace(
            "Your `Summary` should be in the same language as the `User Input`.",
            "Your `Summary` should always be in English.",
        )
        qa_prompt = PromptTemplate(
            input_variables=["adb_schema", "user_input", "aql_query", "aql_result"],
            template=_AQL_QA_TEMPLATE,
        )
    except Exception:
        qa_prompt = None

    # AQL examples showing INBOUND direction for person->org relationships.
    # Use CONTAINS(LOWER(...)) so partial names like 'acme' match 'Acme Corporation'.
    _AQL_EXAMPLES = (
        "Q: Who works for Acme Corporation?\n"
        "A: ```\n"
        "WITH knowledge_graph_ENTITY, knowledge_graph_LINKS_TO\n"
        "LET org = FIRST(FOR e IN knowledge_graph_ENTITY FILTER CONTAINS(LOWER(e.text), LOWER('Acme Corporation')) RETURN e)\n"
        "FOR v, e IN 1..1 INBOUND org knowledge_graph_LINKS_TO\n"
        "  FILTER e.type == 'WORKS_FOR'\n"
        "  RETURN v.text\n"
        "```\n\n"
        "Q: Who works for acme?\n"
        "A: ```\n"
        "WITH knowledge_graph_ENTITY, knowledge_graph_LINKS_TO\n"
        "LET org = FIRST(FOR e IN knowledge_graph_ENTITY FILTER CONTAINS(LOWER(e.text), LOWER('acme')) RETURN e)\n"
        "FOR v, e IN 1..1 INBOUND org knowledge_graph_LINKS_TO\n"
        "  FILTER e.type == 'WORKS_FOR'\n"
        "  RETURN v.text\n"
        "```\n\n"
        "Q: What departments does Acme Corporation have?\n"
        "A: ```\n"
        "WITH knowledge_graph_ENTITY, knowledge_graph_LINKS_TO\n"
        "LET org = FIRST(FOR e IN knowledge_graph_ENTITY FILTER CONTAINS(LOWER(e.text), LOWER('Acme Corporation')) RETURN e)\n"
        "FOR v, e IN 1..1 OUTBOUND org knowledge_graph_LINKS_TO\n"
        "  FILTER e.type == 'HAS_DEPARTMENT'\n"
        "  RETURN v.text\n"
        "```"
    )

    chain_kwargs = {**common}
    if qa_prompt:
        chain_kwargs["qa_prompt"] = qa_prompt
    return ArangoGraphQAChain.from_llm(
        aql_generation_prompt=AQL_GENERATION_PROMPT,
        aql_examples=_AQL_EXAMPLES,
        return_aql_query=True,
        return_aql_result=True,
        **chain_kwargs,
    )
