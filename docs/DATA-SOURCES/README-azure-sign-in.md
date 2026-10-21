# Azure Storage Sign-In (Azure Blob)

Once Azure Storage sign-in is configured, Flexible GraphRAG checks Azure Blob documents as the
signed-in user: search and AI chat answer only from the blobs that user may read. **This is
opt-in.** Without `AZURE_AUTH_CLIENT_ID`, Azure Blob documents are not permission-checked and stay
visible to everyone, as before.

This is a **separate sign-in from Microsoft 365** (SharePoint and OneDrive). A storage account
often lives in a different directory: for example, the "Default Directory" of the personal
Microsoft account that owns the Azure subscription.

## For users

- **Header pill:** one **Azure Blob** row, with the account, or offline.
- **Source picker:** the **Azure Blob** chip stays greyed until you sign in.
- **Sign in with Azure Storage** opens Microsoft's own login in a **new window**. Allow pop-ups
  for the Flexible GraphRAG site. The account used last is passed as a hint next time.
- **Links:** while you are signed in, a result's link opens the blob itself: a *user delegation
  SAS* URL signed with your own sign-in, so Azure still applies your access. Links last an hour
  (never longer than the sign-in). Text, PDF and image files open in the tab, text always as
  plain text; other files download. Without a sign-in there is no link.
  - Making the link needs `generateUserDelegationKey`, which **Storage Blob Data Reader** includes.
  - A SAS link works for anyone who has it, for that one file, until it expires.
- **Expiry:** the token lasts about an hour. Sign-out only forgets it in that browser tab.

## Setting it up (Azure portal)

Work in the **directory that holds the storage account**. To find it, open the storage account,
then **Overview → JSON View** or the subscription's directory. With a personal Microsoft account
this is usually "Default Directory"; its **Tenant ID** is under **Microsoft Entra ID →
Overview**.

1. **Microsoft Entra ID → App registrations → New registration:**
   - Supported account types: **Accounts in this organizational directory only**.
   - Redirect URI: platform **Web**, `http://localhost:8000/api/auth/azure/callback`, or your
     backend's public `https://…/api/auth/azure/callback`.
2. **Certificates & secrets → New client secret.** Copy its **Value**, not its ID.
3. **API permissions → Add a permission → Azure Storage → Delegated → `user_impersonation`**,
   then **Grant admin consent**.
4. **The storage account → Access control (IAM) → Add role assignment:** give each user who
   should see Azure Blob results a data role, e.g. **Storage Blob Data Reader**, on the account
   or on the container.

   > **Owner and Contributor are not enough.** They manage the account but do not grant blob
   > *data* access to a signed-in user.

   Guest users (e.g. a personal Microsoft account added to the directory) sign in the same way.

5. In the backend `.env`:

   ```env
   AZURE_AUTH_CLIENT_ID=<application (client) id>
   AZURE_AUTH_CLIENT_SECRET=<client secret value>
   AZURE_AUTH_TENANT_ID=<directory (tenant) id of the storage account's directory>
   # Optional:
   # AZURE_AUTH_REDIRECT_URI=https://graphrag.example.com/api/auth/azure/callback
   # AZURE_QUERY_AUTH=required   # optional = show Azure Blob documents to askers not signed in
   ```

The data source's own ingest credentials (connection string, account key or service principal)
are unaffected: ingest and Auto Sync keep using them.

## What is checked

| Source | Check (as the user) | Where the id comes from |
|---|---|---|
| Azure Blob | `GET {account}/{container}/{blob}?comp=metadata` (Get Blob Metadata: headers only, no content) | the doc id `{config_id}:{container}/{blob}`; the account from the datasource's `account_url`, `account_name` or connection string |

A 200 response means readable; 403 or 404 means left out; 401 means the sign-in expired. The
incremental registry is required (`ENABLE_INCREMENTAL_UPDATES=true`), and existing ingests need
no re-ingest.

## Troubleshooting

| What you see | Why, and what to do |
|---|---|
| **AADSTS50011** (redirect URI mismatch) | Add the exact **Web** redirect URI `…/api/auth/azure/callback` to the app. |
| **AADSTS50020** (user not in the tenant) | `AZURE_AUTH_TENANT_ID` names a different directory than the account you sign in with, or that account is not a member or guest of it. |
| **AADSTS65001** / a consent screen every time | Azure Storage `user_impersonation` was added without **Grant admin consent**. |
| "You don't have access to any document that answers this" | The account has no data role: add **Storage Blob Data Reader**. Role assignments can take a few minutes to apply. |

## REST and MCP

The flow is the same as Microsoft's ([README-microsoft-sign-in.md](README-microsoft-sign-in.md)),
with `azure` in place of `microsoft`. Search and query take `source_auth.azure`:
`{"access_token": "…"}`, an Azure Storage token (audience `https://storage.azure.com`).
