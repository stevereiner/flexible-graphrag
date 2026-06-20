# Changelog

All notable changes to this project will be documented in this file.

## [2026-06-19] v0.6.3 — Frontend package cleanup and icons

### Fixed

- **`frontend-react/package.json` + `package-lock.json`** — version bumped to `0.6.3`; added `public/react.svg` (React atom icon); `index.html` favicon updated from generic Vite logo to React icon; title updated to `Flexible GraphRAG (React)`.
- **`frontend-vue/package.json` + `package-lock.json`** — name corrected from `cmis-graphrag-vue` to `flexible-graphrag-vue`; version bumped to `0.6.3`; added `public/vue.svg` (Vue V-logo); `index.html` favicon updated.
- **`frontend-angular/package.json` + `package-lock.json`** — name corrected from `cmis-graphrag-ui` to `flexible-graphrag-ui`; version bumped to `0.6.3`.

---

## [2026-06-19] v0.6.3 — Python 3.14 patches, Docker env fixes

### Fixed

- **`flexible-graphrag/main.py`** — `CancelScope` patch rewritten to use `id()`-based set; `anyio 4.14+` uses `__slots__` which prevented the old attribute assignment and crashed httpcore connections.
- **`flexible-graphrag/main.py`** — `AsyncShieldCancellation` replacement now also patches cached references in `httpcore._async.*` modules (imported before our patch runs).
- **`flexible-graphrag/main.py`** — Added `_patch_ssl_context()`: clears `ssl.VERIFY_X509_STRICT` and loads Windows OS cert store via `load_default_certs()` to fix `APIConnectionError` when antivirus/proxy installs a local root CA.

### Changed

- **`docker/docker-env-sample.txt`** — added `ENABLE_OBSERVABILITY=false` override (prevents OTLP export errors when no collector is running) and commented `OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318` option for when observability stack is active.

---


## [2026-06-18] v0.6.3 — Docker production builds and image publish pipeline

### Added

- **`flexible-graphrag/.dockerignore`** — excludes `.env`, virtual environments, local DBs (`ladybug/`, `arcadedb_data/`), uploads, and logs from the backend image.
- **`flexible-graphrag-ui/frontend-react/Dockerfile`** — rewritten as multi-stage build: Node 24 Alpine builder (`npm run build`) + `nginx:stable-alpine` serve; static files placed at `/ui/react/` with SPA fallback and gzip.
- **`flexible-graphrag-ui/frontend-react/nginx.conf`** — nginx config serving React at `/ui/react/` with 1-year immutable cache on hashed assets.
- **`flexible-graphrag-ui/frontend-react/.dockerignore`**
- **`flexible-graphrag-ui/frontend-vue/Dockerfile`** — same multi-stage pattern as React; serves at `/ui/vue/`.
- **`flexible-graphrag-ui/frontend-vue/nginx.conf`** — nginx config serving Vue at `/ui/vue/`.
- **`flexible-graphrag-ui/frontend-vue/.dockerignore`**
- **`flexible-graphrag-ui/frontend-angular/Dockerfile`** — multi-stage build: runs `generate-env-config.ts` with `DOCKER_MODE=true`, then `ng build --configuration=production --base-href /ui/angular/`; serves static files at `/ui/angular/` via nginx.
- **`flexible-graphrag-ui/frontend-angular/nginx.conf`** — nginx config serving Angular at `/ui/angular/` with SPA fallback.
- **`flexible-graphrag-ui/frontend-angular/.dockerignore`**
- **`.github/workflows/docker-publish.yml`** — builds all 4 images in parallel on `v*` tag push; pushes to `docker.io/integratedsemantics/` and `ghcr.io/stevereiner/` with semver, `major.minor`, and `latest` tags; multi-platform (`linux/amd64`, `linux/arm64`).

### Changed

- **`flexible-graphrag/Dockerfile`** — rewritten to install optional extras via `ARG EXTRAS` build argument (default `langchain,langchain-extras,rdf,observability`); uses `--override extras-overrides.txt` to suppress advisory-only transitive downgrades; `extras-overrides.txt` now copied before the install step so it is available at build time.
- **`docker/includes/app-stack.yaml`** — added `image: integratedsemantics/<name>:${FLEXIBLE_GRAPHRAG_VERSION:-latest}` to all four services alongside existing `build:` contexts.
- **`docker/nginx/nginx.conf`** — Angular `location /ui/angular/` simplified to direct `proxy_pass http://angular/ui/angular/` (removed rewrite + `sub_filter`); all three UIs now use the same proxy pattern.
- **`flexible-graphrag/pyproject.toml`** — version bumped to `0.6.3`.
- **`flexible-graphrag-mcp/pyproject.toml`** — version bumped to `0.6.3`.

---

## [2026-06-02] v0.6.2 — version updated

### Changed

- **`flexible-graphrag/pyproject.toml`** — version updated from `0.6.1` to `0.6.2`.
- **`flexible-graphrag-mcp/pyproject.toml`** — version updated from `0.6.1` to `0.6.2`.

---

## [2026-05-30] - .env/.env-sample cleanup: remove legacy individual DB vars, add cloud examples

### Changed

- **`flexible-graphrag/.env`** and **`flexible-graphrag/env-sample.txt`** — Removed the "DATABASE CONNECTION DETAILS (Individual Configs)" section and all legacy individual DB vars (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `QDRANT_HOST`, `QDRANT_PORT`, `ELASTICSEARCH_URL`, `WEAVIATE_URL`, `OPENSEARCH_URL`, etc.); replaced with a renamed **"CHUNK Size and KG Extraction Configuration"** section containing only chunk size and KG extraction settings. Per-store config vars (`{TYPE}_*_DB_CONFIG`) in their own sections above are the sole connection config path.
- **Neo4j graph config section** — Added `neo4j_database` example and a commented Neo4j AuraDB cloud example using the `neo4j+s://` TLS scheme.
- **Qdrant vector config section** — Added commented Qdrant Cloud / remote HTTPS example with `https: true` and `api_key`.
- **Weaviate vector config section** — Added examples with `text_key`, `grpc_port`, `timeout` options and a Weaviate Cloud (WCS) example.
- **Docling Config section** — Moved `DOCLING_TIMEOUT` and `DOCLING_CANCEL_CHECK_INTERVAL` comments here from the chunk/KG section; KG timeout vars (`KG_EXTRACTION_TIMEOUT`, `KG_CANCEL_CHECK_INTERVAL`) remain in the chunk/KG section.
- **OpenAI-Like LLM and Embedding sections** — Added LM Studio example info and connection details.

---

## [2026-05-29] - Docker env config style, ontology paths in Docker, ArcadeDB embedded naming

### Changed

- **`docker/docker.env`** — Removed all legacy unprefixed `GRAPH_DB_CONFIG`, `VECTOR_DB_CONFIG`, `SEARCH_DB_CONFIG`, `NEO4J_URI`, `QDRANT_HOST`, `ELASTICSEARCH_URL` vars; replaced with per-store prefixed equivalents (`NEO4J_GRAPH_DB_CONFIG`, `QDRANT_VECTOR_DB_CONFIG`, `ELASTICSEARCH_SEARCH_DB_CONFIG`, etc.) matching the precedence order already used by `config.py`. All PG, vector, search, and RDF store overrides now appear as prefixed vars with Scenario A / Scenario B commented options.
- **`docker/docker-env-sample.txt`** — Same overhaul as `docker.env`: all config vars switched to the per-store prefixed style; Scenario A (`host.docker.internal`) and Scenario B (Docker service name) variants documented inline for every supported store.
- **`docker/includes/app-stack.yaml`** — Added `../../schemas:/app/schemas:ro` volume mount so ontology `.ttl` files from the repo root `schemas/` directory are available inside the backend container at `/app/schemas/`. Fixes `USE_ONTOLOGY=true` failures ("file not found") when running the backend in Docker.
- **`docker/docker.env`** — Added `ONTOLOGY_DIR=schemas/` override (resolves against container `/app` cwd) so `USE_ONTOLOGY=true` works in full-stack Docker without changing `.env`. Added `POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@postgres-pgvector:5432/flexible_graphrag_incremental` override (Docker service name + internal port 5432) so `ENABLE_INCREMENTAL_UPDATES=true` works; `.env` default uses `localhost:5433` which is unreachable from inside the backend container.
- **`docker/DOCKER-ENV-SETUP.md`** — Updated examples to use per-store prefixed config vars throughout; added troubleshooting entries for ontology path failures and incremental Postgres connection refused.
- **`README.md`** — ArcadeDB embedded pip package corrected from `arcadedb` to `arcadedb-embedded` in the Optional prerequisites section and the full source-install quickstart block; added comment pointing to `flexible-graphrag/pyproject.toml` for all available extra options.
- **`docs/GETTING-STARTED/PYTHON-BACKEND.md`** — PyPI install step for ArcadeDB embedded corrected from `arcadedb` to `arcadedb-embedded`; added `--override extras-overrides.txt` to the `langchain-extras` install command; added comment pointing to `pyproject.toml` for all extra options.

---

## [2026-05-28] - Frontend package name cleanup

### Fixed

- **`flexible-graphrag-ui/frontend-react/package.json`** — Renamed package from `cmis-graphrag-react` to `flexible-graphrag-react`; removed hardcoded `--port 5174` from the `dev` script (port now read from `vite.config.ts`).
- **`flexible-graphrag-ui/frontend-vue/package.json`** — Renamed package from `cmis-graphrag-vue` to `flexible-graphrag-vue`.

---

## [2026-05-26] - Fix default Neo4j port (Bug #14)

### Fixed

- **`flexible-graphrag/config.py`** — Default Neo4j Bolt URI for the property graph store corrected from `bolt://localhost:7689` to `bolt://localhost:7687` (standard Neo4j port). The 7689 value and caused connection failures when NEO4J_GRAPH_DB_CONFIG url was not set in `.env` and neo4j uses the default port.

---

## [2026-05-17] - LlamaParse 1.x to 2.x migration

### Changed

- **`flexible-graphrag/pyproject.toml`** — Replaced `llama-parse<1.0` + `llama-cloud<2.0` with `llama-cloud>=2.1` (the unified v2 SDK). The old `llama-parse` package is no longer a dependency.
- **`flexible-graphrag/process/document_processor.py`** — Migrated LlamaParse integration from v1 API (`llama_parse.LlamaParse`, `aget_json()`, flat kwargs) to v2 API (`llama_cloud.AsyncLlamaCloud`, two-step `files.create()` + `parsing.parse()`, structured `processing_options`/`output_options`/`agentic_options`). Old v1 `parse_mode` names (`parse_page_with_llm`, `parse_page_with_agent`, `parse_page_without_llm`) are mapped to v2 tiers via `_TIER_MAP` for backward compatibility. `job_id` now correctly reads from `result.job.id`.
- **`flexible-graphrag/env-sample.txt`** — LlamaParse config block updated for v2: `LLAMA_CLOUD_API_KEY` added as canonical env var name (old `LLAMAPARSE_API_KEY` still accepted); `LLAMAPARSE_MODE` documented with both v1 legacy names and v2 tier names (`fast`, `cost_effective`, `agentic`, `agentic_plus`); `LLAMAPARSE_AGENT_MODEL` removed (model is auto-selected by tier in v2); `LLAMAPARSE_LANGUAGE` and `LLAMAPARSE_CUSTOM_PROMPT` added (map to `processing_options.ocr_parameters.languages` and `agentic_options.custom_prompt` respectively).

---

## [2026-05-15] (v0.6.1) - Packaging fix, README and description improvements

### Fixed

- **`flexible-graphrag/pyproject.toml`** — `adapters*` was missing from `[tool.setuptools.packages.find] include`, causing `ModuleNotFoundError: No module named 'adapters'` after a PyPI install. Added `adapters*` to the explicit include list. 

### Updated

