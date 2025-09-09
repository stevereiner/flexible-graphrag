# Schema Configuration Examples

This document provides examples for configuring knowledge graph schemas in Flexible GraphRAG.

## 🏗️ **Schema Overview**

Schemas control how entities and relationships are extracted from your documents. You can use:
- **No schema** (`SCHEMA_NAME=none`) - Natural language extraction
- **Default schema** (`SCHEMA_NAME=default`) - Built-in comprehensive schema
- **Custom schemas** - Define your own entity types and relationships

## 📋 **Built-in Schemas**

### **Default Schema (SAMPLE_SCHEMA)**
```bash
SCHEMA_NAME=default
```

**Entities**: `PERSON`, `ORGANIZATION`, `LOCATION`, `TECHNOLOGY`, `PROJECT`, `DOCUMENT`

**Relations**: `WORKS_FOR`, `LOCATED_IN`, `USES`, `COLLABORATES_WITH`, `DEVELOPS`, `MENTIONS`

**Features**: 
- `strict: false` - Allows additional entities beyond the schema
- Best of both worlds: structured + flexible extraction

### **No Schema**
```bash
SCHEMA_NAME=none
```

**Features**:
- Uses `SimpleLLMPathExtractor` 
- Natural language entity and relationship discovery
- No constraints or validation
- Good for exploration and content analysis

## 🎨 **Custom Schema Examples**

### **Where to Put Custom Schemas**

Custom schemas are defined in your environment configuration (`.env` file). Add them to the **Schema Configuration** section. See `docs/ENVIRONMENT-CONFIGURATION.md` for complete setup details.

### **Business Schema**
```bash
SCHEMA_NAME=business
SCHEMAS=[{
  "name": "business", 
  "schema": {
    "entities": ["COMPANY", "PERSON", "PRODUCT", "MARKET"],
    "relations": ["WORKS_FOR", "COMPETES_WITH", "SELLS", "TARGETS"],
    "validation_schema": {
      "relationships": [
        ("PERSON", "WORKS_FOR", "COMPANY"),
        ("COMPANY", "COMPETES_WITH", "COMPANY"), 
        ("COMPANY", "SELLS", "PRODUCT"),
        ("PRODUCT", "TARGETS", "MARKET")
      ]
    },
    "strict": true,
    "max_triplets_per_chunk": 10
  }
}]
```

### **Scientific Research Schema**
```bash
SCHEMA_NAME=research
SCHEMAS=[{
  "name": "research",
  "schema": {
    "entities": ["RESEARCHER", "INSTITUTION", "PAPER", "EXPERIMENT", "DATASET"],
    "relations": ["AUTHORED", "AFFILIATED_WITH", "CITES", "CONDUCTED", "USES"],
    "validation_schema": {
      "relationships": [
        ("RESEARCHER", "AUTHORED", "PAPER"),
        ("RESEARCHER", "AFFILIATED_WITH", "INSTITUTION"),
        ("PAPER", "CITES", "PAPER"),
        ("RESEARCHER", "CONDUCTED", "EXPERIMENT"),
        ("EXPERIMENT", "USES", "DATASET")
      ]
    },
    "strict": false,
    "max_triplets_per_chunk": 15
  }
}]
```

### **Legal Documents Schema**
```bash
SCHEMA_NAME=legal
SCHEMAS=[{
  "name": "legal",
  "schema": {
    "entities": ["PARTY", "CONTRACT", "CLAUSE", "OBLIGATION", "DATE"],
    "relations": ["BOUND_BY", "CONTAINS", "REQUIRES", "EXPIRES_ON"],
    "validation_schema": {
      "relationships": [
        ("PARTY", "BOUND_BY", "CONTRACT"),
        ("CONTRACT", "CONTAINS", "CLAUSE"),
        ("CLAUSE", "REQUIRES", "OBLIGATION"),
        ("CONTRACT", "EXPIRES_ON", "DATE")
      ]
    },
    "strict": true,
    "max_triplets_per_chunk": 8
  }
}]
```

