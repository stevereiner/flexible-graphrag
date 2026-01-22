# Knowledge Graph Extractors Guide

This document explains the different knowledge graph extractors available in Flexible GraphRAG and how to configure them.

## 📊 **Overview**

Flexible GraphRAG supports three different extraction methods, each optimized for different use cases:

1. **SimpleLLMPathExtractor** - Fast, flexible relationship extraction
2. **SchemaLLMPathExtractor** - Schema-guided structured extraction (with internal or custom schema)
3. **DynamicLLMPathExtractor** - Adaptive schema with flexible type discovery

## ⚙️ **Extractor Configuration**

Set the extractor type using the `KG_EXTRACTOR_TYPE` environment variable:

```bash
# Schema-based extraction (default, recommended)
KG_EXTRACTOR_TYPE=schema

# Simple path extraction (fastest)
KG_EXTRACTOR_TYPE=simple

# Dynamic extraction (most flexible)
KG_EXTRACTOR_TYPE=dynamic
```

## 🔧 **Extractor Types**

### **1. SimpleLLMPathExtractor**

**Configuration:**
```bash
KG_EXTRACTOR_TYPE=simple
```

**Characteristics:**
- **Fastest** extraction method
- No schema constraints or validation
- Discovers entities and relationships naturally from text
- Best for: Quick exploration, unstructured content analysis

**Use Cases:**
- Rapid prototyping and testing
- Exploratory data analysis
- When you don't know the domain structure yet
- Processing diverse, unstructured content

**Performance:**
- ⚡ Fastest processing time
- 🔓 No schema overhead
- 🎯 Good for general-purpose extraction

---

### **2. SchemaLLMPathExtractor**

**Configuration:**
```bash
KG_EXTRACTOR_TYPE=schema
SCHEMA_NAME=default     # Use internal schema (LlamaIndex builtin)
# OR
SCHEMA_NAME=sample      # Use project's SAMPLE_SCHEMA
# OR  
SCHEMA_NAME=custom_name # Use your custom schema
```

**Characteristics:**
- **Structured** extraction with validation
- Can use **internal schema**, **default schema**, or **custom schema**
- Produces consistent, well-labeled entities and relationships
- Best for: Production systems, domain-specific extraction
- **Default** extractor type

#### **Internal Schema (Recommended for Most Use Cases)**

When you set `SCHEMA_NAME=default`, the extractor uses LlamaIndex's built-in internal schema:

**10 Entity Types:**
- `PRODUCT` - Products, services, offerings
- `MARKET` - Markets, industries, sectors
- `TECHNOLOGY` - Technologies, tools, frameworks
- `EVENT` - Events, incidents, milestones
- `CONCEPT` - Concepts, ideas, theories
- `ORGANIZATION` - Companies, institutions, groups
- `PERSON` - People, individuals, names
- `LOCATION` - Places, addresses, geographic entities
- `TIME` - Dates, times, periods
- `MISCELLANEOUS` - Anything that doesn't fit above

**10 Relationship Types:**
- `USED_BY` - Entity is used by another
- `USED_FOR` - Entity is used for a purpose
- `LOCATED_IN` - Entity is located in a place
- `PART_OF` - Entity is part of another
- `WORKED_ON` - Person/org worked on something
- `HAS` - Entity has/owns another
- `IS_A` - Entity is a type of another
- `BORN_IN` - Person born in location/time
- `DIED_IN` - Person died in location/time
- `HAS_ALIAS` - Entity has alternative name

**27 Validation Rules (Triplet Patterns):**
```
(PRODUCT, USED_BY, PRODUCT)
(PRODUCT, USED_FOR, MARKET)
(PRODUCT, HAS, TECHNOLOGY)
(MARKET, LOCATED_IN, LOCATION)
(MARKET, HAS, TECHNOLOGY)
(TECHNOLOGY, USED_BY, PRODUCT)
(TECHNOLOGY, USED_FOR, MARKET)
(TECHNOLOGY, LOCATED_IN, LOCATION)
(TECHNOLOGY, PART_OF, ORGANIZATION)
(TECHNOLOGY, IS_A, PRODUCT)
(EVENT, LOCATED_IN, LOCATION)
(EVENT, PART_OF, ORGANIZATION)
(CONCEPT, USED_BY, TECHNOLOGY)
(CONCEPT, USED_FOR, PRODUCT)
(ORGANIZATION, LOCATED_IN, LOCATION)
(ORGANIZATION, PART_OF, ORGANIZATION)
(ORGANIZATION, PART_OF, MARKET)
(PERSON, BORN_IN, LOCATION)
(PERSON, BORN_IN, TIME)
(PERSON, DIED_IN, LOCATION)
(PERSON, DIED_IN, TIME)
(PERSON, WORKED_ON, EVENT)
(PERSON, WORKED_ON, PRODUCT)
(PERSON, WORKED_ON, CONCEPT)
(PERSON, WORKED_ON, TECHNOLOGY)
(LOCATION, LOCATED_IN, LOCATION)
(LOCATION, PART_OF, LOCATION)
```

