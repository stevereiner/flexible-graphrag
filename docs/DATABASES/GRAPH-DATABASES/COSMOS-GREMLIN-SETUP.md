# Azure Cosmos DB for Gremlin Setup

## Prerequisites

- Azure account with an active subscription
- Azure Cosmos DB account created with **Gremlin (Graph)** API selected at account creation time
  (the API cannot be changed after creation)
- Python package: `gremlinpython` (included in `.[langchain-extras]`)
- For auto-create: `azure-mgmt-cosmosdb` and `azure-identity` (included in `.[langchain-extras]`)

## Create the Cosmos DB Account

In the Azure Portal:

1. Search for **Azure Cosmos DB** → **Create**
2. Select **Azure Cosmos DB for Apache Gremlin**
3. Choose your subscription, resource group, and account name
4. Select a region
5. Complete creation (takes a few minutes)

## Create the Graph Container

Cosmos DB Gremlin requires a **database** and a **graph container** (the graph). These can be
created manually or automatically by the adapter on startup.

### Option A — Auto-create (recommended)

Add `subscription_id`, `resource_group`, and service principal credentials to the config.
The adapter creates the database and graph on first startup if they do not exist.

Create a service principal with the **Cosmos DB Operator** role:

```bash
az ad sp create-for-rbac --name flexible-graphrag-cosmos \
  --role "Cosmos DB Operator" \
  --scopes /subscriptions/<subscription_id>/resourceGroups/<resource_group>
```

The output gives you `appId` (→ `client_id`), `password` (→ `client_secret`), `tenant` (→ `tenant_id`).

Using `ClientSecretCredential` (pure HTTPS) avoids spawning `az` CLI / PowerShell subprocesses,
which can trigger antivirus behavioral detection on Windows (e.g. Norton IDP.HELU.PSE73%s_cmd).

### Option B — Azure Portal

Cosmos DB account → **Data Explorer** → **New Graph**:

- Database id: `graphdb` (or your choice)
- Graph id: `knowledge_graph`
- Partition key: `/partitionKey`

### Option C — Azure CLI

```bash
az cosmosdb gremlin database create \
  --account-name <account-name> \
  --name graphdb \
  --resource-group <resource-group>

az cosmosdb gremlin graph create \
  --account-name <account-name> \
  --database-name graphdb \
  --name knowledge_graph \
  --partition-key-path /partitionKey \
  --resource-group <resource-group>
```

## Get Connection Details

In the Azure Portal → your Cosmos DB account:

- **Keys** → **Primary Key** — this is your `password`
- **Keys** → **Gremlin Endpoint** — e.g. `wss://my-account.gremlin.cosmos.azure.com:443/`
- **Username format**: `/dbs/<database-id>/colls/<graph-id>`

## Configuration

```env
PG_GRAPH_DB=cosmos_gremlin

# Minimal config (graph already exists):
COSMOS_GREMLIN_GRAPH_DB_CONFIG={"url": "wss://my-account.gremlin.cosmos.azure.com:443/", "username": "/dbs/graphdb/colls/knowledge_graph", "password": "your_primary_key==", "partition_key_property": "partitionKey", "partition_key_value": "graph"}

# With auto-create (service principal — no subprocess spawning):
COSMOS_GREMLIN_GRAPH_DB_CONFIG={"url": "wss://my-account.gremlin.cosmos.azure.com:443/", "username": "/dbs/graphdb/colls/knowledge_graph", "password": "your_primary_key==", "partition_key_property": "partitionKey", "partition_key_value": "graph", "subscription_id": "your-sub-id", "resource_group": "your-rg", "tenant_id": "your-tenant-id", "client_id": "your-client-id", "client_secret": "your-client-secret"}
```

### Config Keys

| Key | Required | Description |
|---|---|---|
| `url` | Yes | Gremlin endpoint: `wss://<account>.gremlin.cosmos.azure.com:443/` |
| `username` | Yes | `/dbs/<database>/colls/<graph>` |
| `password` | Yes | Primary key from Azure Portal → Keys |
| `partition_key_property` | No | Property name for partition key (default: `partitionKey`) |
| `partition_key_value` | No | Fixed value written on every vertex (default: `graph`) |
| `subscription_id` | No | Azure subscription ID — enables auto-create |
| `resource_group` | No | Azure resource group — enables auto-create |
| `tenant_id` | No | Azure AD tenant ID — use with `client_id`/`client_secret` |
| `client_id` | No | Service principal application ID (`appId` from `az ad sp`) |
| `client_secret` | No | Service principal secret (`password` from `az ad sp`) |

## Partition Key Design

All vertices must carry a `partitionKey` property. The adapter injects this automatically on
every vertex write. Using a **fixed value** (e.g. `"graph"`) keeps all vertices in one logical
partition so graph traversals never cross partition boundaries.

Do not use the entity type as the partition key — that scatters vertices across partitions,
forcing every traversal to fan out across all partitions.

## Framework Support

Cosmos DB Gremlin is **LC only** — LangChain backend (`GRAPH_BACKEND=langchain`) is set
automatically when `PG_GRAPH_DB=cosmos_gremlin`.

## Inspect the Graph

In the Azure Portal → Cosmos DB account → **Data Explorer**:

- Expand your database → graph container
- Click **Load Graph** or run a Gremlin query in the query panel
- `g.V()` — list all vertices
- `g.V().count()` — count vertices
- `g.E().count()` — count edges

## IAM Required Permissions

| Permission | Purpose |
|---|---|
| Cosmos DB Operator (`roles/cosmosdb.operator`) | Auto-create database and graph container |
| No additional role needed for data plane | The Gremlin password (primary key) covers reads/writes |
