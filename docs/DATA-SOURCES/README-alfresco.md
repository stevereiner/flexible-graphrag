# Alfresco Integration Guide

This guide covers Alfresco-specific configuration for Flexible GraphRAG: the three authentication
methods (**basic**, **ticket**, **OAuth2**), path / node selection, and real-time incremental sync.
Some of this is summarized in the root `README.md` and `OVERVIEW.md`; this page is the detailed
reference.

## About Alfresco

[Alfresco](https://www.hyland.com/en/solutions/products/alfresco-platform) (Hyland) is an open-source
content services platform. Flexible GraphRAG connects to an Alfresco repository as a data source —
enumerating documents under a path (or by node id / multi-select), downloading each document's
content, and ingesting it into the knowledge graph / vector / search stores. It supports optional
real-time incremental auto-sync so changes in Alfresco flow into the graph as they happen.

The Alfresco REST/CMIS access is built on the **[`python-alfresco-api`](https://github.com/stevereiner/python-alfresco-api)**
client (see its **AUTHENTICATION_GUIDE.md** for the underlying auth utilities). A dedicated Alfresco
MCP server also exists — **[`python-alfresco-mcp-server`](https://github.com/stevereiner/python-alfresco-mcp-server)**
— which exposes the same three auth methods via environment variables.

## Requirements

- A running Alfresco repository. The bundled Docker stack (`docker/includes/alfresco.yaml`) is
  **Alfresco Community 26.2.0**. ACS 26.2 deprecates Solr and indexes into **Elasticsearch or OpenSearch**
  instead; `docker/includes/alfresco-elasticsearch.yaml` (9202, the default) or
  `docker/includes/alfresco-opensearch.yaml` (9203) runs one for Alfresco alone, or you can drop both and
  set `ALFRESCO_SEARCH_HOST=elasticsearch`/`=opensearch` in `docker/.env`
  to share the engine and dashboard the rest of Flexible GraphRAG already uses. The app's own Alfresco
  settings are unaffected either way — it reaches Alfresco over the REST API on 8080 and never touches the
  Alfresco database or search index directly. **OAuth2 requires Community 23.2+** (the built-in `identity-service`
  subsystem; no Acosix/enterprise add-on needed — it's config-only).
- **`python-alfresco-api >= 1.2.1`** — already declared in `pyproject.toml`, so a normal install pulls
  it in. To add to an existing venv:
  ```bash
  uv pip install --system-certs "python-alfresco-api>=1.2.1"   # uv < 0.11: --native-tls
  ```

## Configuration

Set these in your `.env` (used by the REST API and MCP server; the UIs have their own form):

```env
# Alfresco Configuration
ALFRESCO_URL=http://localhost:8080/alfresco
ALFRESCO_USERNAME=admin
ALFRESCO_PASSWORD=admin
# Auth method: basic | ticket | oauth2   (default: basic)
ALFRESCO_AUTH_METHOD=basic
# ActiveMQ STOMP port for real-time events (default 61613; the bundled stack publishes 8613)
ALFRESCO_STOMP_PORT=8613
```

In the UI, choose **Alfresco** as the data source, pick the **Authentication** method, and fill in the
fields for that method plus the path/nodes.

## Authentication methods

### 1. `basic`

HTTP Basic (`Authorization: Basic base64(user:password)`). Simplest; fine for local/dev.

- **UI / config:** `username` + `password`.

### 2. `ticket`

The source logs in once and uses an Alfresco **ticket** (`Authorization: Basic base64(TICKET_…)`).
You still provide username/password — the source **self-fetches** the ticket (no separate token
step), analogous to Nuxeo's token mode.

- **UI / config:** `username` + `password`, auth method `ticket`.

### 3. `oauth2` — OIDC Bearer via `identity-service`

Alfresco validates an OIDC **Bearer** token through its built-in **`identity-service`** subsystem
(Community 23.2+). Any OIDC IdP works; the bundled stack uses **Keycloak**.

**Bundled Keycloak (compose-only — `docker/includes/keycloak.yaml`):**

| Setting | Value |
|---|---|
| Image | `quay.io/keycloak/keycloak:26.0` |
| Host port / issuer | `8091` (`KC_HOSTNAME=http://host.docker.internal:8091`) |
| Realm | `alfresco` |
| Client (confidential) | `flexible-graphrag` |
| Client secret (dev) | `flexible-graphrag-secret` |
| Realm user | `admin` / `admin` |
| Token endpoint | `http://localhost:8091/realms/alfresco/protocol/openid-connect/token` |

**Alfresco side (`docker/includes/alfresco.yaml`, JAVA_OPTS — no Acosix):**

```
-Dauthentication.chain=identity-service1:identity-service,alfrescoNtlm1:alfrescoNtlm
-Didentity-service.authentication.enabled=true
-Didentity-service.auth-server-url=http://host.docker.internal:8091
-Didentity-service.realm=alfresco
-Didentity-service.resource=flexible-graphrag
-Didentity-service.credentials.secret=flexible-graphrag-secret
-Didentity-service.public-client=false
-Didentity-service.enable-basic-auth=true
```

Basic auth still works alongside OAuth2 (the chain keeps `alfrescoNtlm`), so enabling OAuth2 is
non-breaking.

#### Client-credentials vs. user token — **prefer a user token**

| Grant | Identity | ACLs | Get it via |
|---|---|---|---|
| **client_credentials** | the client's **service account** (`service-account-flexible-graphrag`) — a JIT user, **no display name**, only default permissions (not admin, not guest) | limited | the source self-fetches it (leave `access_token` blank, provide `client_id` + `client_secret` + `token_endpoint`) |
| **password (user token)** | the **real user** (display name + that user's ACLs) | full user ACLs | `scripts/alfresco/get-user-token` (Keycloak password grant), then paste the token |

For real content operations, **use a user token** — `client_credentials` runs as the service
account, which can read only what its default permissions allow.

#### `.env` variables for OAuth2

```env
ALFRESCO_AUTH_METHOD=oauth2
ALFRESCO_OAUTH2_CLIENT_ID=flexible-graphrag
ALFRESCO_OAUTH2_CLIENT_SECRET=flexible-graphrag-secret
ALFRESCO_OAUTH2_TOKEN_ENDPOINT=http://localhost:8091/realms/alfresco/protocol/openid-connect/token
# client_credentials (service account, self-fetched) — the default when no token is provided
ALFRESCO_OAUTH2_GRANT_TYPE=client_credentials
# OR provide a pre-obtained USER token (from scripts/alfresco/get-user-token):
# ALFRESCO_OAUTH2_ACCESS_TOKEN=<paste>
# ALFRESCO_OAUTH2_REFRESH_TOKEN=<paste>
# ALFRESCO_OAUTH2_SCOPE=
```

Minting a user token:
```bash
# defaults to the bundled realm (client secret flexible-graphrag-secret, user admin/admin)
venv-3.14/Scripts/python scripts/alfresco/get-user-token.py
# or PowerShell / cmd / bash variants — see scripts/alfresco/README.md
```

## Path & node selection

- **`path`** — an Alfresco path, e.g. `/Shared/GraphRAG` (a folder) or `/Shared/GraphRAG/cmispress.txt`
  (a single document).
- **`nodeIds`** — an array of node UUIDs (REST API node ids) for multi-select.
- **KG Spaces ACA** — multi-select documents/folders directly from the Alfresco Content Application
  (passes `nodeDetails`).

## Real-time incremental sync

With auto-sync enabled, Alfresco create/update/delete events flow into the graph in real time via
**Apache ActiveMQ** (STOMP). The detector is auth-aware (basic/ticket/oauth2). Note the STOMP
connection authenticates to the **ActiveMQ broker** (default `admin`/`admin`), which is separate from
the Alfresco repository credentials; ACS 26.1+'s ActiveMQ 6.x enforces broker auth. Configure the STOMP
port with `ALFRESCO_STOMP_PORT` (bundled stack: `8613`).

## REST API / MCP config

Pass an `alfresco_config` object (the source path goes in `path`):

```jsonc
// basic
{ "url": "http://localhost:8080/alfresco", "auth_method": "basic",
  "username": "admin", "password": "admin", "path": "/Shared/GraphRAG" }

// ticket (self-fetches the ticket from user/pass)
{ "url": "http://localhost:8080/alfresco", "auth_method": "ticket",
  "username": "admin", "password": "admin", "path": "/Shared/GraphRAG" }

// oauth2 — client_credentials (service account, self-fetched)
{ "url": "http://localhost:8080/alfresco", "auth_method": "oauth2", "path": "/Shared/GraphRAG",
  "oauth2": { "client_id": "flexible-graphrag", "client_secret": "flexible-graphrag-secret",
    "token_endpoint": "http://localhost:8091/realms/alfresco/protocol/openid-connect/token",
    "grant_type": "client_credentials" } }

// oauth2 — user token (paste from scripts/alfresco/get-user-token)
{ "url": "http://localhost:8080/alfresco", "auth_method": "oauth2", "path": "/Shared/GraphRAG",
  "oauth2": { "access_token": "<paste>", "refresh_token": "<paste>",
    "token_endpoint": "http://localhost:8091/realms/alfresco/protocol/openid-connect/token" } }
```

## Related

- **[python-alfresco-api](https://github.com/stevereiner/python-alfresco-api)** — the client library
  (basic/ticket/OAuth2 auth utilities; see its `AUTHENTICATION_GUIDE.md`).
- **[python-alfresco-mcp-server](https://github.com/stevereiner/python-alfresco-mcp-server)** — a
  standalone Alfresco MCP server; same three auth methods via `ALFRESCO_AUTH_METHOD` / `ALFRESCO_OAUTH2_*`.
- **`scripts/alfresco/`** — token-minting helpers (`get-user-token.{ps1,bat,sh,py}`).
- OAuth2 verified compose-only (no Acosix): add `docker/includes/keycloak.yaml`, run with
  `docker compose -p flexible-graphrag …`.

## File structure (Alfresco-specific)

- `sources/alfresco.py` — the Alfresco data source connector (basic/ticket/oauth2, `_build_auth_util`).
- `incremental_updates/detectors/alfresco_detector.py` — real-time change detector (auth-aware).
- `incremental_updates/detectors/alfresco_broadcaster.py` — ActiveMQ/STOMP event consumer.
