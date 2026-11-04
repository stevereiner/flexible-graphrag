# Security Policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub:
**[Report a vulnerability](https://github.com/stevereiner/flexible-graphrag/security/advisories/new)**
(Security tab → Advisories → Report a vulnerability).

Please don't open a public issue for a security problem.

A useful report includes the affected version or commit, the configuration needed to reach the
problem (for example `PG_GRAPH_DB=memgraph`), and a proof of concept or the code path involved.

This is a single-maintainer project. I aim to acknowledge reports within a week. Confirmed issues
are fixed in a release, then published as a GitHub Security Advisory with a CVE where one applies.
Reporters are credited unless they ask not to be.

## Supported versions

Only the latest release on PyPI (`flexible-graphrag`) gets security fixes. Please check that a
problem still exists on the latest release or on `main` before reporting.

## Deployment model

Knowing these points helps you judge whether something is a vulnerability:

- **Flexible GraphRAG is a backend for a controlled application.** It is meant to sit behind an
  app that handles user login, such as KG Spaces for Alfresco or Nuxeo. End users don't query the
  databases directly. They use hybrid search, AI query and AI chat. For sources that support it,
  the user's data-source permissions are checked at ingest and again at search time.
- **The backend REST API (port 8000) has no authentication of its own.** Don't expose it to end
  users: bind it to localhost or a private network so that only your application reaches it. A
  reverse proxy in front of it only helps if the proxy requires login, and lets only admin logins
  reach the admin endpoints below. A report that only says "the API has no auth" is not a vulnerability. A report
  showing that an API caller can go beyond what the API is meant to do is: reading arbitrary
  files, writing outside `uploads/`, reaching other hosts, or getting stored credentials back.
- **Admin endpoints.** The UIs only call search, query, ingest, upload, processing status,
  remove (`/api/sync/remove`, `/api/sync/ingest-status`), the source list, sign-in (`/api/auth/*`)
  and UI defaults. The other endpoints are for admins and should be reachable only with an admin
  login:
  - `/api/graph/query` and `/api/rdf/query/sparql` run the query the caller sends (Cypher,
    Gremlin, SPARQL and so on) as written, including queries that change or delete data. That is
    by design.
  - `/api/rdf/*` (ontology upload, connecting to and removing RDF stores).
  - `/api/sync/*` apart from the two above (auto sync on / off, intervals, sync now), and
    `/api/cocoindex/*`.
  - `/api/cleanup-uploads`, and the diagnostics `/api/info`, `/api/python-info` and `/api/graph`.
- **Search, query and chat check permissions for permission-checked sources.** Users only get
  results from documents they can read in Alfresco, Nuxeo, CMIS, SharePoint / OneDrive, Box,
  Google Drive / Cloud Storage, Azure Blob or Amazon S3. Getting results from such a source that
  the user can't read there is a vulnerability. Sources without per-user permissions (file upload,
  filesystem, web pages, Wikipedia, YouTube) are visible to every user of the app, by design. An
  app can leave them out: KG Spaces for Alfresco and Nuxeo can be configured to offer only
  permission-checked sources (the Angular library's `enabledSources`), and users upload files into
  the repository's own permissioned folders instead. The backend still has `/api/upload` and `/api/ingest`, so such an app should not pass
  other sources through to them.
- **Configuration is trusted.** `.env` values, ontology files and `SOURCE_PATHS` /
  `INGEST_ALLOWED_PATHS` are set by the operator. Problems that need write access to them are out
  of scope.
- **Graph Q&A runs only read queries.** It has the LLM write a query (Cypher, SPARQL, Gremlin and
  so on) and refuses any query that would write, change the schema or reach other hosts. A
  generated query that gets past this check and changes data is a vulnerability.
- **The MCP server** calls the backend REST API, so the same rules apply. It supports optional
  OAuth2 on its HTTP transport.
  - Ingest reads a data source with the credentials passed to the tool, so the source's own
    permissions decide what can be ingested. Filesystem paths must be inside the allowed folders.
  - Search and query check permissions for each source the call passes `source_auth` for. A call
    without credentials is unfiltered only if the backend trusts the MCP server (the same
    `TRUSTED_CLIENT_KEY` on both sides); otherwise the backend's `SOURCE_QUERY_AUTH` rules apply.
    Anyone holding that key gets unfiltered answers, so keep it secret.
  - Getting results through the MCP server from a permission-checked source that the user can't
    read, without the trusted key, is a vulnerability.
