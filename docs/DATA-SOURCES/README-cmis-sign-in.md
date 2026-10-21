# CMIS Sign-In and Permission-Aware Search

CMIS documents can be searched and asked about as the signed-in user, like Alfresco and Nuxeo
documents: answers draw only on the documents that user may read, checked against the repository
when the question is asked. CMIS has no ticket or token API of its own, so this works through
**vendor adapters**. Each adapter signs in to the server behind CMIS the way that vendor's own clients do.

Built and tested against ACS 26.2 and Nuxeo 2025:

| Vendor (`cmis:vendorName`) | Sign-in | Credential on CMIS calls | Stored by the UIs |
|---|---|---|---|
| Alfresco | REST `POST /alfresco/api/-default-/public/authentication/versions/1/tickets` | `Authorization: Basic base64(ROLE_TICKET:<ticket>)` | the ticket (`auth_method: "ticket"`) |
| Nuxeo | `GET /nuxeo/authentication/token` | `X-Authentication-Token: <token>` | the token (`auth_method: "token"`) |

No password is kept after sign-in: the UI stores only the ticket or token, in the tab's sessionStorage.

These forms were measured on the servers, not taken from vendor notes. Alfresco refuses
`user:<ticket>` as basic auth (401), and Nuxeo's CMIS binding refuses `user:<token>` (401). Only
the forms in the table work.

## What a CMIS server of another vendor does

Without an adapter for a server's vendor:

- `POST /api/auth/cmis/login` answers 400 ("CMIS sign-in supports Alfresco and Nuxeo servers…").
- The server's documents keep path-based doc ids (no `cmis://`). They are not permission-checked
  and stay visible to every asker, as before.

## How it fits together

1. **Ingest** (`sources/cmis.py`): `CmisSource` reads `cmis:vendorName` from the repository info.
   For a vendor with an adapter, each document's metadata gets
   `stable_file_path: cmis://<versionSeriesId or objectId>`, and the doc id becomes
   `{config_id}:cmis://<id>`.
2. **Requirements** (`GET /api/auth/requirements`): every CMIS server that has `cmis://` documents in
   the stores is listed as a provider: `{"source": "cmis", "url": "<CMIS service URL>", ...}`.
3. **Sign-in** (`POST /api/auth/cmis/login`, `sources/cmis_auth.py`):
   - Reads the vendor from the service document with the user's basic credentials.
   - Hands off to that vendor's adapter, which returns `{auth_method, ticket|token, user_id, vendor, url}`.
   - `GET /api/auth/cmis/me?auth_method=…&url=…` with `X-Cmis-Credential` re-checks a stored credential.
4. **Search / query**:
   - The request carries `source_auth.cmis`: one entry, or a list with one per server.
   - `permission_filter.py` fetches each candidate `cmis://` document through the server's AtomPub
     `objectbyid` URI template, using the adapter's headers. 200 means readable; 403 or 404 means
     left out; 401 means "sign in again".
5. **Ingest from the sign-in**:
   - The CMIS form sends `auth_method` + `ticket`/`token` + `username` instead of a password.
   - `CmisSource` then calls the adapter's `cmislib_session`, which drops basic auth from cmislib's
     `requests` session and adds the adapter's headers.

## Adding a vendor

Everything vendor-specific is in `flexible-graphrag/sources/cmis_auth.py`. Subclass `CmisAdapter` and
add the instance to `ADAPTERS`:

```python
class OpenTextCmisAdapter(CmisAdapter):
    name = "opentext"        # matched case-insensitively inside cmis:vendorName
    auth_method = "ticket"   # how its credential is named in source_auth.cmis / cmis_config

    def headers(self, credential: str) -> Dict[str, str]:
        return {"OTCSTICKET": credential}

    async def login(self, cmis_url, username, password):
        # POST <server>/api/v1/auth with username/password -> {"ticket": ...}
        ...
        return {"credential": ticket, "user_id": username}

    async def user(self, cmis_url, credential):
        # any authenticated call that names the user; raise PermissionError on 401
        ...

ADAPTERS = [AlfrescoCmisAdapter(), NuxeoCmisAdapter(), OpenTextCmisAdapter()]
```

Notes:

- **`auth_method` must be unique across adapters.** `adapter_for_method` maps a stored credential back to its
  adapter by this name. The request models in `main.py` (`CmisConfig`, `CmisQueryAuth`) carry
  `ticket` and `token` fields. A vendor whose credential is neither needs a new field there, and in the UIs' `ingestCredential`
  / `sourceAuthBody` (React and Vue `src/auth/sourceAuth.ts`, Angular lib
  `services/source-auth.storage.ts`).
- **Cookies** (e.g. FileNet's LTPA token from WebSphere): have `headers()` return
  `{"Cookie": "LtpaToken2=<token>"}`. Capture the cookie in `login()` from the server's login response.
- **The objectbyid check** (`permission_filter._check_url`) uses the AtomPub service document's `objectbyid`
  URI template, which any CMIS 1.0+ AtomPub server publishes. Nothing in it is vendor-specific.
- **After adding an adapter**, re-ingest that server's CMIS folders. Documents ingested earlier keep their path
  ids and stay ungoverned. Remove them first (Processing tab, or `/api/sync/remove`) so the stores don't hold both copies.
- **Test** with `tests/test_permission_filter.py`, which mocks a CMIS server, then live with
  `POST /api/auth/cmis/login` and a search carrying `source_auth.cmis`.

Vendor notes gathered so far (unverified, no servers to test with):

| Vendor | Token | How it's sent |
|---|---|---|
| IBM FileNet P8 | LTPA token from WebSphere/WebLogic after a form or SSO login | `Cookie: LtpaToken2=…` |
| OpenText Content Server (Extended ECM) | OTCS ticket from `/api/v1/auth` | `OTCSTICKET: <ticket>` header |
| Documentum (DCTM) | repository session token via Documentum REST | vendor-specific header or cookie |

## Settings

`CMIS_QUERY_AUTH` (or `SOURCE_QUERY_AUTH`), default `required`. With `required`, `cmis://`
documents are left out of a question that has no CMIS identity for their server. `optional`
shows them to such a question instead. Set `optional` only on a backend that nothing but trusted callers can reach.

Related: [README-cmis.md](README-cmis.md), [README-alfresco.md](README-alfresco.md),
[README-nuxeo.md](README-nuxeo.md).
