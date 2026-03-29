"""
Inspect Elasticsearch index contents and test doc_id query patterns.

Usage:
    python check_elasticsearch.py                      # list all docs (up to --limit)
    python check_elasticsearch.py cmispress.txt        # list + test queries for that file
    python check_elasticsearch.py --limit 20           # show up to 20 docs
    python check_elasticsearch.py --port 9201          # OpenSearch port
"""
import argparse
import asyncio
from elasticsearch import AsyncElasticsearch

INDEX = "hybrid_search_fulltext"
PREVIEW_LEN = 300


def _print_hit(i, hit):
    doc = hit['_source']
    print(f"\n--- Document {i} (ID: {hit['_id']}) ---")
    print(f"Top-level fields: {list(doc.keys())}")

    meta = doc.get('metadata', {})
    if meta:
        print(f"Metadata fields: {list(meta.keys())}")
        for key in ('file_name', 'file_path', 'doc_id', 'ref_doc_id', 'document_id'):
            if key in meta:
                print(f"  metadata.{key}: {meta[key]}")

    content = doc.get('content', '')
    if content:
        preview = content[:PREVIEW_LEN]
        truncated = "..." if len(content) > PREVIEW_LEN else ""
        print(f"\nContent preview:\n  {preview}{truncated}")

    print("-" * 80)


async def list_docs(client, filename_filter: str, limit: int):
    if filename_filter:
        query = {"bool": {"should": [
            {"wildcard": {"metadata.file_name": f"*{filename_filter}*"}},
            {"wildcard": {"metadata.file_path": f"*{filename_filter}*"}},
        ]}}
    else:
        query = {"match_all": {}}

    result = await client.search(
        index=INDEX,
        body={"query": query, "size": limit}
    )
    total = result['hits']['total']['value']
    showing = len(result['hits']['hits'])
    filter_note = f" matching '{filename_filter}'" if filename_filter else ""
    print(f"\n=== TOTAL DOCS{filter_note}: {total} (showing {showing}) ===")

    for i, hit in enumerate(result['hits']['hits'], 1):
        _print_hit(i, hit)

    return result['hits']['hits']


async def test_queries_for_file(client, filename: str):
    """Find the doc_ids that belong to filename, then test every query pattern against them."""
    # Step 1: find chunks for this file
    result = await client.search(
        index=INDEX,
        body={
            "query": {"bool": {"should": [
                {"wildcard": {"metadata.file_name": f"*{filename}*"}},
                {"wildcard": {"metadata.file_path": f"*{filename}*"}},
            ]}},
            "size": 5,
        }
    )
    hits = result['hits']['hits']
    if not hits:
        print(f"\n=== No chunks found for '{filename}' — nothing to test ===")
        return

    # Collect unique ref_doc_id and doc_id values from the found chunks
    ref_doc_ids = set()
    doc_ids = set()
    for hit in hits:
        meta = hit['_source'].get('metadata', {})
        if meta.get('ref_doc_id'):
            ref_doc_ids.add(meta['ref_doc_id'])
        if meta.get('doc_id'):
            doc_ids.add(meta['doc_id'])

    all_ids = list(ref_doc_ids | doc_ids)
    if not all_ids:
        print(f"\n=== Chunks found for '{filename}' but no doc_id/ref_doc_id in metadata ===")
        return

    print(f"\n=== QUERY PATTERN TEST for '{filename}' ===")
    print(f"doc_ids found:     {list(doc_ids) or '(none)'}")
    print(f"ref_doc_ids found: {list(ref_doc_ids) or '(none)'}")

    for test_id in all_ids[:2]:  # test at most 2 distinct IDs
        print(f"\n  Testing id: {test_id}")
        queries = [
            ("term",  "metadata.ref_doc_id.keyword",  test_id),
            ("term",  "metadata.doc_id.keyword",      test_id),
            ("term",  "metadata.document_id.keyword", test_id),
            ("match", "metadata.ref_doc_id",          test_id),
            ("match", "metadata.doc_id",              test_id),
        ]
        for qtype, field, value in queries:
            r = await client.search(
                index=INDEX,
                body={"query": {qtype: {field: value}}, "size": 1}
            )
            count = r['hits']['total']['value']
            tick = "[+]" if count else "[ ]"
            print(f"    {tick} {qtype:5s}  {field:40s}  -> {count} match(es)")


async def main(args):
    client = AsyncElasticsearch([f"http://localhost:{args.port}"])
    try:
        hits = await list_docs(client, args.filename, args.limit)
        if args.filename and hits:
            await test_queries_for_file(client, args.filename)
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect Elasticsearch index")
    parser.add_argument("filename", nargs="?", default="",
                        help="Filter docs by file_name / file_path substring")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max docs to list (default: 10)")
    parser.add_argument("--port", type=int, default=9200,
                        help="Elasticsearch port (default: 9200)")
    asyncio.run(main(parser.parse_args()))
