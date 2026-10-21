# Sign-In and Permission-Aware Search

Flexible GraphRAG can answer **only from the documents the person asking may read**. You sign in
to each repository whose documents are in the stores. Search, AI query and AI chat then check each
candidate result against that repository, as you, when the question is asked. Results you may not
open are left out.

This page covers how it works for users, which sources support it, the setup each one needs, and
what to do when something goes wrong.

---

## Which sources support it

| Data source | How you sign in | Opt-in setting (backend `.env`) | Setup guide |
|---|---|---|---|
| **Alfresco** | Username / password (an Alfresco ticket, as ACA uses) | always on | [below](#alfresco) |
| **Nuxeo** | Username / password (a Nuxeo token) | always on | [Nuxeo](README-nuxeo.md#sign-in-and-permission-aware-search) |
| **CMIS** (on Alfresco or Nuxeo servers) | Username / password (that vendor's ticket / token) | always on | [CMIS sign-in](README-cmis-sign-in.md) |
| **SharePoint + OneDrive** | **Sign in with Microsoft 365** popup, one sign-in for both | `MICROSOFT_AUTH_CLIENT_ID` | [Microsoft 365](README-microsoft-sign-in.md) |
| **Box** | **Sign in with Box** popup | `BOX_AUTH_CLIENT_ID` | [Box](README-box-sign-in.md) |
| **Google Drive + Cloud Storage** | **Sign in with Google** popup, one sign-in for both | `GOOGLE_AUTH_CLIENT_ID` | [Google](README-google-sign-in.md) |
| **Azure Blob** | **Sign in with Azure Storage** popup (separate from Microsoft 365) | `AZURE_AUTH_CLIENT_ID` | [Azure Storage](README-azure-sign-in.md) |
| **Amazon S3** | Your IAM **access key** (exchanged for a temporary session) | `S3_AUTH_ENABLED=true` | [Amazon S3](README-s3-sign-in.md) |
| Files, uploads, web, Wikipedia, YouTube | no per-user permissions | | visible to everyone |

**Opt-in** means: until the setting is present, that source's documents are not
permission-checked and stay visible to everyone, as in earlier versions. Alfresco, Nuxeo and CMIS
need no extra app, so they are always checked; see [Settings](#settings) to relax that.

**The incremental registry is required** for everything except Alfresco and Nuxeo
(`ENABLE_INCREMENTAL_UPDATES=true` with `POSTGRES_INCREMENTAL_URL`). It records which source,
server and repository item each document came from.

---

## Using it (React, Vue, Angular)

### The sign-in pill

The header has **one pill** for every repository sign-in.

- It reads **Sign-ins 2/5** with several servers, or e.g. **Nuxeo: Administrator** with one.
- A dashed outline means a server whose documents are in the stores has no sign-in yet.
- Its menu lists each server:
  - **Signed in:** a coloured dot, the account and **Sign out**.
  - **Offline:** a grey dot and **Sign in**.
  - Each row shows how many documents the stores hold from it (e.g. "SharePoint 2 docs ·
    OneDrive 1 doc"). Hover a row for its server address.
- **Sign out** only forgets the sign-in in that browser tab. It does not end your session at
  Alfresco, Microsoft, Box or Google, so ACA and other tabs keep working.

### Signing in

- **Username / password sources** (Alfresco, Nuxeo, CMIS) open a dialog. The password is sent once
  to the backend, which exchanges it for the repository's ticket or token. Only that ticket or
  token is kept, in the tab's session storage.
- **Amazon S3** opens the same dialog with **Access key ID** and **Secret access key**. The key is
  sent once and exchanged for a temporary AWS session (12 hours by default); only that session is
  kept.
- **Popup sources** (Microsoft 365, Box, Google, Azure Storage) open the vendor's own login in a **new window**,
  so multi-factor authentication works. The window closes itself when you are signed in.

  > **Allow pop-ups for the Flexible GraphRAG site.** If the browser blocks the window, the
  > dialog says so: allow pop-ups for the UI's address (the blocked-pop-up icon in the address
  > bar), then click the sign-in button again.

- **Before your first question**, the UI asks for each server that still needs a sign-in.
  **Continue without** answers from the other sources instead (for that browser tab).
- **Microsoft, Google and Azure Storage** remember the account you used (only its name, never a token) and pass
  it as a hint next time, so they skip the account picker.
- **Tokens expire:** Microsoft, Box, Google and Azure Storage after about an hour; Alfresco tickets on the
  server's schedule. The pill then shows offline; sign in again.

### Picking sources

Search (Hybrid Search and AI Query) and AI Chat have a **Sources** row: **All sources**, plus one
chip per source in the stores.

- **Pick several chips** to answer only from those sources.
- **A greyed chip needs a sign-in first:** hover it to see which one, and click it to sign in.
- **Picking only some sources** also limits the sign-in prompts to those sources.

### Results

Each result line names the file, the data source and the store, e.g.
`Source: cmispress.pdf | SharePoint | Qdrant vector | Score: 0.250`.

The file name opens the document in its repository: ACA or Share for Alfresco, the Nuxeo Web UI,
the SharePoint or OneDrive page, Box's viewer, Drive's viewer, or the GCS object. S3 and Azure Blob links, while you
are signed in to them, open the file itself through a short-lived URL signed with your own
sign-in (an hour); without a sign-in an S3 link opens the AWS console and Azure has none. Each of those
applies your own permissions again.

### Ingesting with your sign-in

The Alfresco, Nuxeo and CMIS data-source forms show **Signed in to X as Y (used for this
ingest)** when you are signed in to that server. The ingest then uses your ticket or token, and
no credentials are typed.

**Use other credentials** brings the fields back. Use it for a service account, e.g. for Auto
Sync: an Alfresco ticket expires, while a Nuxeo token does not.

---

## Setup by source

### Alfresco

Nothing to register. The sign-in uses Alfresco's own ticket API (as ACA does) against the server
the documents came from. `ALFRESCO_URL` is the default server.

- **KG Spaces in ACA** passes ACA's own ticket, so no sign-in is asked there for ACA's own server.
  Every other source signs in from the **sign-in pill** at the right end of the KG Spaces title bar
  (with a signed-in count); questions then carry ACA's ticket plus
  those sign-ins. `plugins.kgSpaces.searchSignIn: false` in ACA's `app.config.json` sends only
  ACA's ticket.
- **Several Alfresco servers** each get their own row in the pill.

### Nuxeo and CMIS

Nothing to register. Nuxeo issues a token for the user. A CMIS server on Alfresco or Nuxeo gets
that vendor's ticket or token. Details: [Nuxeo](README-nuxeo.md#sign-in-and-permission-aware-search),
[CMIS](README-cmis-sign-in.md), including how to add another CMIS vendor.

### Microsoft 365, Box, Google, Azure Storage: what they have in common

Each needs an **OAuth app registered at the vendor**, separate from, or in addition to, the
credentials the data source ingests with:

| | Microsoft 365 (Entra ID) | Box (Developer Console) | Google (Cloud console) | Azure Storage (Entra ID) |
|---|---|---|---|---|
| App type | App registration; platform **Web** | Platform App of type **User** (OAuth 2.0) | OAuth client of type **Web application** | App registration in the **storage account's directory**; platform **Web** |
| Redirect URI | `<backend>/api/auth/microsoft/callback` | `<backend>/api/auth/box/callback` | `<backend>/api/auth/google/callback` | `<backend>/api/auth/azure/callback` |
| Permissions / scopes | Delegated Graph `Files.Read.All`, `Sites.Read.All`, `User.Read`, `offline_access`, plus **admin consent** | "Read all files and folders stored in Box" | `drive.readonly`, `devstorage.read_only`, `openid` / email / profile; test users while in Testing | Delegated Azure Storage `user_impersonation` plus **admin consent**; users need **Storage Blob Data Reader** |
| `.env` | `MICROSOFT_AUTH_CLIENT_ID`, `_CLIENT_SECRET`, `_TENANT_ID` | `BOX_AUTH_CLIENT_ID`, `_CLIENT_SECRET` | `GOOGLE_AUTH_CLIENT_ID`, `_CLIENT_SECRET` | `AZURE_AUTH_CLIENT_ID`, `_CLIENT_SECRET`, `_TENANT_ID` |
| Can it reuse the ingest app? | Yes: the same Entra app can do both | No: the ingest app (Client Credentials Grant) cannot sign users in | Partly: a different credential type in the same project | Yes, if the Microsoft 365 app is in the same directory; usually it is not |

Notes for all four:

- **`<backend>`** is the backend's address as the browser reaches it, e.g.
  `http://localhost:8000`. A deployed backend needs `https://`. Set `<PROVIDER>_AUTH_REDIRECT_URI`
  when a proxy changes the address.
- **Use `localhost`, not `127.0.0.1`,** in redirect URIs: vendors treat them as different
  addresses.

---

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `SOURCE_QUERY_AUTH` | `required` | `required`: a governed source's documents are left out of a question that brings no sign-in for their server. `optional`: they are shown, which suits only a backend that nothing but trusted callers can reach. |
| `ALFRESCO_QUERY_AUTH`, `NUXEO_QUERY_AUTH`, `CMIS_QUERY_AUTH`, `MICROSOFT_QUERY_AUTH`, `BOX_QUERY_AUTH`, `GOOGLE_QUERY_AUTH`, `AZURE_QUERY_AUTH`, `S3_QUERY_AUTH` | (from `SOURCE_QUERY_AUTH`) | The same, per source |
| `MICROSOFT_AUTH_*`, `BOX_AUTH_*`, `GOOGLE_AUTH_*`, `AZURE_AUTH_*` | unset | Turn on that source's popup sign-in (and its permission checks) |
| `S3_AUTH_ENABLED` | unset | `true` turns on Amazon S3 sign-in and its permission checks |
| `S3_AUTH_SESSION_SECONDS` | `43200` | How long an S3 sign-in lasts (900 to 129600 seconds) |

---

## Troubleshooting

| What you see | Why, and what to do |
|---|---|
| "The browser blocked the … sign-in window" | Allow pop-ups for the Flexible GraphRAG site, then click the sign-in button again. |
| A blank pop-up window | An older UI build: reload the page (Ctrl+F5). |
| **AADSTS50011** (redirect URI mismatch) | The Entra app lacks the exact **Web** redirect URI `…/api/auth/microsoft/callback`. |
| **AADSTS65001** / a consent screen every time | The delegated permissions were added without **Grant admin consent**. |
| "Google hasn't verified this app" | Normal while the Google OAuth app is in Testing: choose **Continue**. Only the consent screen's test users can sign in. |
| Box asks which account / uses the wrong one | Box takes no account hint; sign out of the other Box account in that browser, or use a separate browser profile. |
| Opening a SharePoint / OneDrive link asks which account | SharePoint's own sign-in in the new tab; with several Microsoft accounts in one browser it asks. A browser profile per account avoids it. |
| "The documents that answer this are in X. Sign in to X…" | You have no sign-in for that server: use the pill, or pick other sources. |
| A source's documents are missing after signing in | Your account cannot open them at the repository. For GCS that means a bucket role such as **Storage Object Viewer**; for Azure Blob a data role such as **Storage Blob Data Reader** (Owner is not enough); for S3 `s3:GetObject` on the objects. |
| "… credentials were refused (expired or invalid)" | The token or ticket expired or was revoked: sign in again from the pill. |

---

## REST and MCP

- **`GET /api/auth/requirements`:** which servers need a sign-in.
- **`GET /api/sources/available`:** the sources a question can be limited to.
- **Search and query** take:
  - `source_auth`: one credential, or a list with one per server, under `alfresco`, `nuxeo`,
    `cmis`, `microsoft`, `box`, `google`, `azure` or `s3`;
  - `sources`: the source picker's choice.
- **Username / password sign-in:** `POST /api/auth/{alfresco|nuxeo|cmis}/login`; S3:
  `POST /api/auth/s3/login` with the access key as username / password.
- **Popup sign-in:** `GET /api/auth/{microsoft|box|google|azure}/popup` → `/callback` → `/result`.
- **MCP tools:**
  - `sign_in` (username / password sources and S3), `get_auth_requirements` and `list_sources`;
  - Three levels, set on the MCP side (details in the MCP server README): **1** no credentials,
    no filtering (the backend must trust the MCP server: `TRUSTED_CLIENT_KEY` on the backend =
    `FLEXIBLE_GRAPHRAG_TRUSTED_KEY` on the MCP server); **2** credentials in `source_auth` filter
    those sources; **3** `MCP_BROWSER_SIGN_IN=true` adds the browser sign-in tools below.
  - `start_sign_in` and `finish_sign_in` for the browser sign-ins (Microsoft 365, Box, Google,
    Azure Storage): `start_sign_in` gives a link, the user opens it in any browser and signs in at
    the vendor, and `finish_sign_in` (once they say they have; it returns at once, or waits with
    `wait_seconds`) collects the credential to pass as `source_auth`. The secret
    that collects it stays in the MCP server, never in the model's context; a link works once and
    lasts 10 minutes. REST: `POST /api/auth/{provider}/handoff`, then
    `POST /api/auth/{provider}/handoff/result` with the poll key.
  - `AUTH_HANDOFF_CONFIRM_CODE=true` makes the link first show a code to compare with the client's
    before going on to the vendor. Use it on a shared backend: it stops a sign-in link sent by
    someone else from handing them your token.
  - `search_documents` and `query_documents` take `source_auth` and `sources`.
