# RDF and Ontology Support

## Overview

Flexible GraphRAG supports RDF/RDFS/OWL ontologies to guide knowledge graph extraction, plus optional RDF triple store backends for storing and querying extracted triples alongside property graph stores.

OWL is supported but not required — plain RDFS or any RDF schema works. When present, OWL constructs are used automatically: `owl:Class`, `owl:ObjectProperty`, `owl:DatatypeProperty`, plus `rdfs:domain`, `rdfs:range`, `rdfs:label`, and `rdfs:comment`. Ontologies can be authored in any standard format (Turtle, RDF/XML, N-Triples).

## Key Features

### 1. Ontology-Driven Extraction

Load RDF/RDFS or OWL ontologies to guide entity and relation extraction from documents. Works with **any** configured store — property graph, RDF store, or both. The ontology schema constrains entity and relation types for more consistent, domain-specific extraction.

**Benefits:**
- Higher extraction accuracy through schema guidance
- Consistent entity and relationship types across documents
- Domain-specific vocabulary (Employee, Department, Project, etc.)
- Reduced LLM hallucinations for entity types

### 2. RDF Triple Store Support

All three stores support **RDF 1.2** triple terms and annotations (relation provenance metadata). SPARQL queries use SPARQL 1.1. The stores differ in how they serialise RDF 1.2 annotations on export — see the Troubleshooting section for details.

- **Apache Jena Fuseki** — full SPARQL 1.1 + Update; RDF 1.2 triple terms stored and queryable
- **Ontotext GraphDB** — enterprise RDF store with OWL reasoning and inference; RDF 1.2 via RDF4J
- **Oxigraph** — lightweight local store; native RDF 1.2 blank-node reifier model

### 3. UI Search and Query

Regardless of which stores are configured, the UI always provides:
- **Hybrid Search tab** — combines results from all enabled retrievers: vector, BM25/full-text, property graph, and RDF store (via LangChain QA chain when `USE_LANGCHAIN_RDF=true`)
- **AI Query / AI Chat tabs** — natural language Q&A over all enabled stores simultaneously

RDF store results are fused into the same retrieval pipeline as vector, search, and property graph results — no separate query interface needed.

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    Document Sources                          │
│              (PDF, DOCX, Web, Enterprise CMS)                │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│              Docling/LlamaParse Processing                   │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│            Ontology Integration Layer                        │
│  • Load RDF/RDFS/OWL ontologies (FOAF, DCAT, custom)        │
│  • Extract entity/relation types and properties             │
│  • Build schema for LLM extraction                          │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│      LlamaIndex PropertyGraphIndex with Extractors           │
│  • SchemaLLMPathExtractor (ontology-guided)                 │
│  • DynamicLLMPathExtractor (ontology-guided, some providers)│
└────────────────┬───────────────────────┬────────────────────┘
                 ↓                       ↓
   ┌─────────────────────────┐  ┌──────────────────────┐
   │  Property Graph Stores  │  │   RDF Triple Stores  │
   │  • Neo4j                │  │   • Fuseki (RDF 1.2) │
   │  • FalkorDB             │  │   • GraphDB (RDF 1.2)│
   │  • ArcadeDB             │  │   • Oxigraph (RDF 1.2│
   │  • Kuzu, MemGraph, etc. │  │     native)          │
   └─────────────┬───────────┘  └──────────┬───────────┘
                 ↓                          ↓
┌─────────────────────────────────────────────────────────────┐
│              QueryFusionRetriever (hybrid search)            │
│  Vector + BM25 + Property Graph + RDF (LangChain QA chain)  │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

Add these to your `.env` file. You can use either **standalone variables** (recommended for simplicity) or **JSON array** (for advanced configurations).

#### Method 1: Standalone Variables (Recommended)

Simple, clear configuration with dedicated variables for each store:

