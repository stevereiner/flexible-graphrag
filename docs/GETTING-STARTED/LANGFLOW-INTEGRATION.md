# Langflow Integration

Flexible GraphRAG ships **12 custom [Langflow](https://www.langflow.org/) components** (the **Flexible GraphRAG** node category) and four ready-made flows. There are two ways to use them, and they can be used together:

1. **App-driven flow mode** *(optional)* — the Flexible GraphRAG app runs its **ingest pipeline, hybrid search, and AI query through the Langflow visual flows** (via the Langflow REST API) instead of calling the system directly. The flows execute the **same backend machinery** driven by the same `.env`, so you get identical results — but the pipeline becomes a visual flow you can **customize**. Enabled with `ENABLE_LANGFLOW_FLOWS=true` (off by default).
2. **Visual flow building** — drag the Flexible components onto the Langflow canvas to build or customize your own ingest/query flows. See the developer reference: [Langflow Components](../DEVELOPER/DEVELOPER-LANGFLOW-COMPONENTS.md).

!!! info "All your existing configuration is reused"
    The components are thin nodes over the real backend (`ingest/*` pipeline + retriever + adapter/store layer, both LlamaIndex and LangChain). **Every database, LLM/embedding, chunking, KG-extraction, RDF, and framework (LI/LC per-stage) setting in your backend `.env` applies unchanged.** You do not reconfigure anything for Langflow — the flow just orchestrates the same pipeline.

---

## How it works (app-driven flow mode)

When `ENABLE_LANGFLOW_FLOWS=true`, on startup the backend:

1. **Uploads the flow JSONs** to Langflow (replacing any existing flow of the same name, so a restart always runs the current file). Four flows are used:
   - `flows/fg_ingestion_flow.json` — the ingest pipeline.
   - `flows/fg_search_flow.json` — **search** (ChatInput → Hybrid Search only).
   - `flows/fg_aiquery_flow.json` — **AI query** (ChatInput → AI Query only).
   - `flows/fg_query_flow.json` — combined Hybrid Search + AI Query → Query Summary, for the Langflow **Playground** (the app doesn't run it).
2. Routes each **ingest / hybrid-search / AI-query** request to `POST /api/v1/run/{flow}` on the Langflow server, passing the per-run config as the flow's `input_value` (the ChatInput → Data Source / query edge).
3. Reads the flow's component outputs back and returns them to the UI/API — so flow mode renders identically to direct mode.

!!! note "Why separate search and AI-query flows"
    Langflow runs **every branch present in a flow**. If the app ran the combined query flow for a search, it would also fire an AI Query LLM call (and vice-versa). The dedicated single-branch `fg_search_flow` / `fg_aiquery_flow` avoid that wasted work.

The backend and Langflow communicate **only over HTTP** (`LANGFLOW_URL`), which is why they run as two separate processes (see below).

---

## Setup — all on the host (standalone backend + standalone Langflow)

This is **shape 1** (non-Docker): both the app and Langflow run on the host, in **two venvs, two terminals**. For **shape 2** (everything containerized), see [Running Langflow in Docker](#running-langflow-in-docker) below. Keep the backend and Langflow on the *same* side (both host, or both Docker) so they share a filesystem — needed for file-upload ingest.

Langflow executes the flow's component code **in its own process**, so it needs Flexible GraphRAG installed in its environment. The app runs in its own environment and just talks to Langflow over REST. Use **two virtual environments in two terminal windows**:

| | Langflow venv (Terminal 1) | Backend venv (Terminal 2) |
|---|---|---|
| Runs | `langflow run` (the flow server) | the Flexible GraphRAG app (`uvicorn`/`python main.py`) |
| Needs | Langflow **+** an editable install of `flexible-graphrag` (so it can import the components + pipeline) | the normal backend install (Langflow **not** required) |
| Reads `.env`? | uses `.env` when it executes the pipeline | yes — sets `ENABLE_LANGFLOW_FLOWS`, `LANGFLOW_URL` |

!!! warning "Python build matters for Langflow"
    Create the Langflow venv on **any Python 3.14 except 3.14.0** (3.14.4 and 3.14.5 are both known good), or 3.13 — use an explicit patch version: `uv venv --python 3.14.4` (or greater). Plain `uv venv --python 3.14` resolves to **3.14.0**, whose OpenSSL build aborts on SSL and makes Langflow crash on startup. Litmus test for any venv: `python -c "import ssl; ssl.create_default_context(); print('OK')"`.

### Terminal 1 — Langflow venv

```powershell
# Any 3.14 except 3.14.0 (NOT plain --python 3.14, which resolves to 3.14.0)
uv venv --python 3.14.4 venv-langflow

# Staged install (the combined flexible-graphrag[langflow] extra is unsatisfiable).
# --system-certs is needed behind an SSL-inspecting corporate proxy.
# (uv < 0.11 calls it --native-tls; newer uv deprecates that name. Either sets UV_NATIVE_TLS.)
uv pip install --system-certs langflow==1.11.2
uv pip install --system-certs --override extras-overrides.txt -e ".[langchain,langchain-extras]"   # LlamaIndex + fuller LangChain backends (e.g. Neo4j)

# NOTE: no PyJWT restore step is needed any more.  flexible-graphrag depends on
# plain `nuxeo` + `authlib` + `pyjwt[crypto]`, never `nuxeo[oauth2]` — so the
# GehirnInc `jwt` package that used to evict PyJWT is never installed, and
# Langflow's `from jwt import InvalidTokenError` keeps working.
#
# NUXEO IN FLOW MODE: `nuxeo/auth/oauth2.py` imports three symbols from the
# GehirnInc `jwt` API (`JWT`, `jwk_from_dict`, `JWTDecodeError`).
# `sources/nuxeo.py` implements all three on top of PyJWT, so **all 3 Nuxeo
# auths (basic/token/oauth2) work in Langflow flow mode**, including client-side
# access-token validation.  It only adds those names when PyJWT owns `jwt` and
# never touches PyJWT's own symbols, so Langflow is unaffected.  Alfresco and
# all other sources work fully in flow mode.

# Run Langflow from the flexible-graphrag backend dir. The "Flexible GraphRAG" palette
# auto-registers via the extension bundle (shipped with flexible-graphrag ≥ 0.7.1), so no
# LANGFLOW_COMPONENTS_PATH is needed; running from the backend dir keeps the flow's .env,
# flows/, and schemas/ alongside it (see the warning below).
#
# PYTHONPATH = the backend dir is REQUIRED. This repo ships a package named `langchain` that must
# shadow the real PyPI langchain (our langchain.graph/search back the LC pipeline) — without it,
# search / AI query fail with "No module named 'langchain.graph'". `python main.py` gets this for
# free (the script dir is on sys.path), but the `langflow` console-script does not, and hatchling's
# editable install can't shadow a same-named installed package. (Docker sets PYTHONPATH=/app for the
# same reason.) Run from the backend dir so (Get-Location) IS that dir:
$env:PYTHONPATH = (Get-Location).Path
langflow run --port 7860 --log-level WARNING --log-file langflow.log
```

> **Langflow version:** `1.11.2` is shown (1.11.1 / 1.11.2 fix a number of bugs over 1.11.0). If you
> install a **different** langflow version, re-run `python langflow_components/generate_flows.py` afterward
> so the flow JSONs embed the matching langflow version — each flow carries **both** the langflow version
> and the flexible-graphrag version. Then restart the backend so it re-uploads the flows.

Wait for Langflow to **fully start** — after the purple "Welcome to Langflow" box it prints `Launching Langflow...`; once that finishes, the **Flexible GraphRAG** category with the 12 `Flexible: *` nodes appears in the sidebar (auto-registered by the extension bundle). Open <http://localhost:7860> to confirm. Then **create an API key** for the backend — **Settings → Langflow API Keys → Add New** (copy it, shown once); the backend uses it in Terminal 2. (Prefer no key for local dev? See [Authentication](#authentication) for the auto-login shortcut.)

!!! note "No `LANGFLOW_COMPONENTS_PATH` needed — and don't set it"
    **Changed in v0.7.1.** In **0.7.0** you set `LANGFLOW_COMPONENTS_PATH=langflow_components` (and ran Langflow from a dir where that path resolved). As of **0.7.1** the palette is registered by the **Langflow Extension bundle** as long as `flexible-graphrag` is installed in the **same venv** as Langflow (the editable install above) — Langflow discovers it at startup via `importlib.metadata`, independent of the working directory. So you **no longer set `LANGFLOW_COMPONENTS_PATH`**; if you do, Langflow logs a harmless `bundle-shadowed` warning because the installed extension outranks the inline path.

!!! warning "In flow mode, the components read the *Langflow* process's `.env` — not the backend's"
    When `ENABLE_LANGFLOW_FLOWS=true`, ingest/search/AI-query run **inside the Langflow process**, so every backend setting the components read — `DOCUMENT_PARSER`, `CHUNK_SIZE`, the vector/search/graph/RDF DBs, LLM & embeddings — comes from the `.env` **Langflow** loads. The components resolve that `.env` from their **own installed location** — the flexible-graphrag app dir that is the parent of `langflow_components` (for an editable install, your source checkout; this is *not* the current working directory). The backend's own `.env` only governs **non-flow** (direct) runs. If the backend and Langflow use the **same** flexible-graphrag install (the two-terminal setup above), they share one `.env` and this never surprises you. But if they use **different** installs — e.g. an installed-wheel backend in one place and an editable Langflow checkout in another — editing only the backend's `.env` won't change the flow's behavior (a common symptom: you switch `DOCUMENT_PARSER` but the flow keeps using the old parser). Fix: edit the `.env` next to the `langflow_components` Langflow's install uses. No Langflow restart is needed — the components reload the `.env` on the next run (`load_dotenv(override=True)`).

### Terminal 2 — backend venv

Enable flow mode in the backend `.env`:

```ini
ENABLE_LANGFLOW_FLOWS=true
LANGFLOW_URL=http://localhost:7860
LANGFLOW_API_KEY=<the key from the Langflow UI>   # how the backend authenticates to Langflow (see Authentication)
# Flow paths the app runs — defaults shown, override to customize:
# INGEST_FLOW_PATH=flows/fg_ingestion_flow.json
# SEARCH_FLOW_PATH=flows/fg_search_flow.json
# AIQUERY_FLOW_PATH=flows/fg_aiquery_flow.json
```

Then start the backend as usual. Ingest, hybrid search, and AI query now run through the Langflow flows.

---

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `ENABLE_LANGFLOW_FLOWS` | `false` | Run ingest/search/AI-query through Langflow instead of calling the system directly. |
| `LANGFLOW_URL` | `http://localhost:7860` | URL of the running Langflow server. |
| `LANGFLOW_API_KEY` | *(unset)* | **Recommended** — how the backend authenticates to Langflow. Create one in the Langflow UI under **Settings → Langflow API Keys → Add New** (or the `langflow api-key` CLI). Can be left unset only if you use the no-key auto-login shortcut (see [Authentication](#authentication)). |
| `INGEST_FLOW_PATH` | `flows/fg_ingestion_flow.json` | Path to the ingestion flow JSON. |
| `SEARCH_FLOW_PATH` | `flows/fg_search_flow.json` | Dedicated search-only flow the app runs (no AI Query branch). |
| `AIQUERY_FLOW_PATH` | `flows/fg_aiquery_flow.json` | Dedicated AI-query-only flow the app runs (no Hybrid Search branch). |
| `QUERY_FLOW_PATH` | `flows/fg_query_flow.json` | Combined Hybrid Search + AI Query flow — Langflow **Playground** only (the app doesn't run it). |

All other backend settings (data sources, vector/search/graph/RDF DBs, LLM & embeddings, chunking, KG extraction, LI/LC framework pickers) are read from the same `.env` and apply unchanged.

> **Flow paths when running an installed build.** The `flows/…` defaults above are for a **source checkout**. When you run the installed console command — `flexible-graphrag` (or `flexible-graphrag.exe` on Windows; `python -m start` is equivalent) — the default resolves relative to the installed package (site-packages), **not** your flows, so **set the `*_FLOW_PATH` variables**. A relative path (`flows/fg_ingestion_flow.json`) resolves from the **current working directory** you launch from — the simplest setup is a run folder holding `.env`, a `flows/` copy, and a `schemas/` copy (for `ONTOLOGY_DIR`), and you launch from that folder. Use absolute paths if your working directory varies. (Same cwd rule as `ONTOLOGY_DIR`/`ONTOLOGY_PATH`.)

---

## Authentication

Langflow's API needs a token on every request. The end-user way to give the backend one is an **API key**.

**Recommended (any deployment) — an API key.** In the Langflow UI, open **Settings → Langflow API Keys → Add New**, name it, and **copy the key** (shown once — it's stored hashed; lost it → delete and add another). Set it in the backend `.env`:

```ini
LANGFLOW_API_KEY=<the key from the UI>
```
`flow_service` then sends it as `x-api-key`, which authenticates **both** binding and running flows — no `LANGFLOW_SKIP_AUTH_AUTO_LOGIN` needed. It works under the default single-user `AUTO_LOGIN` and when you later require real auth, and you **don't need to set `LANGFLOW_SECRET_KEY`** for this path (Langflow auto-generates a valid one).

!!! warning "A stale `LANGFLOW_API_KEY` is the most common flow-mode 403"
    A key minted against a *previous* Langflow database — e.g. after recreating the Langflow venv or wiping/replacing `langflow.db` — is unknown to the new instance, so the bind returns **`403 Forbidden`** ("Could not bind Langflow flows"). Mint a fresh key for the current instance, and persist `langflow.db` (the `langflow_data` volume in Docker) so a key survives restarts. (Programmatic key creation: see the [developer doc](../DEVELOPER/DEVELOPER-LANGFLOW-COMPONENTS.md#creating-a-langflow-api-key-programmatically).)

**Local-dev shortcut — no key (auto-login).** To skip the UI step on a trusted machine, let auto-login also *run* flows. Set these where Langflow runs and leave `LANGFLOW_API_KEY` unset:

```ini
LANGFLOW_AUTO_LOGIN=true            # default
LANGFLOW_SKIP_AUTH_AUTO_LOGIN=true  # since Langflow v1.5, /run needs this (or an API key) under auto-login
LANGFLOW_SECRET_KEY=<valid-fernet-key>   # required for this path — see the note below
```
Trade-off: the API (including `/run`) is then **unauthenticated** to anyone who can reach the port — fine on a trusted network, not an exposed one. The compose Langflow service ships this shortcut pre-set; a bare `docker run` needs `-e LANGFLOW_SKIP_AUTH_AUTO_LOGIN=true`.

!!! note "`LANGFLOW_SECRET_KEY` — mostly a developer concern"
    Langflow uses it for JWT signing (the auto-login token) **and** Fernet encryption of stored secrets, so it must be a **valid Fernet key** = 32 url-safe base64-encoded bytes; a plain string throws `Fernet key must be 32 url-safe base64-encoded bytes` at startup and breaks secret storage / API-key creation (blank key field). The **API-key path above doesn't need it** (Langflow auto-generates a valid one). It matters for the **no-key shortcut**, and for **multi-worker / cross-restart** consistency (unset → a random per-worker key → the auto-login token fails elsewhere with `InvalidSignatureError`). Generate one: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

**Production hardening — require login.** Set `LANGFLOW_AUTO_LOGIN=false` + a superuser (`LANGFLOW_SUPERUSER` / `LANGFLOW_SUPERUSER_PASSWORD` — the password default is empty, so set one) wherever Langflow runs; the superuser persists in `langflow.db`. Then log in and mint the API key as above.

---

## Running Langflow in Docker

Run flow mode in one of **two clean shapes** — keep the backend and Langflow **together** so they share one filesystem (required for **file-upload** ingest; cloud sources don't care):

1. **All on the host (non-Docker)** — the two-venv setup above: standalone backend + standalone Langflow.
2. **All in Docker (compose)** — `app-stack.yaml` (backend + UIs), `langflow.yaml`, and optionally `proxy.yaml`, all containerized (this section).

!!! warning "Don't mix host + container across the flow boundary"
    A **host** backend pointed at a **container** Langflow (or vice-versa) runs **cloud sources** fine, but **file upload fails** — the backend passes absolute host paths a container can't resolve (`c:\…\uploads\file` → `Path does not exist`). Pick shape 1 **or** 2; use cloud sources if you must run a mixed setup.

**Images (share one base):** both the backend `Dockerfile` and `Dockerfile.langflow` build on `ghcr.io/astral-sh/uv:python3.14-trixie-slim` — Langflow's own build base (Python 3.14, uv pre-installed). `Dockerfile.langflow` = that base + `langflow==1.11.2` + `flexible-graphrag[extras]` (plus a guard asserting PyJWT still owns the `jwt` module — see the note on `nuxeo[oauth2]` above). The **Flexible GraphRAG** palette auto-registers via the extension bundle (no `LANGFLOW_COMPONENTS_PATH`). (The 12 components import the real backend machinery at runtime, so — unlike a stock Langflow image — this image must install flexible-graphrag too.)

**Enable the all-Docker stack:** in `docker/docker-compose.yaml` uncomment `- includes/app-stack.yaml` (backend + UIs), `- includes/langflow.yaml`, and optionally `- includes/proxy.yaml`. Flow mode is **opt-in** — in `app-stack.yaml` flip the backend's `ENABLE_LANGFLOW_FLOWS` to `"true"` (it defaults to `"false"` / direct mode); the rest of the flow config is already there:

```ini
ENABLE_LANGFLOW_FLOWS: "true"                         # flip from the default "false"
LANGFLOW_URL: http://flexible-graphrag-langflow:7860  # the compose service name, NOT localhost
INGEST_FLOW_PATH: flows/fg_ingestion_flow.json        # + QUERY_/SEARCH_/AIQUERY_FLOW_PATH
```
Then `docker compose up --build`.
It also mounts `flows/` (`../../flows:/app/flows:ro`) and shares the `upload_data` volume with Langflow (both read the same `/app/uploads`, so **file upload works**) — all wired in `app-stack.yaml` / `langflow.yaml`. (The `langflow.yaml` include is self-contained and *can* run against another backend via the "BACKEND SIDE" block in that file — but see the mixed-setup warning above.)

**Config the flow reads (important):** in flow mode the components run **inside the Langflow container** and read config from **its** environment. The container uses `env_file: [../../flexible-graphrag/.env, ../docker/.env]`, layered exactly like the backend (docker/.env's container-reachable DB addresses win). This works because `/app/.env` is **not** present in the image (`.dockerignore` excludes `.env`, and it is not mounted), so `Settings()` reads the compose-injected env vars. **Consequence:** config is fixed at container start — change `DOCUMENT_PARSER`, `CHUNK_SIZE`, DBs, etc. by editing `.env`/`docker/.env` and **recreating** the container (`docker compose up -d --force-recreate`), not by a live edit (the host live-edit behavior needs `/app/.env`, which would defeat the docker/.env override layering).

!!! warning "Bare `docker run --env-file` does not strip inline `#` comments"
    Mostly a concern for a **standalone container** run with `docker run --env-file …` (not the compose stack — modern Docker **Compose** strips ` # ` inline comments, and the shipped `env-sample.txt`'s active lines are already comment-free). `docker run --env-file` passes values **verbatim** — python-dotenv on the host trims `KEY=value  # note` → `value`, but `--env-file` keeps `value  # note`. So a `.env`/`docker/.env` value with an inline comment breaks inside the container: enum/number/bool settings (e.g. `ONTOLOGY_FORMAT`, `*_FUNCTION_CALLING`, `*_TIMEOUT`) fail `Settings` validation → **500 at flow-run time** (`Error building Component Flexible: Data Source`), and string settings silently take the commented value. Fix: move any inline comment to its **own line** (`# note` above the `KEY=value`) in the file that container reads. (Applies too if you *uncomment* an example option that still has an inline comment.)

**Persistence:** `LANGFLOW_CONFIG_DIR=/app/langflow-data` (+ `LANGFLOW_DATABASE_URL=sqlite:////app/langflow-data/langflow.db`) keeps Langflow's **own** SQLite DB — flows, users, API keys — in the `langflow_data` named volume across restarts. (This is Langflow's internal DB, separate from the flexible-graphrag vector/search/graph/RDF stores.) For Postgres instead, override `LANGFLOW_DATABASE_URL=postgresql://…`.

---

## Customizing the flows

The bundled flows cover the full pipeline, but you can edit them visually:

1. In the Langflow UI, open the flow you want to change (Ingestion / Search / AI Query / combined Query), **duplicate** it, and adjust the canvas.
2. **Export** your edited flow to a JSON file.
3. Point the matching `*_FLOW_PATH` (`INGEST_FLOW_PATH` / `SEARCH_FLOW_PATH` / `AIQUERY_FLOW_PATH` / `QUERY_FLOW_PATH`) at your exported copy.

Regenerating the bundled flows from the components is a developer task — see [Langflow Components → Regenerating the bundled flow JSONs](../DEVELOPER/DEVELOPER-LANGFLOW-COMPONENTS.md#regenerating-the-bundled-flow-jsons).

!!! warning "The app replaces flows by name on startup"
    In app-driven mode the backend deletes and re-uploads the flow that matches the configured JSON's `name` every time it starts — so hand-edits made *in the Langflow UI* to the bundled flow are overwritten. Persist changes by **exporting to your own JSON** and pointing the `*_FLOW_PATH` at it (give it a distinct `name`), or by regenerating the bundled JSON.

If you change **backend code that a component imports at runtime** (e.g. `_fg_shared.py`), **restart the Langflow server** — it imported the old module.

### Tips for building flows in the UI

- **Connect nodes** by dragging from an **output handle** (right-side circle) to an **input handle** (left-side circle). A line appears when connected.
- **Use forward slashes in file paths** on Windows inside node fields (`C:/data/file.pdf`) — backslashes can fail in the flow JSON.
- **Red icon on a node = error.** Click the node to inspect its config; open the browser console (F12) for details. If two nodes won't connect, it's usually a port **type mismatch** — delete the edge and reconnect (or refresh the page).

---

## Troubleshooting

- **`Flexible: *` nodes don't appear** — the palette comes from the extension bundle, so confirm `flexible-graphrag` (≥ 0.7.1) is installed in the **same** venv as Langflow: `python -c "from importlib.metadata import entry_points; print(list(entry_points(group='langflow.extensions')))"` should list `flexible-graphrag`. If it's missing, reinstall (`uv pip install -e .` from the backend dir) so the entry point lands in the metadata, then restart Langflow and check its log for `Extension load error`. Do **not** set `LANGFLOW_COMPONENTS_PATH` — with the extension present it only adds a `bundle-shadowed` warning.
- **`duplicate-distribution` extension error in the Langflow log** — two installed distributions named `flexible-graphrag` are visible (e.g. a stale `*.egg-info` in a source dir that's on `sys.path`/`PYTHONPATH` alongside the real install). Remove the stray `*.egg-info`/`build`/`dist` artifacts; the palette still loads (lexicographically-first manifest wins) but the error should be cleared.
- **`ImportError: cannot import name 'InvalidTokenError' from 'jwt'` at Langflow start** — `flexible-graphrag` pulls `nuxeo[oauth2]`, whose `jwt` (GehirnInc) package owns the same `jwt` module as **PyJWT** (which Langflow needs) and evicts it. Fix: `uv pip uninstall jwt` then `uv pip install --reinstall "PyJWT>=2.12.1"`. Re-run it whenever you reinstall `flexible-graphrag[...]` in the Langflow venv. **Nuxeo in flow mode:** a compat shim in `sources/nuxeo.py` grafts nuxeo's `jwt` symbols onto PyJWT, so **all 3 Nuxeo auths (basic/token/oauth2) work in flow mode** — OAuth2 uses a pre-obtained Bearer (minted by `scripts/nuxeo`), so ingest never decodes a JWT. Alfresco + all other sources work fully in flow mode.
- **`ImportError: cannot import name 'get_body_field'` at Langflow start** — fastapi 0.140.x renamed `get_body_field` → `_get_body_field`, which broke older `fastapi-pagination` (a langflow dependency) at import. Fix by pinning a good fastapi **before** the langflow install: `uv pip install --system-certs "fastapi==0.139.2"`, then reinstall langflow. **Verified: langflow 1.11.2 installs fastapi 0.141.1 and works with no pin**, so this pin is only a fallback for other versions that hit the error — try without it first.
- **Benign startup log noise (safe to ignore)** — a clean run still logs a few langflow-internal messages that do **not** affect the Flexible GraphRAG flows: an `altk` "Extension load error / No module named 'altk'" (a langflow-bundled agent component missing its optional dep — `uv pip install altk` if you want that node), `Variable 'FLOW_ID' / 'COMPONENT_ID' / 'FIELD_NAME' has no stored value → skipping` warnings (langflow's global-variable service), and a telemetry-writer `[WinError 11]` (falls back to a legacy path; silence with `DO_NOT_TRACK=true`).
- **SSL abort on Langflow start** — the interpreter's OpenSSL is 3.5.x (uv-standalone). Recreate the venv on a python.org / pythoncore 3.14.5 (or 3.13) interpreter. See the warning above.
- **401 from Langflow in flow mode** — set `LANGFLOW_API_KEY` (x-api-key) if your Langflow requires auth; leave it unset for a default local single-user Langflow.
- **Nothing ingests / long hang** — ingestion runs synchronously over one HTTP call and can take minutes (KG extraction is LLM-bound). This is expected; the connect timeout is short but the read timeout is unlimited. If you drive the API directly (or via a node with its own timeout), raise the request timeout to 300–600s.

---

## See also

- [Langflow Components (developer reference)](../DEVELOPER/DEVELOPER-LANGFLOW-COMPONENTS.md) — the 12 components, flow topology, and how to add/edit them.
- [Environment Configuration](ENVIRONMENT-CONFIGURATION.md) — the full backend `.env` reference.
- [Framework Configuration](../CONFIGURATION/LANGCHAIN-CONFIGURATION.md) — LlamaIndex / LangChain per-stage pickers.
