# Nuxeo Integration Guide

This guide covers Nuxeo-specific configuration for the Flexible GraphRAG system: the three
authentication methods, path conventions, and optional real-time change sync via Kafka.

## About Nuxeo

[Nuxeo](https://www.nuxeo.com/) (owned by Hyland) is an open-source content services platform.
Flexible GraphRAG connects to a Nuxeo repository as a data source — enumerating documents under a
path (or by node id), downloading each document's content, and ingesting it into the knowledge
graph / vector / search stores. Like Alfresco, it supports optional incremental auto-sync so that
changes in Nuxeo flow into the graph in real time.

## Requirements

- A running Nuxeo server (LTS 2023+ recommended). A local option is
  [aborroy/nuxeo-deployment](https://github.com/aborroy/nuxeo-deployment) (PostgreSQL-backed Nuxeo
  built from public source).
- The Nuxeo Python client — already declared in `pyproject.toml`, so a normal
  install pulls it in. To add it to an existing venv:
  ```bash
  uv pip install nuxeo authlib "pyjwt[crypto]"
  ```
  > **Do not install `nuxeo[oauth2]`.** That extra is `authlib` + `jwt`, and its
  > `jwt` is GehirnInc python-jwt, which claims the same top-level `jwt` module
  > as PyJWT and overwrites it — breaking `python-arango` (and so
  > `langchain-arangodb` and the ArangoDB graph store), `authlib` itself, and
  > Langflow. The two cannot coexist and no version pin resolves it.
  >
  > Flexible GraphRAG installs the extra's two halves directly instead —
  > `authlib` and `pyjwt[crypto]` — and `sources/nuxeo.py` implements the three
  > symbols `nuxeo.auth.oauth2` needs (`JWT`, `jwk_from_dict`, `JWTDecodeError`)
  > on top of PyJWT. **All three auth methods, including client-side
  > access-token validation, work normally.**

## Configuration

Set these in your `.env` (used by the REST API and MCP server; the UIs have their own form):

```env
# Nuxeo Configuration
# Base repository URL (NO /api/v1 suffix — the client appends it)
NUXEO_URL=http://localhost:8081/nuxeo
# Auth method: basic | oauth2 | token   (default: basic)
NUXEO_AUTH_METHOD=basic
# Path to ingest (folder or single document)
NUXEO_PATH=/default-domain/workspaces/GraphRAG
```

In the UI, choose **Nuxeo Repository** as the data source, pick the **Authentication** method, and
fill in the fields for that method plus the path.

## Path Conventions

Nuxeo paths are **domain-rooted and use the document's internal name** (`ecm:name`), which is
lowercased/normalized (and truncated ~24 chars) from the title at creation. **Always copy the path
from the Nuxeo browse URL** — everything after `#!/browse` is the exact path:

```
#!/browse/default-domain/workspaces/GraphRAG   ->   /default-domain/workspaces/GraphRAG
```

- A **folder** path ingests all supported documents under it (recursive optional).
- A **single-document** path ingests just that document.
- **File vs Note**: importing a `.txt`/`.md` typically creates a **Note** (text inline in
  `note:note`), while uploaded PDFs/Office files are **File** documents (binary blob in
  `file:content`). Both ingest. Note that only Notes are text-editable inline in the Web UI; to
  "modify" a File you upload a new version of its blob.

## Authentication Methods

### 1. Basic (username / password)

The simplest option — good for local testing (`Administrator` / `Administrator`).

```env
NUXEO_AUTH_METHOD=basic
NUXEO_USERNAME=Administrator
NUXEO_PASSWORD=Administrator
```

### 2. Token (X-Authentication-Token)

A persistent Nuxeo auth token, independent of web-UI sessions (survives UI timeout; valid until
revoked). Mint one with basic auth:

```bash
curl -u Administrator:Administrator \
  "http://localhost:8081/nuxeo/authentication/token?applicationName=flexible-graphrag&deviceId=my-device&permission=ReadWrite"
```

Then:

```env
NUXEO_AUTH_METHOD=token
NUXEO_TOKEN=<the-returned-token>
```

### 3. OAuth2 (Bearer)

Uses the authorization-code + PKCE flow. You obtain a token out-of-band and provide it; the client
auto-refreshes when a refresh token is present.

**Step 1 — register an OAuth2 client in Nuxeo.** In the Admin Center → **Cloud Services →
Consumers**, add a client with a Client ID, an optional secret, and a redirect URI
(e.g. `http://localhost:8888/callback`).

> This is a **manual, per-deployment step that does not survive recreating the
> Nuxeo containers** — the client lives in Nuxeo's `oauth2Clients` directory, not
> in this repo. After a fresh deployment only `nuxeo-drive` and `nuxeo-mobile`
> exist, and `/oauth2/authorize` returns **HTTP 400** until you re-register.

If the Web UI screen doesn't persist it, you can register it via the directory API:

```bash
curl -u Administrator:Administrator -H "Content-Type: application/json" \
  -d '{"entity-type":"directoryEntry","directoryName":"oauth2Clients",
       "properties":{"clientId":"flexible-graphrag","name":"flexible-graphrag",
                     "redirectURIs":"http://localhost:8888/callback",
                     "autoGrant":true,"enabled":true}}' \
  http://localhost:8081/nuxeo/api/v1/directory/oauth2Clients
```

**Step 2 — obtain a token** via the PKCE flow (authorization URL → browser approve → exchange the
redirect for a token). Default endpoints are `<url>/oauth2/authorize` and `<url>/oauth2/token`.

**Step 3 — configure:**

```env
NUXEO_AUTH_METHOD=oauth2
NUXEO_OAUTH2_CLIENT_ID=flexible-graphrag
# NUXEO_OAUTH2_CLIENT_SECRET=        # only if you set one
NUXEO_OAUTH2_ACCESS_TOKEN=<access-token>
NUXEO_OAUTH2_REFRESH_TOKEN=<refresh-token>
# NUXEO_OAUTH2_TOKEN_ENDPOINT=       # optional; defaults to <url>/oauth2/token
```

In the UI's OAuth2 fields, provide the Client ID (and secret if set) plus the access/refresh
tokens.

## Sign-In and Permission-Aware Search

The React, Vue and Angular UIs can sign in to Nuxeo. The backend gets a Nuxeo auth token from
`GET /nuxeo/authentication/token`, the same endpoint the `token` auth method uses, and the UI keeps
only that token.

- **Header:** the one sign-in pill reads `Nuxeo: <user>` when Nuxeo is the only server, else
  "Sign-ins n/m"; its menu has a row per Nuxeo server, next to any Alfresco, CMIS or cloud ones.
  Sign-out only forgets the token in that browser tab.
- **Search / AI chat:** when the stores hold Nuxeo documents, the UI asks for the sign-in before the first
  question. Answers then use only the Nuxeo documents that user may read, checked with
  `GET /api/v1/id/{uid}` when the question is asked. "Continue without" leaves Nuxeo documents out.
- **Ingest:** signed in to the form's server, the Nuxeo form shows "Signed in to Nuxeo as X (used for this
  ingest)" and sends `auth_method: token` + the token. A Nuxeo token does not expire, so it also
  works as an Auto Sync credential.