```bash
# ===========================
# Ontology Configuration
# ===========================
USE_ONTOLOGY=true
ONTOLOGY_PATH=./rdf/schemas/company_ontology.ttl
ONTOLOGY_FORMAT=turtle          # turtle | rdfxml | ntriples | nquads
STRICT_SCHEMA_VALIDATION=false  # true = only extract types in schema; false = schema guides but LLM can go beyond it (default)
# ===========================
# RDF Store Configuration (Standalone Variables)
# ===========================

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

# Oxigraph (optional)
OXIGRAPH_ENABLED=false
OXIGRAPH_STORE_PATH=./data/oxigraph_store

# ===========================
# Query Routing
# ===========================
QUERY_ROUTING_DEFAULT=hybrid    # property_graph | sparql | hybrid | auto
DEFAULT_RDF_BACKEND=graphdb
SUPPORT_SPARQL=true
SUPPORT_CYPHER=true

# ===========================
# RDF Export
# ===========================
ENABLE_RDF_EXPORT=true
RDF_EXPORT_FORMAT=turtle        # turtle | rdfxml | ntriples | nquads
```

#### Method 2: JSON Array (Advanced)

For dynamic or complex configurations, use the JSON array format:

```bash
# ===========================
# Ontology Configuration
# ===========================
USE_ONTOLOGY=true
ONTOLOGY_PATH=./rdf/schemas/company_ontology.ttl
ONTOLOGY_FORMAT=turtle
STRICT_SCHEMA_VALIDATION=false  # true = only extract types in schema; false = schema guides but LLM can go beyond it (default)
# ===========================
# RDF Store Configuration (JSON Array)
# ===========================
# Comma-separated list of enabled RDF stores
RDF_ENABLED_STORES=fuseki,graphdb,oxigraph

# RDF store configurations (JSON array)
RDF_STORES=[
  {
    "name": "fuseki",
    "type": "fuseki",
    "config": {
      "base_url": "http://localhost:3030",
      "dataset": "flexible-graphrag"
    }
  },
  {
    "name": "graphdb",
    "type": "graphdb",
    "config": {
      "base_url": "http://localhost:7200",
      "repository": "flexible-graphrag",
      "username": "admin",
      "password": "admin"
    }
  },
  {
    "name": "oxigraph",
    "type": "oxigraph",
    "config": {
      "store_path": "./data/oxigraph_store"
    }
  }
]

# ===========================
# Query Routing
# ===========================
QUERY_ROUTING_DEFAULT=hybrid    # property_graph | sparql | hybrid | auto
DEFAULT_RDF_BACKEND=graphdb
SUPPORT_SPARQL=true
SUPPORT_CYPHER=true

# ===========================
# RDF Export
# ===========================
ENABLE_RDF_EXPORT=true
RDF_EXPORT_FORMAT=turtle        # turtle | rdfxml | ntriples | nquads
```

### Docker Compose Integration

The RDF stores are already included in the Docker infrastructure:

```yaml
# docker-compose.yaml - Include RDF stores
includes:
  - includes/jena-fuseki.yaml       # Apache Jena Fuseki
  - includes/ontotext-graphdb.yaml  # Ontotext GraphDB
  - includes/oxigraph.yaml          # Oxigraph
```

Start the RDF stores:
```bash
docker-compose up -d fuseki graphdb oxigraph
```

Access dashboards:
- **Fuseki**: http://localhost:3030
- **GraphDB**: http://localhost:7200
- **Oxigraph**: http://localhost:7878

## Storage Modes

Set `INGESTION_STORAGE_MODE` to control where extracted entities and triples go on ingest. Documents are written directly to whichever stores are configured — there is no automatic export step.

### Mode 1: Property Graph Only

Extracted entities and relations go to the configured property graph store (Neo4j, FalkorDB, ArcadeDB, etc.). No RDF store required.

```bash
INGESTION_STORAGE_MODE=property_graph
GRAPH_DB=neo4j

# Optional: load an ontology to guide extraction types
USE_ONTOLOGY=true
ONTOLOGY_PATH=./rdf/schemas/company_ontology.ttl
```