**Example Results with Internal Schema:**
```
Entities: 37 total
- ORGANIZATION (7)
- TECHNOLOGY (10)
- CONCEPT (2)
- EVENT (2)
- PERSON (1)
- PRODUCT (5)
- MARKET (3)
- Others (7)

Relationships: 65 total
- MENTIONS (35)
- HAS (6)
- USED_FOR (7)
- PART_OF (1)
- WORKED_ON (3)
- IS_A (1)
- Others (12)
```

**Use Cases:**
- General business/technology documents
- When you don't want to define a custom schema
- Flexible extraction with good type labeling
- **Recommended starting point** for most projects

---

### **3. DynamicLLMPathExtractor**

**Configuration:**
```bash
KG_EXTRACTOR_TYPE=dynamic
SCHEMA_NAME=sample   # Optional: provide initial guidance
# OR
SCHEMA_NAME=default  # No initial guidance (uses internal schema)
```

**Characteristics:**
- **Adaptive** schema that evolves with content
- Discovers new entity and relationship types dynamically
- Can start with schema guidance or completely free-form
- Best for: Evolving domains, multi-domain content
- **Note:** May create only text chunks with Ollama LLM

**Use Cases:**
- Content spanning multiple domains
- When schema needs to evolve over time
- Research and discovery projects
- Cross-domain knowledge extraction

**Performance:**
- 🧠 Most intelligent extraction
- 🔄 Adaptive to content
- ⏱️ Moderate processing time
- ⚠️ May be inconsistent with Ollama

---

## 🎯 **Choosing the Right Extractor**

### **Quick Decision Guide**

**1. Do you want the fastest extraction?**
- ✅ **YES** → Use `KG_EXTRACTOR_TYPE=simple`
  - Fastest processing
  - More extensive extraction (discovers everything naturally)
  - Entity type labels are basic (not well-categorized)
  - Good for: Testing, exploration, rapid prototyping

**2. Is the built-in schema good enough for your content?**
- ✅ **YES** → Use `KG_EXTRACTOR_TYPE=schema` + `SCHEMA_NAME=default` ✅ **RECOMMENDED**
  - Uses LlamaIndex's internal schema (10 entity types, 10 relationship types)
  - Excellent type labeling for business/technology content
  - No configuration needed
  - Good for: Most projects, general business/tech documents

**3. Is the project's sample schema good enough?**
- ✅ **YES** → Use `KG_EXTRACTOR_TYPE=schema` + `SCHEMA_NAME=sample`
  - Uses project's SAMPLE_SCHEMA (6 entity types, 10 relationship types)
  - Good type labeling for general content
  - No configuration needed
  - Good for: General-purpose projects

**4. Do you need a custom schema for your specific domain?**
- ✅ **YES** → Use `KG_EXTRACTOR_TYPE=schema` + `SCHEMA_NAME=your_custom_name`
  - Define your schema in the config file (`.env` → `SCHEMAS=[...]`)
  - Tailored entity and relationship types for your domain
  - Use `strict: false` for flexible extraction (recommended)
  - Use `strict: true` only for compliance/legal requirements
  - Good for: Domain-specific projects, production systems

**5. Do you need adaptive, multi-domain extraction?**
- ✅ **YES** → Use `KG_EXTRACTOR_TYPE=dynamic`
  - Discovers and adapts entity types as it processes content
  - Most flexible, but may be inconsistent
  - Good for: Research, cross-domain content

---

## 🚀 **Recommended Configurations**