- **REST / MCP:** `POST /api/auth/nuxeo/login` returns `{token, user_id, url}`, and
  `GET /api/auth/nuxeo/me` (header `X-Nuxeo-Token`) checks a stored token. Search and query take
  `source_auth.nuxeo`: one `{url, token}` (or basic / oauth2 credentials), or a list with one per
  server. The MCP server's `sign_in` tool wraps the login.
- **Setting:** `NUXEO_QUERY_AUTH` (or `SOURCE_QUERY_AUTH`) is `required` by default. Set `optional`
  to show Nuxeo documents to askers who haven't signed in.

Nuxeo returns the same token for the same user, application (`flexible-graphrag`) and device
(`flexible-graphrag-ui`), so signing in again does not create more tokens. Revoke it in the Nuxeo
Web UI under user settings, Authentication Tokens.

## Real-Time Change Sync (optional, via Kafka)

With auto-sync enabled, Nuxeo document changes (create / modify / delete) flow into the graph in
real time. This works by consuming Nuxeo's **audit stream** from Kafka. It requires Kafka enabled
on the Nuxeo server.

> **Working reference (unofficial/temporary):** a copy of a compose + `kafka.conf` we got
> working lives in [`examples/nuxeo-deployment/`](../../examples/nuxeo-deployment/). It is
> built on top of Angel Borroy's content-lake POC deployment
> ([github.com/aborroy/nuxeo-deployment](https://github.com/aborroy/nuxeo-deployment),
> Apache-2.0) — a proof-of-concept, not an official Nuxeo image, and not standalone-runnable.
> The generic steps below apply to any Nuxeo deployment.

### 1. Nuxeo server — enable Kafka (compose-only, no image rebuild)

Nuxeo appends any `*.conf` dropped in `/etc/nuxeo/conf.d/` to `nuxeo.conf` at startup. Create a
`kafka.conf`:

```
kafka.enabled=true
kafka.bootstrap.servers=kafka:29092
kafka.topicPrefix=nuxeo-
kafka.default.replication.factor=1
nuxeo.stream.audit.enabled=true
```

> Gotcha: the entrypoint only regenerates `nuxeo.conf` (and re-applies `conf.d`) when
> `/etc/nuxeo/nuxeo.conf` is **absent**. If `/etc/nuxeo` is a **persisted volume**, config freezes
> at first-run and your `kafka.conf` is ignored. Keep `/etc/nuxeo` ephemeral (don't mount a volume
> on it) so `conf.d` applies on every start.

### 2. A single-node Kafka broker (generic docker-compose)

```yaml
services:
  kafka:
    image: apache/kafka:3.8.1
    hostname: kafka
    ports:
      - "9092:9092"                  # host listener for the Python consumer
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://kafka:29092,CONTROLLER://kafka:29093,PLAINTEXT_HOST://0.0.0.0:9092
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT,CONTROLLER:PLAINTEXT
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:29093
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_LOG_DIRS: /tmp/kraft-combined-logs
      CLUSTER_ID: MkU3OEVBNTcwNTJENDM2Qk
```

Notes:
- **Dual listener** so both sides reach the broker: the **Nuxeo container** uses the internal
  `kafka:29092`; the **host-side Python consumer** uses `localhost:9092`. (A containerized Nuxeo
  can't reach a sibling container via `localhost`.)
- Don't mount a named volume on the Kafka log dir — the `apache/kafka` image runs as uid 1000 and a
  root-owned volume breaks KRaft formatting. For a dev broker, persistence isn't needed.
- Optional: add a `provectuslabs/kafka-ui` service to browse topics (point it at `kafka:29092`).

### 3. Flexible GraphRAG — point the consumer at the broker

The consumer defaults to `localhost:9092`. Override if needed:

```env
NUXEO_KAFKA_BOOTSTRAP_SERVERS=localhost:9092
# NUXEO_AUDIT_TOPIC=nuxeo-audit-audit   # default
```

Then in the UI, check **Enable auto change sync** when you ingest the Nuxeo source. Create / edit /
delete a document in the monitored path and it auto-ingests within a second or two (watch the
backend log for `NUXEO EVENT: CREATE / UPDATE / DELETE`).

How it works: Nuxeo publishes audit entries to the `nuxeo-audit-audit` topic; the detector decodes
the embedded JSON, maps `documentCreated / documentModified / documentRemoved` to add / modify /
delete, resolves the live document, and ingests it. Version snapshots (`versionCreated`,
`documentCheckedIn`) are ignored, and each save's event burst is de-duplicated by the document's
`dc:modified` timestamp.

## Python Library Information

- **Nuxeo client**: [`nuxeo`](https://pypi.org/project/nuxeo/) (plain, *not* the
  `[oauth2]` extra — see the install note above) — basic / token / JWT / OAuth2
  auth, NXQL query, blob download.
- **OAuth2 support**: [`authlib`](https://pypi.org/project/Authlib/) plus
  [`pyjwt[crypto]`](https://pypi.org/project/PyJWT/), which together replace the
  `[oauth2]` extra without the `jwt` module collision.
- **Kafka client** (for real-time sync): [`kafka-python-ng`](https://pypi.org/project/kafka-python-ng/).
- Both are declared in `flexible-graphrag/pyproject.toml`, so a standard install includes them.

## File Structure (Nuxeo-specific)

- `sources/nuxeo.py` — Nuxeo data source connector (File + Note documents).
- `incremental_updates/detectors/nuxeo_audit.py` — Kafka audit consumer + JSON decoder.
- `incremental_updates/detectors/nuxeo_detector.py` — real-time change detector.

## Notes

- Nuxeo's default versioning policy snapshots a new version (0.1 → 0.2 → …) on each update. This is
  expected and does not affect ingestion — version events are filtered out.
- Auth tokens (method 2) persist until explicitly revoked; a web-UI session timeout does not affect
  them.
- OAuth2 access tokens are short-lived; supply the refresh token so the client can renew.