**UI**: Hybrid Search and AI Query/Chat work fully — vector, BM25, and property graph retrievers all active.

---

### Mode 2: RDF Stores Only

Extracted triples go directly to the configured RDF store(s). Use when you want native SPARQL 1.1 queries and RDF 1.2 annotation storage.

```bash
INGESTION_STORAGE_MODE=rdf_only

# Enable one or more RDF stores
FUSEKI_ENABLED=true
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag

GRAPHDB_ENABLED=true
GRAPHDB_BASE_URL=http://localhost:7200
GRAPHDB_REPOSITORY=flexible-graphrag

# Optional ontology
USE_ONTOLOGY=true
ONTOLOGY_PATH=./rdf/schemas/company_ontology.ttl
```

**UI**: Hybrid Search and AI Query/Chat include RDF store results when `USE_LANGCHAIN_RDF=true`. Vector and BM25 still active; property graph retriever inactive (no PG store configured).

---

### Mode 3: Property Graph + RDF Stores Side by Side

Extracted entities go to both stores simultaneously on ingest — no export step. Each store is written independently in the same pipeline pass.

```bash
INGESTION_STORAGE_MODE=both
GRAPH_DB=neo4j

FUSEKI_ENABLED=true
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag

# Optional: add GraphDB and/or Oxigraph alongside
GRAPHDB_ENABLED=true
OXIGRAPH_ENABLED=false

USE_ONTOLOGY=true
ONTOLOGY_PATH=./rdf/schemas/company_ontology.ttl
```

**UI**: All retrievers active — vector, BM25, property graph, and RDF store results all fused together in Hybrid Search and AI Query/Chat.

---

### Store Comparison

| | Property Graph | RDF Store |
|---|---|---|
| **Storage** | Nodes + edges (Cypher) | Triples + named graphs (SPARQL 1.1) |
| **Annotations** | Properties on relations | RDF 1.2 triple terms |
| **Hybrid Search** | ✅ Yes | ✅ Yes (with `USE_LANGCHAIN_RDF=true`) |
| **AI Query / Chat** | ✅ Yes | ✅ Yes (with `USE_LANGCHAIN_RDF=true`) |
| **SPARQL** | Via wrapper (not native) | ✅ Native SPARQL 1.1 |
| **OWL Reasoning** | ❌ No | ✅ GraphDB only |

## REST API Endpoints

All RDF endpoints are available under `/api/rdf/`:

### Ontology Management

- **POST** `/api/rdf/ontology/upload` - Upload RDF ontology file
  ```bash
  curl -X POST http://localhost:8000/api/rdf/ontology/upload \
    -F "file=@schemas/company_ontology.ttl"
  ```

- **GET** `/api/rdf/ontology/info` - Get loaded ontology information
  ```bash
  curl http://localhost:8000/api/rdf/ontology/info
  ```

### Direct SPARQL / Cypher Queries

> **Note**: The `/api/rdf/query/` endpoints use the `UnifiedQueryEngine` which is currently untested. For natural language queries over RDF stores, use the standard UI (Hybrid Search / AI Query / AI Chat) with `USE_LANGCHAIN_RDF=true` — that path is fully tested.

- **POST** `/api/rdf/query/sparql` - Execute SPARQL query directly
  ```bash
  curl -X POST http://localhost:8000/api/rdf/query/sparql \
    -H "Content-Type: application/json" \
    -d '{
      "query": "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10",
      "target_backend": "graphdb"
    }'
  ```
      "routing_mode": "hybrid"
    }'
  ```

### RDF Store Management

- **POST** `/api/rdf/rdf-store/connect` - Connect to RDF store
- **GET** `/api/rdf/rdf-store/list` - List connected stores
- **DELETE** `/api/rdf/rdf-store/{store_name}` - Disconnect store

## Ontology Examples

### FOAF (Friend-of-a-Friend)

Sample ontology included at `rdf/schemas/foaf_ontology.ttl`:

```turtle
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .

