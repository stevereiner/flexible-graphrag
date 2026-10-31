# Python 3.15 and 3.15t (free-threaded)

Flexible GraphRAG supports Python 3.12-3.14 (`requires-python = ">=3.12,<3.15"` in
`flexible-graphrag/pyproject.toml`). Python 3.15 was released in October 2026 and is **being
checked, not enabled yet**. The free-threaded build, **3.15t** (no GIL), is **experimental and in
progress**.

This page covers what works on each, how to try regular 3.15, and why the code changes made for
3.15t were needed. Status as of 2026-10-30, on Windows.

## Python 3.15 (regular, with the GIL)

### Status

- **A normal install is refused:** `requires-python` is still `<3.15`. To try 3.15 you raise it
  locally (see below).
- **What is being checked:** whether the backend installs from wheels with only the packages that
  have no 3.15 build left out, then backend startup and an end-to-end ingest, hybrid search and
  AI query.
- **Left out:** only 2 groups have no 3.15 build at all:
  - **chromadb** (needs onnxruntime) and its LlamaIndex vector store: no Chroma.
  - **LadybugDB** (`ladybug` declares `requires-python <3.15`) and its LlamaIndex graph store:
    no LadybugDB.
- **Verified on 3.15.0** with the liteparse parser:
  - backend startup (`/api/health`, `/docs`), incremental updates on
  - ingest of PDF, DOCX, PPTX and XLSX into **Qdrant** + Elasticsearch + Neo4j + GraphDB RDF
  - hybrid search and an AI query with OpenAI, with correct answers
  - the LlamaParse parser, the all-LangChain backend (`*_BACKEND=langchain`) and the CocoIndex
    pipeline also passed end-to-end
- **Being re-checked:** **docling** (docling-parse, torch and spaCy now ship 3.15 wheels, so the
  docling parser installs on 3.15) and the LangChain extras without the earlier workarounds
  (ormsgpack now has a 3.15 wheel).
- **Not on 3.15:** Langflow (langflow / lfx declare `requires-python <3.15`), so flow mode needs
  its own Langflow on 3.14 or earlier.
- **Code changes:** the ones listed under 3.15t (lazy LLM / embedding imports, the docling
  fallbacks, the GCS detector without grpcio, GraphDB SPARQL JSON results) apply on every Python
  version, 3.15 included. 3.15 didn't need them: those packages all install there (fastuuid builds
  with `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1`), and it passed end-to-end before
  they were made. They make a 3.15 install keep working when one of those packages is left out.
- **Speed:** no measurable difference from 3.14 in import or document parsing time.

### How to try it

Use the python.org 3.15 installer (`py -3.15` on Windows). From the repo root:

1. In `flexible-graphrag/pyproject.toml`, raise the Python cap locally (don't commit it):

   ```toml
   requires-python = ">=3.12,<3.16"
   ```

2. Create `flexible-graphrag/py315-overrides.txt` with the 4 packages to leave out (a marker that is
   never true removes the requirement wherever it appears):

   ```text
   chromadb; python_version < "0"
   llama-index-vector-stores-chroma; python_version < "0"
   ladybug; python_version < "0"
   llama-index-graph-stores-ladybug; python_version < "0"
   ```

3. Create and activate a 3.15 venv, then install:

   Windows (`cmd`):

   ```bat
   py -3.15 -m venv venv-3.15
   venv-3.15\Scripts\activate
   cd flexible-graphrag
   set PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
   uv pip install --system-certs --override py315-overrides.txt "grpcio>=1.84" -e .
   ```

   Linux / macOS:

   ```bash
   python3.15 -m venv venv-3.15
   source venv-3.15/bin/activate
   cd flexible-graphrag
   export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
   uv pip install --override py315-overrides.txt "grpcio>=1.84" -e .
   ```

   - `grpcio>=1.84`: the first grpcio with a 3.15 wheel. Without it the resolver may pick an older
     grpcio, a very large C++ source build.
   - `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1`: lets Rust packages built with PyO3 (fastuuid via
     litellm) build against the stable ABI on 3.15; their PyO3 version otherwise refuses
     Python > 3.14.
   - A few small packages may compile from source (C / Rust; Windows needs the MSVC build tools).
   - For the LangChain backend add the extras: `-e ".[langchain,langchain-extras]"`.

4. In `.env`, use a vector store other than Chroma and a graph store other than LadybugDB. Then
   start the backend as usual (`python start.py` with the venv active).

## Python 3.15t (free-threaded, no GIL): experimental

### Status

- **Works (ingest, hybrid search, AI query, with the GIL off):** LlamaIndex core, OpenAI LLM and
  embeddings, the full LangChain backend, Neo4j, ArcadeDB and FalkorDB property graphs,
  Elasticsearch and OpenSearch, GraphDB RDF, OpenArch (store and sync-state store), incremental
  updates (filesystem), LlamaParse.
- **Works, degraded:** docling, with its pypdfium2 PDF backend and no PDF table structure.
- **Blocked:**

  | Area | Why |
  |---|---|
  | Qdrant, Weaviate, GCS Pub/Sub sync | grpcio has no free-threaded wheel (and is a huge C++ build) |
  | liteparse | abi3-only wheel; its source build compiles Tesseract / Leptonica |
  | Milvus | orjson refuses free-threaded builds |
  | Pinecone, LanceDB | PyO3 / abi3-only wheels, no free-threaded build |
  | Chroma, LadybugDB | no 3.15 build at all (as on regular 3.15) |
  | Postgres pgvector | psycopg2-binary / psycopg-binary have no free-threaded wheel |
  | LiteLLM provider | fastuuid (PyO3) refuses 3.15 |
  | MCP server on Windows | `mcp` needs pywin32, no free-threaded wheel |
  | Langflow | declares `requires-python <3.15` |

- **The GIL comes back whenever lxml loads.** lxml has a free-threaded wheel but doesn't declare
  itself GIL-free, so Python re-enables the GIL on import. docling's DOCX / PPTX readers and the
  web readers load it; RDF search no longer does (see below).
- **Installing is manual:** free-threaded Python can't use abi3 (stable-ABI) wheels, and the
  `PYO3_USE_ABI3_FORWARD_COMPATIBILITY` workaround is refused there, so several Rust packages must
  be compiled one at a time. There is no single install command yet.
- **Speed:** one thread is 0-7% slower than with the GIL. CPU-bound work on several threads
  (chunking, rdflib, pydantic) scales 3-5x at 8 threads, where the GIL build doesn't scale at all.
  But an ingest is about 96% waiting on the LLM, embeddings and databases, so a single ingest is
  no faster. Raising `KG_EXTRACTION_WORKERS` (with a cloud LLM) helps ingest time far more than
  free-threading.

### Code changes made for 3.15t, and why

Each one is because of a package that has no free-threaded build, or one that turns the GIL back
on. Normal installs behave as before.

- **LLM and embedding imports are lazy** (`llamaindex/llm/llm_factory.py`, `embedding_factory.py`):
  Groq, OpenRouter, OpenAI-like and LiteLLM are imported only when that provider is used. The
  OpenAI-like module imports transformers (needs tokenizers) and LiteLLM needs fastuuid; with no
  3.15t builds, importing them at module load stopped the backend from starting at all.
- **Docling without docling-parse or opencv** (`process/document_processor.py`): the PDF backend
  falls back to docling's pypdfium2 backend when docling-parse (C++) isn't installed, and PDF table
  structure (TableFormer imports opencv) is skipped when opencv isn't. Neither has a 3.15t wheel.
- **GCS detector without grpcio** (`incremental_updates/detectors/gcs_detector.py`): without
  grpcio, `google.cloud.pubsub_v1` fails with an AttributeError instead of an ImportError. The
  ingest endpoint imports the incremental-update modules even when they're off, so every ingest
  returned HTTP 500.
- **GraphDB RDF search asks for SPARQL JSON** (`GRAPHDB_SPARQL_RESULTS_FORMAT`, default `json`;
  `xml` = the old behaviour): rdflib's SPARQL XML result parser imports lxml, which turned the GIL
  back on at the first RDF query. With `json`, ASK / SELECT come back as SPARQL JSON and CONSTRUCT
  as Turtle, with identical results.
- **`pyarrow` declared as a dependency:** the OpenArch store writes chunks as Parquet with pyarrow,
  which was only installed through LanceDB (not installable on 3.15t). This affects every Python
  version without LanceDB.
