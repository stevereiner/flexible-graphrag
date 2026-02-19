# Neo4j Setup and Configuration Guide

This guide covers Neo4j-specific setup, configuration, and management for the Flexible GraphRAG system.

## Neo4j Database Requirements

**Neo4j Server Versions Supported:**
- Neo4j >= 2025.01
- Neo4j >= 5.18.1

**You can use:**
- Neo4j Enterprise Edition (Self Hosted)
- Neo4j Community Edition (Free, Self hosted)
- Neo4j Desktop (Free, Windows, Mac, Linux)
- Neo4j AuraDB (free, professional, mission critical tiers) + Graph Analytics Serverless
- Neo4j AuraDS

## Required Neo4j Plugins

### APOC Core is Required

**Neo4j Desktop**: 
- Install APOC core plugin (expand side panel)
- Restart Neo4j

**Neo4j Enterprise**: 
- Copy APOC core jar from /product to /plugins dir
- Restart Neo4j

**Neo4j Community**: 
- Download APOC core and copy to /plugins dir
- Restart Neo4j

**Neo4j AuraDB/AuraDS**: 
- Have subset of APOC core with required features

### GDS (Graph Data Science) is Required

**Neo4j Desktop**: 
- Install GDS plugin (expand side panel)
- Restart Neo4j

**Neo4j Enterprise**: 
- Copy GDS jar from /labs to /plugins dir
- Restart Neo4j

**Neo4j Community**: 
- Download GDS jar and copy to /plugins dir
- Restart Neo4j

**Neo4j AuraDB**: 
- Requires Neo4j Graph Analytics Serverless or Neo4j AuraDS

**Neo4j AuraDS**: 
- Includes GDS

## Neo4j Configuration

Add these settings to your `.env` file:

```env
# Neo4j Configuration
NEO4J_URI=neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password
```

## Neo4j Console Commands

### Viewing Data
```cypher
// View limited nodes
MATCH (n) RETURN n LIMIT 25

// View all nodes
MATCH (n) RETURN n

// Show all indexes
SHOW INDEXES
```

### Cleanup Commands for LlamaIndex (for testing)
**⚠️ Warning: These commands will delete data. Use only on test databases.**

```cypher
// 1. Delete all nodes and relationships
MATCH (n) DETACH DELETE n

// 2. Verify deletion
MATCH (n) RETURN n

// 3. Drop LlamaIndex indexes
DROP INDEX hybrid_search_vector IF EXISTS;
DROP INDEX entity IF EXISTS;

// 4. Drop LlamaIndex constraints  
// Entity and Node constraints for faster retrieval
DROP CONSTRAINT constraint_907a464e IF EXISTS;  // __Entity__ id constraint
DROP CONSTRAINT constraint_ec67c859 IF EXISTS;  // __Node__ id constraint

// 5. Show remaining indexes and constraints
SHOW INDEXES
SHOW CONSTRAINTS

// 6. Optional: Reset database completely (requires restart)
// STOP DATABASE neo4j
// DROP DATABASE neo4j IF EXISTS  
// CREATE DATABASE neo4j
```

### **🔍 LlamaIndex Database Structure**

**Node Labels:**
- `__Entity__` - Entities with ID constraints  
- `__Node__` - Nodes with ID constraints
- `Chunk` - Text chunks with vector embeddings
- Domain-specific entity types (PERSON, ORGANIZATION, etc.)

**Indexes:**
- `vector` - Vector index on `Chunk.embedding` property (VECTOR type)
- `entity` - Entity index for faster entity lookups

**Constraints:**
- `constraint_907a464e` - RANGE constraint on `__Entity__.id`
- `constraint_ec67c859` - RANGE constraint on `__Node__.id`

**Relationships:**
- `MENTIONS` - Between text chunks and entities
- Domain-specific relationships between entities

## API Endpoints (Neo4j-specific)

### Graph Data
- `GET /api/graph` - Get graph data (nodes and relationships)

### System Info
- `GET /api/python-info` - Get Python environment information

## File Structure (Neo4j-specific)

- `neo4j_util.py` - Neo4j database and GraphRAG utilities
- `factories.py` - Includes Neo4j database factory
- `hybrid_system.py` - Neo4j integration for vector and graph storage

## Development Notes

- The system builds knowledge graphs using Neo4j's capabilities
- Both vector search and graph-based search are supported
- For production use, configure proper security and authentication
- Between tests use the LlamaIndex cleanup commands above to reset the database 
- Use on a test Neo4j database no one else is using

## Troubleshooting

1. **Neo4j Connection**: Ensure Neo4j is running on bolt://localhost:7687
2. **Missing Plugins**: Verify APOC and GDS plugins are installed and active
3. **Memory**: Large graphs may require increased Neo4j memory settings
4. **Authentication**: Check Neo4j credentials in .env file