# Neo4j URLs

Reference for Neo4j connection URLs across all deployment environments.

| Environment | Database Access URL (Bolt) | Browser/Console URL (HTTP) | Neo4j Desktop Support |
| :-- | :-- | :-- | :-- |
| Neo4j Desktop (local) | `bolt://localhost:7687` | `http://localhost:7474/browser` | Supports running both Community & Enterprise locally |
| Neo4j Community (localhost) | `bolt://localhost:7687` | `http://localhost:7474/browser` | Can be managed via Neo4j Desktop if installed locally or connected externally |
| Neo4j Enterprise (localhost) | `bolt://localhost:7687` | `http://localhost:7474/browser` | Can be managed via Neo4j Desktop if installed locally or connected externally |
| Neo4j Community (non-local server) | `bolt://<server-ip-or-host>:7687` | `http://<server-ip-or-host>:7474/browser` | Neo4j Desktop can connect remotely via Bolt and HTTP URLs |
| Neo4j Enterprise (non-local server) | `bolt://<server-ip-or-host>:7687` | `http://<server-ip-or-host>:7474/browser` | Neo4j Desktop can connect remotely via Bolt and HTTP URLs |
| Neo4j AuraDB (cloud) | `neo4j+s://<unique-database-id>.databases.neo4j.io` | Aura Console: `https://console.neo4j.io` | Neo4j Desktop does **not** support AuraDB directly; use Aura Console |

## Key Points

- Neo4j Desktop supports local and remote connections to Community and Enterprise editions via Bolt and HTTP protocols.
- For Neo4j AuraDB (cloud), use the Aura Console for management and connect using the secure `neo4j+s://` URL for Bolt.
- Neo4j Desktop cannot manage AuraDB databases directly but can connect using drivers configured with AuraDB credentials.
