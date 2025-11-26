# Performance Test Results

**⚠️ Note**: Performance benchmarks are being redone. Results below are from previous testing and will be updated.

**Test Environment**: AMD 5950x 16-core CPU, 64GB RAM, 4090 Nvidia GPU, Windows 11 Pro

**Infrastructure Configuration**: 
- **Vector Database**: Qdrant (consistent across all tests)
- **Search Database**: Elasticsearch (consistent across all tests) 
- **Graph Extractor**: SchemaLLMPathExtractor (extract type: schema) with schema name: default (consistent across all tests)
- **LLM Models**: OpenAI gpt-4o-mini, Ollama llama3.2:3b
- **Embedding Models**: OpenAI text-embedding-3-small, Ollama all-minilm
- **Index Management**: Qdrant + Elasticsearch indexes cleared between LLM/Graph DB configuration changes, but preserved between 2-doc to 4-doc incremental tests within same configuration

## Quick Summary: 6-Document Performance

The table below provides a quick overview of 6-document ingestion performance across different graph database and LLM combinations. See detailed breakdowns in following sections.

| Graph Database | LLM Provider | Ingestion Time | Search Time | Q&A Time |
|----------------|--------------|----------------|-------------|----------|
| Neo4j | OpenAI gpt-4o-mini | 11.31s | 0.912s | 2.796s |
| Kuzu | OpenAI gpt-4o-mini | 15.72s | 1.240s | 2.187s |
| FalkorDB | OpenAI gpt-4o-mini | 21.74s | 1.199s | 2.133s |
| Neo4j | Ollama llama3.2:3b | 72.06s | ~4.2s | ~13.7s |
| Kuzu | Ollama llama3.2:3b | 43.10s | 4.945s | 10.572s |

**Key Observations**:
- OpenAI consistently faster than Ollama across all graph databases
- Neo4j + OpenAI provides fastest overall performance
- Kuzu shows good performance with OpenAI
- All configurations complete Q&A queries in under 15 seconds

---

## Detailed Test Results

## Neo4j + OpenAI

| Documents | Ingestion Time | Search Time | Q&A Time | Notes |
|-----------|----------------|-------------|----------|-------|
| 2 docs (cmispress.txt, space-station.txt) | 14.39s total<br/>Pipeline: 1.31s<br/>Vector: 0.81s<br/>Graph: 10.90s | 1.453s<br/>("cmis" query) | 2.785s<br/>("who was first with cmis") | Initial ingestion |
| +4 docs (incremental to 6 total)<br/>(excel, pptx, docx, pdf) | 11.31s total<br/>Pipeline: 0.76s<br/>Vector: 0.26s<br/>Graph: 9.20s | 0.912s<br/>("cmis" query) | 2.796s<br/>("who was first with cmis") | Incremental ingestion<br/>**Graph**: 49 nodes (43 Entity, 6 Chunk), 88 relationships (45 MENTIONS, 43 semantic types) |
| 6 docs (clean test) | 11.31s total<br/>Pipeline: 0.76s<br/>Vector: 0.26s<br/>Graph: 9.20s | 0.912s<br/>("cmis" query) | 2.796s<br/>("who was first with cmis") | Clean 6-document test |

## Neo4j + Ollama

| Documents | Ingestion Time | Search Time | Q&A Time | Notes |
|-----------|----------------|-------------|----------|-------|
| 2 docs (cmispress.txt, space-station.txt) | 53.66s total<br/>Pipeline: 2.08s<br/>Vector: 0.28s<br/>Graph: 50.71s | 4.252s<br/>("cmis" query) | 13.716s<br/>("who was first with cmis") | Initial ingestion |
| +4 docs (incremental to 6 total)<br/>(excel, pptx, docx, pdf) | 72.06s total<br/>Pipeline: 2.14s<br/>Vector: 0.30s<br/>Graph: 69.40s | ~4.2s<br/>("cmis" query) | ~13.7s<br/>("who was first with cmis") | Incremental ingestion |

## Kuzu + OpenAI

