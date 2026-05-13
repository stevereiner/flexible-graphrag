"""
Knowledge graph extraction utilities.

Owns KG extractor execution, timing, OTel span instrumentation, and the
post-extraction node validation (label sanitisation, doc_id propagation,
entity/relation counting) so all ingest paths share one implementation.
"""

import asyncio
import functools
import io
import sys
import time
from typing import List, Tuple
import logging

from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY
from llama_index.core.schema import BaseNode

logger = logging.getLogger(__name__)

try:
    from observability import get_tracer
    from observability.metrics import get_rag_metrics
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    get_tracer = None
    get_rag_metrics = None



def count_extracted_entities_and_relations(nodes: List[BaseNode]) -> tuple:
    """Validate and count entities and relations after KG extraction.

    Sanitises entity/relation labels (filters empty/whitespace ones), propagates
    doc_id and ref_doc_id from source nodes to extracted entities as properties
    (so they appear in Neo4j and other graph stores), and returns counts.

    Args:
        nodes: List of nodes after kg_extractors have processed them

    Returns:
        Tuple of (entity_count, relation_count)
    """
    entity_count = 0
    relation_count = 0

    logger.info(f"Counting entities/relations from {len(nodes)} nodes...")

    for i, node in enumerate(nodes):
        entities = node.metadata.get(KG_NODES_KEY, [])
        relations = node.metadata.get(KG_RELATIONS_KEY, [])

        # Propagate doc_id and ref_doc_id from source node to extracted entities.
        for entity in entities:
            ref_doc_id_value = None
            if hasattr(node, 'ref_doc_id') and node.ref_doc_id:
                ref_doc_id_value = node.ref_doc_id
                if hasattr(entity, 'properties'):
                    if entity.properties is None:
                        entity.properties = {}
                    entity.properties['ref_doc_id'] = node.ref_doc_id

            doc_id_value = None
            if hasattr(node, 'doc_id') and node.doc_id:
                doc_id_value = node.doc_id
            elif 'doc_id' in node.metadata:
                doc_id_value = node.metadata['doc_id']

            if doc_id_value:
                if hasattr(entity, 'properties'):
                    if entity.properties is None:
                        entity.properties = {}
                    entity.properties['doc_id'] = doc_id_value

            if hasattr(entity, 'metadata'):
                if entity.metadata is None:
                    entity.metadata = {}
                if ref_doc_id_value:
                    entity.metadata['ref_doc_id'] = ref_doc_id_value
                if doc_id_value:
                    entity.metadata['doc_id'] = doc_id_value

        # Filter out entities with empty/whitespace labels.
        valid_entities = []
        filtered_entity_count = 0
        for entity in entities:
            label = getattr(entity, 'label', None) or getattr(entity, 'type', None)
            if label and str(label).strip():
                valid_entities.append(entity)
            else:
                filtered_entity_count += 1
                if i < 3:
                    logger.warning(f"Filtered entity with empty/invalid label: {entity}")

        # Filter out relations with empty/whitespace labels.
        valid_relations = []
        filtered_relation_count = 0
        for relation in relations:
            label = getattr(relation, 'label', None) or getattr(relation, 'type', None)
            if label and str(label).strip():
                valid_relations.append(relation)
            else:
                filtered_relation_count += 1
                if i < 3:
                    logger.warning(f"Filtered relation with empty/invalid label: {relation}")

        node.metadata[KG_NODES_KEY] = valid_entities
        node.metadata[KG_RELATIONS_KEY] = valid_relations

        if filtered_entity_count > 0 or filtered_relation_count > 0:
            logger.warning(
                f"Node {i}: Filtered {filtered_entity_count} entities and "
                f"{filtered_relation_count} relations with invalid labels"
            )

        if i < 3:
            logger.info(f"Node {i}: {len(valid_entities)} entities, {len(valid_relations)} relations (after validation)")
            logger.info(f"Node {i} metadata keys: {list(node.metadata.keys())}")

            if hasattr(node, 'ref_doc_id') and node.ref_doc_id:
                logger.info(f"Node {i} ref_doc_id (attribute): {node.ref_doc_id}")
            if hasattr(node, 'doc_id') and node.doc_id:
                logger.info(f"Node {i} doc_id (attribute): {node.doc_id}")
            if 'doc_id' in node.metadata:
                logger.info(f"Node {i} doc_id (metadata): {node.metadata['doc_id']}")

            if entities and len(entities) > 0:
                sample_entity = entities[0]
                logger.info(f"Node {i} sample entity type: {type(sample_entity).__name__}")
                if hasattr(sample_entity, 'properties') and sample_entity.properties:
                    logger.info(f"Node {i} sample entity properties: {sample_entity.properties}")
                if hasattr(sample_entity, 'name'):
                    logger.info(f"Node {i} sample entity name: {sample_entity.name}")

            logger.info(f"Node {i} full metadata:")
            for key, value in node.metadata.items():
                if isinstance(value, list):
                    logger.info(f"  {key}: list with {len(value)} items")
                    if 0 < len(value) <= 3:
                        logger.info(f"    Content: {value}")
                elif isinstance(value, dict):
                    logger.info(f"  {key}: dict with {len(value)} keys")
                    if len(value) <= 5:
                        logger.info(f"    Content: {value}")
                else:
                    logger.info(f"  {key}: {value}")

        entity_count += len(valid_entities)
        relation_count += len(valid_relations)

    logger.info(f"Total: {entity_count} entities, {relation_count} relations from {len(nodes)} nodes")
    return entity_count, relation_count


