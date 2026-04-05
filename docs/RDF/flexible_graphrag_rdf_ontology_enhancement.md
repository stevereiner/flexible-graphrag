# Enhanced flexible-graphrag: RDF/Ontology Support with PropertyGraphIndex

## Executive Summary

Enhance **flexible-graphrag** to support:
1. **Ontology-Driven Knowledge Graph Extraction** using RDFlib + LlamaIndex's `SchemaLLMPathExtractor`
2. **8 Property Graph Databases** (already supported, with improved schema integration)
3. **RDF Store Targets** (Ontotext GraphDB, Apache Fuseki, Oxigraph, Oracle, etc.) via custom SPARQL store connectors
4. **SPARQL Query Interface** for querying both extracted graphs and wrapped property graphs
5. **RDF Export/Import** capabilities (secondary but important for interoperability)

---

## Architecture Overview

```text
                           Document Sources
                           (PDF, DOCX, etc.)
                                  ↓
                    ┌─────────────────────────────┐
                    │  Flexible-GraphRAG Ingestion │
                    │    (Docling Processing)      │
                    └──────────────┬────────────────┘
                                   ↓
                    ┌──────────────────────────────┐
                    │  Ontology Integration Layer  │ ← NEW
                    │  1. Load RDF ontologies      │
                    │  2. Extract entity/relation  │
                    │     types via SPARQL        │
                    │  3. Build schema for LLM    │
                    └──────────────┬───────────────┘
                                   ↓
      ┌────────────────────────────────────────────────────┐
      │    LlamaIndex PropertyGraphIndex with Extractors    │
      ├─────────────────────────────────────────────────────┤
      │ SchemaLLMPathExtractor (ontology-guided)            │
      │   └─ Validates against ontology schema             │
      │ SimpleLLMPathExtractor (free-form)                 │
      │ ImplicitPathExtractor (structural)                 │
      │ DynamicLLMPathExtractor (guided LLM)              │
      └────────────────┬──────────────────────────────────┘
                       ↓
    ┌──────────────────┴────────────────────────────────────┐
    │                                                        │
    ↓ Property Graph Store Layer                            ↓ RDF Store Layer
    ├─ Neo4j                                                ├─ Ontotext GraphDB
    ├─ Ladybug                                              ├─ Apache Fuseki
    ├─ FalkorDB                                             ├─ Oxigraph
    ├─ ArcadeDB                                             ├─ Oracle SPARQL
    ├─ MemGraph                                             ├─ Virtuoso
    ├─ NebulaGraph                                          └─ Custom SPARQL Endpoint
    ├─ Amazon Neptune                                       
    └─ Amazon Neptune Analytics                            
    
                                 ↓
                    ┌────────────────────────┐
                    │  Unified Query Engine  │
                    ├────────────────────────┤
                    │ Cypher (Property Graph)│
                    │ SPARQL (RDF Stores)    │
                    │ Text-to-Cypher/SPARQL │
                    │ Hybrid Retrieval       │
                    └────────────────────────┘
                                 ↓
                    ┌────────────────────────┐
                    │  Results & Retrieval   │
                    │  (Existing UI clients) │
                    └────────────────────────┘
