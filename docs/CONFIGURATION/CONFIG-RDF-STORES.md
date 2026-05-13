# Configure RDF Graph Databases

Flexible GraphRAG supports RDF/RDFS/OWL ontologies to guide knowledge graph extraction, with optional RDF triple store backends. Ontology-guided extraction works with **any** configured store — property graph, RDF store, or both.

- Load OWL/RDFS ontologies (`owl:Class`, `owl:ObjectProperty`, `owl:DatatypeProperty`, `rdfs:domain`, `rdfs:range`) to constrain entity/relation extraction; OWL is supported but not required
- Works with all 8 property graph databases (Neo4j, ArcadeDB, FalkorDB, Ladybug, etc.) — no RDF store required to use ontology-guided extraction
- Full pipeline for all 3 RDF triple stores: UI document ingest → KG extraction → RDF storage; auto incremental data source change updates; Hybrid Search and AI Query/Chat tabs fuse RDF store results alongside vector, BM25, and graph results
- SPARQL 1.1 queries; RDF 1.2 triple terms and relation annotations (`{| |}` syntax); XSD-typed literals from OWL `DatatypeProperty` ranges

## Storage Modes

Set via `INGESTION_STORAGE_MODE`:

- **`property_graph`** — entities and relations go to the configured property graph (Neo4j, ArcadeDB, FalkorDB, Ladybug, etc.); no RDF store needed
- **`rdf_only`** — triples written directly to enabled RDF store(s); native SPARQL 1.1 queries, RDF 1.2 annotations
- **`both`** — written to property graph and RDF store(s) simultaneously; all retrievers active in hybrid search and AI query/chat

## RDF Store Configuration

Select one RDF store with `RDF_GRAPH_DB`. All three stores support RDF 1.2 triple terms.

```env
RDF_GRAPH_DB=fuseki      # Apache Jena Fuseki
RDF_GRAPH_DB=graphdb     # Ontotext GraphDB
RDF_GRAPH_DB=oxigraph    # Oxigraph
RDF_GRAPH_DB=none        # disabled (default)
```

### Apache Jena Fuseki

SPARQL 1.1 server — dashboard: http://localhost:3030

```env
RDF_GRAPH_DB=fuseki
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag
FUSEKI_USERNAME=admin
FUSEKI_PASSWORD=admin
```

### Ontotext GraphDB

Enterprise RDF store with OWL reasoning — dashboard: http://localhost:7200

```env
RDF_GRAPH_DB=graphdb
GRAPHDB_BASE_URL=http://localhost:7200
GRAPHDB_REPOSITORY=flexible-graphrag
GRAPHDB_USERNAME=admin
GRAPHDB_PASSWORD=admin
```

### Oxigraph

Lightweight local store, native RDF 1.2 — dashboard: http://localhost:7878

```env
RDF_GRAPH_DB=oxigraph
OXIGRAPH_URL=http://localhost:7878
```

## Docker Setup

Uncomment RDF store includes in `docker-compose.yaml`:

```yaml
includes:
  # - includes/jena-fuseki.yaml
  # - includes/ontotext-graphdb.yaml
  # - includes/oxigraph.yaml
```

## Ontology Paths

Set in `.env`:

```bash
# Single ontology file
ONTOLOGY_PATH=./schemas/my_ontology.ttl

# Multiple ontology files
ONTOLOGY_PATHS=./schemas/company_classes.ttl,./schemas/company_properties.ttl,./schemas/common_ontology.ttl

# Directory of ontology files
ONTOLOGY_DIR=./schemas/
```

## LangChain RDF Retrieval

Setting `RDF_GRAPH_DB` to a non-`none` value automatically fuses SPARQL-based results from the configured RDF store into hybrid search and AI query alongside vector and graph results.

See [RDF Store User Guide](../DATABASES/RDF/RDF-STORE-USER-GUIDE.md) | [Ontology Support](../DATABASES/RDF/RDF-ONTOLOGY-SUPPORT.md) for complete documentation.
