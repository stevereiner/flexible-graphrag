"""
RDF export and delete helpers for Flexible GraphRAG.

All three public functions are called exclusively from the RDF pipeline
(ingest/update_rdf_graph.py and hybrid_system.py).  They live here rather
than in index_manager.py so RDF concerns stay grouped together.
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def export_nodes_to_rdf_stores(nodes: List, config, schema_manager=None) -> None:
    """Export LI-extracted KG nodes/relations to the configured RDF store.

    Reads ``EntityNode`` / ``Relation`` objects from ``node.metadata``
    (``KG_NODES_KEY`` / ``KG_RELATIONS_KEY``) and converts them to Turtle
    via ``KGToRDFConverter.convert()``.

    Called by ``update_rdf_graph`` when ``nodes_kg_extracted=True``.
    """
    from rdf.kg_to_rdf_converter import convert_nodes_to_rdf, DEFAULT_BASE_NS, DEFAULT_ONTO_NS
    from rdf.store.rdf_store_factory import RDFStoreFactory

    store_cfg = config.get_rdf_store_config()
    if not store_cfg:
        logger.warning(
            "export_nodes_to_rdf_stores called but RDF_GRAPH_DB is not set. "
            "Set RDF_GRAPH_DB=fuseki|oxigraph|graphdb to enable RDF ingestion."
        )
        return

    onto_ns = DEFAULT_ONTO_NS
    ontology_manager = None
    if schema_manager is not None:
        try:
            ontology_manager = schema_manager.ontology_manager
            if ontology_manager:
                iri = getattr(ontology_manager, "ontology_iri", None)
                if iri:
                    onto_ns = iri.rstrip("#/") + "#"
        except Exception:
            pass

    base_ns = getattr(config, "rdf_base_namespace", DEFAULT_BASE_NS)
    graph_uri = base_ns.rstrip("/")
    annotation_syntax = config.rdf_annotation_syntax

    logger.info("Converting extracted KG to RDF (annotation_syntax=%s)...", annotation_syntax)
    rdf_graph, turtle_annotated = convert_nodes_to_rdf(
        nodes,
        base_ns=base_ns,
        onto_ns=onto_ns,
        ontology_manager=ontology_manager,
        annotation_syntax=annotation_syntax,
    )
    logger.info("RDF graph built: %d triples", len(rdf_graph))

    store_name = store_cfg.get("name", "unknown")
    store_type = store_cfg.get("type", store_name)
    try:
        adapter = RDFStoreFactory.create(store_type, store_cfg.get("config", {}))
        adapter.store_rdf_annotations(turtle_annotated, graph_uri=graph_uri)
        logger.info("Exported KG to RDF store '%s' (%s)", store_name, store_type)
    except Exception as e:
        logger.error(
            "Failed to export KG to RDF store '%s': %s", store_name, e, exc_info=True
        )


def export_lc_graph_docs_to_rdf_stores(
    graph_docs: List, nodes: List, config, schema_manager=None
) -> None:
    """Export LC-extracted GraphDocuments to the configured RDF store.

    Reads LC ``Node`` / ``Relationship`` fields directly via
    ``KGToRDFConverter.convert_lc_docs`` — no conversion to LlamaIndex
    ``EntityNode`` / ``Relation`` objects.

    Called by ``update_rdf_graph`` when ``system._lc_graph_docs`` is set
    (i.e. ``KG_EXTRACTOR_BACKEND=langchain`` ingestion path).
    """
    from rdf.kg_to_rdf_converter import KGToRDFConverter, DEFAULT_BASE_NS, DEFAULT_ONTO_NS
    from rdf.store.rdf_store_factory import RDFStoreFactory

    store_cfg = config.get_rdf_store_config()
    if not store_cfg:
        logger.warning(
            "export_lc_graph_docs_to_rdf_stores called but RDF_GRAPH_DB is not set. "
            "Set RDF_GRAPH_DB=fuseki|oxigraph|graphdb to enable RDF ingestion."
        )
        return

    onto_ns = DEFAULT_ONTO_NS
    ontology_manager = None
    if schema_manager is not None:
        try:
            ontology_manager = schema_manager.ontology_manager
            if ontology_manager:
                iri = getattr(ontology_manager, "ontology_iri", None)
                if iri:
                    onto_ns = iri.rstrip("#/") + "#"
        except Exception:
            pass

    base_ns = getattr(config, "rdf_base_namespace", DEFAULT_BASE_NS)
    graph_uri = base_ns.rstrip("/")
    annotation_syntax = config.rdf_annotation_syntax

    converter = KGToRDFConverter(
        base_ns=base_ns,
        onto_ns=onto_ns,
        ontology_manager=ontology_manager,
    )
    logger.info("Converting LC GraphDocuments to RDF (annotation_syntax=%s)...", annotation_syntax)
    rdf_graph, turtle_annotated = converter.convert_lc_docs(
        graph_docs,
        annotation_syntax=annotation_syntax,
        source_nodes=nodes,
    )
    logger.info("RDF graph built: %d triples", len(rdf_graph))

    store_name = store_cfg.get("name", "unknown")
    store_type = store_cfg.get("type", store_name)
    try:
        adapter = RDFStoreFactory.create(store_type, store_cfg.get("config", {}))
        adapter.store_rdf_annotations(turtle_annotated, graph_uri=graph_uri)
        logger.info("Exported LC KG to RDF store '%s' (%s)", store_name, store_type)
    except Exception as e:
        logger.error(
            "Failed to export LC KG to RDF store '%s': %s", store_name, e, exc_info=True
        )


def delete_from_rdf_stores(ref_doc_id: str, config) -> None:
    """Delete all triples for ref_doc_id from the configured RDF store.

    Errors are logged but never raised so a failed RDF delete never blocks
    the rest of the delete cycle.
    """
    store_cfg = config.get_rdf_store_config()
    if not store_cfg:
        return

    from rdf.store.rdf_store_factory import RDFStoreFactory
    from rdf.kg_to_rdf_converter import DEFAULT_BASE_NS

    graph_uri = DEFAULT_BASE_NS.rstrip("/")
    store_name = store_cfg.get("name", "unknown")
    store_type = store_cfg.get("type", store_name)
    try:
        adapter = RDFStoreFactory.create(store_type, store_cfg.get("config", {}))
        adapter.delete_doc(ref_doc_id, graph_uri=graph_uri)
        logger.info(
            "Deleted RDF triples for doc '%s' from store '%s'",
            ref_doc_id, store_name,
        )
    except Exception as e:
        logger.warning(
            "Failed to delete RDF triples for doc '%s' from store '%s': %s",
            ref_doc_id, store_name, e,
        )
