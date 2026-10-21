# Microsoft 365 Sign-In (SharePoint and OneDrive)

Once Microsoft sign-in is configured, Flexible GraphRAG checks SharePoint and OneDrive documents
as the signed-in user, the same way it checks Alfresco, Nuxeo and CMIS documents. Search and AI
chat then answer only from the files that user may open.

**This is opt-in.** Without `MICROSOFT_AUTH_CLIENT_ID`, SharePoint and OneDrive documents are not
permission-checked and stay visible to everyone, as before.

## How it works for users

- **Header pill:** shows "Microsoft 365" with the user, or offline. Its menu has Sign in / Sign out.
- **Source picker:** on Search and AI Chat, the SharePoint and OneDrive chips stay greyed until
  you sign in.
- **Sign in with Microsoft:** opens Microsoft's own login in a **new window**, so MFA and
  conditional access work. One sign-in covers SharePoint and OneDrive.

  > **Allow pop-ups for the Flexible GraphRAG site.** If the browser blocks the window, the dialog
  > says so. Allow pop-ups for the UI's address (e.g. `http://localhost:5174`, `:3000` or `:4200`),
  > for example through the blocked-pop-up icon in the address bar, then click "Sign in with
  > Microsoft" again.

- **Several Microsoft accounts in one browser:** the first sign-in shows Microsoft's account
  picker. After that the UI remembers which account you used (its name only, in the browser's
  local storage) and passes it as a hint, so Microsoft picks it without asking.
  - Opening a result's SharePoint or OneDrive link is SharePoint's own sign-in in a new tab. With
    several accounts it may ask which one to use; a link cannot say.
  - A separate browser profile per Microsoft account avoids those prompts.
- **Expiry:** the access token lasts about an hour. After it expires the pill shows offline again;
  sign in again, which is usually instant while the Microsoft session is still active.
- **Sign out:** only forgets the token in that browser tab.

Search results and answer sources link to each file's SharePoint or OneDrive page, which
enforces the viewer's own permissions when opened. OneDrive documents ingested before this
version have no link until they are re-ingested.

## Setting it up (Microsoft Entra ID)

The app registration can be the one the SharePoint / OneDrive data sources already use to ingest.
In the [Entra admin center](https://entra.microsoft.com) > App registrations > your app:

1. **Authentication > Add a platform > Web.** Add the redirect URI for each backend address that
   browsers reach:
   - `http://localhost:8000/api/auth/microsoft/callback`
   - in production, your backend's public `https://…/api/auth/microsoft/callback`

   Use the **Web** platform, not "Single-page application": the backend exchanges the code with
   the client secret.
2. **API permissions > Add > Microsoft Graph > Delegated permissions:**
   - `Files.Read.All`
   - `Sites.Read.All`
   - `User.Read`
   - `offline_access`

   Then **Grant admin consent**. These delegated permissions are separate from the Application
   permissions that ingest uses.
3. **Certificates & secrets:** use the existing client secret, or add one.
4. **Backend `.env`:**

   ```env
   MICROSOFT_AUTH_CLIENT_ID=<application (client) id>
   MICROSOFT_AUTH_CLIENT_SECRET=<client secret>
   MICROSOFT_AUTH_TENANT_ID=<directory (tenant) id>
   # Optional:
   # MICROSOFT_AUTH_REDIRECT_URI=https://graphrag.example.com/api/auth/microsoft/callback
   # MICROSOFT_QUERY_AUTH=required   # optional = show SharePoint/OneDrive docs to askers not signed in
   ```

   By default the redirect URI is the backend's own address as the browser reaches it, with
   `127.0.0.1` written as `localhost`. Set `MICROSOFT_AUTH_REDIRECT_URI` when a proxy changes it.

## What is checked

Each SharePoint or OneDrive search result is fetched with the user's token. A 200 response means
the user may read it; 403 or 404 means it is left out.

| Source | Doc id | Graph check (as the user) |
|---|---|---|
| SharePoint | `{config_id}:sharepoint://<item id>` | `GET /sites/{site}/drive/items/{item}`; the site is resolved from the datasource's `site_name` (or `site_id`) |
| OneDrive | `{config_id}:onedrive://<item id>` | `GET /users/{user_principal_name}/drive/items/{item}` |

- A document belongs to the tenant of its datasource (`tenant_id`). A token from another tenant is
  not used for it.
- **The incremental registry is required** (`ENABLE_INCREMENTAL_UPDATES=true`). Without it,
  SharePoint and OneDrive documents carry no item ids and are not checked.

## REST and MCP

1. Open `GET /api/auth/microsoft/popup?state=<new random, 32+ URL-safe characters>` in a browser
   window. The backend records the sign-in, sets a short-lived HttpOnly cookie, and redirects the
   window to Microsoft.
2. Microsoft returns the window to `GET /api/auth/microsoft/callback`, where the backend
   exchanges the code.
3. Poll `GET /api/auth/microsoft/result?state=…` from the same browser, sending the cookie. It
   answers 202 while the user is signing in, then returns
   `{access_token, user_id, url (tenant), expires_at}` once.
4. `GET /api/auth/microsoft/me` with the `X-Microsoft-Token` header checks a token.
5. Search and query take `source_auth.microsoft`: `{"access_token": "…"}`, or a list with one
   entry per tenant.

MCP clients pass a delegated Graph token in `source_auth.microsoft`. MCP has no browser, so it
has no `sign_in` for Microsoft.

Related: [README-cmis-sign-in.md](README-cmis-sign-in.md), [DATA-SOURCE-CONFIGURATION.md](DATA-SOURCE-CONFIGURATION.md).