### **For Most Projects (Recommended)**
```bash
KG_EXTRACTOR_TYPE=schema
SCHEMA_NAME=default
MAX_TRIPLETS_PER_CHUNK=20
```
✅ Uses internal schema with excellent type coverage
✅ No schema definition needed
✅ Great balance of speed and quality

### **For Domain-Specific Projects**

**Flexible Domain Extraction (Recommended)**
```bash
KG_EXTRACTOR_TYPE=schema
SCHEMA_NAME=your_custom_schema
MAX_TRIPLETS_PER_CHUNK=20
SCHEMAS=[{
  "name": "your_custom_schema",
  "schema": {
    "entities": [...],
    "relations": [...],
    "strict": false  # ← Allows discovery beyond schema
  }
}]
```
✅ Tailored to your specific domain
✅ Can discover additional entity types
✅ Best for evolving domains

**Strict Domain Extraction (Compliance/Legal)**
```bash
KG_EXTRACTOR_TYPE=schema
SCHEMA_NAME=your_custom_schema
MAX_TRIPLETS_PER_CHUNK=20
SCHEMAS=[{
  "name": "your_custom_schema",
  "schema": {
    "entities": [...],
    "relations": [...],
    "strict": true  # ← Hard constraint, no discovery
  }
}]
```
✅ Only extracts defined types
✅ Highly predictable and consistent
✅ Best for compliance, legal, regulatory

### **For Quick Testing**
```bash
KG_EXTRACTOR_TYPE=simple
MAX_PATHS_PER_CHUNK=20
```
✅ Fastest processing
✅ Good for prototyping
✅ No configuration needed

### **For Research/Exploration**
```bash
KG_EXTRACTOR_TYPE=dynamic
SCHEMA_NAME=default
MAX_TRIPLETS_PER_CHUNK=30
```
✅ Discovers new entity types
✅ Adapts to content
✅ Good for unknown domains

---

## ⚠️ **Provider-Specific Behavior**

### **Bedrock, Groq, and Fireworks**

These providers have tool-calling limitations with `SchemaLLMPathExtractor`. The system **automatically switches** to `DynamicLLMPathExtractor` when you configure `KG_EXTRACTOR_TYPE=schema`:

```bash
# Your config:
KG_EXTRACTOR_TYPE=schema    # ← Automatically changed to 'dynamic' for Bedrock/Groq/Fireworks
SCHEMA_NAME=sample          # ← Used as initial ontology guidance for DynamicLLMPathExtractor

# Actual behavior:
# Automatically uses DynamicLLMPathExtractor with schema guidance
```

**Log Output:**
```
WARNING - Provider bedrock has SchemaLLMPathExtractor LlamaIndex issue
WARNING - Switching to DynamicLLMPathExtractor for reliable extraction
INFO - Using DynamicLLMPathExtractor for flexible relationship discovery
INFO - Providing initial ontology guidance to DynamicLLMPathExtractor
```

**Affected Providers:**
- Amazon Bedrock (all models)
- Groq (all models)
- Fireworks AI (all models)

**Behavior:**
- If you configure `KG_EXTRACTOR_TYPE=schema`, it automatically switches to `dynamic`
- If you configure `KG_EXTRACTOR_TYPE=simple`, it uses `simple` (no change)
- If you configure `KG_EXTRACTOR_TYPE=dynamic`, it uses `dynamic` (no change)
- Your schema configuration (`SCHEMA_NAME=sample` or custom) is used to provide initial ontology guidance to the dynamic extractor
- This ensures reliable extraction while still providing schema-guided structure

**Why:** These providers have known issues with LlamaIndex's tool-calling integration, causing extraction failures with schema-based extractors.

**Recommendation:** If you need structured extraction with these providers, consider:
1. Using OpenAI, Azure OpenAI, Google Gemini, Vertex AI, Anthropic Claude, or Ollama instead
2. Post-processing the SimpleLLMPathExtractor results
3. Switching to a supported provider for graph extraction

---

## 🔧 **Advanced Configuration**

### **Extraction Limits**

Control how much the extractor processes per text chunk:

```bash
# For schema and dynamic extractors
MAX_TRIPLETS_PER_CHUNK=20    # Default: 20, Range: 1-100

# For simple extractor  
MAX_PATHS_PER_CHUNK=20       # Default: 20, Range: 1-100
```

