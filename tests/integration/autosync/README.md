# Auto-sync matrix

Live end-to-end checks of auto sync per data source, with the OpenArch state store: what a sync
follows after a multiselect or a folder ingest, and what happens on adds, edits, deletes, moves,
renames, Processing rows with Auto Sync off, periodic refreshes and, for a few sources, graph and
RDF removal. Each check reads the OpenArch tree the backend keeps its document state in.

It complements `run_matrix.py` (store combinations, one-shot ingest per source with
`--data-source`; `--state-store openarch` runs those with the OpenArch state store) and
`test_incremental.py` (filesystem add / modify / delete on the Postgres registry).

## Running it

```
venv-3.14/Scripts/python.exe tests/integration/autosync/run_autosync.py
venv-3.14/Scripts/python.exe tests/integration/autosync/run_autosync.py --sources alfresco,nuxeo --scenarios select,follow,move
venv-3.14/Scripts/python.exe tests/integration/autosync/run_autosync.py --backend http://127.0.0.1:8000
```

By default it starts its own backend from this checkout on port 8010 (log in
`tests/integration/results/autosync-<run>-backend.log`) with `flexible-graphrag/.env` plus:

| Setting | Value |
|---|---|
| `ENABLE_INCREMENTAL_UPDATES` | `true` |
| `INCREMENTAL_STATE_STORE` | `openarch` |
| `OPENARCH_ROOT_PATH` / `OPENARCH_DATASOURCES_PATH` | `/fg-e2e-sources` / `/fg-e2e-datasources` (`--root`, `--datasources-root`) |
| `ENABLE_OPENARCH` | `false`, or `true` with `--openarch-store` (OpenArch also the vector and search store) |

Its own OpenArch roots keep it apart from a backend you run on `/fg-sources`. It deletes them
before it starts that backend (`--no-reset` keeps them), so earlier runs' syncs don't come back
with it. The vector, search and graph stores are the ones in `.env`, shared with your own
backend: run `scripts/cleanup.py` after a matrix run. With `--backend` it uses a backend you
started; `--root` must then be that backend's `OPENARCH_ROOT_PATH`.

A report goes to `tests/integration/results/autosync-<run>.json`; the exit code is 1 when a check
failed.

## Sources

| Source | Needs (from the environment or `.env`) | Selection | Notes |
|---|---|---|---|
| `filesystem` | nothing (`AUTOSYNC_FS_DIR`, default the temp folder) | multiselect (paths) | folders are always recursive |
| `alfresco` | `ALFRESCO_URL`, `ALFRESCO_USERNAME`, `ALFRESCO_PASSWORD` | multiselect (nodeDetails) | test folder under `Shared` (`AUTOSYNC_ALFRESCO_PARENT`) |
| `nuxeo` | `NUXEO_URL`, `NUXEO_USERNAME`, `NUXEO_PASSWORD` | multiselect (nodeDetails) | test workspace under `default-domain/workspaces` (`AUTOSYNC_NUXEO_PARENT`) |
| `s3` | `S3_CONFIG` (or `S3_*`), with `sqs_queue_url` for events | prefix | no folder rename (no folders) |
| `azure_blob` | `AZURE_BLOB_CONFIG` | prefix | change feed, else the periodic refresh: slow |
| `box` | `BOX_CONFIG` (server app: `client_id`, `client_secret`, `user_id`, `folder_id`) | folder | test folder inside `folder_id` |
| `sharepoint`, `onedrive` | `SHAREPOINT_CONFIG`, `ONEDRIVE_CONFIG` (app with Files / Sites ReadWrite) | folder | test folder at the drive root |
| `google_drive` | `GOOGLE_DRIVE_CONFIG` (service account) | folder | can't upload: moves `company-ontology-test.txt` (`AUTOSYNC_DRIVE_FILE`) around and puts it back |

GCS isn't here: its test credentials are read-only. A source whose settings are missing is
skipped and listed in the summary.

## Scenarios

Each run works in its own container, `kg-autosync-<run>` (folder, prefix or drive folder):
`sel/` (a.txt b.txt m.txt Sub/c.txt Sub/Deep/d.txt Other/e.txt), `out/` (outside every sync),
`rec/` (r1.txt Deep/r2.txt) and `graphs/` (g1.txt). It is deleted at the end unless `--keep`.

| Scenario | What it checks | Sources |
|---|---|---|
| `select` | multiselect a.txt + Sub, not recursive (repositories) or the whole `sel/`, with auto sync: exactly the selected files are followed | all |
| `search` | hybrid search finds the ingested text (repositories with their sign-in) | all |
| `follow` | a new file in scope and an edit are followed; new files outside the selection, below a non-recursive folder, or in `out/` are not | all |
| `delete` | a deleted file leaves the tree | all |
| `move` | rename in place; move out of the selection (gone); repositories: renamed selected file still followed; folder sources: move within | all |
| `folder` | folder rename inside the sync's scope | filesystem, Box, SharePoint, OneDrive |
| `rule` | Processing row Sub with Auto Sync off (`item_actions`): ingest status says so, new files and edits there are not followed, its files stay | Alfresco, Nuxeo |
| `recursive` | recursive root: nested files, new nested file, move up, folder rename | Alfresco, Nuxeo |
| `graphs` | graph + RDF on for `graphs/`: ingest status and search; a Processing row `remove_graph` keeping RDF; then out of every store (`/api/sync/remove` for repositories, a `remove_all` row for single-row sources; the filesystem has no removal) | `--graph-sources` (default filesystem, alfresco, s3: a repository, a single-row source and the filesystem) |
| `late` | after periodic refreshes (interval set to 60 s): out-of-scope files still not followed | all |
| `drive` | Google Drive: nested file followed, edit, move within, move out | Google Drive |

All ingests except `graphs` set `enabled_graph` / `enabled_rdf` false, so most of the matrix
builds no graphs.
