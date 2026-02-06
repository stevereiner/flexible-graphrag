"""
Check Elasticsearch documents to see exact structure and metadata
"""
import asyncio
from elasticsearch import AsyncElasticsearch

async def check_elasticsearch():
    # Connect to Elasticsearch
    client = AsyncElasticsearch(["http://localhost:9200"])
    
    try:
        # Get all documents from the index
        result = await client.search(
            index="hybrid_search_fulltext",
            body={
                "query": {"match_all": {}},
                "size": 10
            }
        )
        
        print(f"\n=== TOTAL DOCUMENTS: {result['hits']['total']['value']} ===\n")
        
        for i, hit in enumerate(result['hits']['hits'], 1):
            doc = hit['_source']
            print(f"\n--- Document {i} (ID: {hit['_id']}) ---")
            print(f"Top-level fields: {list(doc.keys())}")
            
            if 'metadata' in doc:
                print(f"\nMetadata fields: {list(doc['metadata'].keys())}")
                
                # Print important metadata
                if 'doc_id' in doc['metadata']:
                    print(f"  metadata.doc_id: {doc['metadata']['doc_id']}")
                if 'ref_doc_id' in doc['metadata']:
                    print(f"  metadata.ref_doc_id: {doc['metadata']['ref_doc_id']}")
                if 'document_id' in doc['metadata']:
                    print(f"  metadata.document_id: {doc['metadata']['document_id']}")
                if 'file_name' in doc['metadata']:
                    print(f"  metadata.file_name: {doc['metadata']['file_name']}")
                if 'file_path' in doc['metadata']:
                    print(f"  metadata.file_path: {doc['metadata']['file_path']}")
            
            # Show content preview
            if 'content' in doc:
                content_preview = doc['content'][:100] if len(doc['content']) > 100 else doc['content']
                print(f"\nContent preview: {content_preview}...")
            
            print("-" * 80)
        
        # Try a test query with the doc_id we're looking for
        test_doc_id = "56afdcac-156d-4d9d-9e98-4103d8648232:alfresco://cdfcb2a7-214c-4dff-bcb2-a7214c8dff5d"
        print(f"\n=== TEST QUERY for doc_id: {test_doc_id} ===")
        
        # Try different query patterns
        queries = [
            {"term": {"metadata.ref_doc_id.keyword": test_doc_id}},
            {"term": {"metadata.doc_id.keyword": test_doc_id}},
            {"term": {"metadata.document_id.keyword": test_doc_id}},
            {"match": {"metadata.ref_doc_id": test_doc_id}},
            {"match": {"metadata.doc_id": test_doc_id}},
        ]
        
        for query in queries:
            result = await client.search(
                index="hybrid_search_fulltext",
                body={"query": query, "size": 1}
            )
            query_str = str(query)[:80]
            print(f"\nQuery: {query_str}")
            print(f"  Matches: {result['hits']['total']['value']}")
        
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(check_elasticsearch())
