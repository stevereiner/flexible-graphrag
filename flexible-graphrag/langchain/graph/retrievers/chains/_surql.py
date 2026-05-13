"""SurrealQL chain builder — SurrealDB."""

import logging
from typing import Any

_logger = logging.getLogger(__name__)


def build_surql_surrealdb(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """SurrealDB graph QA chain using SurrealQL."""
    from langchain_surrealdb.experimental.graph_qa.chain import SurrealDBGraphQAChain
    from langchain_core.prompts import PromptTemplate

    _SURQL_GEN_TEMPLATE = """\
Task: Generate a SurrealDB (SurrealQL) graph query from a User Input.

You are a SurrealDB expert.  Translate the User Input into a single SELECT query.

Graph Schema (JSON):
{surql_schema}

CRITICAL RULES — follow every rule or the query will return no results:
1. NEVER use exact equality for names: do NOT write `WHERE name = "acme"`.
2. ALWAYS use partial, case-insensitive matching:
       WHERE string::lowercase(name) CONTAINS "keyword"
   Use only lowercase in the keyword string.
3. ALWAYS wrap every traversal result in array::distinct() to remove duplicates:
       SELECT array::distinct(<-relation_EDGE_NAME<-graph_NodeType) AS alias
4. Incoming edge traversal (who/what points TO the node):
       SELECT array::distinct(<-relation_EDGE_NAME<-graph_NodeType) AS alias
       FROM graph_SourceType WHERE string::lowercase(name) CONTAINS "keyword";
5. Outgoing edge traversal (what the node points TO):
       SELECT array::distinct(->relation_EDGE_NAME->graph_NodeType) AS alias
       FROM graph_SourceType WHERE string::lowercase(name) CONTAINS "keyword";
6. Fetch all related nodes (unknown direction):
       SELECT array::distinct(<->relation_EDGE_NAME<->graph_NodeType) AS alias
       FROM graph_SourceType WHERE string::lowercase(name) CONTAINS "keyword";
7. Generate ONLY the SELECT query — no explanation, no markdown fences.
8. Do NOT generate any DELETE or UPDATE statements.

{surql_examples}

Examples:

Q: Who works for Acme?
A: SELECT array::distinct(<-relation_WORKS_FOR<-graph_Person) AS workers
   FROM graph_Company WHERE string::lowercase(name) CONTAINS "acme";

Q: What departments does Acme have?
A: SELECT array::distinct(->relation_HAS_DEPARTMENT->graph_Department) AS departments
   FROM graph_Company WHERE string::lowercase(name) CONTAINS "acme";

Q: What projects is Alice working on?
A: SELECT array::distinct(->relation_ASSIGNED_TO->graph_Project) AS projects
   FROM graph_Person WHERE string::lowercase(name) CONTAINS "alice";

Q: Who leads the Engineering department?
A: SELECT array::distinct(<-relation_LED_BY<-graph_Person) AS leaders
   FROM graph_Department WHERE string::lowercase(name) CONTAINS "engineering";

Q: What offices or locations does Acme have?
A: SELECT array::distinct(->relation_HAS_LOCATION->graph_Location) AS locations
   FROM graph_Company WHERE string::lowercase(name) CONTAINS "acme";

Q: Who works in the Engineering department?
A: SELECT array::distinct(<-relation_WORKS_IN_DEPARTMENT<-graph_Person) AS staff
   FROM graph_Department WHERE string::lowercase(name) CONTAINS "engineering";

User Input:
{user_input}

SurrealDB Query:"""

    _surql_gen_prompt = PromptTemplate(
        input_variables=["surql_schema", "surql_examples", "user_input"],
        template=_SURQL_GEN_TEMPLATE,
    )

    # SurrealDBGraphQAChain does not accept allow_dangerous_requests — omit it.
    return SurrealDBGraphQAChain.from_llm(
        llm=llm,
        graph=graph,
        surql_generation_prompt=_surql_gen_prompt,
        verbose=False,
        return_intermediate_steps=include_intermediate,
    )
