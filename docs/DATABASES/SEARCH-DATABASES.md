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

- **Dashboard**: OpenSearch Dashboards at http://localhost:5602
- **Docker**: Uncomment `includes/opensearch.yaml` in `docker-compose.yaml` (and
  `includes/opensearch-dashboards.yaml` for the web UI — it is a separate include)

```env
SEARCH_DB=opensearch
OPENSEARCH_SEARCH_DB_CONFIG={"hosts": ["http://localhost:9201"], "index_name": "hybrid_search"}
```

For optimal hybrid search with OpenSearch, set up the hybrid search pipeline:

```bash
python scripts/create_opensearch_pipeline.py
```

---

## Sharing the engine with Alfresco

Alfresco Community 26.2 dropped Solr and indexes into Elasticsearch or OpenSearch too. By default
`includes/alfresco-elasticsearch.yaml` gives it a dedicated engine on port 9202 (or
`includes/alfresco-opensearch.yaml` on 9203), but you can point it at the one configured above
instead: drop both includes and set `ALFRESCO_SEARCH_HOST=elasticsearch` (or `=opensearch`) in
`docker/.env`. Alfresco writes its own `alfresco` index, so it
coexists with `hybrid_search`, and your existing Kibana / OpenSearch Dashboards covers both.
The `includes/elasticsearch-dev.yaml` (8.17.10) and `includes/opensearch.yaml` (2.19.6) pins match
the versions ACS 26.2 is tested against, so no version change is needed.

## Disabling Full-Text Search

```env
SEARCH_DB=none
```