foaf:Person a owl:Class ;
    rdfs:label "Person" ;
    rdfs:comment "A human being" .

foaf:Organization a owl:Class ;
    rdfs:label "Organization" ;
    rdfs:comment "A collective entity" .

foaf:workplaceHomepage a owl:ObjectProperty ;
    rdfs:domain foaf:Person ;
    rdfs:range foaf:Organization ;
    rdfs:label "workplaceHomepage" .
```

### Company Domain Ontology

Sample ontology at `rdf/schemas/company_ontology.ttl`:

```turtle
@prefix company: <http://example.org/company/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .

company:Employee a owl:Class ;
    rdfs:label "Employee" ;
    rdfs:comment "A person employed by the company" .

company:Department a owl:Class ;
    rdfs:label "Department" ;
    rdfs:comment "An organizational unit" .

company:Project a owl:Class ;
    rdfs:label "Project" ;
    rdfs:comment "A company project or initiative" .

company:worksIn a owl:ObjectProperty ;
    rdfs:domain company:Employee ;
    rdfs:range company:Department ;
    rdfs:label "works in" .

company:manages a owl:ObjectProperty ;
    rdfs:domain company:Employee ;
    rdfs:range company:Project ;
    rdfs:label "manages" .
```

## Installation

### Dependencies

RDF support is included in the default installation. The required packages are:

```bash
# Core dependencies (already in requirements.txt)
rdflib>=7.0.0
pyoxigraph>=0.3.20
requests>=2.31.0
```

### Using pip
```bash
pip install -r requirements.txt
```

### Using uv (recommended)
```bash
uv pip install -e .
```

### Optional: Full RDF Stack
For advanced SPARQL features:
```bash
uv pip install -e ".[rdf-full]"
```

## Performance Considerations

### Ontology Loading
- Ontologies are loaded once at startup
- Large ontologies (>10,000 triples) may take 1-2 seconds to load
- Consider caching extracted schema in production

### Query Performance
- SPARQL queries on RDF stores: 10-100ms (depending on store and query complexity)
- Property graph Cypher queries: 5-50ms
- Hybrid queries: Sum of both + merge overhead (~10ms)

### Extraction Performance
- Ontology-guided extraction: ~10-20% slower than free-form due to validation
- Trade-off: Better accuracy and consistency vs. speed
- Recommendation: Use ontology guidance for important/structured documents

## Troubleshooting

### Ontology Not Loading
```python
# Check ontology file exists
import os
print(os.path.exists("rdf/schemas/company_ontology.ttl"))

# Try loading manually
from rdf.ontology_manager import OntologyManager
ontology = OntologyManager()
ontology.load_ontology("rdf/schemas/company_ontology.ttl", format="turtle")
print(f"Loaded: {len(ontology.entities)} entities, {len(ontology.relations)} relations")
```

### RDF Store Connection Issues
```bash
# Check if RDF store is running
docker ps | grep -E "fuseki|graphdb|oxigraph"

# Check connectivity
curl http://localhost:3030/$/ping  # Fuseki
curl http://localhost:7200/rest/repositories  # GraphDB
curl http://localhost:7878  # Oxigraph
```

### Inspecting RDF Data Directly

Export the full contents of a named graph from each store to a local file for manual inspection. This is useful for verifying ingestion quality, checking RDF 1.2 annotations, and debugging provenance metadata.

The default named graph URI used by flexible-graphrag is:
`https://integratedsemantics.org/flexible-graphrag/kg`

#### Oxigraph (port 7878)

**PowerShell:**
```powershell
Invoke-WebRequest `
  -Uri "http://localhost:7878/store?graph=https://integratedsemantics.org/flexible-graphrag/kg" `
  -Headers @{ Accept = "text/turtle" } `
  -OutFile "$env:USERPROFILE\Downloads\oxigraph-full.ttl"
```

**curl (Linux/macOS/WSL):**
```bash
curl -H "Accept: text/turtle" \
  "http://localhost:7878/store?graph=https://integratedsemantics.org/flexible-graphrag/kg" \
  -o ~/Downloads/oxigraph-full.ttl
