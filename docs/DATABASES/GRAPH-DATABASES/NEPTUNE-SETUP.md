# Amazon Neptune Setup Guide

Covers Neptune Database (property graph) and Neptune Analytics (graph analytics with vector search).

## Framework Support

| Store | LlamaIndex | LangChain |
|---|---|---|
| Neptune Database (`neptune`) | Yes | Yes |
| Neptune Analytics (`neptune_analytics`) | Yes | Yes |

## Cost Tip — Avoid Serverless

**Avoid Neptune Serverless** — it is billed even when idle (no auto-pause).

Neptune Database **provisioned** clusters and Neptune Analytics graphs auto-pause after 7 days of
inactivity and are not charged while stopped. Use provisioned clusters for development to avoid
unexpected costs.

---

## Neptune Database

### Create a Cluster

1. AWS Console → **Amazon Neptune** → **Databases** → **Create database**
2. Choose **Regional** or **Global** cluster
3. Instance class:
   - `db.r5.*` / `db.r6g.*` — memory-optimized, support Statistics/Summary API
   - `db.t3.medium` / `db.t4g.medium` — burstable, lower cost, no Statistics API
   - For development a `db.t3.medium` works fine — the Summary API fallback handles it automatically
4. Configure VPC, subnet group, and security group
   - Security group must allow inbound TCP 8182 from your application's IP/CIDR

### IAM Permissions

Attach these policies to your IAM user or role:

```json
{
  "Effect": "Allow",
  "Action": [
    "neptune-db:connect",
    "neptune-db:ReadDataViaQuery",
    "neptune-db:WriteDataViaQuery",
    "neptune-db:DeleteDataViaQuery",
    "neptune-db:GetQueryStatus",
    "neptune-db:CancelQuery"
  ],
  "Resource": "arn:aws:neptune-db:<region>:<account-id>:<cluster-id>/*"
}
```

Or attach the managed policy `NeptuneFullAccess` for development.

### Configuration

```env
PG_GRAPH_DB=neptune

# Explicit credentials:
NEPTUNE_GRAPH_DB_CONFIG={"host": "your-cluster.cluster-xxxx.us-east-1.neptune.amazonaws.com", "port": 8182, "region": "us-east-1", "access_key": "YOUR_ACCESS_KEY", "secret_key": "YOUR_SECRET_KEY"}

# IAM role (EC2/ECS/Lambda — no explicit keys needed):
NEPTUNE_GRAPH_DB_CONFIG={"host": "your-cluster.cluster-xxxx.us-east-1.neptune.amazonaws.com", "port": 8182, "region": "us-east-1"}

# AWS credentials profile:
NEPTUNE_GRAPH_DB_CONFIG={"host": "your-cluster.cluster-xxxx.us-east-1.neptune.amazonaws.com", "port": 8182, "region": "us-east-1", "credentials_profile_name": "my-profile"}
```

### Summary API and T-Class Instances

The LlamaIndex Neptune adapter requires the **Statistics/Summary API** to discover graph schema.
This API is only available on R/X-class instances with statistics enabled.

Flexible GraphRAG includes an automatic fallback for T-class instances and older engine versions:
it issues direct openCypher queries to discover node labels and relationship types. No
configuration is needed — the fallback activates automatically.

Log messages:
- `"Neptune Database: Workaround query found X node labels"` — fallback active (T-class or statistics off)
- `"Neptune Database: Real Summary API returned X node labels"` — Summary API working (R/X-class)

**Note:** This fallback applies to the **LlamaIndex backend only**. The LangChain backend
(`GRAPH_BACKEND=langchain`) does not use the Summary API — it queries schema directly via
openCypher, so it works on all instance types without any fallback logic.

---

## Neptune Analytics

### Create a Graph

1. AWS Console → **Amazon Neptune** → **Analytics** → **Graphs** → **Create graph**
2. Configure graph name and region
3. **Vector search settings** — set the number of dimensions to match your embedding model:

