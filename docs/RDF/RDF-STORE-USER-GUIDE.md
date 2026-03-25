# RDF Store User Guide

How to configure Flexible GraphRAG to write extracted knowledge graphs to RDF triple stores, and how to explore the data in each store's dashboard.

---

## Configuration

### Ingestion Mode

Set in `.env` — controls where extracted KG data is written:

```env
# property_graph   — Neo4j / Kuzu only (default)
# rdf_only         — RDF stores only (skips property graph)
# both             — Neo4j/Kuzu AND RDF stores simultaneously
INGESTION_STORAGE_MODE=both
```

### RDF 1.2 Annotation Syntax

Relation properties (e.g. `employment_role`, `proficiency_level`) are stored as RDF 1.2 annotations by default:

```env
# RDF_ANNOTATION_SYNTAX controls how relation properties are encoded:
RDF_ANNOTATION_SYNTAX=rdf_1.2      # {| prop value |}  — RDF 1.2 Turtle standard (default)
                                  # Fuseki 5 (Jena 5), GraphDB 10+, Oxigraph 0.4+
RDF_ANNOTATION_SYNTAX=rdf_star   # << s p o >> prop value  — legacy RDF-star lines
                                  # same store support, older syntax
RDF_ANNOTATION_SYNTAX=flat       # onto:rel__prop value    — plain SPARQL 1.1 triples
                                  # works with any triple store, no annotation semantics
```

**RDF 1.2 `{| |}` annotation example:**
```turtle
:alice_johnson  onto:works_for  :techcorp
    {| onto:since  "2020"^^xsd:string ;
       onto:role   "Engineer"^^xsd:string |} .
```
This is the W3C Turtle 1.2 / RDF 1.2 standard (Recommendation, 2024). The `{| |}` block creates an anonymous reifier node linked via `rdf:reifies <<( s p o )>>`, which can be queried with SPARQL 1.2.

### Base Namespace

```env
RDF_BASE_NAMESPACE=https://integratedsemantics.org/flexible-graphrag/kg/
```

Named graph URI = base namespace with trailing slash stripped:
`https://integratedsemantics.org/flexible-graphrag/kg`

---

## Apache Fuseki

**Dashboard:** http://localhost:3030  
**Login:** admin / admin (set via `ADMIN_PASSWORD` in `docker/includes/jena-fuseki.yaml`)

### `.env` settings

```env
FUSEKI_ENABLED=true
FUSEKI_BASE_URL=http://localhost:3030
FUSEKI_DATASET=flexible-graphrag
FUSEKI_USERNAME=admin
FUSEKI_PASSWORD=admin
```

### Dashboard usage

1. Open http://localhost:3030 and log in
2. Click **flexible-graphrag** dataset → **query** tab
3. The dataset is auto-created on first ingest via the Fuseki admin API

**View all entities and relations (readable):**
```sparql
PREFIX base: <https://integratedsemantics.org/flexible-graphrag/kg/>
PREFIX onto: <https://integratedsemantics.org/flexible-graphrag/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?subjectLabel ?relName ?objectLabel WHERE {
  GRAPH <https://integratedsemantics.org/flexible-graphrag/kg> {
    ?s ?rel ?o .
    ?s rdfs:label ?subjectLabel .
    ?o rdfs:label ?objectLabel .
    BIND(STRAFTER(STR(?rel), STR(onto:)) AS ?relName)
    FILTER(?relName != "")
  }
}
ORDER BY ?subjectLabel ?relName
```

**View RDF 1.2 relation annotations (SPARQL 1.2 `rdf:reifies`):**
```sparql
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX onto: <https://integratedsemantics.org/flexible-graphrag/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?subjectLabel ?relName ?objectLabel ?prop ?val WHERE {
  GRAPH <https://integratedsemantics.org/flexible-graphrag/kg> {
    ?s ?rel ?o .
    ?s rdfs:label ?subjectLabel .
    ?o rdfs:label ?objectLabel .
    ?reifier rdf:reifies <<( ?s ?rel ?o )>> ;
             ?annprop ?val .
    BIND(STRAFTER(STR(?rel),     STR(onto:)) AS ?relName)
    BIND(STRAFTER(STR(?annprop), STR(onto:)) AS ?prop)
    FILTER(?prop NOT IN ("source","file_name","file_path","file_type",
                         "modified_at","conversion_method","ref_doc_id"))
    FILTER(?relName != "" && ?prop != "")
  }
}
ORDER BY ?subjectLabel ?relName ?prop
```