**Guidelines:**
- **Low (5-10):** Very fast, may miss entities in dense content
- **Medium (20-30):** Balanced, works for most content ✅ **Recommended**
- **High (50-100):** Comprehensive, slower, for complex documents

### **Combining Extractor with Schema**

The relationship between `KG_EXTRACTOR_TYPE` and `SCHEMA_NAME`:

| KG_EXTRACTOR_TYPE | SCHEMA_NAME | Result |
|-------------------|-------------|--------|
| `simple` | (any) | SimpleLLMPathExtractor (schema ignored) |
| `schema` | `default` | SchemaLLMPathExtractor with **internal schema** ✅ |
| `schema` | `sample` | SchemaLLMPathExtractor with **project's SAMPLE_SCHEMA** |
| `schema` | `custom` | SchemaLLMPathExtractor with **your custom schema** |
| `dynamic` | `default` | DynamicLLMPathExtractor (no initial guidance) |
| `dynamic` | `sample` | DynamicLLMPathExtractor (with SAMPLE_SCHEMA guidance) |

### **Strict Mode Configuration**

When using `SchemaLLMPathExtractor` with a custom schema, the `strict` parameter controls how rigidly the schema is enforced:

**`strict: false` (Recommended)**
```bash
SCHEMAS=[{
  "name": "my_schema",
  "schema": {
    "entities": ["PERSON", "ORGANIZATION", "TECHNOLOGY"],
    "relations": ["WORKS_FOR", "USES"],
    "strict": false  # ← Allows additional types
  }
}]
```

**Behavior:**
- ✅ Extracts entities/relationships defined in schema
- ✅ **Also extracts** entities/relationships **not** in schema
- ✅ Schema provides **guidance**, not **constraints**
- ✅ LLM can discover new entity/relationship types
- ✅ More flexible and comprehensive extraction
- ⚠️ May include unexpected entity types

**When to use:**
- General-purpose extraction
- When you're not sure what all entity types might appear
- When documents may contain diverse content
- **Recommended for most use cases** ✅

**Example Results:**
```
Schema defines: PERSON, ORGANIZATION, TECHNOLOGY
Extracted: PERSON (5), ORGANIZATION (7), TECHNOLOGY (3), 
          LOCATION (2), EVENT (1), CONCEPT (4)  ← Additional types discovered!
```

---

**`strict: true` (Restrictive)**
```bash
SCHEMAS=[{
  "name": "my_schema",
  "schema": {
    "entities": ["PERSON", "ORGANIZATION", "TECHNOLOGY"],
    "relations": ["WORKS_FOR", "USES"],
    "strict": true  # ← Only allows defined types
  }
}]
```

**Behavior:**
- ✅ Extracts **only** entities/relationships defined in schema
- ❌ **Ignores** any entity/relationship not in schema
- ✅ Schema provides **hard constraints**
- ✅ LLM cannot discover new types
- ✅ Highly consistent, predictable output
- ⚠️ May miss important entities that don't fit schema

**When to use:**
- Highly controlled, domain-specific extraction
- When schema is comprehensive and well-defined
- When consistency is more important than completeness
- Production systems with strict requirements

**Example Results:**
```
Schema defines: PERSON, ORGANIZATION, TECHNOLOGY
Extracted: PERSON (5), ORGANIZATION (7), TECHNOLOGY (3)
          ← Locations, events, concepts ignored even if present in text
```

---

**Strict Mode Comparison:**

| Aspect | strict: false | strict: true |
|--------|---------------|--------------|
| **Schema role** | Guidance | Hard constraint |
| **Entity types** | Schema + discovered | Schema only |
| **Relationship types** | Schema + discovered | Schema only |
| **Flexibility** | ⭐⭐⭐⭐ High | ⭐⭐ Low |
| **Completeness** | ⭐⭐⭐⭐ High | ⭐⭐⭐ Variable |
| **Consistency** | ⭐⭐⭐ Good | ⭐⭐⭐⭐ Excellent |
| **Risk of missing data** | ⭐ Low | ⭐⭐⭐ High |
| **Best for** | General use, exploration | Strict domains, compliance |

---

**Internal Schema Note:**

