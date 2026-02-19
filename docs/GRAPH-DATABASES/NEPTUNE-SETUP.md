# Amazon Neptune Setup Guide for Flexible GraphRAG

This guide covers the complete setup process for integrating Amazon Neptune (both Neptune Database and Neptune Analytics) with Flexible GraphRAG.

## Table of Contents

1. [Neptune Database Setup](#neptune-database-setup)
2. [Neptune Analytics Setup](#neptune-analytics-setup)
3. [Configuration in Flexible GraphRAG](#configuration-in-flexible-graphrag)
4. [Troubleshooting](#troubleshooting)

---

## Neptune Database Setup

Neptune Database is a fully managed graph database service that supports both property graph (openCypher/Gremlin) and RDF graph models.

### Prerequisites

- AWS Account with appropriate permissions
- Neptune Database cluster created in AWS Console
- Network access configured (VPC, Security Groups)

### Configuration Steps

1. **Create Neptune Database Cluster** in AWS Console:
   - Go to Amazon Neptune → Clusters → Create database
   - Choose cluster configuration (instance type, storage)
   - Configure networking and security

2. **Get Connection Details**:
   - Cluster endpoint: `your-cluster.cluster-xxxxx.region.neptune.amazonaws.com`
   - Port: `8182` (default)
   - Region: Your AWS region (e.g., `us-east-1`)

3. **Configure AWS Credentials**:
   - Access Key ID and Secret Access Key
   - Or use IAM roles if running on EC2/ECS

4. **Update `.env` file**:

```env
GRAPH_DB=neptune

# Neptune Database Configuration
GRAPH_DB_CONFIG={"host": "your-cluster.cluster-xxxxx.region.neptune.amazonaws.com", "port": 8182, "region": "us-east-1", "access_key": "YOUR_ACCESS_KEY", "secret_key": "YOUR_SECRET_KEY"}
```

### Neptune Database Limitations

**Summary API Requirement:**
- Neptune Database's Summary API requires:
  - Engine version >= 1.2.1.0
  - Statistics to be enabled
  - **Memory-optimized instance classes (R or X classes)**
    - ✅ Supported: `db.r5.*`, `db.r6g.*`, `db.x2g.*`, `db.x2iedn.*` instances
    - ❌ Not available: Burstable T classes (`db.t3.medium`, `db.t4g.medium`)
    - Statistics/Summary API cannot be enabled on burstable T-class instances
    - T-class instances are lower-cost options but lack this feature

**Workaround for Low-Cost Configurations:**
- Flexible GraphRAG includes a wrapper that automatically detects when the Summary API is unavailable
- Falls back to direct openCypher queries to discover graph schema
- Works seamlessly with burstable T-class instances, older engine versions, or when statistics are disabled
- No manual intervention required
- **Logging:** Watch for these log messages:
  - T-class or older instances: `"Neptune Database: Workaround query found X node labels"`
  - R/X-class with statistics enabled: `"Neptune Database: Real Summary API returned X node labels"`

---

## Neptune Analytics Setup

Neptune Analytics is a serverless graph analytics engine optimized for fast analytics queries on large graphs.

### Prerequisites

- AWS Account with appropriate permissions
- Understanding of your embedding dimensions before creating the graph
- Network access configured

### **CRITICAL: Vector Search Configuration**

⚠️ **IMPORTANT:** When creating your Neptune Analytics graph, you **MUST** configure vector dimensions correctly during creation. **This cannot be changed after the graph is created.**

#### Steps to Configure Vector Dimensions:

1. **Create Graph** in AWS Console:
   - Go to Amazon Neptune → Analytics → Graphs → Create graph
   - Choose graph name and configuration

2. **Vector Search Settings** (Critical Step):
   - In the **"Vector search settings"** section:
   - ✅ Choose **"Use vector dimension"**
   - ✅ Set **"Number of dimensions in each vector"** to match your embedding model:
     - `1536` - OpenAI `text-embedding-3-small`, `text-embedding-ada-002`
     - `3072` - OpenAI `text-embedding-3-large`
     - `768` - Ollama `nomic-embed-text`, Google `text-embedding-004`, Vertex AI models
     - `1024` - Ollama `mxbai-embed-large`, Bedrock `amazon.titan-embed-text-v2:0`
     - `384` - Ollama `all-minilm`

3. **Complete Graph Creation**:
   - Review settings and create the graph
   - Note the Graph Identifier (e.g., `g-123456789`)

#### ⚠️ Important Notes:

- **Cannot be modified:** Vector dimensions are set at graph creation and cannot be changed later
- **Must match embeddings:** The dimension you set MUST exactly match your embedding model's output dimension
- **Switching dimensions:** To use a different embedding dimension, you must create a new graph with the new dimension
- **Multiple graphs:** You can have multiple Neptune Analytics graphs with different dimensions for different use cases (although increased cost)

#### Example Scenarios:

**Scenario 1: Using OpenAI embeddings (1536 dimensions)**
```env
EMBEDDING_KIND=openai
EMBEDDING_MODEL=text-embedding-3-small

# Neptune Analytics graph must be created with 1536 dimensions
GRAPH_DB_CONFIG={"graph_identifier": "g-openai-1536", "region": "us-east-1"}
```

**Scenario 2: Using Ollama nomic-embed-text (768 dimensions)**
```env
EMBEDDING_KIND=ollama
EMBEDDING_MODEL=nomic-embed-text

# Neptune Analytics graph must be created with 768 dimensions
GRAPH_DB_CONFIG={"graph_identifier": "g-ollama-768", "region": "us-east-1"}
```

**Scenario 3: Switching embedding models**
- Current: Using OpenAI (1536 dims) with graph `g-openai-1536`
- Want to switch to: Ollama (768 dims)
- **Solution:** Create a NEW Neptune Analytics graph with 768 dimensions (e.g., `g-ollama-768`)
- Update your `.env` to use the new graph identifier

### Configuration in `.env`

```env
GRAPH_DB=neptune_analytics

# With explicit AWS credentials
GRAPH_DB_CONFIG={"graph_identifier": "g-123456789", "region": "us-east-1", "access_key": "YOUR_ACCESS_KEY", "secret_key": "YOUR_SECRET_KEY"}

# With AWS credentials profile
GRAPH_DB_CONFIG={"graph_identifier": "g-123456789", "region": "us-east-1", "credentials_profile_name": "my-aws-profile"}

# Using default AWS credentials (from environment variables, IAM role, etc.)
GRAPH_DB_CONFIG={"graph_identifier": "g-123456789", "region": "us-east-1"}
```


---

## Neptune Graph Explorer

Neptune Graph Explorer is a web-based tool for visualizing and querying your Neptune graphs. It's included in the Docker Compose setup for easy access.

### Setup Graph Explorer

1. **Enable Graph Explorer in Docker Compose:**
   - Edit `docker/docker-compose.yaml`
   - Uncomment the Neptune Graph Explorer section (remove the `#` comment markers)
   - The `neptune.yaml` include should be active

2. **Start the Graph Explorer:**
   ```bash
   docker-compose -f docker-compose.yaml -p flexible-graphrag up -d
   ```
   - Note: Running this command again will add any new services you've uncommented without affecting existing services

3. **Access Graph Explorer:**
   - Open your browser to: http://localhost:3007/explorer

### Configure Neptune Database Connection

1. **Click the `+` button** to add a new connection configuration

2. **Configure Neptune Database:**
   - **Graph Type:** OpenCypher - PG
   - **✓ Use Proxy Server:** `http://localhost:3007`
   - **✓ AWS IAM Auth Enabled:** (check this box)
   - **Graph Connection URL:** `https://db-neptune-1.cluster-123456abcdef.us-east-1.neptune.amazonaws.com:8182`
     - Replace with your actual Neptune Database cluster endpoint
   - **AWS Region:** `us-east-1` (or your Neptune region)
   - **Service Type:** Neptune DB

3. **Save the configuration** and connect

### Configure Neptune Analytics Connection

1. **Click the `+` button** to add a new connection configuration

2. **Configure Neptune Analytics:**
   - **Graph Type:** OpenCypher - PG
   - **✓ Use Proxy Server:** `http://localhost:3007`
   - **✓ AWS IAM Auth Enabled:** (check this box)
   - **Graph Connection URL:** `https://g-123456789.us-east-1.neptune-graph.amazonaws.com/opencypher`
     - Replace `g-123456789` with your actual Neptune Analytics graph identifier
     - Replace `us-east-1` with your Neptune region
   - **AWS Region:** `us-east-1` (or your Neptune region)
   - **Service Type:** Neptune Analytics

3. **Save the configuration** and connect

### AWS Credentials Configuration

The Graph Explorer container uses AWS credentials from the `docker/neptune.env` file:

```env
AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY
AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY
AWS_REGION=us-east-1
```

**Important Notes:**
- These credentials are for the Graph Explorer container only
- Your main application uses Neptune credentials from `flexible-graphrag/.env`
- S3 data source credentials are also in `flexible-graphrag/.env`
- This separation allows different AWS accounts/regions for different services

### Using Graph Explorer

Once connected, you can visualize and query your Neptune graph:

#### Basic Workflow

1. **Open the Graph:**
   - Select "Open Graph Explorer" from the menu
   - Choose your configured Neptune connection

2. **Run a Query:**
   - Click the **magnifying glass icon** (search/query button)
   - Enter your openCypher query in the editor
   - Click **Run** to execute

3. **View Results:**
   - **Graph view:** Interactive visualization of nodes and relationships
   - **Table view:** Tabular display of query results
   - **Both views:** Split screen showing both graph and table
   - Switch views using the view selector

4. **Manage Canvas:**
   - **Clear canvas:** Click the clear icon (circle with line through it)
   - **Add all results:** Click "Add All" to visualize all query results on the canvas
   - **Filter and explore:** Click nodes to expand relationships

#### Example Query Template

Use this query to visualize your graph (comment/uncomment lines as needed):

```cypher
// Uncomment this line to delete all data (use with caution!)
//MATCH (n) DETACH DELETE n

// View the graph structure
MATCH (n)-[r]->(m) RETURN n, r, m
```

**Tips:**
- Use `//` to comment out lines you don't want to execute
- The `DETACH DELETE` query will remove all data - use carefully!
- Limit large result sets: `MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50`

#### Additional Useful Queries

```cypher
// Count all nodes
MATCH (n) RETURN count(n) AS nodeCount

// Count all relationships
MATCH ()-[r]->() RETURN count(r) AS relationshipCount

// Get all node labels
MATCH (n)
WITH DISTINCT labels(n) AS labels
UNWIND labels AS label
RETURN DISTINCT label

// Get all relationship types
MATCH ()-[r]->()
RETURN DISTINCT type(r) AS relType

// Find specific entities by name
MATCH (n)
WHERE n.name CONTAINS 'search_term'
RETURN n

// View sample data (limited)
MATCH (n)-[r]->(m)
RETURN n, r, m
LIMIT 50
```

---

## Configuration in Flexible GraphRAG

### Full Configuration Example

**Neptune Database:**
```env
# Graph Database
GRAPH_DB=neptune
GRAPH_DB_CONFIG={"host": "db-neptune-1.cluster-123456abcdef.us-east-1.neptune.amazonaws.com", "port": 8182, "region": "us-east-1", "access_key": "YOUR_ACCESS_KEY", "secret_key": "YOUR_SECRET_KEY"}

# Enable Knowledge Graph Extraction
ENABLE_KNOWLEDGE_GRAPH=true
KG_EXTRACTOR_TYPE=schema

```

**Neptune Analytics:**
```env
# Graph Database
GRAPH_DB=neptune_analytics
GRAPH_DB_CONFIG={"graph_identifier": "g-123456789", "region": "us-east-1", "access_key": "YOUR_ACCESS_KEY", "secret_key": "YOUR_SECRET_KEY"}

# Enable Knowledge Graph Extraction
ENABLE_KNOWLEDGE_GRAPH=true
KG_EXTRACTOR_TYPE=schema

# Embedding Configuration - MUST match Neptune Analytics graph dimension!
EMBEDDING_KIND=openai
EMBEDDING_MODEL=text-embedding-3-small  # 1536 dimensions
```

---

## Troubleshooting

### Neptune Database Issues


#### 1. Connection Issues
```
Could not connect to Neptune endpoint
```

**Solution:**
- Verify network connectivity (VPC, Security Groups)
- Check if endpoint and port are correct
- Ensure IAM permissions are configured
- Test connection from your application's network

#### 2. Authentication Errors
```
Access denied or signature verification failed
```

**Solution:**
- Verify AWS credentials are correct
- Check IAM role/policy permissions
- Ensure region is correctly specified
- Try using AWS credentials profile instead of explicit keys

### Neptune Analytics Issues

#### 1. Vector Dimension Mismatch
```
Vector dimension mismatch error
```

**Solution:**
- Check your embedding model's dimension (see `.env` file `EMBEDDING_MODEL`)
- Verify Neptune Analytics graph was created with matching dimension
- If dimensions don't match: Create a new graph with correct dimension
- Cannot modify existing graph dimensions

#### 2. Graph Not Found
```
Graph identifier not found
```

**Solution:**
- Verify the graph identifier (starts with `g-`)
- Check the graph exists in the correct region
- Ensure your AWS credentials have access to the graph

#### 3. Performance Issues
```
Queries are slow or timing out
```

**Solution:**
- Neptune Analytics is optimized for analytics, not transactional workloads
- Consider using Neptune Database for frequently updated graphs
- Use separate vector database to reduce Neptune Analytics load
- Check graph size and query complexity

### General AWS Issues

#### Region Configuration
- Ensure `region` in `GRAPH_DB_CONFIG` matches where your Neptune resource is deployed
- Common regions: `us-east-1`, `us-west-2`, `eu-west-1`

#### Credential Precedence
1. Explicit credentials in `GRAPH_DB_CONFIG` (`access_key`, `secret_key`)
2. Credentials profile (`credentials_profile_name`)
3. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
4. IAM role (if running on EC2/ECS/Lambda)

---

## Additional Resources

- [Amazon Neptune Database Documentation](https://docs.aws.amazon.com/neptune/latest/userguide/intro.html)
- [Amazon Neptune Analytics Documentation](https://docs.aws.amazon.com/neptune-analytics/latest/userguide/what-is-neptune-analytics.html)
- [Neptune Pricing](https://aws.amazon.com/neptune/pricing/)
- [Flexible GraphRAG Embedding Configuration](../LLM/LLM-EMBEDDING-CONFIG.md)

---

**Last Updated:** February 2026
