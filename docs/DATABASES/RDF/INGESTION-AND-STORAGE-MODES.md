# Ingestion and Storage Modes

## Overview

After the LLM extracts entities and relations from your documents, Flexible GraphRAG
can store the resulting knowledge graph in:

- **Property Graph** (Neo4j, FalkorDB, ArcadeDB, Memgraph, …) — LPG model, Cypher queries
- **RDF Graph Store** (Fuseki, GraphDB, Oxigraph) — triple store, SPARQL queries
- **Both simultaneously** — set both `PG_GRAPH_DB` and `RDF_GRAPH_DB` to non-`none` values

---

## Configuration

Use the two picker vars to control where extracted knowledge graph data is written:

```env
PG_GRAPH_DB=neo4j        # neo4j | arcadedb | falkordb | ... | none
RDF_GRAPH_DB=fuseki      # fuseki | graphdb | oxigraph | none

# Base namespace for entity instance URIs in RDF output
RDF_BASE_NAMESPACE=https://integratedsemantics.org/flexible-graphrag/kg/
```

---

## Storage Modes

### Property Graph Only (Default)

Set `RDF_GRAPH_DB=none`. Stores extracted entities and relations in the configured property graph store only.

```env
PG_GRAPH_DB=neo4j
RDF_GRAPH_DB=none
```

**Data flow:**
```
Documents → LLM Extraction → PropertyGraphIndex → Neo4j (Cypher)
```

---

### RDF Graph Store Only

Set `PG_GRAPH_DB=none`. Extracted entities and relations are converted to RDF and pushed directly to the selected RDF store. No property graph is written.

```env
PG_GRAPH_DB=none
RDF_GRAPH_DB=fuseki
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag
```

**Data flow:**
```
Documents → LLM Extraction → KGToRDFConverter → Fuseki / GraphDB / Oxigraph (SPARQL)
```

**Use case:** Semantic web / linked data workflows where you only need SPARQL access.

---

### Both Simultaneously

Set both `PG_GRAPH_DB` and `RDF_GRAPH_DB` to non-`none` values. Extraction runs once; the same nodes are written to both destinations.

```env
PG_GRAPH_DB=neo4j
RDF_GRAPH_DB=fuseki
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag
```

**Data flow:**
```
                              ┌→ PropertyGraphIndex → Neo4j (Cypher)
Documents → LLM Extraction ──┤
                              └→ KGToRDFConverter  → Fuseki / GraphDB / Oxigraph (SPARQL)
```

**Use case:** Best of both worlds — fast Cypher traversal + SPARQL reasoning in a triple store.

---

## Skipping Graph Extraction

Both the property graph and RDF graph stores can be bypassed at ingest time, while leaving previously extracted data intact for search and Q&A.

### Per-document: `skip_graph`

Pass `skip_graph=true` on a per-ingest call to skip KG extraction (and therefore skip both PG and RDF writes) for that document only. Available from:

| Entry point | How |
|---|---|
| UI | "Skip graph extraction" checkbox on the ingest form |
| REST API | `POST /api/ingest`, `POST /api/ingest-text`, `POST /api/test-sample` — `skip_graph` in body |
| MCP tools | `ingest_documents`, `ingest_text`, `test_with_sample` — `skip_graph` parameter |
| Python API | `backend.ingest_documents(skip_graph=True)`, `backend.ingest_text(skip_graph=True)` |
| Python API | `system.ingest_documents(skip_graph=True)`, `system.ingest_text(skip_graph=True)` |
| Datasource config | `skip_graph` field persisted in DB — applies to every auto-sync cycle for that datasource (filesystem, S3, GCS, Azure Blob, Google Drive, OneDrive, Alfresco, Box) |

When `skip_graph=true`:
- LLM KG extraction is skipped entirely (faster ingest)
- No new triples are written to the RDF graph store
- No new nodes/edges are written to the property graph store
- Vector and full-text (BM25/search) stores are still updated normally

### Global: `ENABLE_KNOWLEDGE_GRAPH=false`

Set in `.env` to disable KG extraction for all ingestion globally:

```env
ENABLE_KNOWLEDGE_GRAPH=false
```

Equivalent to passing `skip_graph=true` on every ingest call — KG extraction and graph writes are skipped for both PG and RDF stores.

### Previously extracted data is preserved

In both cases, **previously ingested graph data is not deleted**. Hybrid Search and AI Query / Chat will still return results from graph extractions that happened before `skip_graph` was used or `ENABLE_KNOWLEDGE_GRAPH` was disabled. To remove stale graph data, use:

- `scripts/rdf_cleanup.py clear-doc <ref_doc_id>` — remove one document's RDF triples
- `scripts/rdf_cleanup.py clear-all` — wipe the entire RDF named graph
- `scripts/cleanup.py` — clear the property graph store

---

## RDF Representation

### Entity → RDF triples

