# Hyland OpenArch

[Hyland OpenArch](https://github.com/Hyland/OpenArch) is Hyland's open source (Apache 2.0) AI-ready content repository, for documents with their extracted text and vector embeddings,
built on the Nuxeo repository core, with MongoDB for documents and OpenSearch for full-text and vector search.
Flexible GraphRAG can use it in two ways, separately or together:

| Use | Setting | What OpenArch holds |
|---|---|---|
| **Search + vector store** | `ENABLE_OPENARCH=true` | Each ingested document, its parsed text (full-text search) and its chunks with their embeddings (vector search), in place of `VECTOR_DB` and `SEARCH_DB` |
| **Auto-sync state store** | `INCREMENTAL_STATE_STORE=openarch` | The incremental registry: data source configs, per-document state and per-folder / per-document scope rules, in place of PostgreSQL. See [OpenArch as the Auto-Sync State Store](OPENARCH-STATE-STORE.md) |

Property graphs (`PG_GRAPH_DB`) and RDF graphs (`RDF_GRAPH_DB`) are not affected: they are written and searched as
usual, and their results are fused with OpenArch's.

## Running OpenArch

OpenArch needs MongoDB and OpenSearch. Any of these works:

- **Hyland's Docker Compose**: the `docker-compose.yml` of the [OpenArch repository](https://github.com/Hyland/OpenArch)
  runs the published image (`ghcr.io/hyland/openarch-app-jvm`) with MongoDB and OpenSearch.
- **Built from source**: `mvn install -DskipTests` in a clone of the OpenArch repository, then run
  `server/openarch-app` (see its README). Use this for a commit newer than the published image.
- **On a graph database** (prototype): [openarch-graph-storage](https://github.com/stevereiner/openarch-graph-storage)
  keeps OpenArch's repositories in Neo4j or ArcadeDB instead of MongoDB, with the same REST API.

The local OpenArch users are in its `openarch-users.yml` (for example `admin` / `password`). Its REST API is at
`http://<host>:<port>/api/...`, with Swagger UI at `/swagger-ui/index.html` (newer builds offer HTTP Basic under
**Authorize**).

Port 8080 is OpenArch's default, which Alfresco also uses: when both run on one machine, publish OpenArch on
another port (for example 8088) and set `OPENARCH_URL` to it.

## Setup

1. The OpenArch client, [python-openarch-api](https://pypi.org/project/python-openarch-api/), comes with the
   backend (a dependency since 0.9.0). With an older environment, install it:

    ```bash
    uv pip install "python-openarch-api>=0.1.0"
    ```

2. Set the embedding dimension to **1024**. OpenArch indexes 1024-dimension vectors only, and chunks of another
   dimension are not searchable (the backend logs a warning at startup). For OpenAI's `text-embedding-3-small` or
   `-large`: `OPENAI_EMBEDDING_DIMENSION=1024`.

3. Turn it on in the backend's `.env`:

    ```bash
    ENABLE_OPENARCH=true
    OPENARCH_URL=http://localhost:8088
    OPENARCH_USERNAME=admin
    OPENARCH_PASSWORD=password
    ```

4. Restart the backend. `VECTOR_DB` and `SEARCH_DB` are then not used (the backend logs that it ignores them).

### Settings

| Setting | Default | Meaning |
|---|---|---|
| `ENABLE_OPENARCH` | `false` | OpenArch as the search + vector store |
| `OPENARCH_URL` | `http://localhost:8080` | OpenArch's address |
| `OPENARCH_USERNAME` / `OPENARCH_PASSWORD` | `admin` / `password` | An OpenArch user (HTTP Basic) |
| `OPENARCH_REPOSITORY` | `default` | The OpenArch repository to write to |
| `OPENARCH_ROOT_PATH` | `/fg-sources` | The folder ingested documents go under |
| `OPENARCH_SOURCE_IDS` | (none) | Names for repository servers, as JSON: `{"nuxeo-repo-1": "http://localhost:8081/nuxeo"}` (a list of addresses for a server reached under several) |
| `OPENARCH_EMBEDDING_TYPE` | `fg-<embedding kind>-<model>-<dimension>` | The name OpenArch keeps the chunks' embeddings under |
| `OPENARCH_MAX_TEXT_CHARS` | `64000` | Parsed text kept per document for full-text search |
| `OPENARCH_WRITE_CONCURRENCY` | `4` | Documents written in parallel |

All of them are in `env-sample.txt`, in the OpenArch section.

## Where documents go

Each source document is written **once per source system object**, at
`<OPENARCH_ROOT_PATH>/<source type>/<system id>/<source path>`, for example
`/fg-sources/alfresco/68caf25c-.../Shared/Reports/q3.pdf`. Two data sources (ingests or auto syncs) that cover the
same folder share the same OpenArch documents, and a document is found again by its source system and its id in
that system, so re-ingesting it updates it in place.

The `<system id>` folder keeps different servers of the same kind apart:

| Source type | System id |
|---|---|
| Alfresco | the `source_id` of the request's `alfresco_config`, else its name in `OPENARCH_SOURCE_IDS`, else the Alfresco repository id |
| Nuxeo, CMIS | the `source_id` of the request's config, else its name in `OPENARCH_SOURCE_IDS`, else `<host>-<port>` |
| S3, GCS | the bucket name |
| Azure Blob | `<account>-<container>` |
| SharePoint | the site name |
| OneDrive | the user principal name |
| Web | `<host>-<port>` of the URL |
| Wikipedia | the language (`en`, ...) |
| Filesystem, file upload | the backend's host name |
| Box, Google Drive, YouTube | `default` |

Each OpenArch document is a `SysFile` with:

- the `CinRemote` mixin: `cin_sourceId` (the source system) and `cin_id` (the object in it);
- its parsed text, which OpenArch indexes for full-text search (`sys_fulltext`), up to `OPENARCH_MAX_TEXT_CHARS`;
- its chunks and their embeddings in a `SysEmbeddings` child named `_e_<embedding type>`, which OpenArch puts in
  its kNN index.

The original file's content is not copied: the document points back to the source through its source path and ids.
For every field, and how this fits with the auto-sync state kept on the same documents, see the
[data model](OPENARCH-STATE-STORE.md#data-model).

When a document is moved or renamed in the source system, its OpenArch document follows. OpenArch's REST API has
no rename yet, so a rename is done as a copy under the new name and a delete, and the OpenArch document gets a new
OpenArch id; its source ids stay the same.

## Search

Hybrid search, AI query and AI chat send one query to OpenArch that combines kNN over the chunks with a match of
the query terms in the chunk text, fused inside OpenArch (OpenSearch's RRF). Its results are fused with those of
the property graph and RDF graph retrievers, as with any other vector + search store. A question scoped to a
document or folder (for example KG Spaces' **Ask about this document / folder**) is filtered inside OpenArch, by
the documents' source ids.

## Removing documents

Removing documents from search + vector (the Processing tab's per-row columns, or `POST /api/sync/remove`) removes
their text and chunks from OpenArch. The OpenArch document goes once no data source refers to it any more; while
an auto sync still keeps state on it ([state store](OPENARCH-STATE-STORE.md)), it stays without text and chunks.

To delete everything Flexible GraphRAG put into OpenArch (test data, a fresh start):

```bash
python scripts/cleanup.py --openarch
```

This deletes the documents under `OPENARCH_ROOT_PATH`, and with `INCREMENTAL_STATE_STORE=openarch` also the data
sources and their state.

## Limits

- Embeddings must be 1024-dimension (see [Setup](#setup)).
- Tested with the default ingest pipeline. The CocoIndex pipeline (`PIPELINE_BACKEND=cocoindex`) has no OpenArch
  target.
- OpenArch is under active development; Flexible GraphRAG 0.9.0 is tested against OpenArch `main` at commit
  `28f4b833`, the commit [KG Spaces Deployment](https://github.com/stevereiner/kg-spaces-deployment) builds
  OpenArch from (`OPENARCH_GIT_REF`).