### **Technical Documentation Schema**
```bash
SCHEMA_NAME=technical
SCHEMAS=[{
  "name": "technical",
  "schema": {
    "entities": ["SYSTEM", "COMPONENT", "API", "DATABASE", "USER_ROLE"],
    "relations": ["CONTAINS", "CONNECTS_TO", "STORES_IN", "ACCESSED_BY"],
    "validation_schema": {
      "relationships": [
        ("SYSTEM", "CONTAINS", "COMPONENT"),
        ("COMPONENT", "CONNECTS_TO", "API"),
        ("API", "STORES_IN", "DATABASE"),
        ("SYSTEM", "ACCESSED_BY", "USER_ROLE")
      ]
    },
    "strict": false,
    "max_triplets_per_chunk": 12
  }
}]
```

## ⚙️ **Schema Configuration Parameters**

### **entities**
List of allowed entity types. Use uppercase for consistency.

### **relations** 
List of allowed relationship types. Use uppercase with underscores.

### **validation_schema**
Defines which entities can connect with which relationships:
```json
"relationships": [
  ("SOURCE_ENTITY", "RELATIONSHIP", "TARGET_ENTITY")
]
```

### **strict**
- `true`: Only extract entities/relations defined in schema
- `false`: Allow additional entities beyond schema (recommended)

### **max_triplets_per_chunk**
Maximum number of entity-relationship-entity triplets to extract per text chunk.
- Used by: `DynamicLLMPathExtractor` and `SchemaLLMPathExtractor`
- Default: 100
- Higher values: More comprehensive extraction from dense content, slower processing
- Lower values: Faster processing, may miss entities in complex documents

### **max_paths_per_chunk**
Maximum number of relationship paths to extract per text chunk.
- Used by: `SimpleLLMPathExtractor`
- Default: 100
- Higher values: More comprehensive relationship extraction, slower processing
- Lower values: Faster processing, may miss relationships in complex documents

## 💡 **Best Practices**

### **Schema Design**
1. **Start simple** - Begin with 3-5 entity types
2. **Use clear names** - Avoid ambiguous entity labels
3. **Plan relationships** - Think about how entities connect
4. **Consider domain** - Tailor to your specific content type

### **Configuration Tips**
1. **Use strict=false** for better coverage
2. **Adjust extraction limits** based on document complexity:
   - Dense content (technical docs, research papers): `MAX_TRIPLETS_PER_CHUNK=100`, `MAX_PATHS_PER_CHUNK=100`
   - Simple content (news articles, basic docs): `MAX_TRIPLETS_PER_CHUNK=20`, `MAX_PATHS_PER_CHUNK=20`
   - Very complex content (legal docs, scientific papers): `MAX_TRIPLETS_PER_CHUNK=200`, `MAX_PATHS_PER_CHUNK=200`
3. **Test with small samples** before processing large datasets
4. **Compare with default schema** to see extraction differences
5. **Monitor processing time** - higher limits increase extraction quality but slow processing

### **Performance Considerations**
- **Complex schemas** may slow extraction
- **Too many entity types** can confuse the LLM
- **Simple schemas** often produce better results
- **Domain-specific schemas** outperform generic ones

## 🔄 **Schema Switching**

You can easily switch between schemas by changing the `SCHEMA_NAME`:

```bash
# Use built-in comprehensive schema
SCHEMA_NAME=default

# Use natural extraction  
SCHEMA_NAME=none

# Use your custom business schema
SCHEMA_NAME=business
```

This allows you to test different extraction approaches on the same content and choose the best fit for your use case.

## 📚 **Related Documentation**

- **Environment setup**: `docs/ENVIRONMENT-CONFIGURATION.md` - Complete configuration guide
- **Source paths**: `docs/SOURCE-PATH-EXAMPLES.md` - File path configuration  
- **Timeout settings**: `docs/TIMEOUT-CONFIGURATIONS.md` - Performance tuning
- **Neo4j setup**: `docs/Neo4j-URLs.md` - Database connection details