| Embedding model | Dimensions |
|---|---|
| OpenAI `text-embedding-3-small`, `text-embedding-ada-002` | 1536 |
| OpenAI `text-embedding-3-large` | 3072 |
| Google `gemini-embedding-2-preview`, `text-embedding-004` | 768 |
| Ollama `nomic-embed-text`, Vertex AI | 768 |
| Bedrock `amazon.titan-embed-text-v2:0`, Ollama `mxbai-embed-large` | 1024 |
| Ollama `all-minilm` | 384 |

Vector dimensions **cannot be changed after graph creation**. To switch embedding models,
create a new graph with the correct dimension.

### IAM Permissions

```json
{
  "Effect": "Allow",
  "Action": [
    "neptune-graph:ReadDataViaQuery",
    "neptune-graph:WriteDataViaQuery",
    "neptune-graph:DeleteDataViaQuery",
    "neptune-graph:GetGraph",
    "neptune-graph:ListGraphs"
  ],
  "Resource": "arn:aws:neptune-graph:<region>:<account-id>:graph/<graph-id>"
}
```

Or attach `NeptuneGraphFullAccess` for development.

### Configuration

```env
PG_GRAPH_DB=neptune_analytics

# Explicit credentials:
NEPTUNE_ANALYTICS_GRAPH_DB_CONFIG={"graph_identifier": "g-123456789", "region": "us-east-1", "access_key": "YOUR_ACCESS_KEY", "secret_key": "YOUR_SECRET_KEY"}

# IAM role (no explicit keys):
NEPTUNE_ANALYTICS_GRAPH_DB_CONFIG={"graph_identifier": "g-123456789", "region": "us-east-1"}
```

The `graph_identifier` starts with `g-` and is shown in the AWS Console on the graph's
**Configuration** tab.

### Embedding Must Match

The embedding dimension in your `.env` must exactly match the dimension the graph was created with:

```env
# If graph was created with 1536 dimensions:
EMBEDDING_KIND=openai
EMBEDDING_MODEL=text-embedding-3-small
```

---

## AWS Credential Precedence

1. Explicit `access_key` + `secret_key` in config
2. `credentials_profile_name` in config (reads from `~/.aws/credentials`)
3. `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` environment variables
4. IAM role (EC2 instance profile, ECS task role, Lambda execution role)

---

## Neptune Graph Explorer

Neptune Graph Explorer is included in the Docker Compose setup for visualizing your graph.

Enable in `docker/docker-compose.yaml` (uncomment the neptune explorer include), then start:

```bash
docker compose -f docker-compose.yaml -p flexible-graphrag up -d
```

Access at: `http://localhost:3007/explorer`

### Connect to Neptune Database

- **Graph Type**: OpenCypher - PG
- **Use Proxy Server**: `http://localhost:3007`
- **AWS IAM Auth Enabled**: checked
- **Graph Connection URL**: `https://your-cluster.cluster-xxxx.us-east-1.neptune.amazonaws.com:8182`
- **AWS Region**: your region
- **Service Type**: Neptune DB

### Connect to Neptune Analytics

- **Graph Type**: OpenCypher - PG
- **Use Proxy Server**: `http://localhost:3007`
- **AWS IAM Auth Enabled**: checked
- **Graph Connection URL**: `https://g-123456789.us-east-1.neptune-graph.amazonaws.com/opencypher`
- **AWS Region**: your region
- **Service Type**: Neptune Analytics

AWS credentials for Graph Explorer go in `docker/neptune.env`:

```env
AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY
AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY
AWS_REGION=us-east-1
```

### Useful Queries

```cypher
-- All nodes and relationships (limit for large graphs)
MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50

-- Count nodes
MATCH (n) RETURN count(n) AS nodeCount

-- Count relationships
MATCH ()-[r]->() RETURN count(r) AS relCount

-- All node labels
MATCH (n) WITH DISTINCT labels(n) AS l UNWIND l AS label RETURN DISTINCT label

-- All relationship types
MATCH ()-[r]->() RETURN DISTINCT type(r)
```
