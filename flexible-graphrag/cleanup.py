#!/usr/bin/env python3
"""
Database Cleanup Script for Flexible GraphRAG
Wipes all data from PostgreSQL, Qdrant, Elasticsearch/OpenSearch, and Neo4j
"""
import os
import sys
import json
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables
load_dotenv()

def parse_postgres_url(url):
    """Parse PostgreSQL URL into connection parameters"""
    parsed = urlparse(url)
    return {
        'host': parsed.hostname or 'localhost',
        'port': parsed.port or 5432,
        'database': parsed.path.lstrip('/') if parsed.path else 'postgres',
        'user': parsed.username or 'postgres',
        'password': parsed.password or 'postgres'
    }

def cleanup_postgres():
    """Clean PostgreSQL document_state and datasource_config tables"""
    print("\n=== PostgreSQL Cleanup ===")
    try:
        import psycopg2
        
        # Get connection params from POSTGRES_INCREMENTAL_URL
        postgres_url = os.getenv('POSTGRES_INCREMENTAL_URL')
        if not postgres_url:
            print("  Skipped: POSTGRES_INCREMENTAL_URL not configured")
            return
        
        conn_params = parse_postgres_url(postgres_url)
        print(f"  Connecting to: {conn_params['host']}:{conn_params['port']}/{conn_params['database']}")
        
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        # Delete from document_state
        cursor.execute("DELETE FROM document_state;")
        deleted_docs = cursor.rowcount
        print(f"  Deleted {deleted_docs} rows from document_state")
        
        # Delete from datasource_config
        cursor.execute("DELETE FROM datasource_config;")
        deleted_sources = cursor.rowcount
        print(f"  Deleted {deleted_sources} rows from datasource_config")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("  PostgreSQL cleanup: SUCCESS")
        
    except Exception as e:
        print(f"  PostgreSQL cleanup: FAILED - {e}")

