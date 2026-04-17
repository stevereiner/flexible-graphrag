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

Before creating any schema, always select your space using the **"Please select Graph Space"** dropdown/combobox in Nebula Studio interface.

**Important**: Do NOT use `USE flexible_graphrag;` in the console - Nebula Studio shows a warning: "DO NOT switch between graph spaces with nGQL statements in the console." Always use the dropdown selector instead.

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
    `last_modified_date` STRING,
    `alfresco_id` STRING,
    `stable_file_path` STRING,
    `content_type` STRING,
    `modified_at` STRING
);
```

**Note**: The last 4 properties (`alfresco_id`, `stable_file_path`, `content_type`, `modified_at`) are specific to Alfresco data sources. Include them if you plan to use Alfresco, or omit them if only using file uploads.

### Alternative: Add Missing Columns

If the tag exists but is missing columns, add them:

```nGQL
-- Add basic required columns
ALTER TAG Props__ ADD (`source` STRING, `conversion_method` STRING);

-- Add Alfresco-specific columns (if using Alfresco data source)
ALTER TAG Props__ ADD (
    `alfresco_id` STRING,
    `stable_file_path` STRING,
    `content_type` STRING,
    `modified_at` STRING
);
```

### Verify Props__ Schema
```nGQL
DESCRIBE TAG Props__;
```

Expected output should include all columns:
- **Basic properties**: `source`, `conversion_method`, `file_type`, `file_name`
- **Node properties**: `_node_content`, `_node_type`, `document_id`, `doc_id`, `ref_doc_id`
- **File properties**: `triplet_source_id`, `file_path`, `file_size`, `creation_date`, `last_modified_date`
- **Alfresco properties** (if using Alfresco): `alfresco_id`, `stable_file_path`, `content_type`, `modified_at`

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
    `ref_doc_id` STRING,
    `alfresco_id` STRING,
    `stable_file_path` STRING,
    `content_type` STRING,
    `modified_at` STRING
);
```

**Note**: The last 4 properties are specific to Alfresco data sources. Include them if you plan to use Alfresco.

### Alternative: Add Missing Columns

If the edge exists but is missing columns, add them:

```nGQL
-- Add basic required columns
ALTER EDGE Relation__ ADD (`source` STRING, `conversion_method` STRING);

-- Add Alfresco-specific columns (if using Alfresco data source)
ALTER EDGE Relation__ ADD (
    `alfresco_id` STRING,
    `stable_file_path` STRING,
    `content_type` STRING,
    `modified_at` STRING
);
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

4. **"Unknown column 'alfresco_id' (or other property) in schema" Error**
   - Different data sources add their own metadata properties
   - **Quick fix**: Add the missing column(s):
   ```nGQL
   ALTER TAG Props__ ADD (`alfresco_id` STRING);
   ALTER EDGE Relation__ ADD (`alfresco_id` STRING);
   ```
   - **Common data source properties**:
     - Alfresco: `alfresco_id`, `stable_file_path`, `content_type`, `modified_at`, `node_id`
     - S3: `bucket_name`, `prefix`, `region`, `s3_key`, `s3_uri`, `etag`
     - Box: `folder_id`, `box_file_id`, `path_collection`
     - OneDrive/SharePoint: `user_principal_name`, `client_id`, `tenant_id`, `site_name`, `site_id`, `folder_id`, `human_file_path`, `last_modified_datetime`
     - Google Drive: `query` (note: GDrive uses spaces in property names like `file id`, `file path`, `modified at`)
     - GCS: `bucket`, `project_id`
     - Azure Blob: `container_name`, `account_name`
   - Add only the properties you need for your specific data sources

5. **"Space was not chosen" Error**
   - Select `flexible_graphrag` from the "Please select Graph Space" dropdown before schema operations
   - Do NOT use `USE flexible_graphrag;` in the console

### Verification Commands

**Note**: First select `flexible_graphrag` from the "Please select Graph Space" dropdown, then run:

```nGQL
-- Check overall system status
SHOW HOSTS;
SHOW SPACES;

-- Verify schema (make sure space is selected in dropdown first!)
DESCRIBE TAG Props__;
DESCRIBE EDGE Relation__;

