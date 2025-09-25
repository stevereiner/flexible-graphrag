# NebulaGraph Setup Guide for Flexible GraphRAG

This guide covers the complete setup process for integrating NebulaGraph with Flexible GraphRAG, including all the manual schema configuration steps required.

## Prerequisites

- NebulaGraph services running via Docker Compose
- NebulaGraph Studio accessible at http://localhost:7001
- Basic understanding of nGQL (NebulaGraph Query Language)

## Step 1: Register Storage Hosts

First, you need to register the storage hosts with the NebulaGraph cluster.

### Check Current Hosts
```nGQL
SHOW HOSTS;
```

If no hosts are registered or storage hosts are missing, add them:

### Add Storage Hosts
```nGQL
ADD HOSTS "nebula-storaged":9779;
```

Or if using IP address:
```nGQL
ADD HOSTS "172.20.0.10":9779;
```

### Verify Hosts Registration
```nGQL
SHOW HOSTS;
```

Expected output should show:
```
nebula-storaged	9779	ONLINE	1	flexible_graphrag:1	flexible_graphrag:1	3.6.0
```

## Step 2: Create Graph Space

### Check Existing Spaces
```nGQL
SHOW SPACES;
```

### Create the Flexible GraphRAG Space
```nGQL
CREATE SPACE IF NOT EXISTS flexible_graphrag(vid_type=FIXED_STRING(256));
```

**Important Notes:**
- Use `FIXED_STRING(256)` as recommended by LlamaIndex documentation
- This allows for longer UUID identifiers that LlamaIndex generates

### Verify Space Creation
```nGQL
SHOW SPACES;
DESCRIBE SPACE flexible_graphrag;
```

## Step 3: Select the Working Space

Before creating any schema, always select your space:

```nGQL
USE flexible_graphrag;
```

## Step 4: Configure Vertex Schema (Props__ Tag)

### Check Current Props__ Schema
```nGQL
DESCRIBE TAG Props__;
```

### Create or Update Props__ Tag

If the tag doesn't exist or is missing required columns, create it:

```nGQL
CREATE TAG Props__(
    `source` STRING,
    `conversion_method` STRING,
    `file_type` STRING,
    `file_name` STRING,
    `_node_content` STRING,
    `_node_type` STRING,
    `document_id` STRING,
    `doc_id` STRING,
    `ref_doc_id` STRING,
    `triplet_source_id` STRING,
    `file_path` STRING,
    `file_size` INT,
    `creation_date` STRING,
    `last_modified_date` STRING
);
```

### Alternative: Add Missing Columns
If the tag exists but is missing `source` and `conversion_method`:

```nGQL
ALTER TAG Props__ ADD (`source` STRING, `conversion_method` STRING);
```

### Verify Props__ Schema
```nGQL
DESCRIBE TAG Props__;
```

Expected output should include all columns:
- `source`, `conversion_method`, `file_type`, `file_name`
- `_node_content`, `_node_type`, `document_id`, `doc_id`, `ref_doc_id`
- `triplet_source_id`, `file_path`, `file_size`, `creation_date`, `last_modified_date`

## Step 5: Configure Edge Schema (Relation__ Edge)

### Check Current Relation__ Schema
```nGQL
DESCRIBE EDGE Relation__;
```

### Create or Update Relation__ Edge

If the edge doesn't exist or is missing required columns, create it:

```nGQL
CREATE EDGE Relation__(
    `label` STRING,
    `source` STRING,
    `conversion_method` STRING,
    `file_type` STRING,
    `file_name` STRING,
    `triplet_source_id` STRING,
    `file_path` STRING,
    `file_size` INT,
    `creation_date` STRING,
    `last_modified_date` STRING,
    `_node_content` STRING,
    `_node_type` STRING,
    `document_id` STRING,
    `doc_id` STRING,
    `ref_doc_id` STRING
);
```

### Alternative: Add Missing Columns
If the edge exists but is missing `source` and `conversion_method`:

```nGQL
ALTER EDGE Relation__ ADD (`source` STRING, `conversion_method` STRING);
```

### Verify Relation__ Schema
```nGQL
DESCRIBE EDGE Relation__;
```

## Step 6: Configure Flexible GraphRAG

Update your `.env` file with NebulaGraph configuration:

```env
GRAPH_DB=nebula
GRAPH_DB_CONFIG={"space_name": "flexible_graphrag", "address": "localhost", "port": 9669, "username": "root", "password": "nebula"}
```

Alternative configuration formats:
```env
# Using space parameter
GRAPH_DB_CONFIG={"space": "flexible_graphrag", "overwrite": true, "address": "localhost", "port": 9669, "username": "root", "password": "nebula"}

# Using URL format
GRAPH_DB_CONFIG={"space": "flexible_graphrag", "overwrite": true, "url": "nebula://localhost:9669", "username": "root", "password": "nebula"}
```

## Step 7: Test the Integration

Run your Flexible GraphRAG application to test the integration. You should see successful document processing with output like:

```
✅ Processing completed successfully
✅ Created 15 vertices and 14 edges
✅ Knowledge graph stored in NebulaGraph
```

## Troubleshooting

### Common Issues

1. **"SpaceNotFound" Error**
   - Ensure the space is created: `CREATE SPACE flexible_graphrag(...)`
   - Verify space exists: `SHOW SPACES;`

2. **"Host not enough" Error**
   - Register storage hosts: `ADD HOSTS "nebula-storaged":9779;`
   - Check host status: `SHOW HOSTS;`

3. **"Unknown column 'source' in schema" Error**
   - Add missing columns to Props__ tag and Relation__ edge
   - Use the ALTER commands provided above

4. **"Space was not chosen" Error**
   - Always run `USE flexible_graphrag;` before schema operations

### Verification Commands

```nGQL
-- Check overall system status
SHOW HOSTS;
SHOW SPACES;

-- Select working space
USE flexible_graphrag;

-- Verify schema
DESCRIBE TAG Props__;
DESCRIBE EDGE Relation__;

-- Check data (after processing)
MATCH (v) RETURN count(v) AS vertex_count;
MATCH ()-[e]->() RETURN count(e) AS edge_count;
```

## NebulaGraph Studio Navigation

1. **Access Studio**: http://localhost:7001
2. **Connect**: Use host `localhost:9669`, username `root`, password `nebula`
3. **Select Space**: Use the dropdown in NebulaGraph Studio to select `flexible_graphrag`
4. **Run Queries**: Use the console to execute nGQL commands

## Next Steps

Once NebulaGraph is working:
- Explore the knowledge graph using NebulaGraph Studio
- Query entities and relationships
- Visualize the graph structure
- Test search and Q&A functionality

## Success Indicators

✅ Storage hosts registered and ONLINE  
✅ Space created with FIXED_STRING(256) vid_type  
✅ Props__ tag has all required columns including `source` and `conversion_method`  
✅ Relation__ edge has all required columns including `source` and `conversion_method`  
✅ Document processing completes without schema errors  
✅ Vertices and edges successfully created in the graph  

---

**Note**: This setup process addresses the specific schema requirements for LlamaIndex integration with NebulaGraph. The manual schema creation is necessary because LlamaIndex's automatic schema creation doesn't always include all required properties.
