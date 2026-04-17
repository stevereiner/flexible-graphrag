# Search Database Configuration

**Configuration**: Set via `SEARCH_DB` and `SEARCH_DB_CONFIG` environment variables

## BM25 (Built-in)

Local file-based BM25 full-text search with TF-IDF ranking. No extra service required.

- Dashboard: None (file-based)

```bash
SEARCH_DB=bm25
SEARCH_DB_CONFIG={"persist_dir": "./bm25_index"}
```

## Elasticsearch

Enterprise search engine with advanced analyzers, faceted search, and real-time analytics.

- Dashboard: Kibana (http://localhost:5601) for search analytics, index management, and query debugging

```bash
SEARCH_DB=elasticsearch
SEARCH_DB_CONFIG={"hosts": ["http://localhost:9200"], "index_name": "hybrid_search"}
```

## OpenSearch

AWS-led open-source fork with native hybrid scoring (vector + BM25) and k-NN algorithms.

- Dashboard: OpenSearch Dashboards (http://localhost:5601) for cluster monitoring and search pipeline management

```bash
SEARCH_DB=opensearch
SEARCH_DB_CONFIG={"hosts": ["http://localhost:9201"], "index_name": "hybrid_search"}
```

## Disable Full-Text Search

To use vector search only:

```bash
SEARCH_DB=none
```

See [Search Databases](../DATABASES/SEARCH-DATABASES.md) for more details.
