# Schema Configuration Examples

This document provides examples for configuring knowledge graph schemas in Flexible GraphRAG.

## 🏗️ **Schema Overview**

Schemas control how entities and relationships are extracted from your documents. You can use:
- **Internal schema** (`SCHEMA_NAME=default` + `KG_EXTRACTOR_TYPE=schema`) - LlamaIndex built-in schema (recommended)
- **Sample schema** (`SCHEMA_NAME=sample`) - Project's SAMPLE_SCHEMA
- **Custom schemas** - Define your own entity types and relationships

**📖 For detailed information about extractors and internal schema, see: `docs/KNOWLEDGE-GRAPH-EXTRACTORS.md`**

## 📋 **Built-in Schemas**

### **Internal Schema (Recommended)**
```bash
SCHEMA_NAME=default
KG_EXTRACTOR_TYPE=schema
```

**Features**:
- Uses LlamaIndex's built-in comprehensive schema
- 10 entity types: PRODUCT, MARKET, TECHNOLOGY, EVENT, CONCEPT, ORGANIZATION, PERSON, LOCATION, TIME, MISCELLANEOUS
- 10 relationship types: USED_BY, USED_FOR, LOCATED_IN, PART_OF, WORKED_ON, HAS, IS_A, BORN_IN, DIED_IN, HAS_ALIAS
- 27 validation rules for consistent extraction
- Excellent type labeling for business/technology content
- **Recommended for most projects**

**📖 See `docs/KNOWLEDGE-GRAPH-EXTRACTORS.md` for complete internal schema details**

---

### **Sample Schema (SAMPLE_SCHEMA)**
```bash
SCHEMA_NAME=sample
```

**Entities**: `PERSON`, `ORGANIZATION`, `LOCATION`, `TECHNOLOGY`, `PROJECT`, `DOCUMENT`

**Relations**: `WORKS_FOR`, `LOCATED_IN`, `USES`, `COLLABORATES_WITH`, `DEVELOPS`, `MENTIONS`

**Features**: 
- `strict: false` - Allows additional entities beyond the schema
- Best of both worlds: structured + flexible extraction

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
- `true`: Only extract entities/relations defined in schema (hard constraint)
- `false`: Allow additional entities beyond schema (guidance, **recommended**)

**Impact:**
- **`strict: false`** (Recommended):
  - Schema provides guidance, LLM can discover additional types
  - More flexible and comprehensive extraction
  - May extract: "PERSON", "ORG", plus "LOCATION", "EVENT" (not in schema)
  - Best for: General use, when schema may not cover all possibilities
  
- **`strict: true`** (Restrictive):
  - Schema enforces hard constraints, LLM cannot go beyond schema
  - Only extracts exactly what's defined
  - Ignores entities/relationships not in schema
  - Best for: Compliance, legal, highly controlled domains

**Example:**
```bash
# Flexible extraction (recommended)
"strict": false  # ← Can extract beyond schema

# Strict extraction (controlled)
"strict": true   # ← Only extracts schema-defined types
```

**See `docs/KNOWLEDGE-GRAPH-EXTRACTORS.md` for detailed strict mode comparison**

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
2. **Adjust extraction limits** based on document complexity (default: 20/20):
   - Standard content (most documents): `MAX_TRIPLETS_PER_CHUNK=20`, `MAX_PATHS_PER_CHUNK=20` **(default)**
   - Dense content (technical docs, research papers): `MAX_TRIPLETS_PER_CHUNK=50`, `MAX_PATHS_PER_CHUNK=50`
   - Very complex content (legal docs, scientific papers): `MAX_TRIPLETS_PER_CHUNK=100`, `MAX_PATHS_PER_CHUNK=100`
3. **Test with small samples** before processing large datasets
4. **Compare with default schema** to see extraction differences
5. **Monitor processing time** - higher limits increase extraction quality but slow processing

### **Performance Considerations**
- **Complex schemas** may slow extraction
- **Too many entity types** can confuse the LLM
- **Simple schemas** often produce better results
- **Domain-specific schemas** outperform generic ones

## 🔄 **Schema Switching**

You can easily switch between schemas by changing the `SCHEMA_NAME` and `KG_EXTRACTOR_TYPE`:

```bash
# Use LlamaIndex internal schema (recommended for most projects)
SCHEMA_NAME=default
KG_EXTRACTOR_TYPE=schema

# Use project sample schema
SCHEMA_NAME=sample
KG_EXTRACTOR_TYPE=schema

# Use simple extraction (fastest, less structured)
KG_EXTRACTOR_TYPE=simple

# Use your custom business schema
SCHEMA_NAME=business
KG_EXTRACTOR_TYPE=schema
```

This allows you to test different extraction approaches on the same content and choose the best fit for your use case.

**📖 For extractor comparison and recommendations, see: `docs/KNOWLEDGE-GRAPH-EXTRACTORS.md`**

## 📚 **Related Documentation**

- **Extractor Guide**: `docs/KNOWLEDGE-GRAPH-EXTRACTORS.md` - Comprehensive extractor types and internal schema details
- **Environment setup**: `docs/ENVIRONMENT-CONFIGURATION.md` - Complete configuration guide
- **LLM Testing**: `docs/LLM-TESTING-RESULTS.md` - Provider compatibility with extractors
- **Source paths**: `docs/SOURCE-PATH-EXAMPLES.md` - File path configuration  
- **Timeout settings**: `docs/TIMEOUT-CONFIGURATIONS.md` - Performance tuning
- **Neo4j setup**: `docs/Neo4j-URLs.md` - Database connection details