**Note:** If using legacy `RDF_ANNOTATION_SYNTAX=rdf_star`, query annotations with:
```sparql
  << ?s ?rel ?o >> ?annprop ?val .
```

**Drop and reload graph** (SPARQL Update tab):
```sparql
DROP GRAPH <https://integratedsemantics.org/flexible-graphrag/kg>
```

**Download data:** Dataset page → **download** → choose Turtle or TriG.  
The raw Turtle file (with annotations) is also available at:
```
GET http://localhost:3030/flexible-graphrag/data?graph=https://integratedsemantics.org/flexible-graphrag/kg
Accept: text/turtle
```

---

## Ontotext GraphDB

**Dashboard:** http://localhost:7200  
**Default login:** admin / root (free edition — create a repository first)

### `.env` settings

```env
GRAPHDB_ENABLED=true
GRAPHDB_BASE_URL=http://localhost:7200
GRAPHDB_REPOSITORY=flexible-graphrag
GRAPHDB_USERNAME=admin
GRAPHDB_PASSWORD=root
```

### Setup

The repository is **auto-created on first ingest** with RDF 1.2 annotation support enabled. No manual setup required.

If you prefer to create it manually (or need custom settings):

1. Open http://localhost:7200
2. **Setup → Repositories → Create new repository**
   - Type: GraphDB Repository
   - Repository ID: `flexible-graphrag`
   - Enable RDF-star: ✅ (required for RDF 1.2 `{| |}` annotations and `rdf:reifies`)
3. Click **Create**

### Dashboard usage

GraphDB Workbench has the richest visual exploration of the three stores:

- **Explore → Visual graph** — click any entity to see its connections as a graph diagram
- **Explore → Graphs overview** — lists all named graphs with triple counts
- **SPARQL** tab — full SPARQL 1.1/1.2 editor with syntax highlighting and results table/download
- **Import** tab — upload Turtle/TriG files directly

Use the same SPARQL queries as Fuseki above. GraphDB also supports:

**Visual graph exploration:**  
Explore → Visual graph → search for `Alfresco Software` → click to expand neighbours

**Class hierarchy:**  
Explore → Class hierarchy → shows all `onto:` types extracted (company, employee, project, etc.)

**Download:** SPARQL results → CSV / JSON / TSV buttons in the results toolbar.

---

## Oxigraph

**Dashboard:** http://localhost:7878  
**No login required.**

### `.env` settings — HTTP mode (recommended)

```env
OXIGRAPH_ENABLED=true
OXIGRAPH_URL=http://localhost:7878
```

Uses the Oxigraph Docker container as an HTTP server. No file-locking issues; safe for concurrent requests from the API server.

### `.env` settings — Embedded mode

```env
OXIGRAPH_ENABLED=true
OXIGRAPH_STORE_PATH=./data/oxigraph_store
```

Uses `pyoxigraph` directly with a local RocksDB file store. **Limitations:**
- Only one process can hold the file lock at a time — if the API server is running, a second ingestion request will fail with `IO error: Failed to create lock file: LOCK`
- Not recommended when the backend API server is already running
- Best suited for standalone scripts or single-process use

The adapter auto-recovers from RocksDB corruption (`CURRENT file corrupted`) by wiping and recreating the store directory.

### Docker setup (HTTP mode)

```yaml
# docker/includes/oxigraph.yaml — already configured
command: ["serve", "--bind", "0.0.0.0:7878", "--location", "/data"]
```

The `--bind 0.0.0.0:7878` flag is required — without it the Oxigraph HTTP server binds to `127.0.0.1` inside the container and is unreachable from the host via Docker port forwarding.

