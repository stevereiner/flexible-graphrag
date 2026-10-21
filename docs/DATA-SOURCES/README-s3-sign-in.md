# Amazon S3 Sign-In

Once S3 sign-in is on, Flexible GraphRAG checks Amazon S3 documents as the signed-in user: search
and AI chat answer only from the objects that user may read. **This is opt-in.** Without
`S3_AUTH_ENABLED=true`, S3 documents are not permission-checked and stay visible to everyone, as
before.

AWS has no browser sign-in that a third-party app can use for plain IAM users, so users sign in
the way the AWS CLI does: with **their own IAM access key**.

## For users

- **Header pill:** an **Amazon S3** row, with the IAM user name, or offline.
- **Source picker:** the **Amazon S3** chip stays greyed until you sign in.
- **Sign in** opens a dialog with **Access key ID** and **Secret access key**.
  - The key is sent once to the backend, which trades it with AWS STS (`GetSessionToken`) for
    temporary session credentials.
  - Only that temporary session is kept, in the browser tab's session storage. Your secret access
    key is never stored, by the browser or the backend.
- **Expiry:** the session lasts 12 hours by default (`S3_AUTH_SESSION_SECONDS`). The pill then
  shows offline; sign in again. Sign-out only forgets it in that browser tab.
- **Links:** while you are signed in, a result's link opens the file itself: a presigned URL
  made with your own S3 session, so S3 still applies your access. Links last an hour (never
  longer than the sign-in). Text, PDF and image files open in the tab, text always as plain text;
  other files download. Without a sign-in, links open the object's page in the AWS S3 console.
  - A presigned link carries a temporary credential for that one file: anyone you share the link
    with can open that file until the link expires.

## Setting it up

There is **no app to register**. In the backend `.env`:

```env
S3_AUTH_ENABLED=true
# Optional:
# S3_AUTH_SESSION_SECONDS=43200   # 900 .. 129600 (STS's limits for an IAM user)
# S3_QUERY_AUTH=required          # optional = show S3 documents to askers not signed in
```

In AWS IAM, for each user who should sign in:

1. **Security credentials → Create access key** (use case: *Command Line Interface* or *Other*).
   The user keeps the key; it is typed only into the sign-in dialog.
2. **Permissions:** `s3:GetObject` on the objects they may read, e.g.

   ```json
   {
     "Effect": "Allow",
     "Action": "s3:GetObject",
     "Resource": "arn:aws:s3:::my-bucket/*"
   }
   ```

   Without `s3:ListBucket` on the bucket, S3 answers a missing object with AccessDenied instead of
   NoSuchKey; either way the object is left out.

No extra permission is needed for the sign-in itself: every IAM user may call
`sts:GetSessionToken` and `sts:GetCallerIdentity`.

> **MFA-protected policies:** if a user's policies require MFA (`aws:MultiFactorAuthPresent`),
> the session from a plain `GetSessionToken` does not satisfy them. MFA codes are not supported
> in the dialog yet.

## What is checked

| Source | Check (as the user) | Where the id comes from |
|---|---|---|
| Amazon S3 | a SigV4-signed `GET` of the object with `Range: bytes=0-0` (one byte, never the content) | the doc id `{config_id}:s3://{bucket}/{key}`; the region from the datasource's `region_name` |

- **200 / 206** (or 416 for an empty object): readable.
- **403 AccessDenied / 404:** left out.
- **InvalidAccessKeyId, ExpiredToken, SignatureDoesNotMatch:** the session expired or is invalid;
  the question returns 401 and the UI asks to sign in again.

A ranged GET is used instead of HEAD because a HEAD error has no body, so an expired session could
not be told apart from "no access". The incremental registry is required
(`ENABLE_INCREMENTAL_UPDATES=true`), and existing ingests need no re-ingest.

## REST and MCP

- **Sign in:** `POST /api/auth/s3/login` with `{"access_key_id": "...", "secret_access_key": "..."}`
  (or `username` / `password`) → `{token, user_id, expires_at, url: "aws"}`.
- **Check a sign-in:** `GET /api/auth/s3/me` with the header `X-Auth-Token: <token>`.
- **Search and query** take `source_auth.s3`: `{"token": "…"}`.
- **MCP:** `sign_in` with `source="s3"`, the access key ID as `username` and the secret access key
  as `password`.
