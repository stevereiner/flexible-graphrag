"""Gremlin chain builder — GremlinGraph, CosmosDBGremlinGraph (Azure Cosmos DB for Gremlin)."""

import logging
from typing import Any

_logger = logging.getLogger(__name__)


def build_gremlin_generic(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """Generic Gremlin traversal QA chain.

    CRITICAL — Azure Cosmos DB for Gremlin does NOT support Groovy closures.
    Queries using filter{it.get()...} or any {...} closure syntax will be
    rejected with "Unsupported groovy language rule: closure".

    Use ONLY pure Gremlin bytecode steps:
    - Partial/case-insensitive match: has('id', TextP.containing('term'))
      (Cosmos DB supports TinkerPop TextP predicates)
    - Exact match:                    has('id', 'ExactName')
    - Filter by vertex type:          hasLabel('Person')
    """
    from langchain_community.chains.graph_qa.gremlin import GremlinQAChain
    from langchain_core.prompts import PromptTemplate

    # IMPORTANT: ALL examples must use TextP.containing() for partial matching.
    # Groovy closures (filter{it.get().value('id').contains(...)}) are NOT supported
    # by Azure Cosmos DB for Gremlin — they cause a GraphSyntaxException (code 597).
    _GREMLIN_EXAMPLES = (
        "Q: Who works for Acme Corporation?\n"
        "A: g.V().has('id', TextP.containing('Acme')).in('WORKS_FOR').hasLabel('Person').values('id')\n\n"
        "Q: Who works for acme?\n"
        "A: g.V().has('id', TextP.containing('Acme')).in('WORKS_FOR').hasLabel('Person').values('id')\n\n"
        # 'How is X organized' — LLM may store departments via HAS_DEPARTMENT (out) or PART_OF (in).
        # both() traverses outbound AND inbound in one step — supported by Cosmos DB.
        # Do NOT use union(out(...), in(...)) — Cosmos DB rejects nested traversals inside union().
        "Q: What departments does Acme have?\n"
        "A: g.V().has('id', TextP.containing('Acme')).both('HAS_DEPARTMENT', 'PART_OF').hasLabel('Department').dedup().values('id')\n\n"
        "Q: How is Acme organized?\n"
        "A: g.V().has('id', TextP.containing('Acme')).both('HAS_DEPARTMENT', 'PART_OF', 'WORKS_IN_DEPARTMENT').hasLabel('Department').dedup().values('id')\n\n"
        "Q: Who manages the Engineering department?\n"
        "A: g.V().has('id', TextP.containing('Engineering')).in('MANAGES').values('id')\n\n"
        "Q: What projects is Sarah Chen working on?\n"
        "A: g.V().has('id', 'Sarah Chen').out('WORKS_ON').values('id')\n\n"
        # Abbreviation queries: entity IDs are FULL names extracted from the document.
        # 'cmis' maps to multiple nodes:
        #   'Cmis'                                      (entity, matched by TextP.containing('Cmis'))
        #   'Cmis Specification Draft Implementation'   (Product, matched by TextP.containing('Cmis'))
        #   'Content Management Interoperability Services' (Topic, matched by TextP.containing('Content Management'))
        # Use or() to match all of them in one traversal — Cosmos DB supports or() at the has() level.
        # Relationships: AFFILIATED_WITH (org->Topic), PRODUCED_BY (org->Product), RELATED_TO (Cmis->org).
        "Q: Who supported cmis?\n"
        "A: g.V().has('id', TextP.containing('Cmis')).both('AFFILIATED_WITH', 'PRODUCED_BY', 'RELATED_TO', 'CREATED_BY').hasLabel('Organization', 'Person').dedup().values('id')\n\n"
        "Q: Who was first with cmis?\n"
        "A: g.V().has('id', TextP.containing('Cmis')).both('AFFILIATED_WITH', 'PRODUCED_BY', 'RELATED_TO', 'CREATED_BY').hasLabel('Organization', 'Person').dedup().values('id')\n\n"
    )

    _GREMLIN_TEMPLATE = (
        "Task: Generate a Gremlin traversal to query a graph database.\n\n"
        "RULES (mandatory — violations cause query failures):\n"
        "- Use ONLY relationship types and properties shown in the schema below.\n"
        "- Entity names are stored in the 'id' property.\n"
        "- For partial/case-insensitive name matching use: has('id', TextP.containing('Term'))\n"
        "  where 'Term' is capitalised the same way as in the data (e.g. 'Acme', not 'acme').\n"
        "- For exact name matching use: has('id', 'ExactName')\n"
        "- To filter by vertex type use: hasLabel('Person')\n"
        "- Relationship direction is uncertain — use both('REL') to traverse in and out simultaneously.\n"
        "  Example: .both('HAS_DEPARTMENT', 'PART_OF').hasLabel('Department').dedup()\n"
        "- NEVER use union(out(...), in(...)) — Cosmos DB rejects nested traversals inside union().\n"
        "- NEVER use Groovy closures like filter{{it.get()...}} — they are NOT supported.\n"
        "- NEVER use has('partitionKey', ...) — partitionKey is an internal storage field, not a name.\n"
        "- NEVER use has('label', ...) to match entity names — use hasLabel() for vertex type filters.\n"
        "- For ordering use incr/decr, NOT asc/desc and NOT Order.asc/Order.decr:\n"
        "  CORRECT: .order().by('prop', incr)   WRONG: .order().by('prop', asc)\n"
        "- Entity names are FULL names extracted from the document.\n"
        "  Abbreviations in queries may appear in entity IDs in capitalised form:\n"
        "  'cmis' -> search TextP.containing('Cmis') to match 'Cmis', 'Cmis Specification Draft Implementation', etc.\n"
        "  If the abbreviation is also spelled out, try the key word: TextP.containing('Content Management').\n"
        "- Output ONLY the Gremlin traversal — no explanation, no code fences.\n\n"
        "Schema:\n{schema}\n\n"
        "Examples:\n"
    ) + _GREMLIN_EXAMPLES + "The question is:\n{question}\n"

    # Fix/retry prompt — teaches the LLM how to rewrite an invalid Gremlin query.
    # Key instruction: replace Groovy closures and textContains() with TextP.containing().
    _GREMLIN_FIX_TEMPLATE = (
        "The following Gremlin query is invalid:\n"
        "Query: {generated_sparql}\n"
        "Error: {error_message}\n\n"
        "Schema:\n{schema}\n\n"
        "RULES for fixing (Azure Cosmos DB for Gremlin):\n"
        "- Entity names are stored in the 'id' property.\n"
        "- NEVER use Groovy closures: filter{{...}} is NOT supported.\n"
        "- NEVER use textContains('term') — use TextP.containing('Term') instead.\n"
        "- NEVER use has('partitionKey', ...) — partitionKey is an internal field, not an entity name.\n"
        "- For partial name matching: has('id', TextP.containing('Term'))\n"
        "  (Capitalise the term the same way as in the schema, e.g. 'Acme'.)\n"
        "- For exact name matching: has('id', 'ExactName')\n"
        "- For vertex type filtering: hasLabel('Person')\n"
        "- If a single-direction traversal returns nothing, use both() to traverse in and out:\n"
        "  .both('REL1', 'REL2').hasLabel('Type').dedup()\n"
        "- NEVER use union(out(...), in(...)) — Cosmos DB rejects nested traversals inside union().\n"
        "- For ordering use incr or decr, NEVER asc/desc or Order.asc/Order.decr.\n"
        "- Abbreviations in queries appear capitalised in entity IDs: 'cmis' -> TextP.containing('Cmis').\n"
        "  This matches 'Cmis', 'Cmis Specification Draft Implementation', etc. in one step.\n"
        "Output ONLY the corrected Gremlin traversal — no explanation.\n"
    )

    try:
        gremlin_prompt = PromptTemplate(
            input_variables=["schema", "question"],
            template=_GREMLIN_TEMPLATE,
        )
        gremlin_fix_prompt = PromptTemplate(
            input_variables=["error_message", "generated_sparql", "schema"],
            template=_GREMLIN_FIX_TEMPLATE,
        )
    except Exception:
        gremlin_prompt = None
        gremlin_fix_prompt = None

    kwargs: dict = {}
    if gremlin_prompt:
        kwargs["gremlin_prompt"] = gremlin_prompt
    if gremlin_fix_prompt:
        kwargs["gremlin_fix_prompt"] = gremlin_fix_prompt
    return GremlinQAChain.from_llm(**common, **kwargs)