```turtle
# rdf:type from entity label
:alice_johnson  rdf:type   onto:EMPLOYEE .

# rdfs:label from entity name (original casing preserved)
:alice_johnson  rdfs:label "Alice Johnson" .

# Datatype properties
:alice_johnson  onto:age   "30"^^xsd:integer .
:alice_johnson  onto:email "alice@example.com" .
```

### Relation → RDF 1.2 Annotation

LPG relations are typed edges that carry properties:

```
(Alice)-[:WORKS_FOR {since: 2020, role: "Engineer"}]->(TechCorp)
```

This maps to **RDF 1.2 inline annotation syntax** (Turtle 1.2, W3C Recommendation),
which is supported natively by all three stores:

```turtle
# RDF 1.2 annotation syntax (default: RDF_ANNOTATION_SYNTAX=rdf_1.2)
:alice_johnson  onto:works_for  :techcorp
    {| onto:since  "2020"^^xsd:string ;
       onto:role   "Engineer"^^xsd:string |} .
```

The `{| |}` block desugars to an anonymous reifier node linked via `rdf:reifies`:

```turtle
[] rdf:reifies <<( :alice_johnson onto:works_for :techcorp )>> ;
   onto:since "2020"^^xsd:string ;
   onto:role  "Engineer"^^xsd:string .
```

**Annotation syntax options** (set via `RDF_ANNOTATION_SYNTAX`):

| Value | Syntax | Notes |
|---|---|---|
| `rdf_1.2` (default) | `{| prop value |}` inline annotation | RDF 1.2 Turtle standard, recommended |
| `rdf_star` | `<< s p o >> prop value .` lines | Legacy RDF-star (pre-RDF-1.2 proposal), same store support |
| `flat` | `onto:rel__prop value` triples | Plain SPARQL 1.1, works with any triple store |

**Store support:**
| Store | `rdf_1.2` | `rdf_star` | `flat` |
|---|---|---|---|
| Apache Fuseki (Jena 5) | ✅ | ✅ | ✅ |
| Ontotext GraphDB 10+ | ✅ | ✅ | ✅ |
| Oxigraph 0.4+ | ✅ | ✅ | ✅ |
| Any SPARQL 1.1 store | ❌ | ❌ | ✅ |

---

## URI Generation

Entity and predicate URIs are generated from names using a slug strategy:

| Input | URI |
|---|---|
| Entity name `"Alice Johnson"` | `<https://integratedsemantics.org/flexible-graphrag/kg/alice_johnson>` |
| Entity label `"EMPLOYEE"` | `<https://integratedsemantics.org/flexible-graphrag/ontology#employee>` |
| Relation label `"WORKS_FOR"` | `<https://integratedsemantics.org/flexible-graphrag/ontology#works_for>` |
| Property name `"since"` | `<https://integratedsemantics.org/flexible-graphrag/ontology#since>` |

When `USE_ONTOLOGY=true`, the ontology IRI is used as the `ONTO_NS` so extracted
types align with the loaded OWL ontology.

---

## RDF Store Connection Configuration

Configure connection details for the store selected by `RDF_GRAPH_DB`:

```env
# Apache Fuseki
RDF_GRAPH_DB=fuseki
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag
FUSEKI_USERNAME=admin
FUSEKI_PASSWORD=admin

# Ontotext GraphDB
RDF_GRAPH_DB=graphdb
GRAPHDB_BASE_URL=http://localhost:7200
GRAPHDB_REPOSITORY=flexible-graphrag
GRAPHDB_USERNAME=admin
GRAPHDB_PASSWORD=admin

# Oxigraph (HTTP mode)
RDF_GRAPH_DB=oxigraph
OXIGRAPH_URL=http://localhost:7878
```

See `env-sample.txt` (RDF / Graph Store Configuration section) for the full reference.

---

## Terminology

| Term | Meaning |
|---|---|
| **Hybrid Search** | Vector + Fulltext + Graph retrieval (main search feature) |
| **Property Graph** | LPG store: Neo4j, FalkorDB, ArcadeDB, Memgraph, etc. |
| **RDF Graph Store** | Triple store: Fuseki, GraphDB, Oxigraph |
| **Ontology** | OWL/RDF schema defining entity/relation types |
| **Knowledge Graph** | Extracted entity/relation instances from documents |
| **RDF 1.2** | W3C Recommendation (2024) that standardizes triple terms, `rdf:reifies`, and the `{| |}` annotation shorthand |
| **Triple term** | `<<( s p o )>>` — a reference to an RDF proposition used with `rdf:reifies` |
| **Annotation syntax** | `{| prop value |}` inline shorthand; desugars to a blank-node reifier via `rdf:reifies` |
| **RDF-star** | Pre-RDF-1.2 proposal for embedded triples (`<< s p o >>` assertion form); superseded by RDF 1.2 |
