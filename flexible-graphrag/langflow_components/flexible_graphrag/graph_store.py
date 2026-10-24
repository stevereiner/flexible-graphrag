"""Flexible GraphRAG Property Graph Component for Langflow.

Stores the already-extracted KG into the property-graph DB (per .env: PG_GRAPH_DB) via the
real backend update_pg_graph with pre_extracted=True (store phase only — extraction was
done once by the KG Extraction node). For the LangChain backend the KG node already wrote
the graph, so this node passes through.
"""

from langflow_components.flexible_graphrag._fg_shared import get_run, make_payload, get_loop, has_ingest_chunks, run_graphs

from langflow.custom import Component
from langflow.io import HandleInput, Output
from langflow.schema import Data


class FlexibleGraphStoreComponent(Component):
    """Index the extracted KG into the property graph DB (per .env: PG_GRAPH_DB)."""

    display_name = "Flexible: Property Graph"
    description = "Store the extracted KG into the property-graph DB (Neo4j/… per .env) via the backend pipeline"
    icon = "Workflow"
    name = "FlexibleGraphStore"

    inputs = [
        HandleInput(name="kg", display_name="KG", input_types=["Data"],
                    info="From KG Extraction: shared system + KG-extracted nodes."),
    ]

    outputs = [
        Output(display_name="Result", name="result", method="store_graph"),
    ]

    async def store_graph(self) -> Data:
        from ingest.update_pg_graph import update_pg_graph

        run = get_run(self.kg)
        system, nodes, documents = run["system"], run.get("nodes"), run.get("documents")
        if not has_ingest_chunks(run):
            raise ValueError("No chunk nodes in the ingestion run")

        db = str(getattr(system.config, "pg_graph_db", "none") or "none")
        if run.get("pg_done"):
            self.status = "Property graph already written by KG Extraction (LangChain backend)."
            return make_payload(run["_key"], "graph", db=db,
                                entities=run.get("entities", 0), relations=run.get("relations", 0))
        # Skip when KG was skipped (skip_graph / ENABLE_KNOWLEDGE_GRAPH=false) or there is no
        # property-graph store (PG_GRAPH_DB=none).
        # ... or this run leaves the property graph out (enabled_graph=false).
        if not run.get("kg_extracted") or db.lower() == "none" or not run_graphs(run).graph:
            self.status = "Property graph skipped (no KG extracted / PG_GRAPH_DB=none / enabled_graph off)."
            return make_payload(run["_key"], "graph", db=db, entities=0, relations=0)

        nodes, _extracted, _kg_dur, graph_dur, num_e, num_r = await update_pg_graph(
            system, nodes, documents, get_loop(), skip_graph=False, pre_extracted=True
        )
        run["nodes"] = nodes
        self.status = f"Property graph: {num_e} entities, {num_r} relations into {db} in {graph_dur:.2f}s."
        return make_payload(run["_key"], "graph", db=db, entities=num_e, relations=num_r,
                            seconds=round(graph_dur, 2))