Start with:
```bash
docker compose --profile oxigraph up -d
```

### Dashboard usage

Oxigraph's dashboard is a minimal YASGUI SPARQL editor only — no visual graph or data browser. Results can be downloaded as CSV, JSON, or TSV from the toolbar.

Add these prefixes to every query (YASGUI doesn't persist them):
```sparql
PREFIX base: <https://integratedsemantics.org/flexible-graphrag/kg/>
PREFIX onto: <https://integratedsemantics.org/flexible-graphrag/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
```

**All entities and relations:**
```sparql
SELECT ?subjectLabel ?relName ?objectLabel WHERE {
  GRAPH <https://integratedsemantics.org/flexible-graphrag/kg> {
    ?s ?rel ?o .
    ?s rdfs:label ?subjectLabel .
    ?o rdfs:label ?objectLabel .
    BIND(STRAFTER(STR(?rel), STR(onto:)) AS ?relName)
    FILTER(?relName != "")
  }
}
ORDER BY ?subjectLabel ?relName
```

**RDF 1.2 annotations (meaningful only):**
```sparql
SELECT ?subjectLabel ?relName ?objectLabel ?prop ?val WHERE {
  GRAPH <https://integratedsemantics.org/flexible-graphrag/kg> {
    ?s ?rel ?o .
    ?s rdfs:label ?subjectLabel .
    ?o rdfs:label ?objectLabel .
    FILTER(STRSTARTS(STR(?rel), STR(onto:)))
    BIND(STRAFTER(STR(?rel), STR(onto:)) AS ?relName)
    OPTIONAL {
      ?reifier rdf:reifies <<( ?s ?rel ?o )>> ;
               ?annprop ?val .
      BIND(STRAFTER(STR(?annprop), STR(onto:)) AS ?prop)
      FILTER(?prop NOT IN ("source","file_name","file_path","file_type",
                           "modified_at","conversion_method","ref_doc_id"))
    }
  }
}
ORDER BY ?subjectLabel ?relName ?objectLabel ?prop
```

**Raw data download** (outside YASGUI):
```
GET http://localhost:7878/store?graph=https://integratedsemantics.org/flexible-graphrag/kg
Accept: text/turtle
```

---

## Store Comparison

| Feature | Fuseki 5 | GraphDB 10 | Oxigraph 0.5 |
|---------|----------|-----------|--------------|
| RDF 1.2 `{\| \|}` annotation syntax | ✅ | ✅ | ✅ |
| Legacy RDF-star `<< >>` syntax | ✅ | ✅ | ✅ |
| SPARQL 1.2 (`rdf:reifies`) queries | ✅ | ✅ | ✅ |
| Visual graph explorer | ❌ | ✅ | ❌ |
| Class hierarchy view | ❌ | ✅ | ❌ |
| Named graph browser | ✅ | ✅ | ❌ |
| SPARQL editor + download | ✅ | ✅ | ✅ (minimal) |
| HTTP mode | ✅ | ✅ | ✅ |
| Embedded mode | ❌ | ❌ | ✅ (single-process) |
| License required | No | Free tier available | No |
| Auth | Basic (admin / admin) | Basic (admin / root) | None |

---

## LangChain RDF Retrieval

When `USE_LANGCHAIN_RDF=true`, extracted RDF data is queried at search/Q&A time via LangChain graph QA chains fused into the same `QueryFusionRetriever` as vector, BM25, and property graph results.

### How it works

1. A natural language query arrives at `/api/search` or `/api/qa`
2. **`SynonymExpander`** (if `USE_SYNONYM_EXPLODER=true`) generates related keywords and adds them to the query bundle — the original query string is preserved unchanged for SPARQL generation
3. **`TextToGraphQueryRetriever`** translates the query to SPARQL via LangChain and executes it against the configured RDF store
4. Results are returned as a synthesized answer node, scored and ranked alongside all other retriever results

### Per-store chain type

| Store | Adapter | LangChain chain |
|---|---|---|
| GraphDB | `GraphDBLangChainAdapter` | `OntotextGraphDBQAChain` (dedicated) |
| Fuseki | `FusekiLangChainAdapter` | `GraphSparqlQAChain` (generic) |
| Oxigraph | `OxigraphLangChainAdapter` | `GraphSparqlQAChain` (generic) |
| Neptune RDF | `NeptuneRDFAdapter` | `GraphSparqlQAChain` (generic) |

### Configuration

```env
USE_LANGCHAIN_RDF=true
RDF_STORE_TYPE=graphdb        # graphdb | fuseki | oxigraph

# Optional: expand query keywords before SPARQL generation
USE_SYNONYM_EXPLODER=true
SYNONYM_EXPLODER_SCOPE=langchain_rdf_graph   # or: all | none | comma-separated tag list
```

### Additional LangChain PG retrievers (property graphs)

When `GRAPH_DB=neo4j` is set, two additional retrievers can be enabled alongside the RDF retriever:

- **`GraphEntityVectorRetriever`** (`LANGCHAIN_PG_VECTOR_SEARCH=true`) — Neo4j entity embedding similarity search via LangChain
- **`GraphNeighborhoodRetriever`** (`USE_PG_NEIGHBORHOOD=true`) — k-hop graph expansion from seed entity nodes

---

## Implementation Status

A summary of what is confirmed working, what is wired but untested end-to-end, and what is not yet implemented.

### Fully Working

These paths are confirmed working end-to-end.

| Component | Notes |
|-----------|-------|
| **Document ingestion via UI** | Upload docs in the UI → KG extracted → entities/relations written to all enabled RDF stores simultaneously; works with `INGESTION_STORAGE_MODE=rdf_only` or `both` |
| **Hybrid Search tab (UI)** | RDF store results fused into search results alongside vector, BM25, and property graph; requires `USE_LANGCHAIN_RDF=true` and at least one store enabled; all three stores confirmed working |
| **AI Query / Chat tab (UI)** | Same fusion pipeline as Hybrid Search; RDF store contributes SPARQL-generated answers to AI responses; all three stores confirmed working |
| **Incremental update / auto-sync** | Auto-sync checkbox in UI triggers incremental update engine; on document delete or modify, `_delete_from_rdf_stores(ref_doc_id)` is called across all enabled stores before re-ingest; two-pass SPARQL DELETE by `onto:ref_doc_id` |
| Ontology loading | Loads `.ttl` / RDF/OWL; extracts entity + relation type lists for `SchemaLLMPathExtractor` / `DynamicLLMPathExtractor` |
| KG → RDF conversion | LlamaIndex `EntityNode`/`Relation` → `rdflib.Graph` Turtle with RDF 1.2 `{| |}` annotations; provenance key filter prevents doc metadata leaking onto reifiers |
| Fuseki adapter | Connect, append graphs, `delete_doc` (SPARQL DELETE WHERE), SPARQL SELECT — confirmed working |
| GraphDB adapter | Same capability set — confirmed working |
| Oxigraph adapter | pyoxigraph parses RDF 1.2 Turtle in-process, re-serialises to N-Quads, POSTs to HTTP store — confirmed working |
| RDF store factory | Creates correct adapter from `rdf/store/rdf_store_factory.py` by type string (`fuseki`, `graphdb`, `oxigraph`) |
| Hybrid system ingest integration | `_export_nodes_to_rdf_stores()` called after every KG extraction; pushes to all enabled stores |
| LangChain RDF QA fusion | `TextToGraphQueryRetriever` via all three store adapters (Fuseki, GraphDB, Oxigraph); fused into `QueryFusionRetriever` alongside vector/BM25/PG |
| `SynonymExpander` | LLM-based query keyword expansion applied per-retriever |
| `GraphEntityVectorRetriever` | Neo4j entity vector search via LangChain (`LANGCHAIN_PG_VECTOR_SEARCH=true`) |
| `GraphNeighborhoodRetriever` | k-hop graph expansion from seed nodes (`USE_PG_NEIGHBORHOOD=true`) |
| Manual cleanup utility | `scripts/rdf_cleanup.py` — `list-docs`, `count`, `clear-doc <ref_doc_id>`, `clear-all` |
| XSD-typed literals | `OntologyManager.get_xsd_type_map()` + `_infer_xsd_type()` emit `xsd:date`, `xsd:decimal`, etc. from OWL `DatatypeProperty` range |

### Implemented — Not Yet Tested End-to-End

Code exists and is wired into the app, but these paths have not been verified in testing.

| Component | How to reach it | Notes |
|-----------|----------------|-------|
| `GET /api/rdf/ontology/info` | REST API | Returns loaded ontology entity/relation type lists |
| `POST /api/rdf/ontology/upload` | REST API | Upload a new ontology file at runtime |
| `POST /api/rdf/query/sparql` | REST API | Routes to `UnifiedQueryEngine` → SPARQL against configured RDF store |
| `POST /api/rdf/query/cypher` | REST API | Routes to `UnifiedQueryEngine` → Cypher against configured property graph |
| `POST /api/rdf/query/natural-language` | REST API | Routes to `UnifiedQueryEngine` → NL-to-query via LLM |
| `POST /api/rdf/rdf-store/*` | REST API | Connect/list/disconnect RDF stores at runtime |
| `UnifiedQueryEngine` | `rdf/unified_query_engine.py` | Query routing between SPARQL (RDF stores) and Cypher (PG); not called by the UI — use Hybrid Search / AI Query tabs instead |
| Neptune RDF adapter | `langchain/graph/langchain_adapters/neptune_rdf_adapter.py` | `NeptuneRDFAdapter` + `GraphSparqlQAChain`; implemented, no test environment |
| `delete_doc()` on all adapters | All three adapters | Called automatically by incremental update engine on document delete/modify; also callable manually via `rdf_cleanup.py clear-doc <ref_doc_id>`. **Not called automatically when re-ingesting the same document manually** via the upload UI without first deleting it — use `rdf_cleanup.py clear-doc <ref_doc_id>` to avoid duplicate triples in that case |

### Not Implemented / Stubbed

| Component | Notes |
|-----------|-------|
| `POST /api/rdf/export/rdf` | Hard `501 Not Implemented` stub — raises `HTTPException(501, ...)`. Use direct HTTP export to store endpoints instead (see per-store sections above) |
| `/api/rdf/import` | No import endpoint exists anywhere |
| Automatic delete on re-ingest (manual upload) | `delete_doc()` is called automatically by the incremental update engine, but **not** when re-uploading the same document manually via the UI without deleting it first; triples accumulate. Workaround: `scripts/rdf_cleanup.py clear-doc <ref_doc_id>` before re-ingesting |
| RDF-native extraction | Proposed design only (LLM produces Turtle directly from ontology + doc chunk, bypassing `kg_to_rdf_converter.py`); not started |
| OWL domain/range enforcement | LLM sees flat label lists — domain/range constraints from the ontology are not enforced on LLM output; LLM may use a relation on entity types outside its declared domain/range |
| Subclass hierarchy awareness | LLM sees flat label list — `rdfs:subClassOf` structure is not passed to the extractor |

### Reference / Example Files

These files in `examples/rdf/` are standalone rdf usage examples  — not re-tested.

| File | Purpose |
|------|---------|
| `examples/rdf/unified_query_engine_examples.py` | Usage examples for `UnifiedQueryEngine` |
| `examples/rdf/sparql_examples.py` | Sample SPARQL queries |
| `examples/rdf/store_index_example.py` | Example: build a LlamaIndex from an RDF store |
| `examples/rdf/ontology_guided_ingestion_example.py` | Example: `OntologyAwarePropertyGraphBuilder` usage |
| `examples/rdf/rdf_export_import_examples.py` | Export/import examples |
| `examples/rdf/config_rdf_stores.py` | Config snippets / reference |
| `examples/rdf/ingest_with_ontology.py` | `OntologyAwarePropertyGraphBuilder` example class |
| `rdf/sparql_property_graph_wrapper.py` | Executes SPARQL over a property graph via an RDF representation wrapper; standalone utility, not wired into the app |

