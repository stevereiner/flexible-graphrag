# Ingestion and Storage Modes

## Overview

After the LLM extracts entities and relations from your documents, Flexible GraphRAG
can store the resulting knowledge graph in:

- **Property Graph** (Neo4j, Kuzu, FalkorDB, Memgraph, …) — LPG model, Cypher queries
- **RDF Stores** (Fuseki, GraphDB, Oxigraph) — triple store, SPARQL queries
- **Both simultaneously**

The `INGESTION_STORAGE_MODE` setting controls this.

---

## Configuration

```env
# Where to store extracted knowledge graph data
# property_graph (default) | rdf_only | both
INGESTION_STORAGE_MODE=property_graph

# Base namespace for entity instance URIs in RDF output
# "Alice Johnson" -> <http://example.org/kg/alice_johnson>
RDF_BASE_NAMESPACE=https://integratedsemantics.org/flexible-graphrag/kg/
```

---

## Storage Modes

### `property_graph` (Default)

Stores extracted entities and relations in the configured property graph store only.
RDF stores are not written during ingestion.

```env
GRAPH_DB=neo4j
INGESTION_STORAGE_MODE=property_graph
```

**Data flow:**
```
Documents → LLM Extraction → PropertyGraphIndex → Neo4j (Cypher)
```

---

### `rdf_only`

Skips `PropertyGraphIndex` entirely. Extracted entities and relations are converted
to RDF and pushed directly to all enabled RDF stores. No property graph is written.

```env
INGESTION_STORAGE_MODE=rdf_only
FUSEKI_ENABLED=true
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag
```

**Data flow:**
```
Documents → LLM Extraction → KGToRDFConverter → Fuseki / GraphDB / Oxigraph (SPARQL)
```

**Use case:** Semantic web / linked data workflows where you only need SPARQL access.

---

### `both`

Stores in the property graph **and** all enabled RDF stores. Extraction runs once;
the same nodes are written to both destinations.

```env
INGESTION_STORAGE_MODE=both
GRAPH_DB=neo4j
FUSEKI_ENABLED=true
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag
```

**Data flow:**
```
                              ┌→ PropertyGraphIndex → Neo4j (Cypher)
Documents → LLM Extraction ──┤
                              └→ KGToRDFConverter  → Fuseki / GraphDB / Oxigraph (SPARQL)
```

**Use case:** Best of both worlds — fast Cypher traversal in Neo4j + SPARQL reasoning
in a triple store.

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
# The {| |} block annotates the relation triple with its properties.
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

Configure which stores to write to using standalone env vars (recommended):

```env
# Apache Fuseki
FUSEKI_ENABLED=true
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag

# Ontotext GraphDB
GRAPHDB_ENABLED=true
GRAPHDB_BASE_URL=http://localhost:7200
GRAPHDB_REPOSITORY=flexible-graphrag
GRAPHDB_USERNAME=admin
GRAPHDB_PASSWORD=admin

# Oxigraph (embedded)
OXIGRAPH_ENABLED=true
OXIGRAPH_STORE_PATH=./data/oxigraph_store
```

Multiple stores can be enabled simultaneously — ingestion writes to all of them.

See `env-sample.txt` (RDF / Triple Store Configuration section) for the full reference.

---

## Query Routing

`QUERY_ROUTING_DEFAULT` controls where **queries** go — independent of where data
was stored:

```env
QUERY_ROUTING_DEFAULT=property_graph  # Cypher only
QUERY_ROUTING_DEFAULT=sparql          # SPARQL only
QUERY_ROUTING_DEFAULT=hybrid          # Both, merge results
QUERY_ROUTING_DEFAULT=auto            # Auto-detect from query
```

---

## Terminology

| Term | Meaning |
|---|---|
| **Hybrid Search** | Vector + Fulltext + Graph retrieval (main search feature) |
| **Query Routing** | Choosing between Property Graph vs RDF stores for queries |
| **Property Graph** | LPG store: Neo4j, Kuzu, FalkorDB, Memgraph, etc. |
| **RDF Store** | Triple store: Fuseki, GraphDB, Oxigraph |
| **Ontology** | OWL/RDF schema defining entity/relation types |
| **Knowledge Graph** | Extracted entity/relation instances from documents |
| **RDF 1.2** | W3C Recommendation (2024) that standardizes triple terms, `rdf:reifies`, and the `{| |}` annotation shorthand |
| **Triple term** | `<<( s p o )>>` — a reference to an RDF proposition used with `rdf:reifies` |
| **Annotation syntax** | `{| prop value |}` inline shorthand; desugars to a blank-node reifier via `rdf:reifies` |
| **RDF-star** | Pre-RDF-1.2 proposal for embedded triples (`<< s p o >>` assertion form); superseded by RDF 1.2 |