```

To export all graphs (full dataset) as TriG:
```powershell
Invoke-WebRequest `
  -Uri "http://localhost:7878/store" `
  -Headers @{ Accept = "application/trig" } `
  -OutFile "$env:USERPROFILE\Downloads\oxigraph-all.trig"
```

#### Apache Fuseki (port 3030)

**PowerShell:**
```powershell
Invoke-WebRequest `
  -Uri "http://localhost:3030/flexible-graphrag/get?graph=https://integratedsemantics.org/flexible-graphrag/kg" `
  -Headers @{ Accept = "text/turtle" } `
  -OutFile "$env:USERPROFILE\Downloads\fuseki-full.ttl"
```

**curl:**
```bash
curl -H "Accept: text/turtle" \
  "http://localhost:3030/flexible-graphrag/get?graph=https://integratedsemantics.org/flexible-graphrag/kg" \
  -o ~/Downloads/fuseki-full.ttl
```

#### Ontotext GraphDB (port 7200)

GraphDB's `/statements` endpoint supports about 10 export formats. **Use a format that supports named graphs** (dataset formats), otherwise GraphDB will warn that graph context information cannot be represented and will strip named graph membership from the output.

| Format | Accept header | Supports named graphs | Notes |
|--------|--------------|----------------------|-------|
| **TriG** | `application/trig` | ✅ Yes | Recommended — preserves named graph, full RDF 1.2 |
| **N-Quads** | `application/n-quads` | ✅ Yes | Good for machine processing |
| **JSON-LD** | `application/ld+json` | ✅ Yes | Verbose but interoperable |
| Turtle | `text/turtle` | ⚠️ No graphs | Flattens all triples, drops graph context |
| N-Triples | `application/n-triples` | ⚠️ No graphs | Same limitation |
| RDF/XML | `application/rdf+xml` | ⚠️ No graphs | Same limitation |

> **Warning you may see:** *"The selected serialization format does not support contexts/named graphs. The export will not contain graph information."* — This appears in the GraphDB Workbench UI and in API responses when using Turtle, N-Triples, or RDF/XML. Switch to TriG or N-Quads to avoid it.

**PowerShell (TriG — recommended):**
```powershell
Invoke-WebRequest `
  -Uri "http://localhost:7200/repositories/flexible-graphrag/statements?context=%3Chttps://integratedsemantics.org/flexible-graphrag/kg%3E" `
  -Headers @{ Accept = "application/trig" } `
  -OutFile "$env:USERPROFILE\Downloads\graphdb-full.trig"
```

**PowerShell (Turtle — no graph context):**
```powershell
Invoke-WebRequest `
  -Uri "http://localhost:7200/repositories/flexible-graphrag/statements?context=%3Chttps://integratedsemantics.org/flexible-graphrag/kg%3E" `
  -Headers @{ Accept = "text/turtle" } `
  -OutFile "$env:USERPROFILE\Downloads\graphdb-full.ttl"
```

**curl (TriG):**
```bash
curl -H "Accept: application/trig" \
  "http://localhost:7200/repositories/flexible-graphrag/statements?context=<https://integratedsemantics.org/flexible-graphrag/kg>" \
  -o ~/Downloads/graphdb-full.trig
```

#### SPARQL: Count Triples per Store

Run this query against any store's SPARQL endpoint to verify data volume:

```sparql
SELECT (COUNT(*) AS ?triples) WHERE {
  GRAPH <https://integratedsemantics.org/flexible-graphrag/kg> { ?s ?p ?o }
}
```

- Oxigraph SPARQL endpoint: `http://localhost:7878/query`
- Fuseki SPARQL endpoint: `http://localhost:3030/flexible-graphrag/sparql`
- GraphDB SPARQL endpoint: `http://localhost:7200/repositories/flexible-graphrag`

### RDF Cleanup Utility (`scripts/rdf_cleanup.py`)

