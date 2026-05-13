# Search Database Configuration

## Database Selection

Set `SEARCH_DB` to select the search store:

```env
SEARCH_DB=elasticsearch    # bm25 | elasticsearch | opensearch | none
```

## Framework Selection

Set `SEARCH_BACKEND` to choose the framework. All three stores are supported with both:

```env
SEARCH_BACKEND=llamaindex  # or langchain
```

## BM25 (Built-in)

Local in-memory BM25 full-text search with TF-IDF ranking. No external service required.

```env
SEARCH_DB=bm25
```

## Elasticsearch

Enterprise search engine with advanced analyzers, faceted search, and real-time analytics.

- Dashboard: Kibana (http://localhost:5601)

```env
SEARCH_DB=elasticsearch
```

## OpenSearch

AWS-led open-source fork with native hybrid scoring (vector + BM25) and k-NN algorithms.

- Dashboard: OpenSearch Dashboards (http://localhost:5601)

```env
SEARCH_DB=opensearch
```

## Disable Full-Text Search

```env
SEARCH_DB=none
```

See [Search Databases](../DATABASES/SEARCH-DATABASES.md) for more details.
