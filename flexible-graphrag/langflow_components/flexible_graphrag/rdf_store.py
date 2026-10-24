"""Flexible GraphRAG RDF Graph Component for Langflow.

Writes an RDF graph via the real backend update_rdf_graph (per RDF_GRAPH_DB), using the
shared system. Reuses the KG-extracted nodes from the Knowledge Graph node when present.
"""

from langflow_components.flexible_graphrag._fg_shared import get_run, make_payload, has_ingest_chunks, run_graphs

from langflow.custom import Component
from langflow.io import HandleInput, BoolInput, Output
from langflow.schema import Data


class FlexibleRDFStoreComponent(Component):
    """Write an RDF graph (per .env: RDF_GRAPH_DB)."""

    display_name = "Flexible: RDF Graph"
    description = "Write RDF triples (Fuseki/Oxigraph/GraphDB/Neptune per .env) via the backend pipeline"
    icon = "Share2"
    name = "FlexibleRDFStore"

    inputs = [
        HandleInput(name="kg", display_name="KG", input_types=["Data"],
                    info="From KG Extraction: shared system + KG-extracted nodes (parallel with Property Graph)."),
        BoolInput(name="skip_graph", display_name="Skip", value=False,
                  info="Skip RDF writing for this run."),
    ]

    outputs = [
        Output(display_name="Result", name="result", method="store_rdf"),
    ]

    async def store_rdf(self) -> Data:
        from ingest.update_rdf_graph import update_rdf_graph

        run = get_run(self.kg)
        system, nodes = run["system"], run.get("nodes")
        if not has_ingest_chunks(run):
            raise ValueError("No chunk nodes in the ingestion run")

        db = str(getattr(system.config, "rdf_graph_db", "none") or "none")
        # The KG Extraction node is the single extraction point (its result feeds both the
        # Property Graph and RDF nodes). Mirror the Property Graph node: if KG was skipped
        # (skip_graph on the run, or its own field, KG extraction otherwise skipped — e.g.
        # ENABLE_KNOWLEDGE_GRAPH=false), or there is no RDF store (RDF_GRAPH_DB=none), store
        # nothing — do NOT let update_rdf_graph re-extract a full KG here.
        # (rdf_extracts: the LangChain KG node left extraction to this node, property graph off)
        extracts_here = bool(run.get("rdf_extracts"))
        if (bool(self.skip_graph) or not run_graphs(run).rdf
                or not (run.get("kg_extracted") or extracts_here) or db.lower() == "none"):
            self.status = "RDF writing skipped (enabled_rdf off / no KG extracted / RDF_GRAPH_DB=none)."
            return make_payload(run["_key"], "rdf", db=db, entities=0, relations=0)

        from graph_flags import GraphFlags
        rdf_kg_duration, rdf_store_duration = await update_rdf_graph(
            system, nodes, nodes_kg_extracted=not extracts_here, graphs=GraphFlags(False, True)
        )
        self.status = (f"RDF written to {db}: {run.get('entities', 0)} entities, "
                       f"{run.get('relations', 0)} relations (kg {rdf_kg_duration:.2f}s, "
                       f"store {rdf_store_duration:.2f}s).")
        return make_payload(run["_key"], "rdf", db=db,
                            entities=run.get("entities", 0), relations=run.get("relations", 0),
                            seconds=round(rdf_store_duration, 2))