When using the internal schema (`SCHEMA_NAME=default` or not set), the `strict` parameter defaults to `false` because our implementation doesn't pass a strict parameter to LlamaIndex. This allows the internal schema to be flexible and comprehensive, balancing structure with discovery. This is a design choice - the internal schema works best with `strict=false` to provide both guidance and flexibility.

---

**Recommendation:**

Start with `strict: false` for your custom schemas. Only use `strict: true` if:
1. You have a complete, well-tested schema for your domain
2. Consistency is critical (legal, compliance, regulatory documents)
3. You want to exclude entities outside your specific domain
4. You're willing to sacrifice completeness for predictability

---

## 📈 **Performance Comparison**

Based on cmispress.txt (2480 chars) extraction:

| Extractor | Processing Time | Entities | Relationships | Quality |
|-----------|----------------|----------|---------------|---------|
| Simple (Groq) | ~3.5s | 34 | 17 | ⭐⭐⭐ Good |
| Schema Internal (OpenAI) | ~26s | 37 | 65 | ⭐⭐⭐⭐ Excellent |
| Schema Default (OpenAI) | ~26s | 38 | 19 | ⭐⭐⭐⭐ Excellent |

**Notes:**
- Simple extractor is 7x faster but extracts fewer relationships
- Schema extractors provide richer, more structured graphs
- Internal schema discovered more relationship types (65 vs 19)

---

## 📚 **Related Documentation**

- **Schema Configuration**: `docs/SCHEMA-EXAMPLES.md` - Custom schema examples
- **LLM Testing**: `docs/LLM-TESTING-RESULTS.md` - Provider compatibility
- **Environment Setup**: `docs/ENVIRONMENT-CONFIGURATION.md` - Complete configuration
- **Performance Tuning**: `docs/PERFORMANCE.md` - Optimization tips

---

## 💡 **Best Practices**

1. **Start with internal schema** (`SCHEMA_NAME=default` + `KG_EXTRACTOR_TYPE=schema`)
2. **Use `strict: false` by default** - Only use `strict: true` for compliance/legal requirements
3. **Test on small samples** before processing large datasets
4. **Monitor extraction quality** by checking entity/relationship counts
5. **Use simple extractor** for rapid prototyping and testing
6. **Create custom schemas** only when internal schema doesn't fit your domain
7. **Adjust extraction limits** based on document complexity
8. **Consider provider limitations** when choosing extractors
9. **Compare strict vs non-strict** results before committing to strict mode

---

## 🐛 **Troubleshooting**

### **Issue: No entities extracted**
**Solution:** Check logs for extractor type and schema being used. Verify LLM provider compatibility.

### **Issue: Only chunk nodes, no entities**
**Solution:** If using Bedrock/Groq/Fireworks, the system automatically switches from schema to dynamic extractor. Check logs for "Switching to DynamicLLMPathExtractor" message. If still seeing issues, manually set `KG_EXTRACTOR_TYPE=simple`.

### **Issue: Wrong extractor being used**
**Solution:** Verify `KG_EXTRACTOR_TYPE` in `.env` file. Check logs for "create_extractor called with: extractor_type='...'" message.

### **Issue: Poor entity type labels**
**Solution:** Switch from simple to schema extractor with internal schema (`SCHEMA_NAME=default` + `KG_EXTRACTOR_TYPE=schema`).

### **Issue: Too few relationships extracted**
**Solution:** Increase `MAX_TRIPLETS_PER_CHUNK` or `MAX_PATHS_PER_CHUNK` to 50-100.

### **Issue: Missing important entities**
**Solution:** 
- If using custom schema with `strict: true`, switch to `strict: false`
- Check if entities are outside your schema definition
- Consider using internal schema (`SCHEMA_NAME=default`) for broader coverage

### **Issue: Too many unexpected entity types**
**Solution:**
- If using `strict: false` and need more control, create a comprehensive custom schema
- Or use `strict: true` to enforce hard constraints (but test first!)
- Review and refine your schema definition to include expected types

---

## 📝 **Source Code Reference**

The internal schema is defined in LlamaIndex:
```
venv/Lib/site-packages/llama_index/core/indices/property_graph/transformations/schema_llm.py
Lines 22-78: DEFAULT_ENTITIES, DEFAULT_RELATIONS, DEFAULT_VALIDATION_SCHEMA
```

This is the canonical source for the internal schema used when `SCHEMA_NAME=default`.