- **`flexible-graphrag/pyproject.toml`** — Version bumped to `0.6.1`. `description` rewritten to be keyword-rich (AI context platform, document processing, KG auto-building, GraphRAG/RAG, hybrid search types, LLM/DB counts, both frameworks).
- **`flexible-graphrag/README.md`** (PyPI short readme) — First paragraph replaced with the canonical project intro from the root README. Install paragraph rewritten as a proper quick-start (code block, LLM key note, `rdf/schemas/` copy hint, LlamaIndex-only caveat with link to [Framework Configuration](https://stevereiner.github.io/flexible-graphrag/CONFIGURATION/LANGCHAIN-CONFIGURATION/) docs, pointer to full README for Docker/frontend/extras).
- **`flexible-graphrag/start.py`** — Docstring usage comment corrected: `uv run python -m start` replaced with `python -m start` (the former only works from a source checkout directory, not a PyPI install).
- **`flexible-graphrag-mcp/pyproject.toml`** — Version bumped to `0.6.1`. `description` updated, "HTTP bridge" replaced with "connects to" (neutral re stdio/HTTP transport), DB / data source counts added to description.
- **`flexible-graphrag-mcp/README.md`** — Top paragraph replaced with the canonical project intro. Second sentence clarifies this package is the MCP server. "HTTP bridge/client" and raw `GET /api/status` references removed.

---

## [2026-05-13] (v0.6.0) - Status API config, README/package metadata, ontology env docs, LangChain install story

### Added

- **`backend.py`** — `get_system_status()` builds `status.config` with **`rdf_graph_db`**, **`enable_knowledge_graph`**, and **`graph_backend`**, **`vector_backend`**, **`search_backend`**, **`chunker_backend`**, **`kg_extractor_backend`**, **`retrieval_fusion`** (returned by **`GET /api/status`** and MCP **`get_system_status`**). **`get_config()`** returns the same keys as that `config` object, plus **`search_db`**.

### Removed

- **`flexible-graphrag/langchain/langchain-requirements.txt`** — Obsolete flat dependency list; use **`pyproject.toml`** **`[project.optional-dependencies]`** (e.g. `.[langchain]`, `.[langchain,langchain-extras]`, `age-extras`, `surrealdb-extras`, `spanner-extras`).

### Updated

- **Repository `README.md`** — Broader doc refresh (dual framework intro, RDF/Neptune, optional-install cheat sheet, Framework/Optional/Prerequisites); not repeated line-by-line here.
- **`flexible-graphrag/README.md`** (PyPI short readme) — Peer-framework blurb, repo / full README / docs links, note that optional extras are **only** in **`pyproject.toml`**.
- **`flexible-graphrag-mcp/README.md`** — Intro + **duplicate** repo / full README / docs link block under the MCP Server heading for quick copy-paste.
- **`docs/DATABASES/RDF/ontology_examples_and_config.md`** — Clarified that ontologies guide KG extraction for both property graph databases and RDF triple stores (not RDF-only). Removed the `RDF_GRAPH_DB` config block and link that implied otherwise. All schema paths corrected to `../schemas/...` (repo root, matching `env-sample.txt`). Added install-type note explaining source checkout vs PyPI schema placement. Per-example `.env` snippets updated to consistent `../schemas/` paths.
- **`pyproject.toml`** (**`flexible-graphrag`** and **`flexible-graphrag-mcp`**) — **`keywords`** expanded for PyPI/search alignment (graph, RDF, hybrid search, MCP, etc.).
- **`env-sample.txt`** — **Ontology** section: **comments only** (paths and `ONTOLOGY_PATHS` defaults unchanged): documents repo **`schemas/`** layout and sample **`.ttl`** file names.
- **`extras-overrides.txt`** — Dropped redundant llama-cloud / llama-parse **commentary**; version pins for those stay in **`pyproject.toml`** only.

---

## [2026-05-08] (v0.6.0) - Incremental Delete Fixes, Docling OCR, Dependency Compatibility

### Added

Configurable Docling OCR: `DOCLING_OCR=true` + `DOCLING_OCR_ENGINE` (auto / rapidocr / easyocr / tesseract_cli / tesserocr / ocrmac). Optional extras `docling-ocr-easyocr`, `docling-ocr-tesserocr`, `docling-ocr-ocrmac`. `Docling OCR config (app):` log line records the requested engine separately from Docling's own runtime selection message.

### Fixed

**Incremental delete** now works end-to-end for all active databases in LangChain-backed mode:
- Qdrant — `QdrantVectorAdapter.delete()` queries `metadata.ref_doc_id`, `metadata.doc_id`, and flat variants
- Elasticsearch — `ElasticsearchSearchAdapter.delete()` uses `delete_by_query` across both `ref_doc_id` and `doc_id` metadata keys
- Neo4j — `ref_doc_id` injected into entity node properties and stamped on `Chunk` nodes after `add_graph_documents`
- RDF (GraphDB) — SPARQL DELETE confirmed working; debug logging added to adapter
- LlamaIndex Elasticsearch — uses `await store.adelete()` to avoid event-loop conflict in async engine path

**`langchain-age` Python 3.14** — pinned to `langchain-age==0.1.2` (standalone package; requires `antlr4>=4.11`). The PyPI `0.2.0` used `antlr4<4.11` causing `TypeError: ord()` on startup. New `age-extras` optional group.

**`omegaconf` / `antlr4` conflict** — `extras-overrides.txt` pins `omegaconf>=2.4.0.dev10` so `rapidocr` (bundled in `docling-slim[standard]`) and `langchain-age==0.1.2` coexist in one environment.

**SPARQL hallucination** — `_GraphDBQAChain` and `_GenericSparqlQAChain` return an empty string (skip LLM call) when a query yields 0 rows; previously the LLM answered from training data.

**`check_elasticsearch.py`** — reads document text from `text` key (LangChain) in addition to `content`/`page_content`; `--content-len` arg; all metadata fields printed.

---

## [2026-05-07] - v0.6.0 — Spanner + Cosmos Gremlin Cloud Graphs, Cleanup for All 15 PG Stores

### Added

`PG_GRAPH_DB=spanner` — Google Cloud Spanner Graph via LlamaIndex (`llama-index-spanner`), `spanner-extras` dependency group. Auto-creates `{graph_name}_NODE` / `{graph_name}_EDGE` tables and property graph on first ingest.

Auto-create graph container on first ingest for Cosmos Gremlin (uses `ClientSecretCredential` to avoid antivirus false positives) and Spanner — no manual setup required.

Per-store setup guides: `COSMOS-GREMLIN-SETUP.md`, `NEPTUNE-SETUP.md` (rewritten), `SPANNER-SETUP.md` — linked from `DATABASE-CONFIGURATION.md` and docs nav.

### Fixed / Improved

`scripts/cleanup.py` — all 15 property graph stores now have native-client cleanup (previously LC-only stores had no automated path). Spanner table names corrected (`{graph_name}_NODE` / `_EDGE`). Early exit before slow imports when `VECTOR_DB=none` / `SEARCH_DB=none` / `PG_GRAPH_DB=none`. PostgreSQL incremental state cleanup skipped when `ENABLE_INCREMENTAL_UPDATES=false`. Windows `ProactorEventLoop` teardown error suppressed.

### Updated

`pyproject.toml` version `0.6.0` for flexible-graphrag and flexible-graphrag-mcp. `PG_GRAPH_DB` picker in `.env` / `env-sample.txt` reorganised: **LI + LC** (8), **LI only** (Spanner), **LC only** (6)

---

## [2026-05-06] - Spanner LI Adapter, Cosmos Gremlin Cloud Config, Neptune Analytics + Neptune RDF, Namespace From Config

### Added

`PG_GRAPH_DB=spanner` — Google Cloud Spanner property graph now uses **LlamaIndex** via `llama-index-spanner` (`SpannerPropertyGraphStore`). Supports cloud and emulator. New `spanner-extras` optional dependency group (`uv pip install -e ".[spanner-extras]"`). Config keys: `project_id`, `instance_id`, `database_id`, `graph_name`, `credentials_file` (optional; uses ADC if absent). This supersedes the LC-only `langchain-google-spanner` which requires `langchain-core<1.0` and is incompatible.

`PG_GRAPH_DB=cosmos_gremlin` cloud config documented — `COSMOS_GREMLIN_GRAPH_DB_CONFIG` cloud format added to `.env`, `env-sample.txt`, and `CONFIG-PROPERTY-GRAPH.md`: `{"url": "wss://my-cosmos.gremlin.cosmos.azure.com:443/", "username": "/dbs/<db>/colls/<graph>", "password": "<primary_key>"}`.

`RDF_GRAPH_DB=neptune_rdf` — Amazon Neptune RDF/SPARQL backend with IAM SigV4 auth. Included in the integration test matrix.

`PG_GRAPH_DB=neptune_analytics` LangChain backend — `NeptuneAnalyticsAdapter` passes explicit AWS credentials via `SecretStr` (no env-var race), wraps `NeptuneAnalyticsGraph` in `_NeptuneGraphWithWrite` to add `add_graph_documents` support. Both LlamaIndex and LangChain backends validated end-to-end.

### Fixed

SPARQL namespace prefixes and graph URIs now use `RDF_BASE_NAMESPACE` / `RDF_ONTOLOGY_NAMESPACE` from `config.py` across all RDF adapters (Fuseki, Oxigraph, GraphDB, Neptune). Defaults are unchanged.

### Updated

Property graph database counts corrected: **15 total** — 8 both LI+LC, 1 LI-only (Spanner), 6 LC-only (ArangoDB, Apache AGE, Cosmos Gremlin, HugeGraph, SurrealDB, TigerGraph). Updated in `DATABASE-CONFIGURATION.md`, `CONFIG-PROPERTY-GRAPH.md`, and `README.md`.

---

## [2026-04-06 → 2026-05-06] - LangChain as Full Peer Framework, New Databases, Retriever Refactor, Docs Site, Matrix Testing

### Added — LangChain as Full Peer Framework

Every pipeline stage can independently run on LlamaIndex or LangChain via env var pickers: `GRAPH_BACKEND`, `VECTOR_BACKEND`, `SEARCH_BACKEND`, `CHUNKER_BACKEND`, `KG_EXTRACTOR_BACKEND`, `RETRIEVAL_FUSION`. LangChain-only graph stores auto-select `GRAPH_BACKEND=langchain`.

`LC_SPLITTER_TYPE` selects from 6 LangChain text splitters: `recursive`, `character`, `token`, `markdown`, `python`, `sentence_transformers`.

`skip_graph` parameter added to `POST /api/ingest-text`, `POST /api/test-sample`, and corresponding MCP tools — ingests into vector/search without KG extraction.

### Added — New LangChain-Only Property Graph Backends

Seven new graph databases (auto-select `GRAPH_BACKEND=langchain`):

| `PG_GRAPH_DB` | Database | Port |
|---|---|---|
| `arangodb` | ArangoDB | 8529 |
| `apache_age` | Apache AGE (PostgreSQL + Cypher) | 5434 |
| `cosmos_gremlin` | Azure Cosmos DB Gremlin / TinkerPop | 8182 |
| `hugegraph` | Apache HugeGraph | 8082 |
| `surrealdb` | SurrealDB | 8010 |
| `tigergraph` | TigerGraph | 9002 / 14240 |
| `spanner` | Google Cloud Spanner (emulator supported) | 9010 / 9020 |

LangChain-backed ingestion + retrieval also added for all existing LlamaIndex-supported stores: `neo4j`, `arcadedb`, `falkordb`, `memgraph`, `nebula`, `neptune`, `neptune_analytics`, `ladybug`.

### Added — New LangChain Vector and Search Backends

New LC vector adapters (`VECTOR_BACKEND=langchain`): Milvus, Weaviate, LanceDB, Chroma, Pinecone, pgvector, OpenSearch — alongside existing Qdrant, Elasticsearch, Neo4j paths.

New LC search adapters (`SEARCH_BACKEND=langchain`): BM25 (in-memory), Elasticsearch, OpenSearch.

### Added — Adapter Layer Refactor

- **`adapters/`** — framework-neutral ABCs and factories for graph, vector, search, process, and LLM subsystems
- **`llamaindex/`** — all LlamaIndex-specific implementations extracted into subpackages (`graph/`, `llm/`, `vector/`, `search/`, `process/`)
- **`langchain/graph/pg_store_adapters/`** — one file per LC property graph store (15 stores)
- **`langchain/graph/retrievers/`** — `li_`/`lc_` two-layer retriever classes; `langchain/retriever_bridge.py` bridge classes
- **`langchain/vector/`**, **`langchain/search/`**, **`langchain/process/`** — LC adapters for each subsystem
- **`ingest/`** — fully modular pipeline steps: `run_chunk_pipeline`, `update_pg_graph`, `update_rdf_graph`, `update_vector`, `update_search`, `ingest_lc_graph`

### Added — New Docker Containers

| Service | Port(s) |
|---|---|
| Apache AGE (PostgreSQL + Cypher) | 5434 |
| Apache HugeGraph + Hubble UI | 8082, 8085 |
| SurrealDB + Surrealist UI | 8010, 8011 |
| TigerGraph Community 4.2.2 | 9002, 14240 |
| Apache TinkerPop Gremlin Server | 8182 |
| Google Spanner emulator | 9010, 9020 |

Standalone pgvector container added at port 5433 (separate from Alfresco PostgreSQL at 5432).

### Added — Retriever Architecture and Search Quality

- Result deduplication and rank-based re-scoring after fusion (`query_engine.py`)
- Source database label on every search result (e.g. *"file.txt | Qdrant vector"*, *"file.txt | Ontotext GraphDB rdf graph"*)
- SPARQL bi-directional fallback retry and improved keyword extraction for zero-result queries
- Cypher tri-part UNION pattern for organizational structure queries (Neo4j, ArcadeDB, Memgraph)
- NebulaGraph dynamic schema patch — `ALTER TAG/EDGE ... ADD` on `SemanticError` during arbitrary property insertion

### Added — Matrix Integration Testing

Full matrix test runner covering 44 backend profiles across both frameworks:
- `tests/integration/run_all_profiles.py` — sequential profile runner with `--clean`, `--include`/`--exclude`, per-profile backend logs, JSON result file
- 44 profiles: 17 property graph × 2 frameworks, 3 RDF stores, 10 vector stores, 4 search stores, combined and LC-pipe profiles
- Test files: `test_ingest_search.py`, `test_incremental.py`, `test_lc_pipeline.py`

### Added — Observability

- **LangChain OpenInference tracing** — `openinference-instrumentation-langchain` added to `observability` and `observability-dual` pyproject.toml groups; `LangChainInstrumentor` initialised alongside `LlamaIndexInstrumentor` in `telemetry_setup.py`; all `custom_hooks.py` span decorators made framework-agnostic with a `framework` kwarg and duck-typed result extraction for both LlamaIndex and LangChain response shapes
- **OpenLIT minimum version bumped to `>=1.41.2`** — this release fixed the long-standing `openai` downgrade (1.x → 2.x); all OpenLIT pyproject.toml groups (`observability-openlit`, `observability-dual`) updated; openai downgrade warnings removed from docs and README
- **Separate KG extraction and graph store timings** — ingestion log now shows distinct elapsed times for the KG extraction phase (LLM calls) and the graph store write phase, making it easier to identify whether latency comes from the LLM or the database

### Changed — Configuration

- **DB pickers**: `PG_GRAPH_DB` (15 stores), `RDF_GRAPH_DB` (4 stores), `VECTOR_DB` (10 stores), `SEARCH_DB` (4 stores) — replace the old generic env vars
- **Per-store config precedence**: `{TYPE}_GRAPH_DB_CONFIG` / `{TYPE}_VECTOR_DB_CONFIG` / `{TYPE}_SEARCH_DB_CONFIG` take priority over generic blobs
- **Per-kind embedding vars**: `OPENAI_EMBEDDING_MODEL`, `OLLAMA_EMBEDDING_MODEL`, `GOOGLE_EMBEDDING_MODEL`, etc. — override generic `EMBEDDING_MODEL` per provider
- **`.env` / `env-sample.txt`** restructured: DB selection section first, then framework config section

### Changed — Documentation

- `README.md` — LangChain framework config, new graph/vector/search databases, framework pickers, updated project structure
- `docs/ADVANCED/LANGCHAIN/LANGCHAIN-GRAPH-INTEGRATION.md` — LangChain architecture, new graph store adapters
- `docs/ADVANCED/PORT-MAPPINGS.md` — new database service ports (AGE, HugeGraph, SurrealDB, TigerGraph, Gremlin, Spanner)
- `docs/CONFIGURATION/CONFIG-PROPERTY-GRAPH.md` — `PG_GRAPH_DB` picker, all 15 stores, per-store config
- `docs/CONFIGURATION/CONFIG-SEARCH-DATABASES.md` — `SEARCH_DB` picker, LC search backends
- `docs/CONFIGURATION/CONFIG-VECTOR-DATABASES.md` — `VECTOR_DB` picker, LC vector backends
- `docs/CONFIGURATION/LANGCHAIN-CONFIGURATION.md` — framework backend pickers, LC splitter types
- `docs/DATABASES/DATABASE-CONFIGURATION.md` — updated database overview
- `docs/DATABASES/GRAPH-DATABASES/NEBULA-SETUP.md` — dynamic schema patch notes
- `docs/DATABASES/GRAPH-DATABASES/NEBULA-LANGCHAIN-SETUP.md` — new: NebulaGraph LangChain backend setup guide
- `docs/GETTING-STARTED/ENVIRONMENT-CONFIGURATION.md` — restructured env sections
- `docs/HOME/HOME-DATABASES.md` — new LC-only graph databases
- `docs/MCP/MCP-TOOLS.md` — `skip_graph` parameter on `ingest_text` and `test_with_sample`

---

## [2026-04-16] - With existing / new md content will  how have a Zensical documentation website, including a user guide with coverage of the 13 data source forms and 4 tabs 

### Added
- **Zensical documentation site** — new `zensical.toml` config and `docs/` folder structure powering a full documentation site hosted on GitHub Pages at `https://stevereiner.github.io/flexible-graphrag/`; GitHub Actions workflow (`.github/workflows/docs.yml`) auto-deploys on push to `main`; new `HOME/`, `GETTING-STARTED/`, `CONFIGURATION/`, `UI-GUIDE/`, `DEVELOPER/`, `ADVANCED/` section folders with new index/hub pages for each section
- **Documentation website sections and navigation** — full `nav` tree configured in `zensical.toml` covering Getting Started, Configuration, UI Guide, Data Sources, LLM, Databases, MCP, Developer, and Advanced; combines existing and new Markdown content into a navigable site covering the full product
- **UI Guide with data source coverage** — new `UI-TAB-SOURCES.md` covers all 13 data source configuration forms; `UI-TAB-PROCESSING.md`, `UI-TAB-SEARCH.md`, `UI-TAB-CHAT.md` cover all 4 UI tabs; `UI-SCREENSHOTS.md` provides overview screenshots
- **New UI screenshots** — React, Angular, and Vue frontend screenshots for all 4 tabs in dark and light themes (8 screenshots per frontend); 13 React data source form screenshots covering all supported sources
- **New documentation pages** — `DEVELOPER-DOCS-SYSTEM.md` (local preview, build, deploy instructions) and HOME hub pages for all nav sections

### Changed
- **Documentation restructured into section folders** — existing `docs/` root files reorganized into section folders; `INCREMENTAL-UPDATE-AUTO-SYNC/` and `DOC-PROCESSING/` moved under `DATA-SOURCES/`; `GRAPH-DATABASES/`, `VECTOR-DATABASES/`, `RDF/` moved under `DATABASES/`; `OBSERVABILITY/` moved under `DEVELOPER/`; `LANGCHAIN/` moved under `ADVANCED/`; all cross-reference links updated in `zensical.toml`, docs files, and root `README.md`
- **UI Screenshots page** — React section first (before Angular and Vue); dark and light theme tabs for all three frontends
- **Angular UI** — replaced Alfresco favicon with standard Angular favicon; renamed leftover `cmis-graphrag-ui` project name to `flexible-graphrag-ui` in `package.json`, `angular.json` (project key, output path, and all `buildTarget` references)

## [2026-04-12] - Ladybug Package Rename, Version 0.5.2

### Fixed
- **MCP stdio crash on Python 3.14** (`flexible-graphrag-mcp/main.py`) — `nest_asyncio.apply()` in stdio mode (present since before 0.5.1, only now first tested on Python 3.14) patched `asyncio.run()` to use `loop.run_until_complete()`, causing anyio's task-state weakref lookup to receive `NoneType` as the host task (`TypeError: cannot create weak reference to 'NoneType' object`); Python 3.14 broke `nest_asyncio` compatibility (3.13 and earlier were unaffected); the 2026-04-05 fix removed it from HTTP mode only; now removed from stdio mode as well — all tools are `async def` using `await` so it was never needed in either mode; `nest-asyncio` dependency removed from `flexible-graphrag-mcp/pyproject.toml`
- **`ingest_text` / `test_with_sample` crash on Python 3.14** (`ingest/ingest_from_text.py`) — `search_index.refresh_ref_docs()` was called synchronously inside the async FastAPI event loop; the Elasticsearch vector store's sync `add()` internally calls `asyncio.get_event_loop().run_until_complete()` which raises `RuntimeError: This event loop is already running` on Python 3.14 (previously masked by `nest_asyncio`); the UI does not call these endpoints so the bug went unnoticed — it surfaced when called via MCP inspector; fixed by replacing `refresh_ref_docs()` with `await system.search_store.async_add(nodes)` — the same direct async path already used by `ingest_from_source.py`; filesystem ingest was unaffected as it already used the async path

### Changed
- **Version** — `flexible-graphrag` and `flexible-graphrag-mcp` bumped to **0.5.2** in their respective `pyproject.toml` files
- **`factories.py` Ladybug import** — `import ladybug as lb` replaces the old `real-ladybug` package import; aligns with the upstream package rename on PyPI
- **`pyproject.toml` Ladybug dependencies** — `real-ladybug` replaced by `ladybug>=0.15.3`; `llama-index-graph-stores-ladybug>=0.3.1` replaces the prior `llama-index-ladybug` specifier; both reflect the renamed packages now published under the `ladybug` namespace

## [2026-04-05] - MCP Server Fix, ingest_text Fix, Schema Move

### Fixed
- **MCP HTTP mode crash** (`flexible-graphrag-mcp/main.py`) — `nest_asyncio.apply()` called before `asyncio.run()` broke `anyio` backend detection on Python 3.14; now only applied in stdio mode, not HTTP mode
- **`ingest_text` / `test_with_sample` not working after modularization** (`ingest/ingest_from_text.py`) — still used pre-modularization `PropertyGraphIndex.from_documents([document], kg_extractors=[...])` which was missed when the pipeline was split into modules; aligned with `ingest_from_source.py`: run `run_kg_extractors_on_nodes` first, then `PropertyGraphIndex(nodes=nodes, kg_extractors=[])`; also added `storage_mode` check and RDF export path that were missing
- **Silent exception swallowing** (`backend.py` `_process_text_async`) — `str(e)` was empty for bare exceptions; `exc_info=True` added to both `RuntimeError` and `Exception` catch blocks so full traceback appears in log



### Fixed
- **Ontology relative-path resolution** — `ontology_path_anchor()` in `rdf/ontology_manager.py` now resolves relative `ONTOLOGY_*` paths against `os.getcwd()` only (no `find_dotenv` walk-up); matches normal shell semantics and avoids stale anchors when installed as a wheel
- **`FLEXIBLE_GRAPHRAG_PROJECT_DIR` removed** — env var and related logic removed from `ontology_manager.py`; not needed given cwd-based resolution

### Changed
- **Bundled TTL schemas removed from source tree** — `rdf/schemas/*.ttl` deleted from package; canonical schema files now live at repo-root `schemas/` (`C:\newdev3\flexible-graphrag\schemas\`)
- **`env-sample.txt` ontology defaults** — example paths updated from `./rdf/schemas/...` to `../schemas/...` (relative to backend cwd `flexible-graphrag/flexible-graphrag/`); notes added for absolute paths, tilde expansion
- **`config.py`** — `ontology_path` field description updated to reflect cwd-relative convention

## [2026-04-04] - FalkorDB ingest, 0.5.1, README, Ladybug replaces Kuzu

### Fixed
- **FalkorDB property-graph ingest** — `falkordb/graph.py` imports `stringify_param_value` by name, so patching `falkordb.helpers` alone had no effect; `llamaindex/graph/falkordb_param_patch.py` now patches **both** modules and stringifies bools, numpy embeddings, and non-identifier metadata keys (e.g. spaced keys) for valid `CYPHER ...` params

### Changed
- **Version** — `flexible-graphrag` and `flexible-graphrag-mcp` set to **0.5.1** in `pyproject.toml`
- **`README.md` Features** — explicit bullets for LLM providers (`LLM_PROVIDER`) and embedding backends (`EMBEDDING_KIND`)
- **Kuzu removed; Ladybug supported** — All Kuzu integration was removed from `factories.py`, `config`, Docker-related samples (`docker/`, `docker.env`), and `env-sample.txt` after Kuzu ended development; the stack now targets the **Ladybug** fork (`GRAPH_DB=ladybug`) for that role
- **`docs/PERFORMANCE.md`** — labeled legacy pending a full rewrite; historical **Kuzu** tables retained; top-of-file note calls out splitting **KG LLM extraction** time vs **graph DB insert** time when benchmarks are redone
- **`pyproject.toml`** — `packages.find` `include` adds `llamaindex*` so `llamaindex/graph` ships in the package

## [2026-04-03] - File Reorganization, Script Moves, Delete Fix

### Fixed
- **Ladybug incremental delete leaves entity nodes behind** — `delete(properties={'doc_id': ...})` silently matched nothing because entity nodes carry no `doc_id` property; see llama-index-ladybug changelog for fix details

### Changed
- **`cleanup.py` moved** from `flexible-graphrag/` to `scripts/`; `.env` loaded from `../flexible-graphrag/.env`, log files cleaned from app dir
- **`check_elasticsearch.py` moved** from `flexible-graphrag/` to `scripts/`; `.env` loaded from `../flexible-graphrag/.env`; handles missing index gracefully instead of crashing
- **`neptune_database_wrapper.py` moved** to `llamaindex/graph/`; import in `factories.py` updated accordingly
- **`document_processor.py` top-level duplicate removed** — canonical copy remains in `process/`; all imports already used `process.document_processor`
- **`requirements.txt` removed** — `uv` / `pyproject.toml` is the only supported install method; README updated to remove legacy `requirements.txt` install instructions

## [2026-04-02] - Ladybug NoneType Fix, Chunk Embedding Fix

### Fixed (llama-index-ladybug)
- `NoneType` crash in `get_rel_map` — `structured_query` returns `None` when the query matches no rows; added `pivot_response = pivot_response or []` null-guard (same pattern as existing `entity_rows or []` in `vector_query`)
- Chunk embeddings not stored on a fresh database — `upsert_nodes` now uses a single reliable path: DELETE existing chunk → DROP index → CREATE chunk with embedding inline → rebuild index, eliminating the broken "SET after index rebuild" approach that failed when no prior index existed

## [2026-04-01] - Ladybug Bug Fixes, Retry on Transient Errors, Logging Improvements

### Fixed
- **Ladybug relation table collision** (llama-index-ladybug) — reserved-keyword labels (e.g. `TIME`) used as both a node type and a relation label caused a native C++ crash; `safe_rel_label()` uses `_REL` suffix for relation tables to keep them distinct from node tables
- **Ladybug schema-defined relations not stored** (llama-index-ladybug) — schema relations (`PART_OF`, `IS_A`, `HAS`, `LOCATED_IN`, etc.) were silently not written to disk; fixed by pre-registering all `FROM/TO` type pairs and switching to typed `MATCH` before each `MERGE`
- **`SynonymExpanderRetriever._aretrieve`** (`langchain/graph/synonym_rewriter.py`) — called sync `llm.complete()` inside FastAPI's async event loop, causing `Detected nested async` crash on first cold search; now uses `await llm.acomplete()` with `_build_bundle()` factored out as a shared sync helper
- **`LoggingRetriever._aretrieve`** (`langchain/graph/logging_retriever.py`) — delegated to sync `inner.retrieve()` instead of `await inner.aretrieve()`; fixed to use the async path

### Added
- **Retry on transient OpenAI errors** — `query_engine.py` `search()` and `backend.py` `qa_query()` / `query_documents()` retry up to 3 times with 5 s / 10 s back-off on HTTP 400 / 429 / 500 / 503, connection errors, and timeouts; non-retryable "index not found" errors return an empty result immediately
- **`LOG_LEVEL` env var** (`main.py`) — controls both file and console log level at startup (default `INFO`); replaces hardcoded `logging.INFO`

### Changed
- **`requirements.txt` / `pyproject.toml`** — `real-ladybug>=0.15.3` and `llama-index-graph-stores-ladybug>=0.15.3` version pins updated to match bug-fix release

### Changed
- **`factories.py` — Ladybug schema resolution** — `schema_name='default'` now falls back to LlamaIndex `DEFAULT_VALIDATION_SCHEMA` (PERSON / ORG / PRODUCT / EVENT / … with WORKED_ON / PART_OF / …) when no ontology or custom schema is provided; embedding dimension auto-detected from embed model (`embed_dim` / `dimensions` / test embedding probe) and passed to `LadybugPropertyGraphStore`
- **`factories.py` — removed fresh-database wipe on startup** — the old Kuzu path deleted the entire database directory on every restart; Ladybug path preserves existing data across restarts
- **Logger suppressions** (`main.py`) — noisy third-party loggers capped at WARNING/ERROR to reduce console clutter: `azure.core`, `azure.storage.blob`, `aiohttp.connector`, `aiohttp.client`, `httpcore`, `httpcore.connection`, `httpcore.http11`, `openai._base_client`; asyncio `"Event loop is closed"` exceptions suppressed via a custom event-loop exception handler installed at startup

---

## [2026-03-29] - Ladybug Property Graph Support, hybrid_system.py Modularization

### Added — Ladybug Property Graph Store
- **`GRAPH_DB=ladybug`** — `LadybugPropertyGraphStore` integrated as a supported property graph backend alongside Neo4j, ArcadeDB, FalkorDB, etc.; set `GRAPH_DB=ladybug` in `.env`
- **Ladybug Explorer** — Docker container added (`docker/includes/ladybug-explorer.yaml`) for browsing the `.lbug` graph database
- **Configuration** (`env-sample.txt`, `config.py`, `factories.py`):
  - `LADYBUG_DB_DIR` / `LADYBUG_DB_FILE` — directory and filename for the `.lbug` database file (created automatically)
  - `LADYBUG_USE_VECTOR_INDEX=true` (default) — enables HNSW vector index on `Chunk.embedding`
  - `LADYBUG_STRUCTURED_SCHEMA=true` — enforces ontology-defined entity/relation types at ingest; `factories.py` builds `relationship_schema` from the loaded ontology manager or `GRAPH_DB_CONFIG`
  - `LADYBUG_STRICT_SCHEMA=true` — when structured schema is on, rejects LLM-extracted types not in the ontology; `false` (default) stores out-of-schema types as additional Ladybug table types alongside the schema-defined ones

### Changed — hybrid_system.py Modularization
- **`hybrid_system.py` split into focused sub-modules** — the monolithic `hybrid_system.py` (~2500 lines) restructured into:
  - `ingest/ingest_from_files.py` — file-based ingestion pipeline
  - `ingest/ingest_from_source.py` — data source ingestion (Alfresco, S3, GCS, Azure Blob, etc.)
  - `ingest/ingest_from_text.py` — direct text/document ingestion
  - `ingest/_helpers.py` — shared ingestion utilities
  - `process/document_processor.py` — Docling/LlamaParse document processing
  - `process/kg_extractor.py` — knowledge graph extraction (SchemaLLMPathExtractor, DynamicLLMPathExtractor, extractor routing)
  - `process/node_pipeline.py` — LlamaIndex ingestion pipeline (chunking, embedding)
  - `stores/index_manager.py` — vector store, search store, and graph index lifecycle management
  - `query_engine.py` — `search()` entry point, `get_query_engine()`, result filtering
  - `retriever_setup.py` — `QueryFusionRetriever` assembly from all configured modalities
  - `schema_manager.py` — ontology and structured schema loading
  - `hybrid_system.py` — reduced to `HybridSearchSystem` class wiring the sub-modules together

### Fixed
- **`cleanup.py`** — `cleanup_graph_store()` updated to handle `GRAPH_DB=ladybug` via `GraphDBType` enum; `cleanup_rdf_stores()` delegates to `scripts/rdf_cleanup.py clear-all` subprocess
- **`scripts/rdf_cleanup.py`** — updated store auto-detection and `--fuseki` / `--graphdb` / `--oxigraph` flags to read from the same `.env` vars as the main app
- **`check_elasticsearch.py`** — new diagnostic script: lists documents in the `hybrid_search_fulltext` Elasticsearch/OpenSearch index and tests doc_id query patterns; supports `--limit` and `--port` flags

---

## [2026-03-24] - LangChain Retrievers: added synonym expansion and graph vector, and LangChain  new LLMs support to match ones added for Flexible GraphRAG with Llamaindex

### Added
- **`SynonymExpander`** — LLM-based query keyword expansion applied per-retriever via `SYNONYM_EXPLODER_SCOPE` tag list; confirmed working with all three RDF stores
- **`GraphEntityVectorRetriever`** — LangChain Neo4j entity vector search; activates independently via `LANGCHAIN_PG_VECTOR_SEARCH=true`
- **`GraphNeighborhoodRetriever`** — k-hop graph expansion from seed nodes (APOC or variable-length path fallback)
- **`TextToGraphQueryRetriever`** (renamed from `TextToCypherRetriever`) — handles both SPARQL and Cypher backends
- **Native LangChain 1.x provider packages** — `langchain-anthropic`, `langchain-google-genai`, `langchain-google-vertexai`, `langchain-ollama`, `langchain-groq`, `langchain-fireworks`; all 13 providers use native classes; `openai_like`/`litellm`/`vllm`/`openrouter` use `ChatOpenAI` + `base_url` (correct for OpenAI-compatible endpoints)
- **`langchain` optional dependency group** (`pyproject.toml`) — `uv pip install -e ".[langchain]"` for the core LangChain 1.x stack; combine with **`langchain-extras`**, **`age-extras`**, etc. per **`pyproject.toml`** (see current README Optional / Install). *Later: flat `langchain/langchain-requirements.txt` was removed (2026-05-13) in favor of extras only.*

---

## [2026-03-21] - RDF/Ontology Support, LangChain RDF QA Fusion, Additional LLM Providers

### Added — RDF/Ontology Support
- **Ontology-guided extraction** (`rdf/ontology_manager.py`) — load OWL/RDFS ontologies to constrain entity/relation types for extraction into **any** property graph store (Neo4j, ArcadeDB, FalkorDB, etc.) or RDF store; `OntologyManager` exposes entity/relation label lists to `SchemaLLMPathExtractor`; LLM sees only plain-string labels, Python maps back to ontology URIs via `get_uri_map()`
- **Schema property support** (`hybrid_system.py`, `config.py`) — entity and relation properties now passed to both `SchemaLLMPathExtractor` (plain type-list schema) and `DynamicLLMPathExtractor` (ontology-guided); `DISABLE_PROPERTIES=true` skips property extraction for models that perform better without it; properties sourced from OWL `DatatypeProperty` definitions when an ontology is loaded
- **Multi-ontology file support** (`config.py`, `rdf/api_rdf_enhancements.py`) — `ONTOLOGY_PATHS` (CSV list) and `ONTOLOGY_DIR` env vars; `load_ontology_files()` and `load_ontology_dir()` added to `OntologyManager`
- **Bundled ontology schemas** (`rdf/schemas/`) — `company_classes.ttl`, `company_properties.ttl`, `common_ontology.ttl` (Person, Place, Event, Product, Topic, Location, etc.), `foaf_ontology.ttl`
- **RDF triple store backends** (`rdf/store/`) — Apache Jena Fuseki, Ontotext GraphDB, and Oxigraph; set `INGESTION_STORAGE_MODE=rdf_only` or `both`; `RDFStoreFactory`, `FusekiAdapter`, `OntotextGraphDBAdapter`, `OxigraphAdapter`
- **LangChain RDF QA fusion retriever** (`hybrid_system.py`, `langchain/graph/langchain_adapters/`, `langchain/graph/langchain_retriever_wrapper.py`) — RDF store and graph results fused into `QueryFusionRetriever` alongside vector/BM25; set `USE_LANGCHAIN_RDF=true` and `RDF_STORE_TYPE`; uses the **same LLM already configured** (no separate LLM setup); 3 RDF store adapters fully working: Fuseki, GraphDB, Oxigraph; 1 property graph adapter working: Neo4j (retrieval); Neptune RDF implemented (store + retrieve, untested); additional property graph adapters (ArangoDB, Apache AGE, Cosmos DB Gremlin, Spanner Graph) are placeholder stubs for future implementation
- **SPARQL query interface** — `UnifiedQueryEngine` routes between Cypher (property graphs), SPARQL (RDF stores), and natural language; `/api/rdf/query/sparql|cypher|natural-language` endpoints
- **RDF document delete** (`rdf/` adapters, `hybrid_system.py`, `incremental_updates/engine.py`) — two-pass SPARQL DELETE by `onto:ref_doc_id`; called automatically on incremental update/delete across all three stores
- **`scripts/rdf_cleanup.py`** — CLI tool: `list-docs`, `count`, `clear-doc <ref_doc_id>`, `clear-all`; auto-detects stores from `.env`; `--fuseki`, `--graphdb`, `--oxigraph` flags
- **`docs/RDF/RDF-ONTOLOGY-SUPPORT.md`** — RDF store setup, ontology configuration, data inspection, annotation syntax, cleanup utility
- **`docs/RDF/INGESTION-AND-STORAGE-MODES.md`** — ingestion mode comparison (property graph only, PG + RDF export, RDF primary)
- **`docs/LANGCHAIN/LANGCHAIN-GRAPH-INTEGRATION.md`** — LangChain RDF QA fusion retriever setup and adapter reference
- **Dependencies**: `rdflib>=7.0.0`, `pyoxigraph>=0.5`, `requests>=2.31.0`; optional `uv pip install -e ".[rdf]"` or `.[rdf-full]`

### Added — LLM Providers and Embeddings
- **OpenRouter LLM provider** (`config.py`, `factories.py`) — `LLM_PROVIDER=openrouter`; auto-switches to `DynamicLLMPathExtractor`; `context_window` and `max_tokens` set correctly
- **LiteLLM proxy provider** (`config.py`, `factories.py`) — `LLM_PROVIDER=litellm`; cloud and Ollama-backed models via proxy; `LITELLM_TIMEOUT=300.0` required for multi-chunk docs; **`scripts/litellm_config.yaml`** — sample proxy config (copy to your LiteLLM install dir); pre-wired for OpenAI `gpt-4o-mini`, `text-embedding-3-small`, and Ollama `gpt-oss:20b`, `llama3.3:70b`, `nomic-embed-text` with `host.docker.internal` for WSL2/Docker setups
- **`openai_like` and `litellm` embedding support** — `EMBEDDING_KIND=openai_like` targets any `/v1/embeddings` endpoint (e.g. Ollama `nomic-embed-text`); `EMBEDDING_KIND=litellm` routes through LiteLLM proxy (`LITELLM_EMBEDDING_API_BASE` must include `/v1`)
- **vLLM Docker container** (`docker/includes/vllm.yaml`) — optional GPU container port 8002; use via `LLM_PROVIDER=openai_like` on Windows
- **`docs/DOCKER-RESOURCE-CONFIGURATION.md`** — WSL2/macOS/Linux Docker memory sizing guide

### Changed — LLM Providers and Embeddings
- **`gpt-4.1-mini` recommended as default OpenAI model** (`env-sample.txt`, `docs/LLM/LLM-EMBEDDING-CONFIG.md`) — zero 0-entity failures, 3-4× faster on multi-chunk docs vs `gpt-4o-mini`; `gpt-5-mini` not recommended (LlamaIndex forces temperature=1.0 for O1/reasoning model family)
- **Groq, Fireworks, `openai_like` extractor routing** — added to `switch_to_dynamic_providers`; two LlamaIndex `DynamicLLMPathExtractor` prompt-template bugs patched in `_make_dynamic_extractor()`: `None→[]` props coercion and `{{`/`}}` double-brace escaping in `SafeFormatter`
- **Groq context window** (`factories.py`) — `_GROQ_CONTEXT` lookup table passes explicit `context_window`/`max_tokens` to `Groq()` (LlamaIndex falls back to 3900 for unknown model names → truncated output → 0 entities)
- **Fireworks streaming workaround** (`factories.py`) — `_FireworksStreaming` subclass overrides `_achat` with `stream=True` to bypass 4096-token non-streaming hard cap
- **`docs/PORT-MAPPINGS.md`** — updated: vLLM=8002, LiteLLM=4000

---

## [2026-03-13] - Windows Console Fixes and PostgreSQL Setup Improvements

### Fixed
- **Emoji and non-ASCII characters removed from `logger.*()` and `print()` calls** — Windows cp1252 console encoding caused `UnicodeEncodeError` at runtime; replaced with ASCII equivalents (`[OK]`, `[FAIL]`, `[WARN]`, `->`) across all affected files
- **Incremental updates PostgreSQL error handling** (`main.py`) — on startup failure now logs a clear actionable message; distinguishes server not running (connection refused) from database not created yet, with the appropriate `docker compose` command for each case
- **PostgreSQL init script converted from shell to SQL** (`docker/postgres-init/`) — `03-init-incremental-schema.sh` replaced with `03-init-incremental-schema.sql`; shell scripts created on Windows have `\r\n` line endings which cause "cannot execute: required file not found" in the Linux container; plain SQL files are unaffected; non-init helper scripts renamed to `.bak` so the entrypoint ignores them

---

## [0.4.0] - 2026-03-09 - Search result filtering, search only mode fix, fixes for building flexible-graphrag package

### Fixed
- **Bare relation links filtered in all modes** (`hybrid_system.py`) — `X -> REL -> Y` strings now filtered in hybrid mode, not just graph-only mode; filtered before `top_k` slice
- **Elasticsearch/OpenSearch-only ingestion crashed** (`hybrid_system.py`) — `_setup_hybrid_retriever` now reuses `self.search_index` instead of trying to rebuild it with an async client in a sync context
- **Misleading variable names** (`hybrid_system.py`) — `vector_only`/`search_only` renamed to `no_vector`/`no_search`
- **Clearer error when no retrievers ready** (`hybrid_system.py`) — distinguishes "not ingested yet" from "all DBs disabled"

### Added
- **`flexible-graphrag` console script** (`pyproject.toml`, `start.py`) — run backend with `flexible-graphrag` after `uv pip install flexible-graphrag`
- **`uv build` packaging fixes** (`pyproject.toml`) — version 0.4.0; PEP 639 license format; all 14 py-modules; `incremental_updates` package included; `Dockerfile`, `env-sample.txt`, `requirements.txt`, `uv.toml` included in sdist; placeholder `README.md` added
- **`flexible-graphrag-mcp` version aligned to 0.4.0** (`flexible-graphrag-mcp/pyproject.toml`) — Apache 2.0 license, author, readme added
- **README.md updated** — PyPI install quickstart (Option A); MCP server quickstart section with steps and tool table; badges for PyPI versions, pepy.tech download counts, license, Python, React, Angular, Vue; project structure updated with `incremental_updates/`, `observability/`, `sources/`, `ingest/`, docs subfolders; UI Usage section moved after frontend setup; Testing Cleanup updated to mention `cleanup.py` first

---

## [2026-03-08] - ArcadeDB Embedded Mode

### Added
- **ArcadeDB embedded mode** (`factories.py`, `config.py`, `env-sample.txt`) — runs in-process, no separate server required; set `ARCADEDB_MODE=embedded`; optionally enable HTTP/Studio via `ARCADEDB_EMBEDDED_SERVER=true`; `arcadedb-embedded>=26.2.1` added to dependencies (commented out)

### Changed
- **`llama-index-graph-stores-arcadedb` bumped to `>=0.4.1`** (`requirements.txt`, `pyproject.toml`)

---

## [2026-03-03] -  Search ranking low scores fixed, display search result filename, added 0.4.0 ArcadeDB packages

### Fixed
- **Search result ranking scores improved for hybrid search** (`hybrid_system.py`) - `QueryFusionRetriever` mode changed from `reciprocal_rerank` to `relative_score`; when combining vector, full-text, and graph retrievers, RRF always produced very low scores (~0.03) regardless of relevance; `relative_score` MinMax-scales each retriever's output to 0–1 giving meaningful rankings
- **Search results "Source" field showed "Unknown" in all three UIs** - backend sends `file_name` as a top-level field (not nested under `metadata`); all three UIs (`search-tab.html`, `SearchTab.tsx`, `SearchTab.vue`, `QueryForm.vue`) updated to use `result.file_name` as primary display, falling back to `result.source`
- **Graph search scoring fixed for graph-only** (`hybrid_system.py`) - when only graph search is active, results could scored 0.0 because `VectorContextRetriever` matches entity node IDs against TextChunk IDs (never a match); ; raw `uuid -> MENTIONS -> entity` triplets filtered before dedup

### Changed
- **`docker/includes/arcadedb.yaml` pinned to ArcadeDB 26.2.1** — changed from `latest` to ensure compatibility with the 0.4.0 arcadedb-python and arcadedb-llama-index packages and to have new vector support
- **`cleanup.py` — ArcadeDB-specific cleanup block added** - directly connects via `arcadedb_python`, queries all vertex/edge types from schema, and issues `DELETE FROM <type>` for each; bypasses the LlamaIndex factory which was causing "index already exists" errors and had no `clear()` implementation for ArcadeDB
- **`arcadedb-python` and `llama-index-graph-stores-arcadedb` pinned to `>=0.4.0`** in `requirements.txt` and `pyproject.toml` — version 0.4.0 enables working vector search and correct node deletion during incremental sync updates
- **Verbose ArcadeDB ingestion log lines moved to DEBUG level** (`hybrid_system.py`) - per-result score lines no longer appear in INFO logs; `ENTITY_TYPE_DETECTION`, `LLM_RELATION_INPUT`, `SQL_RELATION`, `Schema created successfully`, `Created LSM_VECTOR index`, `SQL_FALLBACK_SUCCESS`, and `Dynamically created VERTEX/EDGE type` moved to DEBUG in `arcadedb_property_graph.py` (part of `llama-index-graph-stores-arcadedb` 0.4.0)

## [2026-02-17] - PostgreSQL Auto-Setup, Azure Blob Change Feed, Alfresco Ports, Source Path Fixes & Docs Reorganization

### Added
- **Postgres & pgAdmin auto-setup on first use** - `docker/includes/postgres-pgvector.yaml` now runs init scripts on first container start: creates `flexible_graphrag` (for optional pgvector) and `flexible_graphrag_incremental` (incremental update state management) databases with schema. pgAdmin is pre-configured with both databases registered
- **docs/POSTGRES-SETUP.md** - New guide covering PostgreSQL for pgvector and incremental state management, pgAdmin access, and manual database operations
- **docs/DATA-SOURCES/AZURE-BLOB-SETUP.md** - UI-only setup guide for Azure Blob Storage: storage account, container, credentials, Flexible GraphRAG form configuration, and enabling Change Feed for auto-sync
- **Azure Blob Storage Change Feed support** - `azure_blob_detector.py` now uses the Azure Change Feed API for real-time event detection with fallback to periodic polling

### Changed
- **Alfresco OpenWire and STOMP ports updated** (`docker/includes/alfresco.yaml`) - Changed to avoid conflict with Windows dynamic port range; STOMP port now configurable via `env-sample.txt` and `main.py`
- **`modified_timestamp` column type changed from `TEXT` to `TIMESTAMPTZ`** - All detector files updated to use timezone-aware timestamps
- **Documentation reorganized into subfolders** (`docs/`) - Docs from `flexible-graphrag/incremental_updates/` and the backend root moved into: `DATA-SOURCES/`, `DOC-PROCESSING/`, `GRAPH-DATABASES/`, `INCREMENTAL-UPDATE-AUTO-SYNC/`, `LLM/`, `OBSERVABILITY/`, `VECTOR-DATABASES/`
- **README.md** - Added PostgreSQL/pgAdmin auto-setup info in Incremental Updates section; doc links updated to new subfolder locations
- **`source_path` field now human-readable** for Google Drive, OneDrive, and Azure Blob - stores filename/path instead of raw file IDs or temp paths; `doc_id` comparison logic fixed to correctly identify UUID-prefixed stable IDs vs. Windows drive letter paths


## [2026-02-14] - Neptune Integration & Documentation Updates

### Added
- **docs/NEPTUNE-SETUP.md** - Comprehensive setup guide for Neptune Database and Neptune Analytics with Graph Explorer configuration
- **neptune_database_wrapper.py** - Runtime override wrapper for T-class instances (db.t3.medium, db.t4g.medium) that lack Summary API; automatically falls back to openCypher queries

### Changed
- **docs/NEBULA-SETUP.md** - Updated with comprehensive schema configuration and troubleshooting
- **README.md** - Consolidated unsupported data sources into single row in Incremental Updates table; updated screenshot
- **factories.py** - Neptune Database uses `NeptuneDatabaseNoSummaryWrapper`; Neptune Analytics returns raw PropertyGraphStore

### Removed
- **neptune_analytics_wrapper.py** - Vector dimension configuration now documented in setup guide (must be set at graph creation, immutable)

## [2026-02-05] - Async Client Fixes for Weaviate and Elasticsearch

### Fixed
- **Weaviate async client integration**
  - Fixed "Async method called without WeaviateAsyncClient" by using `weaviate.use_async_with_custom()`
  - Added connection state management for async client throughout search, ingestion, and deletion operations
  - Fixed deletion using async `adelete()` method instead of sync `delete_ref_doc()`

- **Elasticsearch async operations**
  - Fixed `RuntimeError: Timeout context manager should be used inside a task` by calling `async_add()` directly
  - Fixed deletion query to use `match` instead of `term` (no keyword mapping) and `metadata.ref_doc_id` path
  - Multiple sequential ingests now work correctly with async client

- **Error handling improvements**
  - Friendly messages instead of errors when using search and AI query before ingestion (all vector/search stores)
  - Graceful handling for missing collections/indexes with user-friendly messages

### Added
- `check_elasticsearch.py` - Diagnostic tool to inspect Elasticsearch document structure and test queries
- `cleanup.py` - Unified cleanup script for all databases (vector, search, graph) with async client support

## [2026-01-23] - Incremental Updates (Auto-Sync) System

### Added - Core Infrastructure
- **Complete incremental update system** for automatic synchronization of data sources
- **Auto-sync support for 9 data sources**:
  - ✅ Filesystem (watchdog - real-time) **NEW**
  - ✅ Amazon S3 (SQS events - real-time, polling fallback) **NEW**
  - ✅ Alfresco (ActiveMQ, Event Gateway planned) - real-time, polling fallback) **NEW**
  - ✅ Azure Blob Storage (change feed - real-time, polling fallback) **NEW**
  - ✅ Google Cloud Storage (Pub/Sub - real-time, polling fallback) **NEW**
  - ✅ Google Drive (Changes API - polling) **NEW**
  - ✅ Box (Events API - polling) **NEW**
  - ✅ OneDrive (Microsoft Graph - polling) **NEW**
  - ✅ SharePoint (Microsoft Graph - polling) **NEW**
  - **Note**: Delta query support is planned but not fully implemented - all sources use polling for now

- **Auto-sync configuration supported via**:
  - 3 UI clients (Angular, React, Vue) - "Enable Auto-Sync" checkbox
  - MCP Server - `auto_sync` parameter in ingestion tools
  - REST API - `auto_sync` parameter in ingestion endpoints
  - **Note**: MCP Server and REST APIs already supported one-shot manual ingestion from all 13 data sources

### Added - UI Enhancements
- **Auto-sync configuration in UI** (Angular, React, Vue):
  - "Enable Auto-Sync" checkbox for all data sources
  - S3: "SQS Queue URL" field for event notifications
  - GCS: "Pub/Sub Subscription Name" field for real-time updates

### Added - MCP Server and REST API Support
- **Auto-sync support via MCP Server and REST APIs**:
  - `auto_sync` parameter added to ingestion endpoints
  - Configure auto-sync data sources programmatically
  - Supports all 9 auto-sync enabled data sources
  - Complements existing manual ingestion support for all 13 data sources

### Added - REST APIs
- **Incremental update control endpoints**:
  - Trigger immediate sync for configured data sources
  - Set and query polling intervals
  - Query sync status and history
  - Manage auto-sync configurations
- See `incremental_updates/API-REFERENCE.md` for complete API documentation

### Added - Documentation
- `incremental_updates/README.md` - System overview and architecture
- `incremental_updates/QUICKSTART.md` - Quick setup guide
- `incremental_updates/SETUP-GUIDE.md` - Detailed configuration guide
- `incremental_updates/API-REFERENCE.md` - API endpoints and usage
- `incremental_updates/GCS-SETUP.md` - Google Cloud Storage configuration
- `incremental_updates/S3-SETUP.md` - Amazon S3 SQS configuration
- `incremental_updates/detectors/README.md` - Detector implementation details

### Added - Scripts
- `scripts/incremental/sync-now.sh|.ps1|.bat` - Trigger immediate sync
- `scripts/incremental/set-refresh-interval.sh|.ps1|.bat` - Configure polling interval
- `scripts/incremental/README.md` - Script usage guide
- `scripts/incremental/TIMING-CONFIGURATION.md` - Timing configuration details

### Added - Docker Configuration
- **PostgreSQL/pgvector** (`docker/docker-compose.yaml`):
  - Added `includes/postgres-pgvector.yaml` enabled by default
  - Used for both vector database option and incremental updates state management

- **Alfresco real-time events** (`docker/includes/alfresco.yaml`):
  - Enabled OpenWire (61616) and STOMP (61613) ports on ActiveMQ service
  - Enabled messaging subsystem auto-start: `-Dmessaging.subsystem.autoStart=true`
  - Enabled Event2 API: `-Drepo.event2.enabled=true`
  - Supports real-time incremental updates via CloudEvents

### Features
- **Real-time change detection** via event streams (S3 SQS, Alfresco ActiveMQ, GCS Pub/Sub)
- **Polling fallback** for all sources when events unavailable
- **Configurable refresh intervals** (default: 300 seconds)
- **Automatic deletion handling** - Removes deleted files from all indexes
- **Content-based deduplication** - Hash comparison prevents re-processing unchanged files
- **Timestamp optimization** - Skips downloads for files with unchanged timestamps (30x faster)
- **PostgreSQL state management**:
  - `datasource_config` table: Stores data source locations configured for auto-sync
  - `document_state` table: Tracks sync status, content hashes, and timestamps per document
- **Concurrent processing** - Parallel ingestion with configurable worker limits

## [2026-02-01] - Box Auto-Sync Fixes

### Fixed
- Fixed Box path storage to use stable paths instead of temporary file paths
- Fixed incomplete document_state records for Box files
- Fixed DELETE operations not removing legacy temp-path entries from indexes

## [2026-01-20] - Alfresco Real-time Events and Download Optimization

### Added
- **Real-time Alfresco event handling via direct STOMP connection**
  - Direct subscription to ActiveMQ on port 61613 for <1 second latency
  - Smart event-type-specific filtering for CREATE/UPDATE/DELETE
  - Thread-safe queue bridges STOMP callbacks to async processing

- **Download optimization**
  - Timestamp-based change detection skips downloads for unchanged files
  - 30x faster for unchanged files with zero network transfer
  - Migration script: `incremental_updates/migration_add_modified_timestamp.sql`

## [2026-01-26] - Document parser improvements and parsing output inspection

### Added
- **Parser output file saving** - Added `SAVE_PARSING_OUTPUT` to save parsing results to `./parsing_output/` for inspection
  - Both parsers save: markdown (`.md`), plaintext (`.txt`), and metadata JSON (`.json`)
- **LlamaParse plaintext and metadata** - LlamaParse now provides native plaintext in addition to markdown, and rich metadata (pages, images, job info)
  - Changed how LlamaParse is called to get plaintext directly from the parser (not regex-stripped) for higher accuracy
  - Metadata JSON includes page counts, character counts, image counts, and job information
- **Format control for extraction** - Added `PARSER_FORMAT_FOR_EXTRACTION` to control format used for processing
  - `auto` (default): markdown if tables, plaintext otherwise
  - `markdown`: always use markdown
  - `plaintext`: always use plaintext
- **Docling GPU documentation** - Added comprehensive GPU setup guide with CUDA, Metal (Mac), and CPU configuration
- **Error detection** - Automatic detection and logging in saved output files:
  - Parser errors (both parsers): checks for error strings in output
  - LaTeX/math expressions (both parsers): detects LaTeX that causes markdown preview rendering issues
    - Note: Docling passes LaTeX directly to output (visible as parse errors in VS Code/Cursor markdown viewer)
    - LlamaParse processes LaTeX differently (converts/modifies the output)
- **Chunking visibility** - Added detailed pre/post-chunking logging showing:
  - Document count and character lengths before SentenceSplitter
  - Node count, chunk sizes, and metadata preservation after chunking
  - Relationship tracking between chunks (SOURCE, PREVIOUS, NEXT)

### Changed
- Changed to call LlamaParse differently to get plaintext, metadata json, in addition to markdown

### Fixed
- **Issue #8: Long document processing** - Fixed processing failures with long PDFs
  - Tested with user document (7-8 page PDF with lots of tables - Docling CPU mode was taking forever)
  - Verified Docling GPU mode works correctly (NVIDIA RTX 5090 - significantly faster)
  - Successfully tested with 80+ page 10-K PDF
  - Added `DOCLING_TIMEOUT` configuration (default: 600s per document)
  - Verified LlamaParse works with user files

### Documentation
- Added `docs/DOCLING-GPU-CONFIGURATION.md` - GPU setup and troubleshooting guide
- Added `docs/PARSER-OUTPUT-FILES.md` - Parser output documentation
- Added `docs/DOCUMENT-GRANULARITY.md` - Document processing pipeline and chunking behavior
- Updated `README.md` and `env-sample.txt` with new configuration options


## [2026-01-22] - Knowledge graph extractor improvements and schema naming updates

### Added
- **New extractor documentation** - Added `docs/KNOWLEDGE-GRAPH-EXTRACTORS.md` with complete coverage of SimpleLLMPathExtractor, SchemaLLMPathExtractor, and DynamicLLMPathExtractor including internal schema details, strict mode explanation, and provider-specific behaviors
- **Entity/relationship validation** - Added filtering in `count_extracted_entities_and_relations()` to remove entities/relationships with empty labels, preventing Neo4j `'' is not a valid token name` errors

### Changed
- **Schema naming simplification** - `SCHEMA_NAME=default` now uses internal schema (was `none`), `SCHEMA_NAME=sample` uses SAMPLE_SCHEMA (was `default`). Updated `config.py`, `env-sample.txt`, and all docs
- **SAMPLE_SCHEMA format** - Changed from `Literal` types to plain lists to fix DynamicLLMPathExtractor validation errors
- **Provider extractor switching** - Bedrock/Groq/Fireworks now auto-switch from `schema` to `dynamic` extractor (was `simple`) for better structured extraction while avoiding tool-calling issues
- **Extraction limit defaults** - Changed `MAX_TRIPLETS_PER_CHUNK` and `MAX_PATHS_PER_CHUNK` defaults from 100 to 20 in `config.py` and `SAMPLE_SCHEMA` for better balance of speed and quality
- **Environment variable priority** - `MAX_TRIPLETS_PER_CHUNK` and `MAX_PATHS_PER_CHUNK` from `.env` now take priority over values in schema configuration
- **Strict mode default** - `strict` parameter now defaults to `false` for better flexibility in extraction
- **Google embeddings flexibility** - Google embedding models (text-embedding-004, text-multilingual-embedding-002) can now be used with any LLM provider, not just Google LLMs
- **Synchronous extraction for all providers** - Pre-extraction and `insert_nodes()` now run synchronously for all LLM providers (not just Gemini) to avoid async event loop conflicts and state pollution
- **Enhanced observability** - `graph_span` now tracks `num_documents` in addition to `num_nodes` for better insight into batch operations

### Fixed
- **"2nd ingest chunk only" bug for Bedrock/Groq/Fireworks (#12)** - Fixed issue where these providers only created chunk nodes (no entities/relationships) on incremental ingests by auto-switching from SchemaLLMPathExtractor (which has tool-calling bugs) to DynamicLLMPathExtractor
- **DynamicLLMPathExtractor with default schema** - Fixed `pydantic.ValidationError` by converting SAMPLE_SCHEMA from Literal to list format
- **Empty label errors** - Added filtering to remove entities/relationships with empty labels before Neo4j insertion, fixing DynamicLLMPathExtractor reliability issues on incremental ingests

### Documentation
- Added `docs/KNOWLEDGE-GRAPH-EXTRACTORS.md` - 568-line comprehensive extractor guide
- Updated `docs/SCHEMA-EXAMPLES.md` - New naming convention and reordered to highlight internal schema
- Updated `docs/LLM-TESTING-RESULTS.md` - Provider-specific auto-switching behavior, more models now working with dynamic extractor
- Updated `env-sample.txt` - Clearer KG_EXTRACTOR_TYPE descriptions and new SCHEMA_NAME defaults


## [2026-01-10] - Knowledge graph extractor refactoring

### Changed
- **Simplified knowledge graph extractor handling** - Refactored `_run_kg_extractors_on_nodes()` in `hybrid_system.py` to eliminate repeated code
  - Now validates exactly one extractor (current production usage)

### Fixed
- **Gemini/Vertex AI second document ingestion** - Fixed async event loop error when adding documents to existing graph by running `insert_nodes()` directly in main context (not executor) for Gemini/Vertex providers


## [2026-01-09] - Ollama timeout and async event loop fixes

### Fixed
- **Ollama ReadTimeout during graph extraction** - Fixed `httpx.ReadTimeout` errors during knowledge graph entity/relationship extraction by increasing default `OLLAMA_TIMEOUT` from 300s (5 min) to 900s (15 min) in `config.py`
  - Ollama's internal `AsyncClient` already properly uses `request_timeout` parameter
  - Graph extraction with Ollama can take 5-15 minutes per document depending on model size and content complexity
  - Users can override with `OLLAMA_TIMEOUT` environment variable for even longer documents
- **Async event loop conflict when adding documents to existing graph** - Fixed `RuntimeError: <asyncio.locks.Event> is bound to a different event loop` error
  - Root cause: `graph_index.insert_nodes()` is synchronous but uses `asyncio.run()` internally, causing conflict when called from async context
  - Solution: Wrapped `insert_nodes()` call in `run_in_executor()` at line ~1960 in `hybrid_system.py` to isolate event loop
  - Solution: Temporarily clear `_kg_extractors` before calling `insert_nodes()` since extraction already completed manually
  - Affects all LLM providers (OpenAI, Ollama, Claude, etc.) during graph updates with multiple documents
  - **Restored functionality**: Ollama models (llama3.1:8b, llama3.2:3b, gpt-oss:20b) and Anthropic Claude (sonnet-4-5, haiku-4-5) now extract full entities/relationships correctly

### Changed
- **Updated extraction defaults** - Changed `MAX_TRIPLETS_PER_CHUNK` and `MAX_PATHS_PER_CHUNK` defaults from 100 to 20
  - Updated `config.py` lines 172-173: `max_triplets_per_chunk: int = 20`, `max_paths_per_chunk: int = 20`
  - Updated `SAMPLE_SCHEMA` in `config.py` line 509: `"max_triplets_per_chunk": 20`
  - Updated `docs/SCHEMA-EXAMPLES.md` recommendations with 20 as standard default
  - Testing showed 20 provides good balance: captures most entities (e.g., gpt-oss:20b extracted 30 entities vs 34 with limit of 100)
  - Faster processing during ingestion while maintaining extraction quality for typical documents
  - Users can increase to 50-100 for dense/complex content via environment variables
- **Updated Ollama embedding default** - Changed default embedding model from `all-minilm` to `nomic-embed-text` in `config.py` line 209
  - `all-minilm` has 512-token context limit causing "input length exceeds context length" errors when embedding graph nodes (combined entity + relationship text)
  - `nomic-embed-text` has 8192-token context and 768 dimensions (vs 384 for all-minilm), providing better quality and reliability
  - Updated `env-sample.txt` lines 387-392 with warning about `all-minilm` limitations and recommendation to use `nomic-embed-text`

### Documentation
- Updated `flexible-graphrag/env-sample.txt` with `OLLAMA_TIMEOUT=900.0` documentation and notes about ReadTimeout errors
- Added Windows installation note in `README.md` about Microsoft C++ Build Tools requirement for compiling Docling dependencies (tree-sitter-java-orchard)
- Added warning in `env-sample.txt` about `all-minilm` context limitations for graph node embeddings
- Updated `docs/LLM-TESTING-RESULTS.md` to reflect restored functionality:
  - Ollama models (llama3.1:8b, llama3.2:3b, gpt-oss:20b) now work with full entity/relationship extraction
  - Anthropic Claude (sonnet-4-5, haiku-4-5) now creates proper entities/relationships (not just chunk nodes)
  - Updated test summary table and recommendations reflecting event loop fixes

## [2026-01-08] - Gemini async compatibility fixes

### Fixed
- **Gemini LLM event loop conflicts (Issue #11)** - Fixed "Future attached to different loop" errors during graph extraction and searching by running extractors directly in main async context instead of ThreadPoolExecutor for Gemini/Vertex AI providers
- **Google embeddings API key with non-Google LLM providers** - Fixed Google embeddings not working with OpenAI/Ollama/etc LLM providers by correctly retrieving GOOGLE_API_KEY from environment instead of using LLM provider's API key

### Added
- **Configuration validation** - Added startup validation to prevent incompatible combinations: Google/Vertex embeddings require Gemini/Vertex AI LLM due to async SDK limitations

### Documentation
- Updated `docs/LLM-TESTING-RESULTS.md` to reflect Gemini/Vertex AI now fully functional with graph indexing (marked "Fixed 2026-01-08")

## [2026-01-03] - MCP server enhancements for complete REST API parity

### Enhanced
- **MCP server full feature parity** - `ingest_documents` tool now supports all backend REST API features for use with Claude Desktop and other MCP clients:
  - Existing `paths` parameter (for filesystem, Alfresco, CMIS) continues to work as before; other repositories (SharePoint, Box, etc.) use their own config parameters
  - Added `skip_graph` parameter for faster performance on a per-ingest basis (vector + search only, no knowledge graph) - works with all data sources
  - Added support for all 13 data sources: `filesystem`, `cmis`, `alfresco`, `web`, `wikipedia`, `youtube`, `s3`, `gcs`, `azure_blob`, `onedrive`, `sharepoint`, `box`, `google_drive`
  - Added configuration parameters for each data source as JSON strings (e.g., `alfresco_config`, `s3_config`, etc.)
  - Added `nodeDetails` list support for Alfresco integration with ACA (Alfresco Content App) multi-select
  - Tool now accepts same parameters as `/api/ingest` REST endpoint with automatic JSON parsing

### Documentation
- Updated `flexible-graphrag-mcp/README.md` with comprehensive tool documentation including parameter descriptions and configuration examples
- Added examples for filesystem with `skip_graph`, CMIS with single path, Alfresco with single path and with `nodeDetails` list, and Amazon S3 cloud storage
- Updated `flexible-graphrag-mcp/QUICK-USAGE-GUIDE.md` to reflect all 13 data sources and clarify parameter applicability (`paths` for filesystem/Alfresco/CMIS, `skip_graph` for all sources, `nodeDetails` list for Alfresco only; other repositories use config-specific parameters)
- Updated main `README.md` MCP Tools section with clarified parameter descriptions
- Clarified MCP client support to indicate "Claude Desktop and other MCP clients" for broader applicability

## [2026-01-02] - Entity/Relation counting fix for incremental ingestions

### Fixed
- **Entity/relation counting in PATH 3** - Fixed incremental graph updates (second+ documents) showing 0 entities/0 relations by running KG extractors before counting in `hybrid_system.py` line ~1849-1864

## [2025-12-30] - OpenLIT DUAL mode observability integration

### Added
- **DUAL mode observability** - Combined OpenInference + OpenLIT as dual OTLP producers for comprehensive monitoring
- `ObservabilityBackend` enum in `config.py` with three modes: `openinference`, `openlit`, `both` (recommended)
- `observability_backend` field in Settings class with proper Pydantic integration
- Explicit datasource UIDs in Grafana provisioning (`uid: prometheus`, `uid: jaeger`) for reliable dashboard connections
- Auto-refresh (30s) to observability dashboards for real-time monitoring

### Enhanced
- Complete token usage tracking (input/output tokens by model)
- Cost tracking with per-hour and cumulative metrics  
- VectorDB operation monitoring
- LLM latency histograms (P50/P95/P99)
- Dashboard metric queries updated to match OpenLIT output format
- Grafana dashboard JSON files corrected for proper data visualization

## [2025-12-29] - Observability metrics enhancements

### Added
- **Entity and relation counting** - Knowledge graph extraction now tracks and displays entity/relationship counts in Grafana
- **Search and query metrics** - Document retrieval and LLM generation operations now record observability metrics
- Knowledge Graph Entities panel in Grafana showing extraction rates and totals
- Knowledge Graph Relations panel in Grafana showing extraction rates and totals

### Fixed
- **Grafana rate metrics** - Adjusted time window to properly display entity/relation extraction rates during short ingestion operations
- **Missing dashboard data** - Document Retrieval Latency and LLM Generation Latency panels now populate during search/query operations

### Documentation
- Created comprehensive observability documentation for entity/relation counting and search/query metrics
- Added troubleshooting guides for Grafana dashboard metrics

## [2025-12-27] - Observability support added with OpenTelemetry, Prometheus, Grafana, and Jaeger

### Added
- **OpenTelemetry instrumentation** - Comprehensive observability module (`flexible-graphrag/observability/`) with automatic LlamaIndex tracing via OpenInference
- **Custom tracing decorators** - `@trace_retrieval`, `@trace_llm_call`, `@trace_graph_extraction`, `@trace_document_processing` for adding tracing to custom code
- **RAG-specific metrics** - Automatic collection of retrieval latency, LLM token usage, graph extraction stats, document processing metrics, and error tracking
- **Metrics API** - `RAGMetrics` class with methods for recording custom metrics: `record_retrieval()`, `record_llm_call()`, `record_graph_extraction()`, etc.
- **Docker observability stack** - Complete stack with OTLP Collector, Jaeger (traces), Prometheus (metrics), and Grafana (dashboards)
- **Pre-configured Grafana dashboard** - "Flexible GraphRAG - RAG Metrics" dashboard with panels for retrieval latency (P95/P99), LLM generation latency, token usage, document processing rates, error tracking
- **Configuration options** - Added `ENABLE_OBSERVABILITY`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, and other observability settings to config
- **Comprehensive documentation** - Created `docs/OBSERVABILITY.md` with quick start, architecture diagrams, custom instrumentation examples, PromQL queries, and production checklist
- **Optional dependencies** - Added `[observability]` extras group in `pyproject.toml` for easy installation: `uv pip install -e ".[observability]"`

### Enhanced
- **Optional dependencies** - Observability packages (`openinference-instrumentation-llama-index`, `opentelemetry-exporter-otlp`, `opentelemetry-sdk`) are optional extras and gracefully degrade if not installed
- **Automatic initialization** - Observability automatically initializes on startup when `ENABLE_OBSERVABILITY=true` with proper error handling
- **Production-ready configuration** - Includes batch span processor, memory limiter, and configurable service metadata for production deployments
- **Docker Compose integration** - Added to `docker-compose.yaml` include list (commented by default) for easy one-line enabling

### Documentation
- **Updated README.md** - Added "Observability and Monitoring" section with quick start and dashboard access info
- **Updated env-sample.txt** - Added observability configuration section with all OTLP and service settings
- **Docker configuration** - Added `docker/includes/observability.yaml` for easy deployment of complete observability stack
- **OTLP collector config** - Created `docker/otel/otel-collector-config.yaml` with proper trace/metric pipelines
- **Prometheus config** - Created `docker/otel/prometheus.yml` with scrape configurations
- **Grafana provisioning** - Auto-provisions Prometheus and Jaeger datasources plus custom RAG metrics dashboard

## [2026-01-01] - LLM Testing Documentation and Query Timing Improvements

### Documentation
- **Comprehensive LLM testing results** - Updated `docs/LLM-TESTING-RESULTS.md` with complete test matrix for all 9 LLM providers (OpenAI, Azure OpenAI, Gemini, Vertex AI, Groq, Fireworks AI, Claude, Bedrock, Ollama)
- **Graph database compatibility** - Documented that compatibility patterns are LLM-dependent, not database-dependent (Neo4j, FalkorDB, ArcadeDB show identical behavior per LLM)
- **Graph-only mode testing** - Added results for configurations without vector/search databases
- **Updated test summary** - Added table showing specific models tested for each provider with graph extraction, search, and AI query results
- **Bedrock models** - Documented 11 tested models including cross-region inference profile requirements ("us." prefix for most models)

### Enhanced
- **Error logging in backend.py** - Improved error logging for better debugging and troubleshooting of processing failures with detailed error messages and tracebacks

## [2025-12-27] - Added 4 New LLM Providers: Vertex AI, Bedrock, Groq, and Fireworks AI

### Added
- **Google Vertex AI** - Google Cloud-hosted Vertex AI Platform Gemini models with dual package support (`llama-index-llms-vertex` or `google-genai`)
- **Amazon Bedrock** - AWS Bedrock supporting Amazon Nova, Titan, Anthropic Claude, Meta Llama, Mistral AI, etc.
- **Groq** - Fast low-cost LPU inference with OpenAI GPT-OSS, Meta Llama (4, 3.3, 3.1), Qwen3, Kimi, etc. (defaults to Ollama embeddings)
- **Fireworks AI** - Fast inference with fine-tuning support: Meta, Qwen, Mistral AI, DeepSeek, OpenAI GPT-OSS, Kimi, GLM, MiniMax, etc.
- **Independent embeddings** - All providers support separate embedding configuration (`EMBEDDING_KIND`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`)

### Enhanced
- Extended `LLMFactory` with all 4 new providers and their embedding models
- Updated `get_embedding_dimension()` with automatic detection for Vertex AI (768), Bedrock (1024/1536), Fireworks (768)
- Added intelligent provider defaults: Vertex AI → Vertex embeddings, Bedrock → Bedrock embeddings, Groq → Ollama embeddings, Fireworks → Fireworks embeddings

### Documentation
- Added configuration examples to `env-sample.txt` and `docs/LLM-EMBEDDING-CONFIG.md` for all 4 providers
- See [docs/LLM-EMBEDDING-CONFIG.md](docs/LLM-EMBEDDING-CONFIG.md) for detailed configuration examples and model options

## [2025-12-26] - Completed LLM setup support: Azure OpenAI (working), Google Gemini (issue), Anthropic (issue)

### Enhanced
- **Independent embedding provider configuration** - Embeddings can now be configured independently from LLM provider with new environment variables: `EMBEDDING_KIND`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`
- **Google Gemini embeddings support** - Added `text-embedding-004` model with configurable dimensions (768, 1536, or 3072)
- **Azure embeddings support** - Can be used with any LLM provider by setting `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and `AZURE_OPENAI_API_VERSION`
- **Embedding dimension detection** - Unified configuration across all database types using centralized `get_embedding_dimension()` function
- **Removed hardcoded dimension assumptions** - Eliminated `1536 if llm_provider == OPENAI else 1024` patterns in config.py that incorrectly assumed Ollama when not OpenAI

### Fixed
- **Mixed LLM/Embedding provider API key handling** - Correctly fetches credentials from environment for cross-provider scenarios (e.g., Azure LLM with OpenAI embeddings)
- **Azure embeddings deployment name** - Uses `EMBEDDING_MODEL` as deployment name by default, with optional `AZURE_EMBEDDING_DEPLOYMENT` override
- **Google Gemini LLM support** - Enabled for vector and search operations (graph search has known instrumentation issues)
- **Anthropic Claude LLM support** - Enabled for GraphRAG (creates chunk nodes only, no entity extraction)

### Tested
- Comprehensive LLM compatibility testing across Google Gemini, Anthropic Claude, Azure OpenAI, and Ollama models
- Mixed provider configurations validated (OpenAI LLM + Azure embeddings, Azure LLM + OpenAI embeddings, Gemini + OpenAI embeddings)
- See `docs/LLM-TESTING-RESULTS.md` for test results for new models and Ollama

## [2025-12-24] - OneDrive and SharePoint data sources fixed and now working

### Fixed
- **OneDrive authentication** - Corrected parameter name to `userprincipalname` for LlamaIndex library compatibility
- **SharePoint site resolution** - Fixed config parameters passed to SharePointReader constructor
- **Content extraction** - Both sources now return actual document content instead of empty text with metadata only, using PassthroughExtractor with DocumentProcessor for immediate file processing

### Added
- **Data source documentation** - Created `docs/DATA-SOURCE-CONFIGURATION.md` with setup guides for OneDrive, SharePoint, Box, and source path examples

### Documentation
- **Streamlined env-sample.txt** - Moved verbose Box config detail info, OneDrive/SharePoint details, and source path examples to `docs/DATA-SOURCE-CONFIGURATION.md` 

## [2025-12-23] - UI enhancements for skip graph and terminology updates

### Enhanced
- **Skip graph checkbox** - Added "Skip graph (search + vector only) for these documents" checkbox to Processing tab in all three frontends (Angular, React, Vue)
  - Positioned at top right of File Processing header
  - Sends `skip_graph` parameter to backend for per-ingest graph skipping
  - Completion messages automatically reflect whether graph was skipped
- **Tab naming updates** - Updated terminology to match KG Spaces ACA conventions
  - Main "SEARCH" tab renamed to "HYBRID SEARCH"
  - Search sub-tab "Q&A QUERY" renamed to "AI QUERY"
  - Main "CHAT" tab renamed to "AI CHAT"

## [2025-12-22] - Docker documentation updates for workflow clarity

### Documentation
- **Docker workflow improvements** - Updated README.md, docker/README.md, and docker/DOCKER-ENV-SETUP.md for better Docker setup workflow
  - Added environment file setup (`.env` and `docker.env`) before scenario configuration to prevent deployment without proper configuration
  - Changed all Docker commands to assume working from `docker/` directory (removed `docker/` prefix from paths)
  - Added `cd` navigation instructions before file operations for clearer directory context
  - Provided both Linux/macOS (`cp`) and Windows (`copy`) commands for cross-platform compatibility
  - Reordered configuration steps: environment files first, then scenario-specific docker-compose.yaml edits, then deployment

## [2025-12-21] - pyproject.toml added, readme and docker docs updated, errors fixed with llama-core only, switch to google-genai package

### Added
- **pyproject.toml support** - Created modern PEP 517/518 package definition for flexible-graphrag backend
  - Flat layout with py-modules for individual files (backend, config, etc.) and packages.find for ingest/sources subdirectories
  - All 409 dependencies migrated from requirements.txt with optional dev dependencies (pytest, black, ruff, mypy)
  - Python >=3.12,<3.14 requirement (3.12 and 3.13 supported, 3.14 has ChromaDB and Kuzu compatibility issues)
  - Virtual environment management via `managed = false` in [tool.uv] section (user controls venv creation/naming)
- **Docker pyproject.toml support** - Updated Dockerfile to use `uv pip install -e .` with pyproject.toml (legacy requirements.txt kept as commented alternative)
- **Backend REST API documentation** - Added comprehensive REST API endpoint table with all 16 endpoints, Swagger UI and ReDoc links to README

### Fixed
- **requirements.txt package conflicts** - Removed `llama-index` package, kept only `llama-index-core` to fix package version build errors
- **Deprecated Gemini package** - Updated from `llama-index-llms-gemini` to `llama-index-llms-google-genai` in both requirements.txt and factories.py
- **GoogleGenAI class** - Updated import and usage to correct `GoogleGenAI` class instead of deprecated `Gemini` class

### Enhanced
- **Docker documentation** - Updated docker/README.md and docker/docker-env-sample.txt with pyproject.toml approach and accurate service configurations
- **README.md improvements**
  - Reorganized Docker deployment scenarios (A/B/C/D/E) with clearer configuration guidance
  - Updated Supported File Formats with accurate Docling and LlamaParse capabilities
  - Enhanced Prerequisites with detailed cloud data source requirements
  - Added Backend Setup (Standalone) and Frontend Setup (Standalone) sections
  - Shortened and clarified deployment scenarios
  - Added Kuzu deprecation note (LadybugDB fork mention)
- **Backend setup** - Improved installation instructions with pyproject.toml examples, clarified venv management options

### Documentation
- Updated Prerequisites for Python 3.12 or 3.13 (requires-python = ">=3.12,<3.14", 3.14 has ChromaDB and Kuzu compatibility issues)
- Enhanced cloud data source requirements (AWS, GCP, Azure, Google Drive, Box, OneDrive for Business, SharePoint)
- Clarified Docker configuration (.env base + docker.env overrides, app-stack.yaml needs no configuration)

## [2025-12-15] - Alfresco relative_path enhancement and native path support

### Enhanced
- **Alfresco path-based operations** - Leveraged python-alfresco-api 1.1.5+ `relative_path` feature for improved performance
  - Traditional path-based access now uses `nodes.get("-root-", relative_path=path)` to resolve paths via Alfresco REST API
  - Converts path to node ID in single API call, then uses efficient node-based operations
  - Falls back to CMIS `getObjectByPath()` for backward compatibility with older python-alfresco-api versions
  - Provides consistent Alfresco REST API usage across both multi-select (nodeDetails) and traditional (path) modes
- **Performance improvements** - Path resolution now 3x faster using REST API instead of CMIS path traversal
  - Single REST API call vs multiple CMIS path traversal operations
  - Recursive folder operations use `list_children()` instead of repeated path resolution
  - Reduces overhead of CMIS initialization for path-only operations
- **Native Alfresco path format** - Alfresco now supports flexible native path formats
  - Use short format like `/Shared/GraphRAG` (matches Alfresco Share UI where /Company Home is hidden)
  - Or use full format like `/Company Home/Shared/GraphRAG` (both work)
  - System automatically strips `/Company Home` prefix when using `relative_path` (since `-root-` IS Company Home)
  - Works with Sites: `/Sites/my-site/documentLibrary/folder`
  - Works with User Homes: `/User Homes/username/My Files`
  - Works with Data Dictionary: `/Data Dictionary/Scripts`
- **CMIS path format compatibility** - CMIS data source now also strips `/Company Home/` prefix if present
  - Provides consistency between Alfresco and CMIS data sources
  - Users can use same path format for both Alfresco and CMIS repositories
  - Case-insensitive detection handles "Company Home", "company home", etc.
- **ACA/ADF integration paths** - Updated documentation to reflect native Alfresco paths from ACA integration
  - Paths from KG Spaces ACA plugin now include `/Company Home/` prefix (native Alfresco format)
  - All path fields (`path`, `paths`, `nodeDetails.path`) use full format with `/Company Home/`
  - System automatically handles the prefix for proper API calls

### Added
- **Dependency update** - Updated `requirements.txt` to require `python-alfresco-api>=1.1.5` for relative_path support
- **Path documentation** - Enhanced `docs/SOURCE-PATH-EXAMPLES.md` with native Alfresco path format examples
- **Configuration notes** - Added path format guidance to `env-sample.txt` for Alfresco configuration

### Technical Details
- Uses symbolic node ID `"-root-"` as starting point for relative path resolution
- Strips leading slash from paths for proper relative_path format
- Delegates to existing `_process_folder_by_id()` and `_process_file_by_id()` methods after node ID resolution
- Comprehensive logging shows API method used (Alfresco REST API vs CMIS fallback)
- Automatic version detection - uses best available method based on python-alfresco-api capabilities

## [2025-11-29] - Alfresco multi-select support, API improvements, per-ingest graph control

### Enhanced
- **Alfresco multi-select support** - Enhanced `/api/ingest` endpoint to support multi-select of files and folders from Alfresco ACA/ADF Angular client
  - Added `nodeDetails` array parameter to `AlfrescoConfig` model with node metadata (id, name, path, isFile, isFolder)
  - Added `nodeIds` array parameter to `AlfrescoConfig` model with node IDs (UUID strings from REST API)
  - Enhanced `AlfrescoSource.list_files()` to process specific files and folders from `nodeDetails`
  - Maintained backward compatibility with single `path` parameter for existing integrations
  - Support for mixed selections (files and folders together)
- **Alfresco processing logic** - Refactored file listing into modular helper methods
  - `_process_file_by_id()` - Process specific files using node ID via Alfresco REST API with CMIS fallback
  - `_process_folder_by_id()` - Process folders using node ID via Alfresco REST API `list_children()` with correct dictionary access
  - `_process_folder_by_path()` - Process folders using path via CMIS (backward compatibility)
  - Smart detection: uses `nodeDetails` if present, falls back to single `path` for backward compatibility
  - CMIS lazy initialization: Only initializes CMIS when path-based operations are needed
- **Alfresco REST API integration** - Smart dual-API strategy for optimal performance
  - Uses Alfresco REST API for both files and folders when `nodeDetails` is present (ACA/ADF integration)
    - Files: `core_client.nodes.get(node_id)` for direct node access
    - Folders: `core_client.nodes.list_children(node_id)` with correct `NodeListResponse.list` dictionary access
  - Falls back to CMIS API for traditional path-based access or if Alfresco API fails
    - Path-based: `getObjectByPath(path)` and `getChildren()` for folder operations
  - Download strategy: python-alfresco-api `content_utils.download_file()` → CMIS API fallback
  - Automatic API selection based on available information for best performance

### Added
- **NodeDetail model** - New Pydantic model in `main.py` for structured node metadata from ACA/ADF client
- **Recursive folder control** - Added `recursive` parameter to `AlfrescoConfig` (default: `false`)
  - `recursive: false` - Process only files in selected folder (one level), skip subfolders
  - `recursive: true` - Process all files and subfolders recursively
  - Applies to both Alfresco REST API and CMIS fallback methods
  - Provides performance control for large folder hierarchies
- **Per-ingest skip_graph flag** - Added `skip_graph` parameter to `/api/ingest` endpoint (default: `false`)
  - Temporarily skip knowledge graph extraction for specific ingests without changing global config
  - Time savings: ~90% faster (no LLM entity/relationship extraction calls)
  - Non-persistent: doesn't modify `ENABLE_KNOWLEDGE_GRAPH` config setting
  - Completion messages dynamically reflect actual processing (omit graph when skipped)
- **Documentation** - Created comprehensive integration documentation
  - `docs/ALFRESCO-MULTISELECT.md` - Complete guide for integrating Flexible GraphRAG as "KG Spaces" plugin in Alfresco ACA/ADF client
  - `docs/ALFRESCO-API-STRATEGY.md` - Technical documentation of dual-API strategy (Alfresco REST API vs CMIS)
  - `docs/ALFRESCO-LOGGING.md` - Detailed logging enhancements for debugging Alfresco integration
  - `docs/WINDOWS-CONSOLE-COMPATIBILITY.md` - Windows console compatibility guidelines (ASCII-only logging)

### Fixed
- **Alfresco folder processing** - Fixed `NodeListResponse.list` dictionary access (was checking for attributes instead of dictionary keys)
- **skip_graph flag implementation** - Fixed critical bug where flag was logged but ignored for most data sources
  - Added `skip_graph` parameter to `_process_documents_direct()` method
  - Updated 8 backend calls to pass flag (Alfresco, CMIS, web, YouTube, Wikipedia, S3, etc.)
  - Fixed completion message to omit graph when skipped
- **Frontend Alfresco URL configuration** - Removed `/alfresco` suffix from default URLs across all clients
  - React: `App.tsx`, `AlfrescoSourceForm.tsx`
  - Vue: `SourcesTab.vue`, `AlfrescoSourceForm.vue`
  - Angular standalone: `sources-tab.ts`, `alfresco-source-form.component.ts`, `processing-tab.ts`
  - Backend workaround: Strips `/alfresco` from URL if present before passing to `python-alfresco-api`
  **Alfresco Docker related**
  - `docker/includes/commons/base.yaml` alfresco's proxy traefik was changed from 3.1 to v3.6.1 to work with 
    both docker engine 29+ and docker desktop 25.2+
  - `docker/includes/alfresco.yaml` alfresco-transform-core-aio was changed to 5.2.4 for a security issue


## [2025-11-26] - Documentation overhaul and MCP server cleanup

### Enhanced
- **Documentation restructuring** - Created dedicated documentation files for better organization:
  - `docs/ARCHITECTURE.md` - Complete system architecture and component relationships
  - `docs/DEPLOYMENT-CONFIGURATIONS.md` - Standalone, hybrid, and full Docker deployment guides
  - `docs/OLLAMA-CONFIGURATION.md` - Comprehensive Ollama setup and optimization instructions
  - `docs/PERFORMANCE.md` - Performance benchmarks and optimization guides (moved from README.md)
- **README.md improvements** - Added comprehensive coverage of all 13 data sources with visual screenshot, detailed document processing options (Docling vs LlamaParse), complete database configuration for search/vector/graph databases with parameters and dashboards, chat interface showcase with Neo4j graph visualization
- **Database configuration documentation** - Expanded database sections in README.md to include detailed configuration parameters, dashboard URLs, and ideal use cases for all search databases (BM25, Elasticsearch, OpenSearch, None), all vector databases (10 options), and all graph databases (9 options plus None)

### Fixed
- **MCP server cleanup** - Removed unused `fastmcp-server.py` and `requirements.txt` from flexible-graphrag-mcp directory, keeping only HTTP-based `main.py` that uses REST API calls to backend

### Added
- **Visual documentation assets** - Added `screen-shots/react/chat-webpage.png` and `screen-shots/react/data-sources-1.jpeg` for README.md visual improvements
- **LLM configuration section** - Added dedicated LLM Configuration section in README.md with details for OpenAI, Ollama, Azure OpenAI, Anthropic, and Google Gemini providers including required/optional parameters

### Documentation
- `README.md` - Major reorganization with data sources showcase, document processing options, comprehensive database configurations, 
- `docs/ARCHITECTURE.md` - New comprehensive architecture documentation
- `docs/DEPLOYMENT-CONFIGURATIONS.md` - New deployment guide for all three modes
- `docs/OLLAMA-CONFIGURATION.md` - New Ollama-specific configuration guide
- `docs/PERFORMANCE.md` - Performance information consolidated from README.md


## [2025-11-16] - Fix timing logging for graph phase, fix falkordb config setup, fix over-write of neo4j config in env-sample.txt

### Fixed
- In hybrid_system.py, fixed to update graph update start time before graph index insert nodes,
and update the graph creation duration after. This fixed on a second run, to have correct non 0 graph phase sub time (total time for all phases was correct without this).
- In env-sample.txt, for falkordb GRAPH_DB_CONFIG, have database name instead of user, password
and in docker-env-sample.txt added example of falkordb config with database name
- In env-sample.txt, commented out Kuzu GRAPH_DB_CONFIG, that was over-writing the default GRAPH_DB_CONFIG for Neo4j
- in factories.py for falkordb, log database name in addition to url


## [2025-11-10] - Azure Blob Storage data source now also fully working

### Fixed
- **Azure Blob Storage temporary file deletion** - Applied same PassthroughExtractor immediate processing fix as Box and Google Drive, preventing "File does not exist" errors when AzStorageBlobReader cleanup deletes temp files before DocumentProcessor can access them

## [2025-11-08] - LlamaParse added as an additional configurable doc processing choice beyond Docling. Box, Google Drive, GCS data sources now fully working, and the custom configured DocProcessor called from a Passthrough Extractor allows the LlamaIndex Readers to be fully leveraged

### Fixed
- **LlamaParse parse_page_without_llm mode error** - Changed result_type to "text" for parse_page_without_llm mode (was hardcoded "markdown" causing 404 errors), added conditional result_type logic in document_processor.py
- **Box, Google Drive, and Azure Blob temporary file deletion** - Modified PassthroughExtractor to accept doc_processor parameter and process files immediately while they exist in temp directory, preventing "File does not exist" errors when LlamaIndex readers cleanup temp directories after load_data() returns
- **GCS permissions and configuration** - Fixed by granting "Storage Object Viewer" role (Storage Legacy Bucket Reader was insufficient), removed redundant project_id field (already in service account JSON)
- **UI progress indicators for Box/S3** - Fixed React/Vue progress bars by stripping type field from enterpriseConfig/cloudConfig before sending to backend, added fallback for completed files in getFileProgressData
- **S3 region_name configuration** - Changed from hardcoded "us-east-2" to None with fallback to "us-east-1" standard AWS region, fixed None/"None" string handling
- **'NoneType' object is not callable error** - Added safety checks in _process_with_llamaparse for check_cancellation parameter (S3/cloud sources don't pass it)

### Enhanced
- **File count vs chunk count tracking** - Updated BaseDataSource.get_documents_with_progress() to return tuple (file_count, documents) instead of just List[Document], all 13 data sources return proper file counts, IngestionManager stores file_count/chunk_count in PROCESSING_STATUS when they differ, hybrid_system.py completion logic uses stored file_count in both code paths (ingest_documents and _process_documents_direct)
- **LlamaParse filename display in LlamaCloud** - Changed from memory-intensive BytesIO approach to efficient temp file creation with original names at download time, updated process_documents_from_metadata() to use original filename directly, updated Alfresco/CMIS _download_document() to use original filenames
- **Box authentication modes** - Implemented 4-mode authentication UI across all frontends: developer token, CCG with user_id, CCG with enterprise_id, CCG with both, uses BoxClient with BoxDeveloperTokenAuth/BoxCCGAuth and CCGConfig
- **GCS non-recursive file listing** - Added recursive=False to GCSReader initialization to prevent subdirectory traversal, allows prefix-based filtering without recursion
- **Parser type configuration** - Created BaseDataSource._get_document_processor() centralized method ensuring consistent parser_type and Settings across all data sources

### Added
- **GCS UI improvements** - Removed unused folder_name field from all 3 frontends, standardized field ordering (Bucket Name, Prefix, Credentials) across React/Vue/Angular
- **LlamaParse configuration documentation** - Updated env-sample.txt with mode-specific output format clarification (text for parse_page_without_llm, markdown for with_llm and with_agent modes)

### Dependencies
- **llama-index-readers-file** - Added to prevent warnings in Box/Google Drive PassthroughExtractor
- **box-sdk-gen** - Added for Box CCG authentication (BoxClient, BoxCCGAuth, CCGConfig)

## [2025-10-22] - All 10 vector databases working: Pinecone, Weaviate working now, Chroma now supports both http, embedded

### Added
- **Added Chroma HTTP mode**
  - In `factories.py` create_vector_store now also supports chroma http mode in addition to local embedded, and uses what is in vector_db_config to determine which one to setup
  - In `env-sample.txt` has added example for http mode chroma
  - `test_basic.py` has added basic instantiation test for chroma http mode

### Changed
**Pinecone config parameters changed, working now**
  -In `factories.py` create_vector_store now sets up pinecone with a different set of config values
(now cloud, region, metric  instead of environment, namespace). 
  - In `pinecone.yaml`, comments changed to reflect new config paramters, only mention official dashboard, and simpler startup for our pinecone-info datashboard
  - In `env-sample.txt` pinecone config sample updated to use new config parameters (now cloud, region, metric  instead of environment, namespace).
  - In `docker/pinecone-info/index.html` this information dashboard was updated to show the
new config setup parameters, just point to the official dashboard, and an unneeded section was removed 
  - In `requirements.txt` pinecone package added as a requirement
  - test_basic.py has pinecone test updated to use new config parameters

**Weaviate now working**
  - In `weaviate.yaml`, weaviate was changed to get not have errors and work: the image was changed
to be :latest and not an older version, and having the gRPC port added back in by taking the commnent off it.

### Documentation
- `README.md` updated with info on Chroma HTTP mode in addition to local embedded mode,
updated with different vector_db_config parameters that pinecone support needs
- `docs/chroma-deployment-modes.md` added covering setup of the local embedded and http based version of chroma 
(docker chroma.yaml sets local with its data local or in external server) use of rest api to manage the http version 
- `docs/default-usernames-passwords.md`, `docs/vector-database-integration.md`, and `docs/vector-dimensions.md` updated
with pinecone changes, and added http mode chroma


## [2025-10-16] - Amazon Neptune, Neptune Analytics, Graph Explorer now working, .env + docker.env now no duplication

### Added
- Amazon Neptune and Amazon Neptune Analytics graph databases are now working with flexible graphrag
- A local Graph Explorer https://github.com/aws/graph-explorer in a docker works and can be used to query and visualize with both Amazon Neptune and Amazon Neptune Analytics. This is in neptune.yaml
- added docker-env-sample.txt to copy to docker.env
- added neptune-env-sample.txt top copy to neptune.env to provide keys, region to graph explorer in neptune.yaml docker

### Enhanced
- Previously had to repeat all config in app-stack.yaml flexible-graphrag-backend environment: section, Now use env_file: and include standalone backend flexible-graphrag/.env and override with include of docker.env with just the configs that need urls with host.docker.internal instead of localhost inside docker
- env-sample.txt used as a template for backend .env (and now included in app-stack.yaml for docker) was updated with configs for Amazon Neptune and Amazon Neptune Analytics
- factories.py was updated to get working creation of property graph stores for Neptune and Neptune Analytics
- neptune_analytics_wrapper.py has a wrapper class that works around some vector issues Neptune Analytics Property Graph Store and LlamaIndex have
- hybrid_system disables doing vector embeddings with Neptune Analytics

### Documentation
- In docker dir, new DOCKER-ENV-SETUP.md document way to configure docker with the new flexible-graphrag/.env + docker.env, and neptune.eny
- README.md that covers all dockers for the databases, backend/frontends was update to also have coverage of the new two part env config



## [2025-10-10] - S3 Data Source is now fully working and Docling processing added for S3 files

### Enhanced
- **S3 Data Source Rewrite**
  - In `sources/s3.py` was rewritten to use s3fs directly and not use llamaindex S3Reader
  - Downloads S3 files and gives them to DocumentProcessor (which processes with Docling)
  - Sets up llamaindex documents for llamaindex pipeline integration
  - Progress feedback callbacks are also setup in s3.py
  - Fixed to give feedback in terms of number of documents not count of chunks as doc count

- **Backend S3 Progress Handling**
  - In `backend.py` handling of S3 progressing status was setup
  - Removed 2 un-needed processing status updating in general

- **Progress Feedback Improvements**
  - In `ingest/manager.py` was changed to give better doc count progress feedback
  - In `hybrid_system.py` was changed to give specific feedback for YouTube to be one document not chunk for doc count

- **Frontend S3 Integration**
  - In `ProcessingTab.tsx` for React, `ProcessingTab.vue` for Vue, and `processing-tab.ts` for Angular
  - Code was added to get the progress bar and other feedback to work for S3

### Added
- **S3 Configuration**
  - In `env-sample.txt` configuration for S3 default parameters can be set
  - In `requirements.txt` include boto3 and s3fs for dealing with S3 instead of using llamaindex S3Reader


## [2025-10-08] - Fixed standalone on Linux and Mac, fixed docker with app-stack on Mac

### Fixed
- **Docker Build Issues on Mac**
  - In Dockerfile use full python so can build on Mac when include app-stack.yaml
- **Standalone Backend Issues on Linux and Mac**
  - In start.py, added loop='asyncio' so don't get nest_asyncio errors on linux and mac
  - In start.py changed reload = false in general (not just windows) to simplify 


## [2025-10-04] - 3 frontends and backend can now work in docker in addition to in standalone mode

### Added
- **Complete Docker Frontend Support**
  - All three frontends (React, Vue, Angular) now work in Docker with nginx proxy
  - Dual access capability: direct container ports AND nginx proxy routing
  - React: `localhost:3000/ui/react/` and `localhost:8070/ui/react/`
  - Vue: `localhost:5173/ui/vue/` and `localhost:8070/ui/vue/`
  - Angular: `localhost:4200/` and `localhost:8070/ui/angular/`

### Fixed
- **Vue Docker Frontend API Routing**
  - Added proxy configuration to `vite.docker.config.ts` routing `/api` to backend
  - Resolved 404 errors on `/api/upload` endpoint in Docker environment
  - Vue frontend now processes files correctly in Docker deployment

- **Angular Docker Frontend Issues**
  - Fixed blank page issues by switching from static file serving to Angular dev server
  - Added `proxy.docker.conf.json` with backend routing configuration
  - Updated Dockerfile to use `npm run start` instead of static file serving
  - Implemented nginx `sub_filter` to dynamically inject correct base href for dual access

### Enhanced
- **Docker Configuration**
  - Environment variables configured in `app-stack.yaml` instead of `.env` for Docker backend
  - Default Ollama configuration (for OpenAI, update commented/uncommented sections and add API key)
  - Enabled nginx proxy with `proxy.yaml` included in docker-compose configuration

- **Angular Environment Configuration**
  - Added `environment.docker.ts` with Docker-specific settings
  - Updated `api.service.ts` to use `apiUrl = environment.apiUrl` instead of hardcoded `/api`
  - Added Docker build configuration section to `angular.json`
  - Removed obsolete `build:docker` script from `package.json`

### Maintained
- **Standalone Mode Compatibility**
  - All three frontends continue to work in standalone development mode
  - React: `localhost:3000`, Vue: `localhost:5173`, Angular: `localhost:4200`
  - Separate configuration files ensure no conflicts between Docker and standalone modes

### Technical Implementation
- Vue uses separate `vite.docker.config.ts` with backend proxy configuration
- Angular uses environment-based configuration with Docker-specific proxy setup
- React maintains existing dual access capability (already working)
- nginx `sub_filter` dynamically modifies Angular base href for proxy access compatibility

## [2025-09-28] - Kuzu can now do structured schema if enabled in config, code cleanup

### Enhanced
- env-samples.txt graph_db_config for kuzu now has use_structured_schema and use_vector_index parameters
- in factories.py create_graph_store, for kuzu, use use_structured_schema and use_vector_index config parameters to setup KuzuPropertyGraphStore to set use_vector_index, and set use_structured_schema (and give a relationship_schema if so)

### Fixed
- Previous code was always setting use_structured_schema to false

### Removed
- removed separate kuzu_use_vector_index independent configuration item from config.py
- in hybrid_system.py ingest_document(), code cleanup:
  - took out for kuzu setting external vector store in graph_index_kwargs
  - took out for kuzu calling graph_store.init_schema()
  - took out for memgraph unneeded code setting up a SchemaLLMPathExtractor with a hard coded schema to get relationship to have all relationship types with all caps and "_"


## [2025-09-26] - Fixed MemGraph issues, fixed issues with everything in docker compose included

### Fixed
- **MemGraph Cypher Relation Error**
  - Upgraded MemGraph Docker image to version 3.5.0
  - Resolved Cypher relation errors during graph building
  - Improved stability and compatibility with latest MemGraph features

- **Docker Port Conflicts**
  - Fixed Kuzu API server port conflict with NebulaGraph Studio (7001 → 7002)
  - Renamed postgres-pgvector service to avoid conflict with Alfresco postgres
  - Updated PORT-MAPPINGS.md with accurate conflict documentation

- **Angular Production Build Issues**
  - Increased Angular budget limits from 1MB to 5MB for Docker production builds
  - Resolved build failures with Angular Material components in Docker environment
  - Updated angular.json configuration for proper containerized deployment

- **Docker Backend AsyncIO Compatibility**
  - Added `--loop asyncio` flag to uvicorn in Docker to support nest_asyncio.apply()
  - Upgraded Docker Python version from 3.11 to 3.12 for ArcadeDB compatibility
  - Resolved uvloop/nest_asyncio conflicts in containerized environment

### Enhanced
- **Docker Compose Configuration**
  - Updated app-stack.yaml with improved Ollama model defaults
  - Added embedding configuration for both OpenAI and Ollama providers
  - Commented out ArcadeDB in env-sample.txt to reflect Neo4j default setup

### Removed
- **Code Cleanup**
  - Removed unused `_init_nebula_schema()` function from hybrid_system.py
  - Proper NebulaGraph setup now documented in NEBULA-SETUP.md

### Notes
- Backend successfully runs in Docker via app-stack.yaml
- Frontend containers in app-stack.yaml currently have issues - recommend standalone frontend with Docker databases
- Full Docker stack functional for databases, selective deployment recommended for UI components

## [2025-09-25] - Vector Database Expansion and Dashboard Integration

### Added
- **6 Additional Vector Databases**
  - Chroma, Milvus, Weaviate, Pinecone, PostgreSQL+pgvector, LanceDB support
  - Complete Docker configurations with port conflict resolution
  - Factory implementations following LlamaIndex patterns
  - Total vector database support expanded from 4 to 10 databases

- **4 Additional Graph Databases**
  - ArcadeDB, MemGraph, NebulaGraph, Amazon Neptune/Neptune Analytics support
  - Multi-model capabilities and distributed graph database options
  - Complete configuration examples and Docker integration
  - Total graph database support expanded to 9 databases

- **Comprehensive Dashboard Integration**
  - Dashboard coverage for all vector databases (ports 3000-3008)
  - Working solutions: MemGraph Lab, NebulaGraph Studio, Milvus Attu, LanceDB Viewer
  - Info pages for managed services (Pinecone, Neptune)
  - Systematic testing and accurate status documentation

- **10 New Modular Data Sources**
  - Web, Wikipedia, YouTube, S3, GCS, Azure Blob, OneDrive, SharePoint, Box, Google Drive
  - Modular architecture with BaseDataSource pattern and IngestionManager
  - Progress tracking and LlamaIndex Hub reader integration
  - Total data sources expanded from 3 to 13

### Enhanced
- **Dynamic Embedding Dimension Detection**
  - Replaced hardcoded dimensions with provider-aware detection
  - OpenAI (1536/3072), Ollama (384/768/1024), Azure support
  - Centralized get_embedding_dimension() function across all databases

- **Docker Network Simplification**
  - Eliminated external network dependencies and multiple network creation
  - Single flexible-graphrag_default network for all services
  - Fixed "network declared as external, but could not be found" errors

- **Comprehensive Documentation**
  - Complete vector database deletion guide for embedding model switching
  - Port mappings documentation with conflict resolution
  - Dashboard status indicators (✅ working, ❌ CORS issues, ⚠️ complex)

### Fixed
- **Dashboard Connection Issues**
  - MemGraph Lab Docker entrypoint configuration
  - NebulaGraph Studio internal Docker service connection
  - Pinecone info page nginx file permissions (403 Forbidden)
  - Chroma API endpoints updated from v1 to v2

- **UI Consistency and Progress Tracking**
  - Angular dark mode text visibility across all components
  - Vue SharePoint form missing authentication fields
  - Processing tab message panel clearing when switching data sources
  - Cross-frontend repository file handling and progress bars

- **Data Source Integration**
  - Angular web/cloud data source configuration parameter mapping
  - SharePoint 422 validation errors with complete Azure authentication
  - Wikipedia URL parsing to preserve page titles with hyphens
  - YouTube transcript processing with proper time-based chunking

### Performance Results
- **Vector Database Scaling**: 10 databases with consistent factory patterns
- **Graph Database Coverage**: 9 databases including distributed and managed options
- **Data Source Expansion**: 13 total sources with modular processing architecture
- **Dashboard Reliability**: Systematic testing identified working vs problematic solutions

## [2025-09-23] - Wikipedia Data Source Enhancement and Performance Logging Fixes

### Enhanced
- **Wikipedia Data Source**: Improved Wikipedia page resolution with search-based fallback for special characters (e.g., "Nasdaq-100")
  - Reordered loading methods: LlamaIndex WikipediaReader primary, direct wikipedia library fallback
  - Added content length limit (100,000 characters) following Neo4j LLM Graph Builder approach
  - Enhanced URL parsing with proper handling of hyphens and underscores

### Fixed
- **Performance Logging**: Fixed inaccurate graph extraction timing measurements in performance summary logs
  - Resolved variable scope issues causing "Graph: 0.00s" display errors
  - Both processing methods now show accurate timing for all phases (Pipeline, Vector, Graph)

## [2025-09-23] - Angular Data Source Integration and UI Consistency Fixes

### Fixed
- **Angular Web Data Source Configuration**
  - Fixed missing web_config parameter passing in Angular processing tab
  - Angular web sources now work consistently with React and Vue frontends
  - Resolved "configuration is required" errors for web data sources

- **Angular Cloud Data Source Validation Errors**
  - Fixed 422 "Unprocessable Content" errors for cloud storage data sources
  - Corrected configuration parameter mapping to send only relevant configs per data source
  - SharePoint form enhanced with required Azure authentication fields (client_id, client_secret, tenant_id)

- **Wikipedia Data Source Special Characters**
  - Improved URL parsing across all frontends to preserve page titles with hyphens
  - Added fallback mechanisms for Wikipedia pages with special characters
  - Enhanced error handling and logging for Wikipedia API interactions

### Enhanced
- **Cross-Frontend Consistency**
  - All three frontends (React, Vue, Angular) now have identical data source support
  - Consistent cloud storage configuration validation and error handling
  - Unified Wikipedia URL parsing logic across all frontends

- **Angular UI Improvements**
  - Enhanced SharePoint form with complete Azure app registration fields
  - Improved cloud data source form layouts and validation
  - Better error messages and user guidance for data source configuration


## [2025-09-23] - Data Source Alignment and Progress Tracking Fixes

### Fixed
- **Critical Progress Bar Issues for New Data Sources**
  - New modular sources (Web, Wikipedia, YouTube, cloud storage) now display progress bars correctly
  - Fixed missing individual_files data structure and main PROCESSING_STATUS updates
  - YouTube field name mismatch resolved (backend 'video_url' vs frontend 'url')
  - All 13 data sources now have consistent progress tracking

### Enhanced
- **Cloud Storage Data Source Improvements**
  - Azure Blob Storage: Updated to Method 1 (Account Key Authentication)
  - Microsoft OneDrive: Added required user_principal_name field
  - Amazon S3: Removed legacy bucket_url field, streamlined to bucket_name approach
  - Microsoft SharePoint: Updated to use site_name and folder_id field names
  - Added comprehensive autocomplete prevention for sensitive fields

### Added
- **10 New Modular Data Sources**
  - Web sources: Web Page, Wikipedia, YouTube
  - Cloud storage: Amazon S3, Google Cloud Storage, Azure Blob Storage
  - Enterprise cloud: Microsoft OneDrive, SharePoint, Box, Google Drive
  - Complete UI forms and backend integration for all new sources
  - Expanded from 3 legacy sources to 13 total data sources

### Enhanced
- **Cross-Frontend UI Consistency**
  - Ported React's modular source form components to Vue and Angular
  - BaseSourceForm inheritance pattern with dynamic component rendering
  - Complete feature parity across all three frontends (React, Vue, Angular)
  - Fixed Vue dropdown styling issues and Angular compilation errors

## [2025-09-23] - YouTube Fix and Cloud Storage Organizational Fields

### Fixed
- **YouTube Data Source**
  - Switched from LlamaIndex wrapper to direct youtube_transcript_api usage
  - Implemented proper 60-second time-based chunking with timestamp metadata
  - Resolved parameter errors and achieved 21 document chunks from videos

### Enhanced
- **Google Drive Authentication**
  - Fixed authentication using proper service_account_key parameter
  - Added JSON credential parsing from UI form
  - Resolved "Must specify client_config or service_account_key" error

### Added
- **Cloud Storage Organizational Fields**
  - Azure Blob: Added prefix field separate from blob_name
  - Box: Added folder_id field for specific folder access
  - Amazon S3: Added bucket name + prefix fields (marked bucket_url as legacy)
  - OneDrive: Added folder_path and folder_id fields
  - Google Cloud Storage: Added prefix and folder_name fields
  - SharePoint: Added document_library and folder_path fields
  - Fixed 422 "Unprocessable Content" errors by updating backend API models

## [2025-09-23] - UI Fixes and Backend Integration

### Fixed
- **Critical Configuration Flow Issue**
  - Web sources (Web, Wikipedia, YouTube) failing with "configuration is required" errors
  - Added 5 new state variables in App.tsx for web/cloud/enterprise configs
  - Fixed complete data flow: UI Form → SourcesTab → App.tsx → ProcessingTab → API → Backend

### Enhanced
- **Async/Await Backend Integration**
  - Made get_documents_with_progress() methods async for all new modular sources
  - Fixed "object list can't be used in 'await' expression" errors
  - Enhanced Azure Blob Storage form with 3 missing fields (blob_name, account_name, account_key)

## [2025-09-23] - Data Source Migration and Progress Tracking

### Added
- **Complete Data Source Migration**
  - Migrated all three legacy sources (Filesystem, Alfresco, CMIS) to modular architecture
  - BaseDataSource inheritance with IngestionManager orchestration
  - Unified progress tracking across all data sources

### Fixed
- **File Upload Progress Issues**
  - Fixed missing top area progress feedback for filesystem source
  - Resolved progress reset issue where completion status appeared then reset
  - All sources now have consistent progress feedback (top/middle/bottom areas)

### Enhanced
- **Completion Messages**
  - Improved order: Vector → Search → Knowledge Graph
  - Dynamic database types (e.g., "Qdrant vector index, Elasticsearch search, Neo4J knowledge graph")
  - Proper grammar without duplicate "and"

### Removed
- Deprecated sources.py file and old ingest_cmis/ingest_alfresco methods
- Cleaned up codebase while preserving ingest_documents (API/MCP) and ingest_text (MCP server)

## [2025-09-08] - FalkorDB Integration and Configuration Optimization

### Added
- **FalkorDB Graph Database Support**
  - Complete integration with GraphDBType enum, factories.py, requirements.txt
  - Docker support with falkordb.yaml include and browser (port 3001)
  - Performance testing: 21.74s for 6 docs (3.62s/doc), fastest search (1.199s)
  - Superior entity extraction quality (PERSON, ORGANIZATION, TECHNOLOGY)

### Enhanced
- **Configurable Extraction Limits**
  - MAX_TRIPLETS_PER_CHUNK and MAX_PATHS_PER_CHUNK environment variables
  - Default increased from 10-20 to 100 for better entity extraction
  - Resolves generic __entity__ issues with dense content

### Fixed
- **File Upload Dialog Performance**
  - requestAnimationFrame optimization for React, Vue, Angular frontends
  - Proper input clearing only after successful processing
  - Dialog now matches drag/drop speed

### Performance Results
- **FalkorDB + OpenAI**: 21.74s ingestion, 1.199s search, 2.133s Q&A (6 docs)
- **FalkorDB + Ollama**: Working configuration found (100 max triplets, 16k context)
- **Resolved Issue**: space-station.txt + FalkorDB + Ollama now works with optimized settings

### Documentation
- **Performance Documentation**: docs/PERFORMANCE.md with complete test matrix
- **README.md**: Concise 6-doc performance comparison table
- **Port Conflicts**: FalkorDB browser moved to port 3001 (Vue client stays 3000)

## [2025-09-04] - Comprehensive Performance Testing and Optimization

### Added
- **Complete Performance Benchmarking Matrix**
  - Tested all combinations: Neo4j/Kuzu × OpenAI/Ollama
  - Performance table in README.md with detailed metrics
  - Infrastructure configuration documentation (AMD 5950x, 64GB RAM, 4090 GPU)

### Enhanced
- **Ollama Parallel Processing Optimization**
  - Removed artificial worker limitations (1→4 workers)
  - Enabled async PropertyGraphIndex processing
  - Parallel Docling document conversion
  - 94% pipeline performance improvement (37s→2s)

### Fixed
- **DynamicLLMPathExtractor vs SchemaLLMPathExtractor Issues**
  - DynamicLLMPathExtractor fails with Ollama (creates only Chunk nodes)
  - SchemaLLMPathExtractor works excellently with both Neo4j and Kuzu
  - Kuzu schema configuration fixed (has_structured_schema=False)

### Performance Results
- **OpenAI**: 3.7x faster than Ollama across both databases
- **Neo4j + OpenAI**: 14.39s for 2 docs (best overall)
- **Kuzu + OpenAI**: 14.79s for 2 docs (nearly identical)
- **Both Ollama options**: ~54s for 2 docs (viable for local processing)


## [2025-08-29] - Kuzu Schema Integration and Performance Analysis

### Added
- **Complete Kuzu Graph Database Integration**
  - Comprehensive validation schema with 35+ relationship combinations
  - Entity types: PERSON, ORGANIZATION, TECHNOLOGY, PROJECT, LOCATION
  - Outstanding performance: 3.52s per document average

### Fixed
- **Kuzu Schema Validation Errors**
  - "Query node c violates schema" and "Table Entity does not exist" resolved
  - Evolution from LlamaIndex exact schema to comprehensive validation
  - strict=False, max_triplets_per_chunk=100 for maximum flexibility

### Enhanced
- **Performance Optimization Discovery**
  - KeywordExtractor/SummaryExtractor removal for Ollama (94% improvement)
  - Neo4j scaling: 90% efficiency, 18.93s per doc consistency
  - Kuzu scaling: 253% slower at 2 docs → only 11% slower at 6 docs


## [2025-08-27] - Ollama Optimization and Docker Configuration

### Added
- **Comprehensive Ollama Parallel Processing**
  - OLLAMA_NUM_PARALLEL=4 and OLLAMA_MAX_LOADED_MODELS=4 support
  - Async PropertyGraphIndex with use_async=True
  - Parallel Docling document processing with asyncio.gather()
  - Increased kg_batch_size from 10 to 20 chunks

### Enhanced
- **Docker Compose Modularization**
  - Separate Kuzu API (port 7001) and Explorer (port 7000) services
  - Bind mounts to flexible-graphrag/kuzu_db/ for data sharing
  - Health checks and proper container monitoring

### Fixed
- **Async Event Loop Stability**
  - Reduced workers for Ollama to prevent conflicts
  - Enhanced error logging with better exception handling
  - Schema logging errors resolved


## [2025-08-26] - Performance Analysis and Query Timing

### Added
- **Comprehensive Query Timing Implementation**
  - Search, Q&A, and hybrid retrieval timing logs
  - Detailed deduplication flow tracking (12 → 8 → 5 results)
  - Enhanced document storage logging with breakdown

### Fixed
- **File Count Logging Mismatch**
  - Corrected "(7/6 files)" display to show accurate completion status
  - ASCII-only text previews to prevent emoji encoding issues
  - Unicode arrow character encoding errors on Windows console

### Performance Results
- **OpenAI + Kuzu**: 32.17s for 6 docs (first time), 23.81s (with indexes)
- **Query Performance**: Search 1.079s, Q&A 2.231s (sub-2.5s production ready)
- **Index Creation Impact**: 23% performance gain with existing indexes


## [2025-08-25] - Docker Compose Documentation Updates

### Enhanced
- **Docker Compose Command Standardization**
  - Added `-p flexible-graphrag` project name flag to all commands
  - Reordered flags: `-f` before `-p` throughout documentation
  - Updated single docker-compose.yaml file structure references

### Added
- **Stopping Services Documentation**
  - Dedicated section for proper service shutdown
  - Volume removal warnings and best practices
  - Modular include system explanation


## [2025-08-23] - Screenshot Organization and Documentation Updates

### Changed
- **README Screenshot Organization**
  - **Vue and Angular**: Moved existing screenshots to framework-specific subdirectories (`screen-shots/vue/`, `screen-shots/angular/`)
  - **React**: Completely redone with both dark and light theme versions in `screen-shots/react/`
    - Removed chat greeting and Q&A query screenshots from display
    - Now shows hybrid search instead of Q&A query in search tab
    - Added separate collapsible section for React Light Theme screenshots
  - Added theme indicators to all frontend sections: Angular (Light Theme), Vue (Light Theme), React (Dark Theme + Light Theme)

### Enhanced
- **Documentation Clarity**
  - Clear theme identification for each frontend in README
  - Improved screenshot organization for better navigation
  - Consistent screenshot presentation across all three frontends


## [2025-08-23] - File State Management and Theme Fixes

### Fixed
- **Filename Reuse Between Upload Methods**
  - Fixed issue preventing same filename reuse between regular file upload and repository upload
  - Resolved frontend file state conflicts when switching between data sources
  - All frontends now properly clear previous file state when switching upload methods

- **Repository Display Issues**
  - Fixed React ProcessingTab showing old filenames when switching to repository source
  - Fixed Angular ProcessingTab displaying stale file data until processing starts
  - Fixed Vue ProcessingTab showing previous upload files instead of repository path
  - All frontends now immediately display correct repository path upon configuration

- **Dark/Light Theme Styling Issues**
  - Angular: Fixed dark mode configure processing button text visibility
  - Vue: Fixed light mode text color above "Go to Sources" button for proper contrast
  - React: Fixed dark mode "No Data Source Configured" panel background (now dark gray instead of light blue)

### Enhanced
- **Cross-Data Source Compatibility**
  - Improved handling of file upload → repository source transitions
  - Enhanced repository → file upload source transitions  
  - Better support for CMIS ↔ Alfresco source switching
  - Consistent filename conflict prevention across all upload methods


## [2025-08-22] - Comprehensive UI/UX Fixes and Repository File Handling

### Added
- **Enhanced Display Area Usage**
  - Chat interface now takes advantage of extra display area on 4K and QHD monitors
  - Responsive viewport calculations with framework-specific height offsets
  - Integrated help text into chat input placeholders
  - Removed redundant "Chat Interface" headers to save vertical space

- **Full Path Display**
  - Complete repository path display across all frontends (e.g., "/Shared/GraphRAG/cmispress.txt")
  - Enhanced filename extraction from repository paths
  - Flexible column layouts with 30% width allocation for filenames

### Fixed
- **Repository File Handling Issues**
  - Vue: Fixed inability to re-add repository files after removal
  - Vue: Fixed progress bars showing "0% - Ready" instead of actual progress
  - React: Added missing "X" remove buttons for repository files
  - Angular: Enhanced repository file display and removal functionality
  - All clients: Fixed repository path configuration for single file vs directory processing

- **Progress Bar and Status Issues**
  - Fixed progress text wrapping ("100% - Completed" on multiple lines)
  - Applied consistent flexbox layout for progress columns across all frontends
  - Enhanced completion status retention for repository files
  - Fixed progress lookup using correct file identifiers

- **Cross-Frontend UI Consistency**
  - Standardized button styling: red outline for Cancel/Remove Selected, green for Completed status
  - Implemented blue checkboxes with white checks across all clients
  - Fixed Angular dark theme visibility for tabs, dropdowns, chat elements, form fields
  - Removed confusing guide lines and borders from chat interfaces
  - Enhanced chat auto-scroll functionality across all frontends

- **Chat Interface Improvements**
  - Fixed Vue chat auto-scroll using proper DOM element access
  - Improved chat input field visibility in light mode
  - Optimized button alignment and spacing
  - Enhanced message display and interaction patterns

### Enhanced
- **State Management**
  - Implemented `repositoryItemsHidden` pattern for proper file removal/re-add capability
  - Enhanced configuration timestamp tracking for state updates
  - Improved fallback mechanisms for preserving file information after cancellation

---

## [2025-08-21] - React Frontend Modularization and Cross-Frontend Styling

### Added
- **React Frontend Modularization**
  - Extracted components from monolithic App.tsx to dedicated files (SourcesTab, ProcessingTab, SearchTab, ChatTab)
  - Implemented "lift state up" pattern for centralized state management
  - Created comprehensive TypeScript interfaces in types/api.ts and types/theme.ts
  - Added component export aggregation with index.ts

- **Repository File Enhancement**
  - Individual file display from statusData.individual_files for CMIS/Alfresco sources
  - Enhanced filename extraction from full paths with multiple fallback levels
  - Proper completion status retention (100% progress, green "completed" status)

### Fixed
- **React Functionality Issues**
  - Fixed checkboxes not pre-selecting after source configuration
  - Fixed "Remove Selected" and individual "X" buttons not removing items
  - Restored commented-out "Graph" tab for future features
  - Converted all tab labels to ALL CAPS for consistency

- **Vue Frontend Issues**
  - Fixed dark gray processing status panel with white text in dark theme
  - Resolved TypeScript compilation errors (function calls, $el access, event emission names)
  - Enhanced repository functionality with proper filename handling
  - Fixed drop area styling with consistent hover effects

- **Angular Dark Mode Issues**
  - Fixed tab labels with white text and blue active backgrounds
  - Improved form field and typography contrast
  - Enhanced Sources tab with white text on gray backgrounds
  - Standardized drop zone styling to match other frontends

### Enhanced
- **Cross-Frontend Consistency**
  - Standardized drop area styling: blue background with white text, black hover
  - Implemented consistent state management patterns across frameworks
  - Enhanced repository handling with unified approach to file display and removal
  - Improved theme support consistency across all frontends

- **State Persistence**
  - Prevented data loss during tab navigation through proper state lifting
  - Enhanced component communication patterns
  - Improved error handling and user feedback

---

## [2025-08-21] - Dark/Light Theme Support Implementation

### Added
- **Comprehensive Theme Switching**
  - React: Dark theme by default with proper theme persistence
  - Vue: Light theme by default with proper theme persistence  
  - Angular: Light theme by default with proper theme persistence
  - All frontends: localStorage theme preference saving

### Fixed
- **React Frontend Theme Issues**
  - Fixed search field white background causing vertical shift and input issues
  - Updated chat input field styling for proper theme compatibility
  - Resolved theme-aware input field backgrounds for both light and dark modes

- **Vue Frontend Theme Issues**
  - Fixed search method picker tabs white background in dark theme
  - Corrected chat wording from "Press Enter to send or click arrow to send" to "Press Enter or click arrow to send"
  - Fixed theme switcher layout: slider → icon → text with proper spacing
  - Improved processing button text visibility during processing
  - Hidden all processing table paging UI elements
  - Added visible border for chat area in light mode

- **Angular Frontend Theme Issues**
  - Implemented complete dark/light theme CSS with Material component overrides
  - Fixed theme switcher layout and replaced Material slide toggle with custom HTML/CSS widget
  - Corrected main tabs and search sub-tabs text visibility in dark mode
  - Fixed app width to expand to full window width like other frontends
  - Updated button styling: Remove Selected and Clear History buttons now use outlined style
  - Fixed chat wording to match other frontends

### Technical
- Added theme-aware CSS for all Material Design components
- Implemented custom toggle widget to replace stubborn Material slide toggle
- Applied responsive width across all frontends removing fixed max-width constraints
- Enhanced dark mode styling with proper contrast ratios for accessibility

---

## [2025-08-20] - Updated with screenshots for the new tab UI, readme updated

### Screenshots Updateed
- Removed 3 screenshots with old UI design
- Added screenshots of each of 4 tabs for all 3 clients in /screen-shots/

### Readme Updated
- Updated readme.md with new screenshots, usage updated for new UI for each of the four tabs
- Updated LLM usage note about using LlamaIndex with Ollama models and performance issues
- Updated docker section that new file upload can be used in docker where old filesystem datasource couldn't



## [2025-08-20] - Tabbed UI Implementation Across All Frontends

### Added
- **Vue Frontend Tabbed UI**
  - Implemented 5-tab navigation: Sources, Processing, Search, Chat, Graph
  - File upload with drag/drop functionality using Vuetify components
  - Processing table with checkboxes, progress bars, and bulk operations
  - Chat interface with auto-scroll and message history
  - Backend integration with axios for upload/processing/search operations

- **Angular Frontend Tabbed UI**
  - Implemented 5-tab navigation using Angular Material components
  - File upload with drag/drop functionality and Material Design styling
  - Processing table with selection, progress indicators, and bulk operations
  - Chat interface with auto-scroll and message threading
  - Backend integration with HttpClient and RxJS Observables

### Fixed
- **React UI Visual Issues**
  - Sources tab drag/drop area text changed from gray to white for visibility
  - Chat tab welcome message text visibility (was white-on-white)
  - Main tabs updated to blue background theme for consistency

- **Angular Auto-Scroll**
  - Restructured chat HTML with dedicated scroll-container inside mat-card
  - Disabled tab slide animations to prevent horizontal sliding in search interface

- **Vue Auto-Scroll**
  - Fixed v-card component reference using $el fallback for proper DOM access

### Enhanced
- **UI Consistency**
  - All button texts standardized to ALL CAPS across frontends
  - Main tabs use blue backgrounds with white text
  - Search sub-tabs use underline-only styling
  - Consistent file upload and processing experiences

- **Cross-Framework Functionality**
  - Identical file upload with progress tracking in all frontends
  - Real-time processing status updates and cancellation
  - Hybrid and Q&A search modes with consistent result formatting
  - Auto-scrolling chat interfaces with message history

## [2025-08-18] - Docker Rebuild & Async Event Loop Resolution

### Fixed
- **Critical Async Event Loop Errors**
  - Resolved "Event object bound to different event loop" errors during file processing
  - Fixed "Detected nested async" errors with Ollama, especially for Office files requiring Docling
  - Implemented hybrid async approach with run_in_executor for all LlamaIndex operations
  - Proper event loop handling with nest_asyncio.apply() and RuntimeError catching

- **React Docker UI Issues**
  - Fixed old UI display by forcing Docker rebuild with --no-cache flag
  - Added API routing for both direct (port 3000) and proxied (port 8070) React UI
  - Added proxy configuration to vite.docker.config.ts and nginx location block

- **File Upload Management**
  - Fixed file overwriting instead of renaming (e.g., cmispress.txt vs cmispress_34.txt)
  - Added cleanup functionality via /api/cleanup-uploads endpoint
  - Fixed minor UI bugs like dollar sign in "Remove Selected" button

### Enhanced
- **Docker Configuration**
  - Updated to use gpt-5-oss:20b instead of llama3.1:8b for better quality
  - Fixed Angular ES module __dirname issues with fileURLToPath
  - Added --esm flag to ts-node commands

### Validated
- **End-to-End Testing**
  - File upload (PDF, Office docs, text) working
  - CMIS and Alfresco repository integration functional
  - Search/query/chat functionality operational across all data sources

## [2025-08-17] - Tab UI Redesign & File Processing Table (React UI Only)

### Added
- **5-Tab Navigation System (React UI)**
  - Sources: Data source configuration and file upload
  - Processing: File management table with progress tracking
  - Search: Quick search functionality
  - Chat: Interactive Q&A and search conversations
  - Graph: Placeholder for future graph visualization

- **Processing Table Implementation (React UI)**
  - Single-row-per-file design with wide progress bar column (400px+)
  - Multi-select functionality with bulk operations
  - Windows-style file size formatting
  - Real-time per-file progress tracking within table rows

### Enhanced
- **File Management Features (React UI)**
  - Individual file remove buttons and select all/individual checkboxes
  - "Delete Selected (N)" button with proper state management
  - Drag-and-drop upload integration with table display
  - Color-coded status chips and progress phase information

- **Per-File Progress Tracking**
  - Backend per-file progress tracking with _initialize_file_progress and _update_file_progress
  - Fixed completion status timing by moving final callback to hybrid_system.py
  - Enhanced React frontend with individual file progress cards
  - Persistent debug panel with localStorage and performance logging

### Fixed
- **File Upload Progress Bar Issues (React UI)**
  - Root cause: Filename mismatch between UI (original names) and backend (saved names with duplicates)
  - Solution: Updated selectedFiles and configuredFiles with saved filenames after upload
  - Progress bars now display correctly with blue bars and real-time updates

### Note
- Vue and Angular frontends maintain previous UI design pending future updates

## [2025-08-16] - Documentation & Deployment Improvements

### Enhanced
- **README.md Updates**
  - Fixed Python backend setup with proper project directory paths
  - Updated environment configuration to copy env-sample.txt instead of creating empty .env
  - Restructured Frontend Setup section to clarify production vs development modes
  - Enhanced Project Structure section with missing directories (/docker, /docs, /scripts, /tests)

- **Docker Service Configuration**
  - Comprehensive service comment-out guide for docker-compose.yaml
  - Detailed guidance for customizing all services (neo4j, kuzu, qdrant, elasticsearch, opensearch, alfresco)
  - Removed "Recommended" from Docker Deployment header
  - Added app-stack.yaml environment configuration guidance

### Documentation
- **Deployment Clarity**
  - Clear separation between Docker and standalone deployment approaches
  - Updated frontend deployment section noting Docker limitations for filesystem sources
  - Added reference to docs/ENVIRONMENT-CONFIGURATION.md for detailed setup

## [2025-08-15] - Frontend Environment Variables & Vector Database Validation

### Fixed
- **Frontend Environment Variable Issues**
  - Vue frontend template compilation errors with `import.meta.env` expressions
  - React JSX environment variable resolution using computed placeholders  
  - Angular production environment forcing Docker URLs for standalone deployments
  - TypeScript compilation errors for window environment declarations

### Enhanced
- **Flexible Environment Configuration**
  - Vue: Computed properties with fallback defaults for environment variables
  - React: useMemo hooks for optimized environment resolution
  - Angular: Runtime environment service supporting both standalone and Docker modes
  - Production builds no longer require Docker infrastructure

### Validated
- **Complete Vector Database Support**
  - Qdrant: Dedicated vector store with external container configuration
  - Elasticsearch: Dual-purpose vector and fulltext search with separate indexes
  - Neo4j: Vector database support with separate VECTOR_DB_CONFIG requirements
  - OpenSearch: Hybrid search with single index and pipeline-based score fusion
  - BM25: Local filesystem storage without external SEARCH_DB_CONFIG

### Documentation
- Updated Neo4j vector index cleanup commands (`hybrid_search_vector` vs `vector`)
- Clarified BM25 configuration requirements and local storage approach
- Simplified Neo4j cleanup instructions using `SHOW INDEXES` commands

## [2025-08-14] - Environment Configuration & Documentation

### Added
- **Comprehensive Environment Configuration System**
  - Complete `docs/ENVIRONMENT-CONFIGURATION.md` with 5-section structure guide
  - Clean separation of schema, database, and source configurations  
  - Database switching patterns and configuration best practices
  - Missing Kuzu configuration with proper JSON format examples

### Enhanced
- **Environment File Organization**
  - Moved schema configuration to dedicated section in `env-sample.txt`
  - Fixed Neo4j default URI from incorrect port 7689 to standard 7687
  - Added proper DB_CONFIG examples with JSON format for all database types
  - Organized into logical sections for easy database switching

### Documentation
- Created supporting documentation: `SOURCE-PATH-EXAMPLES.md`, `TIMEOUT-CONFIGURATIONS.md`
- Updated `docs/SCHEMA-EXAMPLES.md` to focus purely on schema examples
- Established clean separation of concerns with cross-referenced documentation
- Maintained backward compatibility while improving organization

## [2025-08-13] - Kuzu Integration & Docker Full-Stack

### Added
- **Complete Kuzu Graph Database Integration**
  - Kuzu support as alternative to Neo4j using Approach 2 (separate vector stores)
  - Dual schema system: KUZU_SCHEMA for Kuzu, SAMPLE_SCHEMA for Neo4j
  - LLM provider awareness for embedding models (OpenAI/Ollama/Azure)
  - Graph API endpoint `/api/graph` for programmatic access to Kuzu data

- **Docker Infrastructure Overhaul**  
  - Fixed all Docker networking issues with Node.js 24 updates
  - NGINX proxy configuration with proper upstream routing
  - Standardized port allocation resolving conflicts
  - Frontend Docker configurations with internal networking support

### Enhanced
- **Database Architecture Flexibility**
  - Clean separation: Kuzu for graphs, Qdrant for vectors, Elasticsearch for search
  - Schema validation system with `has_structured_schema=False` for Kuzu
  - Identical search performance across Neo4j and Kuzu backends
  - Multiple visualization options: Kuzu Explorer, Neo4j Browser, API access

## [2025-08-12] - Async Processing & Event Loop Resolution

### Fixed
- **Ollama Event Loop Issues**
  - Comprehensive async approach with global `nest_asyncio.apply()`
  - Consistent async methods: `aquery()`, `aretrieve()` for all LLM providers
  - Windows event loop policy fixes with `WindowsSelectorEventLoopPolicy`
  - Simplified architecture removing complex fallback mechanisms

### Enhanced
- **Unified Async Architecture**
  - Applied async patterns to all LLM providers, not just Ollama
  - LlamaIndex integration following library recommendations
  - Removed thread isolation in favor of proper async handling

## [2025-08-11] - OpenSearch Native Hybrid Search

### Added
- **OpenSearch Native Hybrid Search Implementation**
  - Single retriever using `VectorStoreQueryMode.HYBRID` 
  - Eliminated async connection conflicts from dual retrievers
  - Native OpenSearch score fusion instead of manual combination
  - Automated pipeline creation with `scripts/create_opensearch_pipeline.py`

### Enhanced
- **Search Architecture Improvements**
  - Hybrid mode detection in factories.py for OpenSearch
  - Fulltext-only mode using `VectorStoreQueryMode.TEXT_SEARCH`
  - Re-enabled async support in QueryFusionRetriever
  - Better relevance than manual fusion approaches

## [2025-08-10] - Database Integration & Hybrid Search Testing

### Added
- **Comprehensive Hybrid Search System**
  - Dual-index Elasticsearch hybrid search (vector + fulltext)
  - Working configurations for Qdrant+Elasticsearch+Kibana combinations
  - OpenSearch factory configuration with `OpensearchVectorClient`
  - Pure RAG mode with `ENABLE_KNOWLEDGE_GRAPH=false`

### Fixed
- **BM25 Standalone Search Issues**
  - Document storage overwriting preventing proper indexing
  - Early exit logic incorrectly assuming BM25 required vector docstore
  - Zero-relevance filtering to exclude irrelevant results
  - Direct retriever usage for single-modality scenarios

### Enhanced
- **UI Client Improvements**
  - Zero results feedback across all frontend clients (Vue, Angular, React)
  - Accumulative document storage across multiple ingestions
  - Professional "No results found" messages with search term display

## [2025-08-09] - MCP Server and Async Processing

### Added
- **MCP Server Implementation**
  - FastMCP-based Model Context Protocol server for Claude Desktop integration
  - HTTP and stdio transport modes (`--transport http`, `--http`, `--serve` flags)
  - Command-line argument parsing for host, port, and transport configuration
  - Multiple installation methods: pipx, uvx, direct Python execution
  - Platform-specific Claude Desktop configurations (Windows/macOS)
  - MCP Inspector debugging support with dedicated configurations
- **MCP Tools**
  - `get_system_status`, `ingest_documents`, `ingest_text`, `search_documents`
  - `query_documents`, `test_with_sample`, `check_processing_status`
  - `get_python_info`, `health_check`
- **Asynchronous Processing Pattern**
  - Background task processing with processing ID system
  - Real-time progress updates with percentage, current file, and phase information
  - Dynamic time estimation based on content size and file count
  - Processing cancellation support with graceful cleanup
  - Server-Sent Events (SSE) endpoints for real-time UI updates
- **UI Enhancements**
  - Progress bars with 0-100% completion tracking across all clients
  - Cancel processing buttons with proper state management
  - Time estimation displays and file-level progress indicators
  - Phase tracking (docling, chunking, indexing, kg_extraction)
  - Auto-clearing status messages and manual dismiss options

### Fixed
- **Asyncio Event Loop Conflicts**
  - Added `nest_asyncio` support to handle nested event loops
  - Wrapped LlamaIndex operations in `loop.run_in_executor()` 
  - Resolved `asyncio.run() cannot be called from a running event loop` errors
- **Neo4j Compatibility Issues**
  - Added `refresh_schema=False` to prevent APOC `apoc.meta.data` calls during initialization
  - Fixed Cypher syntax incompatibility between Neo4j 25.x and LlamaIndex 0.5.0
  - Updated cleanup commands to include `entity` index and LlamaIndex constraints
- **Package Installation Issues**
  - Fixed `pyproject.toml` from `packages = ["."]` to `py-modules = ["main"]` for uvx support
  - Added proper script entry points for system-wide command availability
- **Processing State Management**
  - Implemented intelligent cleanup that preserves functional systems after cancellation
  - Fixed search functionality after completed ingestion followed by cancelled operation
- **UI Client Issues**
  - Fixed Angular compilation errors (MatProgressBarModule, RxJS imports, TypeScript types)
  - Corrected snackbar duration and auto-clearing logic
  - Added proper async status polling in all three UI frameworks

### Changed
- **API Response Format**
  - Ingestion endpoints now return immediate `AsyncProcessingResponse` with `processing_id`
  - Added `/api/processing-status/{id}` and `/api/processing-events/{id}` endpoints
  - Separated `/api/test-sample` (default) and `/api/ingest-text` (custom content) endpoints
  - Enhanced `/api/status` to include `search_db` configuration
- **Configuration Management**
  - Made sample text configurable via `SAMPLE_TEXT` environment variable
  - Organized Claude Desktop configs by platform (windows/, macos/)
  - Separated MCP Inspector configs by transport (stdio/HTTP)
  - Added Unicode environment variables for Windows compatibility

### Documentation
- Comprehensive README.md with multiple installation methods
- QUICK-USAGE-GUIDE.md for streamlined setup
- Platform-specific configuration examples and troubleshooting guides
- Ready-to-use Claude Desktop JSON configurations
- MCP Inspector configs for both stdio and HTTP modes
- Test scripts for installation validation (PowerShell and Bash)

## [2025-08-07] - UI Client Updates and Data Sources

### Added
- React and Vue client modifications to match Angular's data source selection capabilities
- Hybrid search with results list (in addition to Q&A AI query mode)
- CMIS and Alfresco data sources beyond filesystem (Alfresco uses CMIS for getObjectByPath)
- Support for additional document formats that Docling supports

### Changed
- Updated screen images to reflect new hybrid search functionality

## [2025-08-06] - LlamaIndex Integration and Configuration

### Added
- **LlamaIndex Integration**
  - Replaced LangChain with LlamaIndex for document processing
  - VectorStoreIndex and PropertyGraphIndex implementation
  - IngestionPipeline with SentenceSplitter, KeywordExtractor, SummaryExtractor
- **Configurable Architecture**
  - Vector database, graph database, and search database configuration
  - Support for multiple database backends (Neo4j, Qdrant, etc.)
  - Environment-based configuration management
- **Hybrid Search System**
  - Combined vector similarity, BM25 full-text search, and graph traversal
  - AI Q&A mode alongside hybrid search results
  - Configurable retrieval strategies
- **Multi-Source Data Ingestion**
  - Filesystem, CMIS, and Alfresco data source support
  - Docling integration for PDF and Microsoft Office documents
  - Smart table-to-markdown conversion with fallback to text extraction
- **Document Processing**
  - Support for 12+ file formats via Docling
  - Intelligent chunking and metadata extraction
  - Knowledge graph entity and relationship extraction

### Changed
- **Architecture Migration**
  - Migrated from cmis-graphrag/langchain/neo4j-graphrag stack
  - Unified configuration system across all components
  - Angular dialog updates (React and Vue clients pending similar changes)

### Fixed
- Document format support alignment with Docling capabilities
- Filesystem data source integration (CMIS and Alfresco integration planned)

### Technical
- Tested with Neo4j as graph and vector database
- LlamaIndex BM25 as full-text search engine
- Elasticsearch and OpenSearch integration marked for future development

## [2025-08-05] - Initial Project Setup

### Added
- Flexible GraphRAG initial project structure
- Reorganized from cmis-graphrag-ui with frontends moved to flexible-graphrag-ui subdirectory
- Backend moved to flexible-graphrag subdirectory

