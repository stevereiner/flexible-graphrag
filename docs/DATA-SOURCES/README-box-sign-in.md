# Box Sign-In

Once Box sign-in is configured, Flexible GraphRAG checks Box documents as the signed-in user:
search and AI chat answer only from the Box files that user may open. **This is opt-in.**
Without `BOX_AUTH_CLIENT_ID`, Box documents are not permission-checked and stay visible to
everyone, as before.

## For users

- The header pill lists **Box** with the account, or offline.
- The source picker's **Box** chip stays greyed until you sign in.
- **Sign in with Box** opens Box's own login in a **new window**. Allow pop-ups for the
  Flexible GraphRAG site if the browser blocks it.
- The token lasts about an hour. Sign-out only forgets it in that browser tab.

## Setting it up (Box Developer Console)

The Box data source ingests with a *Server* app (Client Credentials Grant). That kind of app acts
as itself and cannot sign users in, so the sign-in needs a **second** app:

1. **Platform Apps → Create Platform App:**
   - App name: e.g. `flexible-graphrag-signin`.
   - App Type: **User** ("For apps where users link their Box accounts", OAuth 2.0).
2. On the new app's **Configuration** tab:
   - **OAuth 2.0 Redirect URIs:** `http://localhost:8000/api/auth/box/callback`, or your
     backend's public `https://…/api/auth/box/callback`.
   - **Application Scopes:** **Read all files and folders stored in Box**.
   - Click **Save Changes**.
3. Copy the **Client ID** and **Client Secret** into the backend `.env`:

   ```env
   BOX_AUTH_CLIENT_ID=<client id>
   BOX_AUTH_CLIENT_SECRET=<client secret>
   # Optional:
   # BOX_AUTH_REDIRECT_URI=https://graphrag.example.com/api/auth/box/callback
   # BOX_QUERY_AUTH=required   # optional = show Box documents to askers not signed in
   ```

## What is checked

Each Box search result is fetched with the user's token: `GET https://api.box.com/2.0/files/{id}`.
A 200 response means the user may read it; 403 or 404 means it is left out.

- Box documents keep their path doc ids (`{config_id}:All Files/…/name`), which the Box auto sync
  relies on.
- The check takes the file id from the registry (`document_state.source_id`), so **the incremental
  registry is required** (`ENABLE_INCREMENTAL_UPDATES=true`), and existing Box ingests need no
  re-ingest.

## REST and MCP

The flow is the same as Microsoft's ([README-microsoft-sign-in.md](README-microsoft-sign-in.md)),
with `box` in place of `microsoft`:

1. `GET /api/auth/box/popup?state=…`
2. `GET /api/auth/box/callback`
3. `GET /api/auth/box/result?state=…`
4. `GET /api/auth/box/me` with the `X-Auth-Token` header.

Search and query take `source_auth.box`: `{"access_token": "…"}`. Box returns the sign-in code
in the callback's query string, so the backend redacts `code=` from its access log.
