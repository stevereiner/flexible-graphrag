# Search Databases

Flexible GraphRAG supports three full-text search options for the hybrid search pipeline.

---

## BM25 (Built-in)

Local file-based BM25 full-text search with TF-IDF ranking. No external server required.

- **Dashboard**: None (file-based)
- **Best for**: Local development, simple deployments

```bash
SEARCH_DB=bm25
SEARCH_DB_CONFIG={"persist_dir": "./bm25_index"}
```

---

## Elasticsearch

Enterprise search engine with advanced analyzers, faceted search, and real-time analytics.

- **Dashboard**: Kibana at http://localhost:5601
- **Docker**: Uncomment `includes/elasticsearch-dev.yaml` in `docker-compose.yaml`

```bash
SEARCH_DB=elasticsearch
SEARCH_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search"}
```

---

## OpenSearch

AWS-led open-source fork with native hybrid scoring (vector + BM25) and k-NN algorithms.

- **Dashboard**: OpenSearch Dashboards at http://localhost:5601
- **Docker**: Uncomment `includes/opensearch.yaml` in `docker-compose.yaml`

```bash
SEARCH_DB=opensearch
SEARCH_DB_CONFIG={"hosts": ["http://localhost:9201"], "index_name": "hybrid_search"}
```

!!! tip "OpenSearch Pipeline Setup"
    For optimal hybrid search with OpenSearch, set up the hybrid search pipeline:
    ```bash
    python scripts/create_opensearch_pipeline.py
    # or: scripts/setup-opensearch-pipeline.sh  (Linux/macOS)
    # or: scripts/setup-opensearch-pipeline.bat  (Windows)
    ```

---

## Disabling Full-Text Search

To use vector search only (no full-text):

```bash
SEARCH_DB=none
```

---

## Full Configuration Reference

See [Database Configuration](DATABASE-CONFIGURATION.md) for the full search database configuration reference with all options.