A command-line utility for managing RDF store data without recreating Docker containers or volumes. Run from the project root with the venv active.

> **Note:** The script auto-detects which stores to target from your `.env` (`FUSEKI_ENABLED`, `GRAPHDB_ENABLED`, `OXIGRAPH_ENABLED`). Use the store flags to override and target a specific store regardless of `.env`.

#### Setup

```bash
# From the project root, activate the venv first
# Windows
flexible-graphrag\venv-3.13\Scripts\activate

# Linux / macOS
source flexible-graphrag/venv/bin/activate
```

#### Commands

**`list-docs`** — Show all ingested documents and their triple counts:

```bash
# All enabled stores (auto-detected from .env)
python scripts/rdf_cleanup.py list-docs

# Specific store only
python scripts/rdf_cleanup.py list-docs --oxigraph
python scripts/rdf_cleanup.py list-docs --fuseki
python scripts/rdf_cleanup.py list-docs --graphdb
```

Example output:
```
Documents in graph <https://integratedsemantics.org/flexible-graphrag/kg>:

  [oxigraph]
    {'ref_doc_id': 'b206bab1-1739-4659-8fd5-515b9c6bb369', 'file_name': 'cmispress.txt', 'file_path': 'uploads\\cmispress.txt', 'triples': '173'}
```

---

**`count`** — Count total triples in the named graph:

```bash
python scripts/rdf_cleanup.py count

# Specific store
python scripts/rdf_cleanup.py count --graphdb
```

Example output:
```
Triple counts for graph <https://integratedsemantics.org/flexible-graphrag/kg>:

  [graphdb]
    {'count': '312'}
```

---

**`clear-doc <ref_doc_id>`** — Delete all triples for a specific document (use the UUID from `list-docs`):

```bash
python scripts/rdf_cleanup.py clear-doc b206bab1-1739-4659-8fd5-515b9c6bb369

# From a specific store only
python scripts/rdf_cleanup.py clear-doc b206bab1-1739-4659-8fd5-515b9c6bb369 --fuseki
```

This is safe — only triples carrying the given `ref_doc_id` are removed; other documents are untouched.

---

**`clear-all`** — Clear the entire named graph (all documents, all stores):

```bash
# Prompts for confirmation
python scripts/rdf_cleanup.py clear-all

# Skip confirmation (for scripts/automation)
python scripts/rdf_cleanup.py clear-all --yes

# Clear a specific store only
python scripts/rdf_cleanup.py clear-all --oxigraph --yes
```

#### Store Selection Flags

| Flag | Target |
|------|--------|
| *(none)* | All stores enabled in `.env` |
| `--fuseki` | Apache Fuseki only |
| `--graphdb` | Ontotext GraphDB only |
| `--oxigraph` | Oxigraph only |

Flags can be combined: `--fuseki --graphdb` targets both.

#### Environment Variables Used

The script reads the same `.env` as the main application:

| Variable | Default | Purpose |
|----------|---------|---------|
| `FUSEKI_ENABLED` | `false` | Auto-detect Fuseki |
| `FUSEKI_BASE_URL` | `http://localhost:3030` | Fuseki URL |
| `FUSEKI_DATASET` | `flexible-graphrag` | Fuseki dataset name |
| `GRAPHDB_ENABLED` | `false` | Auto-detect GraphDB |
| `GRAPHDB_BASE_URL` | `http://localhost:7200` | GraphDB URL |
| `GRAPHDB_REPOSITORY` | `flexible-graphrag` | GraphDB repository name |
| `OXIGRAPH_ENABLED` | `false` | Auto-detect Oxigraph |
| `OXIGRAPH_URL` | `http://localhost:7878` | Oxigraph HTTP URL |
| `RDF_BASE_NAMESPACE` | `https://integratedsemantics.org/flexible-graphrag/kg` | Named graph URI |

### RDF 1.2 Annotation Serialisation Differences Between Stores