| Documents | Ingestion Time | Search Time | Q&A Time | Notes |
|-----------|----------------|-------------|----------|-------|
| 2 docs (cmispress.txt, space-station.txt) | 14.79s total<br/>Pipeline: 1.35s<br/>Vector: 0.93s<br/>Graph: 11.16s | 1.998s<br/>("cmis" query) | 5.005s<br/>("who was first with cmis") | Initial ingestion |
| +4 docs (incremental to 6 total)<br/>(excel, pptx, docx, pdf) | 15.72s total<br/>Pipeline: 0.41s<br/>Vector: 0.28s<br/>Graph: 14.40s | 1.240s<br/>("cmis" query) | 2.187s<br/>("who was first with cmis") | Incremental ingestion<br/>**Graph**: 50 nodes (44 Entity, 6 Chunk), 96 relationships (42 LINKS, 54 MENTIONS) |
| 6 docs (clean test) | 15.72s total<br/>Pipeline: 0.41s<br/>Vector: 0.28s<br/>Graph: 14.40s | 1.240s<br/>("cmis" query) | 2.187s<br/>("who was first with cmis") | Clean 6-document test |

## Kuzu + Ollama

| Documents | Ingestion Time | Search Time | Q&A Time | Notes |
|-----------|----------------|-------------|----------|-------|
| 2 docs (cmispress.txt, space-station.txt) | 54.76s total<br/>Pipeline: 2.11s<br/>Vector: 1.00s<br/>Graph: 51.12s | 4.634s<br/>("cmis" query) | 8.595s<br/>("who was first with cmis") | Initial ingestion |
| +4 docs (incremental to 6 total)<br/>(excel, pptx, docx, pdf) | 43.10s total<br/>Pipeline: 2.16s<br/>Vector: 0.26s<br/>Graph: 40.68s | 4.945s<br/>("cmis" query) | 10.572s<br/>("who was first with cmis") | Incremental ingestion<br/>**Graph**: 39 nodes (33 Entity, 6 Chunk), 63 relationships (27 LINKS, 36 MENTIONS) |

## FalkorDB + OpenAI

| Documents | Ingestion Time | Search Time | Q&A Time | Notes |
|-----------|----------------|-------------|----------|-------|
| 1 doc (cmispress.txt) | 17.26s total<br/>Pipeline: 3.34s<br/>Vector: 3.56s<br/>Graph: 9.13s | 1.714s<br/>("cmis" query) | 1.625s<br/>("who was first with cmis") | Initial single document |
| 2 docs (cmispress.txt, space-station.txt) | 16.15s total<br/>Pipeline: 1.21s<br/>Vector: 0.88s<br/>Graph: 13.35s | 1.203s<br/>("cmis" query) | 1.974s<br/>("who was first with cmis") | Two document test |
| +4 docs (incremental to 6 total)<br/>(excel, pptx, docx, pdf) | 10.74s total<br/>Pipeline: 0.51s<br/>Vector: 0.31s<br/>Graph: 8.94s | 0.933s<br/>("cmis" query) | 1.901s<br/>("who was first with cmis") | Incremental ingestion |
| 6 docs (clean test) | 21.74s total<br/>Pipeline: 1.02s<br/>Vector: 3.09s<br/>Graph: 14.99s | 1.199s<br/>("cmis" query) | 2.133s<br/>("who was first with cmis") | Clean 6-document test<br/>**Graph**: 12 nodes, 21 edges with rich entity types |

## FalkorDB + Ollama

| Documents | Ingestion Time | Search Time | Q&A Time | Notes |
|-----------|----------------|-------------|----------|-------|
| 2 docs (cmispress.txt, space-station.txt) | 55.51s total<br/>Pipeline: 2.71s<br/>Vector: 0.27s<br/>Graph: 52.43s | 4.494s<br/>("cmis" query) | 9.734s<br/>("who was first with cmis") | Initial ingestion |
| 4 docs | 52.87s total<br/>Pipeline: 2.14s<br/>Vector: 0.27s<br/>Graph: 50.21s | 4.696s<br/>("cmis" query) | 11.747s<br/>("who was first with cmis") | 4-document test |

(Note to avoid errors with space-station.txt and errors with multiple file processing, with falkorDB + Ollama,  OLLAMA_CONTEXT_LENGTH=16384  set in system environment and TRIPLETS_PER_CHUNK=100 was set in flexible-graphrag .env)
