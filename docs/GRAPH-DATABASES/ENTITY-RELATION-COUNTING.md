# Entity and Relation Counting in Flexible GraphRAG

This document explains how entity and relation counting works in Flexible GraphRAG.

## Overview

The system counts entities and relationships extracted from documents during the knowledge graph extraction phase. These counts are recorded as metrics and displayed in Grafana dashboards for observability.

## Implementation Approach

The system tracks counts during extraction by counting entities and relations from node metadata **after extraction but before insertion** into the graph store.

### Why This Approach?

This approach provides accurate per-ingestion counts by:
1. Examining node metadata (`KG_NODES_KEY`, `KG_RELATIONS_KEY`) after extractors have processed nodes
2. Counting **only the entities/relations from the current ingestion**, not the entire database
3. Avoiding complex database queries that mix old and new data

### Alternative Approaches (Not Used)

- **Query Database After Insertion**: This counts ALL entities/relations in the database, not just the newly extracted ones
- **Incremental Counting**: Complex to implement correctly and prone to race conditions

## Code Flow

### PATH 2: Initial Graph Creation

```python
# 1. Convert documents to nodes
nodes = node_parser.get_nodes_from_documents(documents)

# 2. Run extractors manually to populate metadata
for extractor in kg_extractors:
    nodes = extractor(nodes, show_progress=True)

# 3. Count from node metadata
num_entities, num_relations = count_extracted_entities_and_relations(nodes)

# 4. Create graph index (already extracted)
self.graph_index = PropertyGraphIndex.from_documents(
    documents=documents,
    kg_extractors=kg_extractors,  # Still needed for internal processing
    ...
)
```

### PATH 3: Incremental Updates

```python
# Nodes already processed by IngestionPipeline with extractors
# Just count before insertion
num_entities, num_relations = count_extracted_entities_and_relations(nodes)

# Insert into existing graph
self.graph_index.insert_nodes(nodes)
```

## Helper Function

```python
def count_extracted_entities_and_relations(nodes: List[BaseNode]) -> tuple[int, int]:
    """
    Count entities and relations from node metadata after extraction.
    
    Returns:
        Tuple of (entity_count, relation_count)
    """
    entity_count = 0
    relation_count = 0
    
    for node in nodes:
        # Get entities from metadata
        entities = node.metadata.get(KG_NODES_KEY, [])
        entity_count += len(entities)
        
        # Get relations from metadata
        relations = node.metadata.get(KG_RELATIONS_KEY, [])
        relation_count += len(relations)
    
    return entity_count, relation_count
```

## Metrics

### OpenTelemetry Metrics

Two new counter metrics are recorded:

1. **`rag.graph.entities_extracted`** - Total entities extracted from documents
2. **`rag.graph.relations_extracted`** - Total relations/relationships extracted from documents

### Recording Metrics

```python
metrics.record_graph_extraction(
    latency_ms=graph_creation_duration * 1000,
    num_entities=num_entities,
    num_relations=num_relations
)
```

## Grafana Dashboard

Two new panels show entity and relation metrics:

### Knowledge Graph Entities Panel
- **Rate**: `rate(rag_graph_entities_extracted_total[5m])` - Entities extracted per second
- **Total**: `rag_graph_entities_extracted_total` - Cumulative total entities extracted

### Knowledge Graph Relations Panel
- **Rate**: `rate(rag_graph_relations_extracted_total[5m])` - Relations extracted per second
- **Total**: `rag_graph_relations_extracted_total` - Cumulative total relations extracted

## Logging

The system logs entity/relation counts at key points:

```
Extraction complete: 42 entities, 87 relationships extracted from node metadata
Knowledge graph extraction finished - 42 entities and 87 relationships stored in Neo4jPropertyGraphStore
[PATH 2] Recorded graph extraction metrics: 12543.21ms, 42 entities, 87 relations
```

## Benefits

1. **Accurate Per-Ingestion Counts** - Only counts what was extracted in the current operation
2. **No Database Overhead** - Counts from in-memory metadata, not expensive database queries
3. **Works with All Graph Stores** - Doesn't depend on store-specific query methods
4. **Observable** - Full visibility in traces, metrics, and logs
5. **Maintainable** - Simple, clear implementation following LlamaIndex best practices

## Configuration

No configuration needed - entity/relation counting is automatic when observability is enabled.

To enable observability:

```bash
ENABLE_OBSERVABILITY=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

## Troubleshooting

### Counts Show Zero

If entity/relation counts are always zero:
1. Check that kg_extractors are configured properly
2. Verify LLM is working (extraction requires LLM calls)
3. Check logs for extraction errors

### Counts Don't Match Database

This is expected! The counts show **newly extracted** entities/relations from the current ingestion, not the total in the database.

### Missing in Grafana

1. Verify observability is enabled: `ENABLE_OBSERVABILITY=true`
2. Check Prometheus is scraping: `http://localhost:9090/targets`
3. Verify metrics are being exported: `http://localhost:9090/graph` and query for `rag_graph_entities_extracted_total`
4. Check Grafana data source connection

## References

- **LlamaIndex Documentation**: Property Graph Extractors and Metadata Keys
- **OpenTelemetry**: Counter Metrics
- **Prometheus**: Rate and Counter Queries