All three stores fully support RDF 1.2 relation annotations (triple terms + reification), but each serialises them differently when you export data. This is normal — they are semantically identical.

| Store | Export syntax | Example |
|-------|--------------|---------|
| **Apache Fuseki** (Jena 5) | Legacy RDF-star `<< >>` | `<< :a :employs :b >> onto:employment_role "CTO" .` |
| **Oxigraph** (0.5+) | RDF 1.2 blank-node reifier | `_:b rdf:reifies <<( :a :employs :b )>> ; onto:employment_role "CTO" .` |
| **Ontotext GraphDB** (RDF4J) | `urn:rdf4j:triple:` IRI | `<urn:rdf4j:triple:PDw8...> onto:employment_role "CTO" .` |

**GraphDB `urn:rdf4j:triple:` URIs** look alarming but are completely normal. GraphDB (built on RDF4J) represents triple terms as named IRIs using a `urn:rdf4j:triple:` prefix followed by a base64-encoded serialisation of the triple. For example:

```
<urn:rdf4j:triple:PDw8aHR0cHM6...Pj4=>
    onto:employment_role "Chairman and CTO" ;
    onto:employment_start_date "2008-09-10" .
```

Decoded, the base64 portion is just `<<https://...alfresco_software> <https://...employs> <https://...john_newton>>>` — the annotated triple. You can ignore the encoding when inspecting exports; the data is correct.

**Fuseki `<< >>` syntax** is the legacy Turtle-star format from Apache Jena. It is equivalent to RDF 1.2 but uses the older embedded triple notation.

**Oxigraph blank-node reifiers** use the RDF 1.2 standard model directly: an anonymous blank node that `rdf:reifies` the triple term and carries the annotation properties.

All three representations round-trip correctly through SPARQL queries and the flexible-graphrag pipeline.

### SPARQL Query Errors
```python
# Enable detailed logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check query syntax
from rdflib import Graph
g = Graph()
result = g.query("SELECT ?s WHERE { ?s ?p ?o } LIMIT 10")
```

## Advanced Topics

### Custom Ontology Creation

Create your own domain-specific ontology:

```turtle
@prefix myco: <http://example.org/mycompany/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .

# Define entity types
myco:Customer a owl:Class ;
    rdfs:label "Customer" .

myco:Product a owl:Class ;
    rdfs:label "Product" .

myco:Order a owl:Class ;
    rdfs:label "Order" .

# Define relationships
myco:purchased a owl:ObjectProperty ;
    rdfs:domain myco:Customer ;
    rdfs:range myco:Product .

myco:contains a owl:ObjectProperty ;
    rdfs:domain myco:Order ;
    rdfs:range myco:Product .
```

### Inference and Reasoning

Ontotext GraphDB supports OWL reasoning:

```bash
# Enable reasoning in GraphDB configuration
RDF_STORES=[
  {
    "name": "graphdb",
    "type": "graphdb",
    "config": {
      "base_url": "http://localhost:7200",
      "repository": "flexible-graphrag",
      "reasoning": "rdfsplus"
    }
  }
]
```

### Federation Queries

Query across multiple RDF stores:

```sparql
# Federation example (GraphDB)
PREFIX fedx: <http://www.ontotext.com/fedx#>

SELECT ?person ?name WHERE {
  SERVICE <http://localhost:3030/dataset/sparql> {
    ?person a foaf:Person .
  }
  ?person foaf:name ?name .
}
```

## Further Reading

- [RDFlib Documentation](https://rdflib.readthedocs.io/)
- [SPARQL 1.1 Query Language](https://www.w3.org/TR/sparql11-query/)
- [Apache Jena Fuseki](https://jena.apache.org/documentation/fuseki2/)
- [Ontotext GraphDB](https://graphdb.ontotext.com/documentation/)
- [Oxigraph](https://github.com/oxigraph/oxigraph)
- [FOAF Ontology](http://xmlns.com/foaf/spec/)

## License

Apache 2.0 - Same as flexible-graphrag
