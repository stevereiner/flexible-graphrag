# CocoIndex Integration

[CocoIndex](https://github.com/cocoindex-io/cocoindex) is an incremental data-transformation
framework with a Rust engine. Flexible GraphRAG can use it as an **alternative ingest
pipeline**: same sources, same target databases, same UI and REST/MCP APIs — but CocoIndex
owns orchestration and change processing instead of the default LlamaIndex/LangChain path.

**Noticing that a source changed stays Flexible GraphRAG's job either way.** The event
detectors in `incremental_updates/detectors/` — the filesystem watchdog, S3/GCS/Azure change
feeds, Google Drive and MS Graph delta queries, Alfresco and Nuxeo audit streams — are shared:
the [auto-sync incremental update system](../DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/README.md)
drives them on the default pipeline, and here `FlexibleMapView` adapts the same detector to a
CocoIndex `LiveMapView`. So switching pipelines does not change how your sources are watched,
only what happens to a change once it is detected. (The exception is
`SOURCE_BACKEND=cocoindex`, which reads through CocoIndex's own four native connectors instead
— see [Choosing the source](../CONFIGURATION/CONFIG-COCOINDEX.md).)

Turn it on in `.env`:

```bash
PIPELINE_BACKEND=cocoindex
ENABLE_INCREMENTAL_UPDATES=false
ENABLE_LANGFLOW_FLOWS=false
```

!!! warning "Two settings are mutually exclusive with CocoIndex"
    - `ENABLE_INCREMENTAL_UPDATES=true` — the FG incremental engine re-ingests through
      `hybrid_system` (the default pipeline), *not* CocoIndex. Both enabled means two systems
      writing to the same indexes. Startup skips the FG orchestrator and logs a warning.
    - `ENABLE_LANGFLOW_FLOWS=true` — CocoIndex is not wired into Langflow flows. Startup
      force-disables flow mode and logs a warning.

## Related documentation

- [CocoIndex Configuration](../CONFIGURATION/CONFIG-COCOINDEX.md) — every `.env` setting
- [CocoIndex Developer Guide](../DEVELOPER/DEVELOPER-COCOINDEX.md) — internals, APIs, customizing
- [Meeting notes example](../../examples/cocoindex/meeting_notes_graph_any/README.md) — a
  CocoIndex example ported to this integration: custom extractor, three ways to run it
- [Database Configuration](../DATABASES/DATABASE-CONFIGURATION.md) — connection settings per store
- CocoIndex's own docs: [overview](https://cocoindex.io/docs/getting_started/overview/) ·
  [examples](https://cocoindex.io/docs/examples/)

---

## Should you use it?

CocoIndex mode is **optional**, and the comparison is not "incremental vs. not" — the default
pipeline with the incremental update system enabled already skips unchanged files via the same
event detectors. The two differ in how re-work is avoided and what it costs to avoid it.

**Use CocoIndex when you want:**

- **Step-level memoization.** The default pipeline with incremental updates decides *per file*
  whether to re-ingest. CocoIndex memoizes *per step*: change the chunk size and only chunking
  + embedding re-run — parsing is served from cache. Change the ontology and only KG extraction
  re-runs. This is the substantive difference.
- **Cheaper reprocessing after a config change.** You pay LLM/API calls only for the steps whose
  inputs actually changed, which matters most on large corpora.
- **Automatic delete reconciliation.** Remove a source file and CocoIndex's reconciler issues
  the deletes across every configured target, with no bookkeeping table.
- **A Rust orchestration engine**, with call batching for embeddings. Worth being precise about
  what this does and does not speed up: orchestration, change computation and batching are
  faster, but ingest wall-clock is usually dominated by LLM calls, embedding APIs and database
  writes — none of which Rust makes faster.

**Stay on the default pipeline with incremental updates when:**

- You need Langflow flows (not supported together — see below).
- **You want Postgres-backed state.** The incremental update system tracks documents in
  Postgres, which scales further and is easier to inspect, back up and share between processes.
  The open-source CocoIndex engine currently supports only local LMDB.
- **You want to store less.** CocoIndex's memoization is an *additional* store: cached step
  outputs live in LMDB on top of whatever is already in your vector, search, graph and RDF
  databases. The default pipeline keeps only per-document tracking rows.

---

## What stays the same

Almost everything:

| | Default pipeline | CocoIndex pipeline |
|---|---|---|
| REST / MCP / UI | — | unchanged |
| Data sources | 14 | the same 14 |
| Change detectors | 10 detector-backed sources | the same detectors |
| Multi-source config | Postgres `datasource_config` | the same table |
| Target databases | 15 graph / 4 RDF / 10 vector / 3 search | the same |
| Parsers | Docling / LlamaParse / LiteParse | the same |
| KG extraction | LlamaIndex / LangChain, ontology-guided | the same, plus custom `KGExtractor`s |
| Search + QA | reads the indexes | unchanged — reads the same indexes |

## What changes

Who drives ingest, and where per-document state lives:

| | Default + `ENABLE_INCREMENTAL_UPDATES=true` | CocoIndex |
|---|---|---|
| Who feeds the pipeline | FG incremental system → LI/LC pipeline | CocoIndex `coco.App` (Rust engine) |
| Document tracking | Postgres `document_state` | CocoIndex LMDB (`cocoindex.db`) |
| Re-run cost | unchanged files never enter the pipeline | unchanged *steps* are served from LMDB |
| Deletes | detector DELETE → pipeline | CocoIndex reconciler → `delete_row` on each target |
| Ingest without auto sync (v0.8.2+) | recorded (`datasource_config` with `auto_sync = false` + `document_state`); a repeat replaces the earlier copy | not recorded in Postgres; a repeat is a no-op through CocoIndex's own state |
| Processing-tab "already synced / ingested" status | yes | no (`/api/sync/coverage` answers `enabled: false`) |

CocoIndex needs only `POSTGRES_INCREMENTAL_URL` for its Postgres rows: it writes `datasource_config` for its startup `.env` source and for UI ingests with auto sync checked, and never writes `document_state`. See [Ingests Without Auto Sync Are Recorded Too](../DATA-SOURCES/INCREMENTAL-UPDATE-AUTO-SYNC/README.md#ingests-without-auto-sync-are-recorded-too).

---

## Install and enable

### Install

```bash
# CocoIndex itself
uv pip install -e ".[cocoindex]"

# Optional extras
uv pip install "cocoindex[sentence_transformers]" # local GPU embeddings, no API key
uv pip install "cocoindex[litellm]"               # 100+ embedding providers — already satisfied,
                                                  # litellm is a base dependency
uv pip install "cocoindex[entity_resolution_llm]" # ENTITY_RESOLUTION=llm (see below)

python -c "import cocoindex; print(cocoindex.__version__)"   # expect >= 1.0.20
```

`ENTITY_RESOLUTION=normalize` needs no extra. `llm` needs one of the two extras below, and
degrades to `normalize` with a warning without either, so it never fails an ingest — it just
quietly does less.

| extra | gives you |
|---|---|
| `entity_resolution` | the minimum for `ENTITY_RESOLUTION=llm`. Flexible GraphRAG supplies its own `PairResolver` and `Embedder`, wired to the `LLM_PROVIDER` and embedding model you already configured, so resolution uses the same models as the rest of the pipeline. |
| `entity_resolution_llm` | the whole of [CocoIndex's entity-resolution API](https://cocoindex.io/docs/ops/entity_resolution/), including its built-in `LlmPairResolver`, alongside custom resolvers like ours. |

**`entity_resolution_llm` is the better default.** It lists faiss-cpu, `instructor` and
`litellm`; faiss-cpu is common to both extras and litellm is already a base dependency here, so
the only difference between the two is `instructor` — one package for the whole API surface.

`LlmPairResolver` uses `instructor` to make the model return a validated Pydantic decision
rather than prose. Our own resolver does not need it — it prompts for a bare name and maps the
answer back to a candidate.

!!! warning "Install the extras you need, not `cocoindex[all]`"
    `[all]` is about 30 packages — Valkey, Snowflake, BigQuery, Doris, Kafka, Iggy, OCI,
    turbopuffer, colpali and so on. Almost none of it applies here: Flexible GraphRAG reaches
    its stores through its own adapters, and only three targets (Neo4j, FalkorDB, SurrealDB)
    plus four sources ever go through CocoIndex's native connectors.

    It also overlaps packages this project pins deliberately — `[all]` asks for
    `qdrant-client>=1.6.0` with no upper bound, where `pyproject.toml` caps it at `<1.19`
    because 1.19 moved `IDF_EMBEDDING_MODELS` and breaks `llama-index-vector-stores-qdrant`.

    On Python 3.14 / Windows it fails outright anyway: `valkey-glide` has no matching wheel, so
    uv falls back to its sdist, which builds through maturin and needs Rust in `PATH`.

    ```
    × Failed to build `valkey-glide==2.5.1`
    ╰─▶ Caused by: Cargo metadata failed. Do you have cargo in your PATH?
    ```

    Nothing is left half-installed — uv aborts the whole transaction. Install the four extras
    above instead.

### Enable

In `.env` — the last two are mutually exclusive with CocoIndex (see the warning at the top of
this page), so set them explicitly if anything already turned them on:

```bash
PIPELINE_BACKEND=cocoindex
ENABLE_INCREMENTAL_UPDATES=false
ENABLE_LANGFLOW_FLOWS=false
```

Then:

1. Start the backend as usual (`uv run start.py`).
2. Ingest through the UI, REST, or MCP — how you call it does not change.
3. Or skip the server entirely and run the pipeline
   [from the CLI](#running-without-the-server) — an option CocoIndex mode adds that the default
   pipeline does not have.

---

## How sources work

Point the pipeline at a source and it keeps that source up to date. Every data source you
configure — from `.env`, from the UI Data Source tab, or from a REST/MCP call — becomes its own
`coco.App` with its own connection settings and its own watch root.

**Two kinds of source, two change strategies:**

- **Detector-backed (10)** — filesystem, S3, GCS, Azure Blob, Google Drive, OneDrive,
  SharePoint, Box, Alfresco, Nuxeo. These get a **live stream**: the existing FG change
  detector runs and feeds adds/modifies/deletes to CocoIndex as they happen. Only changed files
  are downloaded — listing is metadata-only.
- **Snapshot-only (4)** — web, Wikipedia, YouTube, CMIS. No change stream, so these are
  reconciled by a periodic re-scan (`COCOINDEX_POLL_INTERVAL`).

`DATA_SOURCE` picks the primary source that starts with the server:

| `DATA_SOURCE` | Behaviour |
|---|---|
| unset | defaults to `filesystem`, watching `WATCH_DIR` |
| a source name | that source starts at boot |
| `""` or `none` | no primary source — the bridge waits for the UI / REST / MCP to supply one |

Sources added later through the UI are stored in `datasource_config` and rebuilt automatically
on the next restart.

**Watching a folder:** pass a directory path to `/api/ingest` with `enable_sync=true` and that
directory becomes its own watched source, exactly as in the default pipeline. It does not have
to be `WATCH_DIR` — that is only the default for the primary `.env` source and the staging area
for UI file uploads.

---

## Mixing CocoIndex and Flexible connectors

Inside the pipeline each stage independently uses either a **native CocoIndex** connector or a
**Flexible** one (Flexible = Flexible GraphRAG's own LlamaIndex/LangChain adapters). You choose
per stage; the defaults are all Flexible.

| Stage | Native CocoIndex option | Flexible option (default) |
|---|---|---|
| Source | `SOURCE_BACKEND=cocoindex` → localfs, S3, Azure Blob, Google Drive | all 14 sources |
| Chunking | `CHUNKER_BACKEND=cocoindex` → syntax-aware splitter | LlamaIndex / LangChain splitters |
| Embedding | `COCOINDEX_EMBEDDING_KIND` → sentence-transformers, LiteLLM | every `EMBEDDING_KIND` provider |
| Vector target | `VECTOR_BACKEND=cocoindex` → Qdrant, LanceDB, Postgres | all 10 vector stores |
| Graph target | `GRAPH_BACKEND=cocoindex` → Neo4j, FalkorDB, SurrealDB | all 15 graph stores |
| RDF target | — | all 4 RDF stores |
| Search target | — | all 3 search stores |
| Parsing | — | Docling / LlamaParse / LiteParse |
| KG extraction | — | LlamaIndex / LangChain, ontology-guided — or your own `KGExtractor` |

Two stages are deliberately Flexible-only. **Parsing** and **KG extraction** have no native
CocoIndex equivalent that produces the multi-label, ontology-guided entity graphs this project
builds, so they always run through Flexible GraphRAG even when every other stage is native.

KG extraction is also the one stage you can replace with your own code:
`KG_EXTRACTOR_BACKEND` accepts a custom
[`KGExtractor`](../CONFIGURATION/CONFIG-COCOINDEX.md#custom-extractors) instead of either
built-in. It still sits in the Flexible column — it is your Python running in the pipeline, not
a native CocoIndex operation — and it can call `ctx.builtin()` to hand content it does not
recognise back to the built-in extractor, so one run can cover a source that is not uniform.

If you request a native connector that isn't available for your chosen database, the pipeline
logs the downgrade and falls back to the Flexible adapter rather than failing.

### CocoIndex connectors this integration does not route

CocoIndex ships connectors beyond the ones wired up here. See its
[connectors reference](https://cocoindex.io/docs/connectors/) for the current list; where they
stand in this integration:

| CocoIndex connector | here |
|---|---|
| **Vector targets** — turbopuffer, valkey, zvec, doris, sqlite | registry stubs, not wired |
| **Relational / analytical targets** — postgres, doris, sqlite, snowflake, bigquery | not routed |
| **Sources** — OCI Object Storage, postgres, Kafka, Iggy | routed, via native passthrough |
| **Targets** — filesystem, postgres (general table)\*, Kafka, Iggy | not routed |

\* Postgres **pgvector** *is* supported — as a native CocoIndex vector target, and through the
Flexible LlamaIndex and LangChain adapters. Only the general table target is unrouted.

The stubs are deliberate: a `None` entry in `COCO_VECTOR_REGISTRY` marks a store as
known-but-unimplemented, so the fallback to a Flexible adapter is explicit rather than
accidental. Wiring one up is a builder function — see
[Extending it](../DEVELOPER/DEVELOPER-COCOINDEX.md#extending-it).

Note the asymmetry between the last two rows: Postgres, Kafka and Iggy are reachable as
**sources** but not as **targets**. Those four sources have no Flexible GraphRAG equivalent, so
they are capabilities this pipeline adds rather than gaps.

---

## Running without the server

The pipeline is a normal CocoIndex app, so it also runs from the CLI with no FastAPI, UI, or MCP
layer — useful for batch jobs and CI:

```bash
cd flexible-graphrag
cocoindex update cocoindex_integration/pipeline/app.py        # one catch-up pass
cocoindex update -L cocoindex_integration/pipeline/app.py     # stay live
```

It reads the same `.env` and runs the same parsers, chunkers, embedders, KG extractors, and store
adapters. Only the HTTP layer is absent.

!!! tip "`WATCH_DIR` is resolved relative to the working directory"
    `./cocoindex-docs` from `flexible-graphrag/` is **not** the same folder as `./cocoindex-docs`
    from the repository root. If a CLI run reports nothing to do, check which directory it
    actually scanned — the startup banner prints it.

    The code default is `./cocoindex-docs`, and both the server and these CLI commands run from
    `flexible-graphrag/` — but the repo keeps the folder at its **root**, so `.env` needs
    `../cocoindex-docs` to reach it:

    ```bash
    WATCH_DIR=../cocoindex-docs
    ```

    An absolute path avoids the question entirely.

---

## Monitoring

Set `COCOINDEX_ENABLE_PG_MONITORING=true` to record ingest activity in the incremental Postgres
database. This is bookkeeping only — it never drives change detection, and it is unrelated to
the OpenTelemetry [observability stack](../DEVELOPER/OBSERVABILITY/OBSERVABILITY.md).

- **`cocoindex_run_log`** — one row per update cycle, with document counts and elapsed time.
- **`cocoindex_ingest_log`** — one row per file by default. Set
  `COCOINDEX_MONITOR_DETAIL=stages` for a row per pipeline stage when you need to see where a
  file stalls.

---