async def run_kg_extractors_on_nodes(
    nodes: List,
    kg_extractors: List,
    config,
    span_name: str = "rag.graph_extraction",
    extra_span_attrs: dict = None,
) -> Tuple[List, int, int, float]:
    """Run a single KG extractor on a list of nodes with timing and OTel tracing.

    Handles the Gemini/Vertex AI special case (synchronous execution to avoid
    event-loop conflicts) and all other providers (executor-based async).

    Args:
        nodes: Pre-chunked nodes to extract from
        kg_extractors: List containing exactly one extractor instance
        config: AppSettings (used for llm_provider)
        span_name: OTel span name (callers can customise create vs update)
        extra_span_attrs: Additional span attributes dict (e.g. graph.database_type)

    Returns:
        Tuple of (extracted_nodes, num_entities, num_relations, duration_seconds)
    """
    if len(kg_extractors) != 1:
        raise ValueError(f"Expected exactly 1 extractor, got {len(kg_extractors)}")

    extractor = kg_extractors[0]
    logger.info(f"Running extractor on {len(nodes)} nodes to extract entities and relationships...")

    # OTel span setup
    graph_span = None
    token = None
    if OBSERVABILITY_AVAILABLE:
        try:
            from opentelemetry import context as otel_context, trace as otel_trace
            tracer = get_tracer(__name__)
            graph_span = tracer.start_span(span_name)
            graph_span.set_attribute("graph.num_nodes", len(nodes))
            llm_model_name = getattr(getattr(config, 'llm_config', {}), 'model', '') or ''
            graph_span.set_attribute("graph.llm_model", llm_model_name)
            graph_span.set_attribute("graph.extractor_type", getattr(config, 'kg_extractor_type', ''))
            if extra_span_attrs:
                for k, v in extra_span_attrs.items():
                    graph_span.set_attribute(k, v)
            ctx = otel_trace.set_span_in_context(graph_span)
            token = otel_context.attach(ctx)
        except Exception as e:
            logger.debug(f"OTel span setup failed (non-fatal): {e}")
            graph_span = None
            token = None

    start_time = time.time()

    try:
        # All providers use run_in_executor (worker thread) for KG extraction.
        # Worker threads have no running event loop, so any internal asyncio.run() calls
        # inside LLM SDK sync paths (e.g. Gemini/Vertex AI) work without conflict.
        logger.info(f"Running extractor asynchronously ({config.llm_provider}) in executor")
        _loop = asyncio.get_running_loop()
        # Capture stdout to catch DynamicLLMPathExtractor's bare print() error messages
        _stdout_capture = io.StringIO()
        _orig_stdout = sys.stdout
        sys.stdout = _stdout_capture
        try:
            extractor_with_progress = functools.partial(extractor, show_progress=True)
            nodes = await _loop.run_in_executor(None, extractor_with_progress, nodes)
        finally:
            sys.stdout = _orig_stdout
            captured = _stdout_capture.getvalue().strip()
            if captured:
                logger.warning(f"Extractor stdout output (hidden errors): {captured}")
        logger.info("Knowledge graph extraction completed")

        duration = time.time() - start_time
        num_entities, num_relations = count_extracted_entities_and_relations(nodes)
        logger.info(f"Extraction complete: {num_entities} entities, {num_relations} relations in {duration:.2f}s")

        if graph_span:
            graph_span.set_attribute("graph.extraction_latency_ms", duration * 1000)
            graph_span.set_attribute("graph.num_entities", num_entities)
            graph_span.set_attribute("graph.num_relations", num_relations)
            graph_span.set_attribute("graph.status", "success")

        if OBSERVABILITY_AVAILABLE and get_rag_metrics:
            try:
                metrics = get_rag_metrics()
                metrics.record_graph_extraction(
                    latency_ms=duration * 1000,
                    num_entities=num_entities,
                    num_relations=num_relations,
                )
                logger.info(
                    f"Recorded graph extraction metrics: {duration * 1000:.2f}ms, "
                    f"{num_entities} entities, {num_relations} relations"
                )
            except Exception as e:
                logger.warning(f"Failed to record graph metrics: {e}")

        return nodes, num_entities, num_relations, duration

    except Exception as e:
        duration = time.time() - start_time
        if graph_span:
            graph_span.set_attribute("graph.status", "error")
            graph_span.set_attribute("graph.error", str(e))
            try:
                graph_span.record_exception(e)
            except Exception:
                pass
        raise
    finally:
        if graph_span:
            try:
                graph_span.end()
            except Exception:
                pass
        if token is not None:
            try:
                from opentelemetry import context as otel_context
                otel_context.detach(token)
            except Exception:
                pass
