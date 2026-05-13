# Search Databases

Flexible GraphRAG supports three full-text search options for the hybrid search pipeline. Set `SEARCH_DB` to select the store and `SEARCH_BACKEND` to choose the framework (`llamaindex` or `langchain`).

---

## BM25 (Built-in)

Local in-memory BM25 full-text search with TF-IDF ranking. No external server required.

- **Best for**: Local development, simple deployments

```env
SEARCH_DB=bm25
BM25_SEARCH_DB_CONFIG={"persist_dir": "./bm25_index"}
```

---

## Elasticsearch

Enterprise search engine with advanced analyzers, faceted search, and real-time analytics.

- **Dashboard**: Kibana at http://localhost:5601
- **Docker**: Uncomment `includes/elasticsearch-dev.yaml` in `docker-compose.yaml`

```env
SEARCH_DB=elasticsearch
ELASTICSEARCH_SEARCH_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search"}
```

---

## OpenSearch

AWS-led open-source fork with native hybrid scoring (vector + BM25) and k-NN algorithms.

- **Dashboard**: OpenSearch Dashboards at http://localhost:5601
- **Docker**: Uncomment `includes/opensearch.yaml` in `docker-compose.yaml`

```env
SEARCH_DB=opensearch
OPENSEARCH_SEARCH_DB_CONFIG={"hosts": ["http://localhost:9201"], "index_name": "hybrid_search"}
```

For optimal hybrid search with OpenSearch, set up the hybrid search pipeline:

```bash
python scripts/create_opensearch_pipeline.py
```

---

## Disabling Full-Text Search

```env
SEARCH_DB=none
```