def cleanup_vector_store():
    """Delete vector store using LlamaIndex abstractions"""
    print("\n=== Vector Store Cleanup ===")
    vector_store = None
    try:
        from factories import DatabaseFactory
        from config import VectorDBType
        
        # Get vector database type
        vector_db = os.getenv('VECTOR_DB', 'qdrant')
        print(f"  Vector DB type: {vector_db}")
        
        if vector_db == 'none':
            print("  Skipped: VECTOR_DB=none (no vector database configured)")
            return
        
        # Parse VECTOR_DB_CONFIG
        vector_db_config_str = os.getenv('VECTOR_DB_CONFIG', '{}')
        config = json.loads(vector_db_config_str)
        
        # Get collection name from config
        collection_name = config.get('collection_name', 'hybrid_search_vector')
        print(f"  Target collection: {collection_name}")
        
        # Get embedding dimension (required for some stores)
        embed_dim = 1536  # Default for OpenAI text-embedding-3-small
        
        # Convert string to enum (values are lowercase)
        try:
            db_type_enum = VectorDBType(vector_db.lower())
        except ValueError:
            print(f"  ERROR: Unknown vector DB type: {vector_db}")
            return
        
        # For Qdrant, use direct client for more reliable deletion
        if vector_db.lower() == 'qdrant':
            try:
                from qdrant_client import QdrantClient
                
                # Get connection params
                host = config.get('host', 'localhost')
                port = config.get('port', 6333)
                url = config.get('url')
                api_key = config.get('api_key')
                
                # Connect to Qdrant
                if url:
                    client = QdrantClient(url=url, api_key=api_key)
                    print(f"  Connected to Qdrant: {url}")
                else:
                    client = QdrantClient(host=host, port=port)
                    print(f"  Connected to Qdrant: {host}:{port}")
                
                # Check if collection exists
                collections = client.get_collections().collections
                collection_names = [c.name for c in collections]
                
                if collection_name in collection_names:
                    client.delete_collection(collection_name)
                    print(f"  Deleted collection: {collection_name}")
                else:
                    print(f"  Collection '{collection_name}' does not exist (already clean)")
                
                client.close()
                print(f"  Vector store cleanup: SUCCESS")
                return
                
            except Exception as e:
                print(f"  Direct client cleanup failed: {e}")
                print(f"  Falling back to LlamaIndex method...")
        
        # For OpenSearch (when used as vector store), use direct client
        elif vector_db.lower() == 'opensearch':
            try:
                from opensearchpy import OpenSearch
                
                # Get connection params
                host = config.get('host', 'localhost')
                port = config.get('port', 9201)
                http_auth = None
                if config.get('username') and config.get('password'):
                    http_auth = (config.get('username'), config.get('password'))
                
                # Connect to OpenSearch
                client = OpenSearch(
                    hosts=[{'host': host, 'port': port}],
                    http_auth=http_auth,
                    use_ssl=config.get('use_ssl', False),
                    verify_certs=config.get('verify_certs', False),
                    ssl_show_warn=False
                )
                
                print(f"  Connected to OpenSearch: {host}:{port}")
                
                # Check if index exists (OpenSearch uses indices as collections)
                index_name = config.get('index_name', collection_name)
                if client.indices.exists(index=index_name):
                    client.indices.delete(index=index_name)
                    print(f"  Deleted index: {index_name}")
                else:
                    print(f"  Index '{index_name}' does not exist (already clean)")
                
                client.close()
                print(f"  Vector store cleanup: SUCCESS")
                return
                
            except Exception as e:
                print(f"  Direct client cleanup failed: {e}")
                print(f"  Falling back to LlamaIndex method...")
        
        # For Weaviate, use direct async client
        elif vector_db.lower() == 'weaviate':
            try:
                import weaviate
                import asyncio
                
                # Get connection params
                url = config.get('url', 'http://localhost:8081')
                index_name = config.get('index_name', 'HybridSearch')
                api_key = config.get('api_key')
                
                print(f"  Connecting to Weaviate: {url}")
                print(f"  Target collection: {index_name}")
                
                async def delete_weaviate_collection():
                    """Async function to delete Weaviate collection"""
                    # Create async client
                    if api_key:
                        from weaviate.classes.init import Auth, AdditionalConfig, Timeout
                        client = weaviate.use_async_with_custom(
                            http_host=url.replace("http://", "").replace("https://", "").replace(":8081", ""),
                            http_port=8081,
                            http_secure=False,
                            grpc_host="localhost",
                            grpc_port=50051,
                            grpc_secure=False,
                            skip_init_checks=True,
                            additional_config=AdditionalConfig(
                                timeout=Timeout(init=60, query=60, insert=180)
                            ),
                            auth_credentials=Auth.api_key(api_key),
                            headers=config.get("additional_headers", {})
                        )
                    else:
                        from weaviate.classes.init import AdditionalConfig, Timeout
                        client = weaviate.use_async_with_custom(
                            http_host=url.replace("http://", "").replace("https://", "").replace(":8081", ""),
                            http_port=8081,
                            http_secure=False,
                            grpc_host="localhost",
                            grpc_port=50051,
                            grpc_secure=False,
                            skip_init_checks=True,
                            additional_config=AdditionalConfig(
                                timeout=Timeout(init=60, query=60, insert=180)
                            ),
                            headers=config.get("additional_headers", {})
                        )
                    
                    # Connect and delete
                    await client.connect()
                    
                    # Check if collection exists and delete it
                    try:
                        await client.collections.delete(index_name)
                        print(f"  Deleted collection: {index_name}")
                    except Exception as e:
                        if 'not found' in str(e).lower() or '404' in str(e):
                            print(f"  Collection '{index_name}' does not exist (already clean)")
                        else:
                            raise
                    
                    await client.close()
                
                # Run async deletion
                asyncio.run(delete_weaviate_collection())
                print(f"  Vector store cleanup: SUCCESS")
                return
                
            except Exception as e:
                print(f"  Direct client cleanup failed: {e}")
                print(f"  Falling back to LlamaIndex method...")
        
        # Fallback: Create vector store using factory and try LlamaIndex methods
        vector_store = DatabaseFactory.create_vector_store(
            db_type=db_type_enum,
            config=config
        )
        
        # Use LlamaIndex to clear the store
        print(f"  Clearing vector store...")
        try:
            # Different stores have different clear methods
            if hasattr(vector_store, 'delete_collection'):
                vector_store.delete_collection()
                print(f"  Deleted collection using delete_collection()")
            elif hasattr(vector_store, 'clear'):
                vector_store.clear()
                print(f"  Cleared vector store using clear()")
            else:
                # Fallback: try to delete via client
                if hasattr(vector_store, 'client'):
                    vector_store.client.delete_collection(collection_name)
                    print(f"  Deleted collection: {collection_name}")
                else:
                    print(f"  WARNING: No known delete method for {vector_db}")
        except Exception as e:
            print(f"  Note: {e}")
            print(f"  (Collection may not exist yet)")
        
        print(f"  Vector store cleanup: SUCCESS")
        
    except Exception as e:
        print(f"  Vector store cleanup: FAILED - {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Close any connections
        if vector_store is not None:
            try:
                if hasattr(vector_store, 'close'):
                    # Check if close is async
                    import inspect
                    if inspect.iscoroutinefunction(vector_store.close):
                        # Async close (e.g., PGVectorStore)
                        asyncio.run(vector_store.close())
                    else:
                        # Sync close
                        vector_store.close()
                elif hasattr(vector_store, 'client') and hasattr(vector_store.client, 'close'):
                    vector_store.client.close()
            except Exception:
                pass  # Ignore close errors

def cleanup_search_store():
    """Delete search store using LlamaIndex abstractions"""
    print("\n=== Search Store Cleanup ===")
    search_store = None
    try:
        from factories import DatabaseFactory
        from config import SearchDBType
        
        # Get search database type
        search_db = os.getenv('SEARCH_DB', 'elasticsearch')
        print(f"  Search DB type: {search_db}")
        
        if search_db == 'none' or search_db == 'bm25':
            print(f"  Skipped: SEARCH_DB={search_db} (no external search database)")
            return
        
        # Parse SEARCH_DB_CONFIG
        search_db_config_str = os.getenv('SEARCH_DB_CONFIG', '{}')
        config = json.loads(search_db_config_str)
        
        # Get index name from config
        index_name = config.get('index_name', 'hybrid_search_fulltext')
        print(f"  Target index: {index_name}")
        
        # Get embedding dimension (required for some stores)
        embed_dim = 1536  # Default for OpenAI text-embedding-3-small
        
        # Convert string to enum (values are lowercase)
        try:
            db_type_enum = SearchDBType(search_db.lower())
        except ValueError:
            print(f"  ERROR: Unknown search DB type: {search_db}")
            return
        
        # For OpenSearch/Elasticsearch, use direct client for more reliable deletion
        if search_db.lower() in ['opensearch', 'elasticsearch']:
            try:
                if search_db.lower() == 'opensearch':
                    from opensearchpy import OpenSearch
                    
                    # Get connection params
                    host = config.get('host', 'localhost')
                    port = config.get('port', 9201)
                    http_auth = None
                    if config.get('username') and config.get('password'):
                        http_auth = (config.get('username'), config.get('password'))
                    
                    # Connect to OpenSearch
                    client = OpenSearch(
                        hosts=[{'host': host, 'port': port}],
                        http_auth=http_auth,
                        use_ssl=config.get('use_ssl', False),
                        verify_certs=config.get('verify_certs', False),
                        ssl_show_warn=False
                    )
                    
                    print(f"  Connected to OpenSearch: {host}:{port}")
                    
                    # Check if index exists
                    if client.indices.exists(index=index_name):
                        client.indices.delete(index=index_name)
                        print(f"  Deleted index: {index_name}")
                    else:
                        print(f"  Index '{index_name}' does not exist (already clean)")
                    
                    client.close()
                
                else:  # elasticsearch
                    from elasticsearch import Elasticsearch
                    
                    # Get connection params
                    host = config.get('host', 'localhost')
                    port = config.get('port', 9200)
                    use_ssl = config.get('use_ssl', False)
                    verify_certs = config.get('verify_certs', False)
                    
                    # Build URL with proper scheme
                    scheme = 'https' if use_ssl else 'http'
                    url = f"{scheme}://{host}:{port}"
                    
                    # Build connection params
                    client_params = {
                        'hosts': [url],
                        'verify_certs': verify_certs
                    }
                    
                    # Add basic auth if provided
                    if config.get('username') and config.get('password'):
                        client_params['basic_auth'] = (config.get('username'), config.get('password'))
                    
                    # Connect to Elasticsearch
                    client = Elasticsearch(**client_params)
                    
                    print(f"  Connected to Elasticsearch: {url}")
                    
                    # Check if index exists
                    if client.indices.exists(index=index_name):
                        client.indices.delete(index=index_name)
                        print(f"  Deleted index: {index_name}")
                    else:
                        print(f"  Index '{index_name}' does not exist (already clean)")
                    
                    client.close()
                
                print(f"  Search store cleanup: SUCCESS")
                return
                
            except Exception as e:
                print(f"  Direct client cleanup failed: {e}")
                print(f"  Falling back to LlamaIndex method...")
        
        # Fallback: Create search store using factory and try LlamaIndex methods
        search_store = DatabaseFactory.create_search_store(
            db_type=db_type_enum,
            config=config
        )
        
        # Use LlamaIndex to clear the store
        print(f"  Clearing search store...")
        try:
            # Different stores have different clear methods
            if hasattr(search_store, 'delete_index'):
                search_store.delete_index()
                print(f"  Deleted index using delete_index()")
            elif hasattr(search_store, 'clear'):
                search_store.clear()
                print(f"  Cleared search store using clear()")
            else:
                # Fallback: try to delete via client
                if hasattr(search_store, '_client') and hasattr(search_store._client, 'client'):
                    client = search_store._client.client
                    if hasattr(client, 'indices'):
                        if client.indices.exists(index=index_name):
                            client.indices.delete(index=index_name)
                            print(f"  Deleted index: {index_name}")
                        else:
                            print(f"  Index '{index_name}' does not exist")
                    else:
                        print(f"  WARNING: No indices method available")
                else:
                    print(f"  WARNING: No known delete method for {search_db}")
        except Exception as e:
            print(f"  Note: {e}")
            print(f"  (Index may not exist yet)")
        
        print(f"  Search store cleanup: SUCCESS")
        
    except Exception as e:
        print(f"  Search store cleanup: FAILED - {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Close any connections
        if search_store is not None:
            try:
                if hasattr(search_store, 'close'):
                    search_store.close()
                elif hasattr(search_store, '_client'):
                    if hasattr(search_store._client, 'close'):
                        search_store._client.close()
                    elif hasattr(search_store._client, 'client') and hasattr(search_store._client.client, 'close'):
                        search_store._client.client.close()
            except Exception:
                pass  # Ignore close errors

def cleanup_graph_store():
    """Clean graph store using LlamaIndex abstractions"""
    print("\n=== Graph Store Cleanup ===")
    try:
        from factories import DatabaseFactory
        from config import GraphDBType
        
        # Get graph database type
        graph_db = os.getenv('GRAPH_DB', 'neo4j')
        print(f"  Graph DB type: {graph_db}")
        
        if graph_db == 'none':
            print("  Skipped: GRAPH_DB=none (no graph database configured)")
            return
        
        # Parse GRAPH_DB_CONFIG
        graph_db_config_str = os.getenv('GRAPH_DB_CONFIG', '{}')
        config = json.loads(graph_db_config_str)
        
        # For Neo4j, use direct driver for more control over cleanup
        if graph_db.lower() == 'neo4j':
            from neo4j import GraphDatabase
            
            uri = config.get('url', 'bolt://localhost:7687')
            username = config.get('username', 'neo4j')
            password = config.get('password', 'password')
            
            print(f"  Connecting to Neo4j: {uri}")
            
            driver = None
            try:
                driver = GraphDatabase.driver(uri, auth=(username, password))
                
                with driver.session() as session:
                    # Delete all nodes and relationships
                    session.run("MATCH (n) DETACH DELETE n")
                    print(f"  Deleted all nodes and relationships")
                    
                    # Drop constraints (if they exist)
                    constraints = [
                        "DROP CONSTRAINT constraint_907a464e IF EXISTS",
                        "DROP CONSTRAINT constraint_ec67c859 IF EXISTS"
                    ]
                    for constraint_cmd in constraints:
                        try:
                            session.run(constraint_cmd)
                            print(f"  Dropped constraint: {constraint_cmd.split()[2]}")
                        except Exception:
                            pass  # Constraint may not exist
                    
                    # Drop only custom indexes (leave node/relationship type indexes alone)
                    # Note: Vector and Search indexes (hybrid_search_vector, hybrid_search_fulltext)
                    # are in their respective databases (Qdrant, Elasticsearch), not Neo4j
                    indexes = [
                        "DROP INDEX entity IF EXISTS"  # Entity name index in Neo4j graph
                    ]
                    for index_cmd in indexes:
                        try:
                            session.run(index_cmd)
                            print(f"  Dropped index: {index_cmd.split()[2]}")
                        except Exception:
                            pass  # Index may not exist
                
                print("  Neo4j cleanup: SUCCESS")
            finally:
                # Ensure driver is closed even if errors occur
                if driver is not None:
                    driver.close()
                    print("  Neo4j driver closed")
        else:
            # For other graph stores, try using LlamaIndex
            try:
                db_type_enum = GraphDBType(graph_db.lower())
            except ValueError:
                print(f"  ERROR: Unknown graph DB type: {graph_db}")
                return
                
            graph_store = DatabaseFactory.create_graph_store(
                db_type=db_type_enum,
                config=config
            )
            
            print(f"  Clearing graph store...")
            if hasattr(graph_store, 'clear'):
                graph_store.clear()
                print(f"  Cleared graph store using clear()")
            else:
                print(f"  WARNING: No known clear method for {graph_db}")
            
            print(f"  Graph store cleanup: SUCCESS")
        
    except Exception as e:
        print(f"  Graph store cleanup: FAILED - {e}")
        import traceback
        traceback.print_exc()

def main():
    print("=" * 60)
    print("Flexible GraphRAG - Database Cleanup Script")
    print("=" * 60)
    print("\nWARNING: This will DELETE ALL DATA from:")
    print("  - PostgreSQL (document_state, datasource_config)")
    print("  - Vector Store (all embeddings)")
    print("  - Search Store (all fulltext indexes)")
    print("  - Graph Store (all nodes, relationships, constraints, indexes)")
    print("\nThis action CANNOT be undone!")
    
    response = input("\nProceed with cleanup? [y/N] (default: N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("\nCleanup cancelled.")
        sys.exit(0)
    
    print("\nStarting cleanup...")
    
    cleanup_postgres()
    cleanup_vector_store()
    cleanup_search_store()
    cleanup_graph_store()
    
    print("\n" + "=" * 60)
    print("Cleanup complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