-- Check data (after processing)
MATCH (v) RETURN count(v) AS vertex_count;
MATCH ()-[e]->() RETURN count(e) AS edge_count;
```

## NebulaGraph Studio Navigation

1. **Access Studio**: http://localhost:7001
2. **Connect**: Use host `nebula-graphd`, port `9669`, username `root`, password `nebula`
   - **Important**: Use `nebula-graphd` (not `localhost`) because Studio runs inside Docker
3. **Select Space**: Use the **"Please select Graph Space"** dropdown/combobox to select `flexible_graphrag`
   - **Do NOT** use `USE flexible_graphrag;` in the console - always use the dropdown selector
4. **Run Queries**: Use the console to execute nGQL commands

## Visualizing Your Knowledge Graph

After processing documents, you can visualize the knowledge graph in Nebula Studio:

1. In the console, run:
   ```nGQL
   MATCH ()-[e]->() RETURN *;
   ```
2. Switch the result panel from **"Table"** view to **"Graph"** view
3. Explore the interactive graph visualization showing entities and their relationships

**Tip**: For large graphs, you may want to limit results:
```nGQL
MATCH ()-[e]->() RETURN * LIMIT 50;
```

## Next Steps

Once NebulaGraph is working:
- Explore the knowledge graph using NebulaGraph Studio
- Query entities and relationships
- Visualize the graph structure using the Graph view
- Test search and Q&A functionality

## Success Indicators

✅ Storage hosts registered and ONLINE  
✅ Space created with FIXED_STRING(256) vid_type  
✅ Props__ tag has all required columns including `source` and `conversion_method`  
✅ Relation__ edge has all required columns including `source` and `conversion_method`  
✅ Document processing completes without schema errors  
✅ Vertices and edges successfully created in the graph  

## Appendix: Comprehensive Schema for All Data Sources

If you plan to use multiple data sources, you can create a comprehensive schema with all possible properties upfront:

```nGQL
-- Comprehensive Props__ tag with all data source properties
CREATE TAG Props__(
    -- Basic properties (all sources)
    `source` STRING,
    `conversion_method` STRING,
    `file_type` STRING,
    `file_name` STRING,
    `file_path` STRING,
    `file_size` INT,
    `source_type` STRING,
    
    -- Node properties (LlamaIndex)
    `_node_content` STRING,
    `_node_type` STRING,
    `document_id` STRING,
    `doc_id` STRING,
    `ref_doc_id` STRING,
    `triplet_source_id` STRING,
    
    -- Timestamp properties (various formats)
    `creation_date` STRING,
    `last_modified_date` STRING,
    `modified_at` STRING,
    `last_modified_datetime` STRING,
    
    -- Alfresco properties
    `alfresco_id` STRING,
    `node_id` STRING,
    `content_type` STRING,
    `stable_file_path` STRING,
    `human_file_path` STRING,
    
    -- S3 properties
    `bucket_name` STRING,
    `prefix` STRING,
    `region` STRING,
    `s3_key` STRING,
    `s3_uri` STRING,
    `etag` STRING,
    
    -- Box properties
    `folder_id` STRING,
    `box_file_id` STRING,
    `path_collection` STRING,
    
    -- OneDrive/SharePoint properties
    `user_principal_name` STRING,
    `client_id` STRING,
    `tenant_id` STRING,
    `site_name` STRING,
    `site_id` STRING,
    
    -- GCS properties
    `bucket` STRING,
    `project_id` STRING,
    
    -- Azure Blob properties
    `container_name` STRING,
    `account_name` STRING,
    
    -- Google Drive properties (note: GDrive uses spaces in some property names)
    `query` STRING
);

-- Comprehensive Relation__ edge with all data source properties
CREATE EDGE Relation__(
    -- Edge label
    `label` STRING,
    
    -- Basic properties (all sources)
    `source` STRING,
    `conversion_method` STRING,
    `file_type` STRING,
    `file_name` STRING,
    `file_path` STRING,
    `file_size` INT,
    `source_type` STRING,
    
    -- Node properties (LlamaIndex)
    `_node_content` STRING,
    `_node_type` STRING,
    `document_id` STRING,
    `doc_id` STRING,
    `ref_doc_id` STRING,
    `triplet_source_id` STRING,
    
    -- Timestamp properties
    `creation_date` STRING,
    `last_modified_date` STRING,
    `modified_at` STRING,
    `last_modified_datetime` STRING,
    
    -- Data source specific properties (same as Props__)
    `alfresco_id` STRING,
    `node_id` STRING,
    `content_type` STRING,
    `stable_file_path` STRING,
    `human_file_path` STRING,
    `bucket_name` STRING,
    `prefix` STRING,
    `region` STRING,
    `s3_key` STRING,
    `s3_uri` STRING,
    `etag` STRING,
    `folder_id` STRING,
    `box_file_id` STRING,
    `path_collection` STRING,
    `user_principal_name` STRING,
    `client_id` STRING,
    `tenant_id` STRING,
    `site_name` STRING,
    `site_id` STRING,
    `bucket` STRING,
    `project_id` STRING,
    `container_name` STRING,
    `account_name` STRING,
    `query` STRING
);
```

**Pros**: Works with all data sources without schema errors  
**Cons**: Creates many unused properties if you only use one or two data sources

**Recommendation**: Start with the minimal schema and add properties as needed based on the data sources you actually use.  

---

**Note**: This setup process addresses the specific schema requirements for LlamaIndex integration with NebulaGraph. The manual schema creation is necessary because LlamaIndex's automatic schema creation doesn't always include all required properties.
