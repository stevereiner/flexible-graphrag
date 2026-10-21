# Google Sign-In (Google Drive and Cloud Storage)

Once Google sign-in is configured, Flexible GraphRAG checks Google Drive and Google Cloud Storage
documents as the signed-in user: search and AI chat answer only from the files and objects that
user may open. **This is opt-in.** Without `GOOGLE_AUTH_CLIENT_ID`, Drive and GCS documents are
not permission-checked and stay visible to everyone, as before.

## For users

- **Header pill:** one **Google Drive, Google Cloud Storage** row, with the account, or offline.
- **Source picker:** the **Google Drive** and **Google Cloud Storage** chips stay greyed until
  you sign in.
- **Sign in with Google** opens Google's own login in a **new window**. Allow pop-ups for the
  Flexible GraphRAG site.
  - While the OAuth app is in Testing mode, Google shows "Google hasn't verified this app";
    choose **Continue**.
  - The account picker appears only the first time. After that the account used last is passed
    as a hint.
- **Links:** results open the Drive file page, or the GCS object through
  `storage.cloud.google.com`. Both apply your own Google permissions.
- **Expiry:** the token lasts about an hour. Sign-out only forgets it in that browser tab.

## Setting it up (Google Cloud console)

Use the project the data sources already use.

1. **APIs & Services → Library:** enable the **Google Drive API** and the **Cloud Storage JSON
   API**.
2. **OAuth consent screen** (Google Auth Platform):
   - **Audience:** External, Testing. Add each user who should sign in as a **test user**.
   - **Data access:** add these scopes:
     - `openid`, `userinfo.email` and `userinfo.profile`, listed as non-sensitive;
     - `devstorage.read_only`, listed as sensitive;
     - `drive.readonly`, listed as restricted.

     Restricted scopes need no Google verification while the app is in Testing.
3. **Clients → Create client**, Application type **Web application**:
   - **Authorized redirect URIs:** `http://localhost:8000/api/auth/google/callback`, or your
     backend's public `https://…/api/auth/google/callback`.
   - **JavaScript origins:** none.
4. In the backend `.env`:

   ```env
   GOOGLE_AUTH_CLIENT_ID=<client id>
   GOOGLE_AUTH_CLIENT_SECRET=<client secret>
   # Optional:
   # GOOGLE_AUTH_REDIRECT_URI=https://graphrag.example.com/api/auth/google/callback
   # GOOGLE_QUERY_AUTH=required   # optional = show Drive / GCS documents to askers not signed in
   ```

5. **Access:**
   - A user sees a Drive result only if the file is theirs or shared with them.
   - A user sees a GCS result only if they have a read role on the bucket, e.g. **Storage
     Object Viewer**.

## What is checked

| Source | Check (as the user) | Where the id comes from |
|---|---|---|
| Google Drive | `GET drive/v3/files/{id}` | the Drive file id in `document_state.source_id` |
| Google Cloud Storage | `GET storage/v1/b/{bucket}/o/{object}` | the doc id: `{config_id}:{bucket}/{object}` |

A 200 response means readable; 403 or 404 means left out. The incremental registry is required
(`ENABLE_INCREMENTAL_UPDATES=true`), and existing ingests need no re-ingest.

## REST and MCP

The flow is the same as Microsoft's ([README-microsoft-sign-in.md](README-microsoft-sign-in.md)),
with `google` in place of `microsoft`. Search and query take `source_auth.google`:
`{"access_token": "…"}`.
