#!/usr/bin/env python3
"""
Database Cleanup Script for Flexible GraphRAG
Wipes all data from PostgreSQL, Qdrant, Elasticsearch/OpenSearch, and Neo4j
"""
import os
import sys
import json
import platform
from pathlib import Path

# Suppress the harmless Windows ProactorEventLoop "Error on reading from the
# event loop self pipe" [WinError 87] that fires on process exit when a library
# (e.g. SurrealDB websocket) closes an async socket while the IOCP handle is
# still registered.  The error bypasses normal exception handling and is routed
# through loop.call_exception_handler() — so we silence it there.
if platform.system() == "Windows":
    import asyncio
    import asyncio.proactor_events as _pev

    _orig_exception_handler = asyncio.BaseEventLoop.call_exception_handler

    def _quiet_exception_handler(self, context: dict) -> None:
        exc = context.get("exception")
        msg = context.get("message", "")
        if (
            isinstance(exc, OSError)
            and getattr(exc, "winerror", None) == 87  # ERROR_INVALID_PARAMETER
            and "self pipe" in msg.lower()
        ):
            return  # swallow — harmless Windows IOCP teardown noise
        _orig_exception_handler(self, context)

    asyncio.BaseEventLoop.call_exception_handler = _quiet_exception_handler  # type: ignore[method-assign]

# Resolve paths relative to this script's location (scripts/)
_SCRIPTS_DIR = Path(__file__).parent.resolve()
_APP_DIR = (_SCRIPTS_DIR / ".." / "flexible-graphrag").resolve()

# Load .env from the app directory (one level up from scripts/)
from dotenv import load_dotenv
load_dotenv(_APP_DIR / ".env")

# Make app modules importable (factories, config, etc.)
sys.path.insert(0, str(_APP_DIR))

from urllib.parse import urlparse

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

    # Skip when incremental updates are disabled — there is no state to clear.
    incremental_enabled = os.getenv('ENABLE_INCREMENTAL_UPDATES', 'false').lower()
    if incremental_enabled not in ('true', '1', 'yes'):
        print("  Skipped: ENABLE_INCREMENTAL_UPDATES is not enabled")
        return

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

    # Check early — before importing factories/config (which are slow to load)
    vector_db = os.getenv('VECTOR_DB', 'qdrant')
    print(f"  Vector DB type: {vector_db}")
    if vector_db == 'none':
        print("  Skipped: VECTOR_DB=none (no vector database configured)")
        return

    vector_store = None
    try:
        from factories import DatabaseFactory
        from config import VectorDBType
        
        # Per-store config takes precedence: {TYPE}_VECTOR_DB_CONFIG > VECTOR_DB_CONFIG
        # This matches the precedence order in config.py.__init__
        _vtype_upper = vector_db.upper()
        vector_db_config_str = (
            os.getenv(f"{_vtype_upper}_VECTOR_DB_CONFIG")
            or os.getenv('VECTOR_DB_CONFIG')
            or '{}'
        )
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
                    client = QdrantClient(url=url, api_key=api_key, check_compatibility=False)
                    print(f"  Connected to Qdrant: {url}")
                else:
                    client = QdrantClient(host=host, port=port, check_compatibility=False)
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
        
        # For Neo4j, use the driver to clear vector index nodes directly
        elif vector_db.lower() == 'neo4j':
            try:
                from neo4j import GraphDatabase

                uri = config.get('url', 'bolt://localhost:7687')
                username = config.get('username', 'neo4j')
                password = config.get('password', 'password')
                index_name = config.get('index_name', 'hybrid_search_vector')

                print(f"  Connecting to Neo4j (vector): {uri}")
                print(f"  Target vector index: {index_name}")

                driver = GraphDatabase.driver(uri, auth=(username, password))
                try:
                    with driver.session() as session:
                        # Delete Chunk nodes (the label Neo4jVectorStore uses)
                        result = session.run("MATCH (n:Chunk) DETACH DELETE n RETURN count(*) AS deleted")
                        deleted = result.single()["deleted"]
                        print(f"  Deleted {deleted} Chunk node(s) from Neo4j vector store")

                        # Drop the named vector index so it is recreated fresh on next ingest
                        session.run(f"DROP INDEX `{index_name}` IF EXISTS")
                        print(f"  Dropped vector index: {index_name}")
                finally:
                    driver.close()

                print(f"  Vector store cleanup: SUCCESS")
                return

            except Exception as e:
                print(f"  Neo4j vector cleanup failed: {e}")
                print(f"  Falling back to generic method...")

        # Milvus: drop and recreate the collection (cleanest reset)
        elif vector_db.lower() == 'milvus':
            try:
                from pymilvus import connections, utility, Collection

                host = config.get('host', 'localhost')
                port = str(config.get('port', 19530))
                uri = config.get('uri')
                collection_name = config.get('collection_name', 'hybrid_search')

                if uri:
                    connections.connect("default", uri=uri)
                    print(f"  Connected to Milvus: {uri}")
                else:
                    connections.connect("default", host=host, port=port)
                    print(f"  Connected to Milvus: {host}:{port}")

                if utility.has_collection(collection_name):
                    utility.drop_collection(collection_name)
                    print(f"  Dropped collection: {collection_name}")
                else:
                    print(f"  Collection '{collection_name}' does not exist (already clean)")

                connections.disconnect("default")
                print(f"  Vector store cleanup: SUCCESS")
                return

            except Exception as e:
                print(f"  Milvus cleanup failed: {e}")
                import traceback
                traceback.print_exc()
                return

        # Weaviate: use sync client (v4) to delete the collection
        elif vector_db.lower() == 'weaviate':
            try:
                import weaviate

                url = config.get('url', 'http://localhost:8081')
                grpc_port = config.get('grpc_port', 50051)
                index_name = config.get('index_name', 'HybridSearch')
                api_key = config.get('api_key')

                # Parse host and port from url
                http_secure = url.startswith('https://')
                stripped = url.replace('https://', '').replace('http://', '')
                if ':' in stripped:
                    host_part, port_part = stripped.rsplit(':', 1)
                    try:
                        http_port = int(port_part)
                    except ValueError:
                        http_port = 443 if http_secure else 8081
                    wv_host = host_part
                else:
                    wv_host = stripped
                    http_port = 443 if http_secure else 8081

                print(f"  Connecting to Weaviate: {url}")
                print(f"  Target collection: {index_name}")

                from weaviate.classes.init import AdditionalConfig, Timeout
                kwargs = dict(
                    http_host=wv_host,
                    http_port=http_port,
                    http_secure=http_secure,
                    grpc_host=wv_host,
                    grpc_port=grpc_port,
                    grpc_secure=http_secure,
                    skip_init_checks=True,
                    additional_config=AdditionalConfig(timeout=Timeout(init=60, query=60, insert=180)),
                )
                if api_key:
                    from weaviate.classes.init import Auth
                    kwargs['auth_credentials'] = Auth.api_key(api_key)

                # Use sync client — no asyncio.run() needed
                client = weaviate.connect_to_custom(**kwargs)
                try:
                    try:
                        client.collections.delete(index_name)
                        print(f"  Deleted collection: {index_name}")
                    except Exception as e:
                        if 'not found' in str(e).lower() or '404' in str(e):
                            print(f"  Collection '{index_name}' does not exist (already clean)")
                        else:
                            raise
                finally:
                    client.close()

                print(f"  Vector store cleanup: SUCCESS")
                return

            except Exception as e:
                print(f"  Weaviate cleanup failed: {e}")
                import traceback
                traceback.print_exc()
                return

        # LanceDB: drop the table
        elif vector_db.lower() == 'lancedb':
            try:
                import lancedb

                uri = config.get('uri', './lancedb')
                table_name = config.get('table_name', 'hybrid_search')

                print(f"  Opening LanceDB at: {uri}")
                db = lancedb.connect(uri)

                table_names = db.table_names()
                if table_name in table_names:
                    db.drop_table(table_name)
                    print(f"  Dropped table: {table_name}")
                else:
                    print(f"  Table '{table_name}' does not exist (already clean)")

                print(f"  Vector store cleanup: SUCCESS")
                return

            except Exception as e:
                print(f"  LanceDB cleanup failed: {e}")
                import traceback
                traceback.print_exc()
                return


        # Pinecone: delete all vectors in the index (namespace-scoped or full index)
        elif vector_db.lower() == 'pinecone':
            try:
                from pinecone import Pinecone

                api_key = config.get('api_key') or os.getenv('PINECONE_API_KEY')
                index_name = config.get('index_name', 'hybrid-search')
                namespace = config.get('namespace', '')

                if not api_key:
                    print("  ERROR: PINECONE_API_KEY not set")
                    return

                pc = Pinecone(api_key=api_key)
                index = pc.Index(index_name)
                stats = index.describe_index_stats()
                print(f"  Pinecone index '{index_name}': {stats.total_vector_count} vectors")

                if stats.total_vector_count > 0:
                    index.delete(delete_all=True, namespace=namespace or '')
                    print(f"  Deleted all vectors in namespace='{namespace or 'default'}'")
                else:
                    print(f"  Index already empty (already clean)")

                print(f"  Vector store cleanup: SUCCESS")
                return

            except Exception as e:
                print(f"  Pinecone cleanup failed: {e}")
                import traceback
                traceback.print_exc()
                return

        # pgvector (postgres): drop the LangChain-postgres collection table
        elif vector_db.lower() == 'postgres':
            try:
                import psycopg2

                host = config.get('host', 'localhost')
                port = config.get('port', 5433)
                database = config.get('database', 'postgres')
                username = config.get('username') or config.get('user', 'postgres')
                password = config.get('password', '')
                table_name = config.get('table_name', 'hybrid_search_vectors')

                conn_str = config.get('connection_string')
                if conn_str:
                    # Strip asyncpg:// or postgresql+psycopg:// scheme for psycopg2
                    conn_str_pg2 = (
                        conn_str
                        .replace('postgresql+psycopg://', 'postgresql://')
                        .replace('postgresql+asyncpg://', 'postgresql://')
                    )
                    conn = psycopg2.connect(conn_str_pg2)
                else:
                    conn = psycopg2.connect(
                        host=host, port=port, dbname=database,
                        user=username, password=password
                    )

                print(f"  Connected to PostgreSQL: {host}:{port}/{database}")
                cursor = conn.cursor()

                # langchain-postgres (PGVector) creates two tables:
                #   langchain_pg_collection — collection metadata
                #   langchain_pg_embedding  — the actual vectors
                # Deleting all rows from langchain_pg_embedding for this collection
                # is sufficient for a clean slate without dropping schema.
                cursor.execute(
                    "SELECT uuid FROM langchain_pg_collection WHERE name = %s",
                    (table_name,)
                )
                row = cursor.fetchone()
                if row:
                    collection_uuid = row[0]
                    cursor.execute(
                        "DELETE FROM langchain_pg_embedding WHERE collection_id = %s",
                        (collection_uuid,)
                    )
                    deleted = cursor.rowcount
                    cursor.execute(
                        "DELETE FROM langchain_pg_collection WHERE uuid = %s",
                        (collection_uuid,)
                    )
                    conn.commit()
                    print(f"  Deleted {deleted} embeddings and collection '{table_name}'")
                else:
                    print(f"  Collection '{table_name}' does not exist (already clean)")

                cursor.close()
                conn.close()
                print(f"  Vector store cleanup: SUCCESS")
                return

            except Exception as e:
                print(f"  pgvector cleanup failed: {e}")
                import traceback
                traceback.print_exc()
                return

        # Elasticsearch (when used as vector store)
        elif vector_db.lower() == 'elasticsearch':
            try:
                from elasticsearch import Elasticsearch

                url = config.get('url', 'http://localhost:9200')
                index_name = config.get('index_name', collection_name)
                client_params = {'hosts': [url], 'verify_certs': False}
                if config.get('username') and config.get('password'):
                    client_params['basic_auth'] = (config['username'], config['password'])

                client = Elasticsearch(**client_params)
                print(f"  Connected to Elasticsearch: {url}")

                if client.indices.exists(index=index_name):
                    client.indices.delete(index=index_name)
                    print(f"  Deleted index: {index_name}")
                else:
                    print(f"  Index '{index_name}' does not exist (already clean)")

                client.close()
                print(f"  Vector store cleanup: SUCCESS")
                return

            except Exception as e:
                print(f"  Elasticsearch vector cleanup failed: {e}")
                print(f"  Falling back to LlamaIndex method...")

        # Chroma: delete collection
        elif vector_db.lower() == 'chroma':
            try:
                import chromadb

                host = config.get('host')
                port = config.get('port', 8001)
                persist_dir = config.get('persist_directory', './chroma_db')
                coll_name = config.get('collection_name', 'hybrid_search')

                if host:
                    client = chromadb.HttpClient(host=host, port=port)
                    print(f"  Connected to Chroma: {host}:{port}")
                else:
                    client = chromadb.PersistentClient(path=persist_dir)
                    print(f"  Opened Chroma at: {persist_dir}")

                try:
                    client.delete_collection(coll_name)
                    print(f"  Deleted collection: {coll_name}")
                except Exception as ce:
                    if 'does not exist' in str(ce).lower() or 'not found' in str(ce).lower():
                        print(f"  Collection '{coll_name}' does not exist (already clean)")
                    else:
                        raise

                print(f"  Vector store cleanup: SUCCESS")
                return

            except Exception as e:
                print(f"  Chroma cleanup failed: {e}")
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

    # Early exit before slow imports
    search_db = os.getenv('SEARCH_DB', 'elasticsearch')
    print(f"  Search DB type: {search_db}")
    if search_db == 'none' or search_db == 'bm25':
        print(f"  Skipped: SEARCH_DB={search_db} (no external search database)")
        return

    search_store = None
    try:
        from factories import DatabaseFactory
        from config import SearchDBType
        
        # Per-store config takes precedence: {TYPE}_SEARCH_DB_CONFIG > SEARCH_DB_CONFIG
        _stype_upper = search_db.upper()
        search_db_config_str = (
            os.getenv(f"{_stype_upper}_SEARCH_DB_CONFIG")
            or os.getenv('SEARCH_DB_CONFIG')
            or '{}'
        )
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

    # Early exit before slow imports
    graph_db = os.getenv('PG_GRAPH_DB', os.getenv('GRAPH_DB', 'neo4j'))
    print(f"  Graph DB type: {graph_db}")
    if graph_db == 'none':
        print("  Skipped: GRAPH_DB=none (no graph database configured)")
        return

    try:
        from factories import DatabaseFactory
        from config import PropertyGraphType
        
        # Parse graph DB config — per-store key takes precedence over generic fallback.
        # Pattern: {TYPE}_GRAPH_DB_CONFIG (e.g. NEPTUNE_GRAPH_DB_CONFIG, NEO4J_GRAPH_DB_CONFIG)
        per_store_key = f"{graph_db.upper()}_GRAPH_DB_CONFIG"
        graph_db_config_str = (
            os.getenv(per_store_key)
            or os.getenv('GRAPH_DB_CONFIG')
            or '{}'
        )
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

                    # Drop ALL user constraints dynamically.
                    # Both LlamaIndex (__Node__, __Relationship__) and LangChain (Chunk)
                    # create auto-named constraints — discover and drop them all so the
                    # next ingest starts with a clean schema.
                    try:
                        constraint_records = session.run(
                            "SHOW CONSTRAINTS YIELD name RETURN name"
                        ).data()
                        for row in constraint_records:
                            cname = row.get("name", "")
                            if not cname:
                                continue
                            try:
                                session.run(f"DROP CONSTRAINT `{cname}` IF EXISTS")
                                print(f"  Dropped constraint: {cname}")
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"  Could not list constraints: {e}")

                    # Drop ALL non-LOOKUP indexes dynamically.
                    # Includes VECTOR (entity embedding), RANGE (Chunk.id), FULLTEXT, etc.
                    # LOOKUP indexes are Neo4j built-ins and must not be dropped.
                    try:
                        index_records = session.run(
                            "SHOW INDEXES YIELD name, type WHERE type <> 'LOOKUP' RETURN name, type"
                        ).data()
                        for row in index_records:
                            iname = row.get("name", "")
                            itype = row.get("type", "")
                            if not iname:
                                continue
                            try:
                                session.run(f"DROP INDEX `{iname}` IF EXISTS")
                                print(f"  Dropped {itype} index: {iname}")
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"  Could not list indexes: {e}")

                print("  Neo4j cleanup: SUCCESS")
            finally:
                # Ensure driver is closed even if errors occur
                if driver is not None:
                    driver.close()
                    print("  Neo4j driver closed")
        elif graph_db.lower() == 'arcadedb':
            host = config.get('host', 'localhost')
            port = config.get('port', 2480)
            username = config.get('username', 'root')
            password = config.get('password', 'playwithdata')
            database = config.get('database', 'graph')

            print(f"  Connecting to ArcadeDB: {host}:{port}/{database}")

            try:
                from arcadedb_python.api.sync import SyncClient
                from arcadedb_python.dao.database import DatabaseDao

                client = SyncClient(
                    host=host,
                    port=port,
                    username=username,
                    password=password,
                    content_type="application/json"
                )
                db = DatabaseDao(client, database)

                # Get all vertex and edge types from schema
                vertex_types = []
                edge_types = []
                try:
                    result = db.query("sql", "SELECT name FROM schema:types WHERE type = 'vertex'")
                    if isinstance(result, list):
                        vertex_types = [r['name'] for r in result if isinstance(r, dict) and 'name' in r]
                except Exception as e:
                    print(f"  Could not query vertex types: {e}")

                try:
                    result = db.query("sql", "SELECT name FROM schema:types WHERE type = 'edge'")
                    if isinstance(result, list):
                        edge_types = [r['name'] for r in result if isinstance(r, dict) and 'name' in r]
                except Exception as e:
                    print(f"  Could not query edge types: {e}")

                print(f"  Found vertex types: {vertex_types}")
                print(f"  Found edge types: {edge_types}")

                # Delete all edges first
                total_edges = 0
                for edge_type in edge_types:
                    try:
                        db.query("sql", f"DELETE FROM {edge_type}", is_command=True)
                        print(f"  Deleted all records from edge type: {edge_type}")
                        total_edges += 1
                    except Exception as e:
                        print(f"  Could not delete from {edge_type}: {e}")

                # Delete all vertices
                total_vertices = 0
                for vertex_type in vertex_types:
                    try:
                        db.query("sql", f"DELETE FROM {vertex_type}", is_command=True)
                        print(f"  Deleted all records from vertex type: {vertex_type}")
                        total_vertices += 1
                    except Exception as e:
                        print(f"  Could not delete from {vertex_type}: {e}")

                print(f"  Cleared {total_edges} edge types and {total_vertices} vertex types")
                print(f"  Graph store cleanup: SUCCESS")

            except Exception as e:
                print(f"  ArcadeDB cleanup: FAILED - {e}")
                import traceback
                traceback.print_exc()

        elif graph_db.lower() == 'arangodb':
            from arango import ArangoClient
            # ArangoDB config is in ARANGODB_GRAPH_DB_CONFIG; fall back to GRAPH_DB_CONFIG
            _arango_cfg_str = os.getenv('ARANGODB_GRAPH_DB_CONFIG') or os.getenv('GRAPH_DB_CONFIG', '{}')
            _arango_cfg = json.loads(_arango_cfg_str)
            url = _arango_cfg.get('url', 'http://localhost:8529')
            database = _arango_cfg.get('database', 'flexible-graphrag')
            username = _arango_cfg.get('username', 'root')
            password = _arango_cfg.get('password', '')
            graph_name = _arango_cfg.get('graph_name', 'knowledge_graph')

            print(f"  Connecting to ArangoDB: {url} (database: {database})")
            try:
                import warnings, logging as _logging
                _logging.getLogger("urllib3").setLevel(_logging.ERROR)

                client = ArangoClient(hosts=url)
                db = client.db(database, username=username, password=password, verify=True)

                if db.has_graph(graph_name):
                    db.delete_graph(graph_name, drop_collections=True)
                    print(f"  Dropped graph '{graph_name}' and its collections")
                else:
                    print(f"  Graph '{graph_name}' does not exist (already clean)")

                # Truncate any lingering LangChain framework collections
                for col_name in [f"{graph_name}_ENTITY", f"{graph_name}_LINKS_TO",
                                 f"{graph_name}_SOURCE", f"{graph_name}_HAS_SOURCE",
                                 "__Entity__", "__Relationship__"]:
                    if db.has_collection(col_name):
                        db.collection(col_name).truncate()
                        print(f"  Truncated collection: {col_name}")

                print(f"  ArangoDB cleanup: SUCCESS")
            except Exception as e:
                if "10061" in str(e) or "Connection refused" in str(e) or "Failed to establish" in str(e) or "NewConnectionError" in str(e):
                    print(f"  Skipped: ArangoDB is not running at {url}")
                else:
                    print(f"  ArangoDB cleanup: FAILED - {e}")
                    import traceback
                    traceback.print_exc()

        elif graph_db.lower() == 'neptune':
            import boto3

            host = config.get('host', '')
            port = config.get('port', 8182)
            region = config.get('region', 'us-east-1')
            access_key = config.get('access_key') or config.get('aws_access_key_id')
            secret_key = config.get('secret_key') or config.get('aws_secret_access_key')
            profile = config.get('credentials_profile_name')

            if not host:
                print("  WARN: 'host' missing from NEPTUNE_GRAPH_DB_CONFIG — skipping Neptune cleanup")
                print("  (Set NEPTUNE_GRAPH_DB_CONFIG with a 'host' key to enable Neptune cleanup)")
                return

            endpoint_url = f"https://{host}:{port}"
            print(f"  Connecting to Neptune: {endpoint_url}")

            if profile:
                import boto3.session as _bs
                boto_session = _bs.Session(profile_name=profile, region_name=region)
                client = boto_session.client("neptunedata", endpoint_url=endpoint_url)
            elif access_key and secret_key:
                client = boto3.client(
                    "neptunedata",
                    region_name=region,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    endpoint_url=endpoint_url,
                )
            else:
                client = boto3.client("neptunedata", region_name=region,
                                      endpoint_url=endpoint_url)

            client.execute_open_cypher_query(openCypherQuery="MATCH (n) DETACH DELETE n")
            print("  Deleted all nodes and relationships")
            print("  Graph store cleanup: SUCCESS")

        elif graph_db.lower() == 'neptune_analytics':
            import boto3

            graph_id = config.get('graph_identifier', '')
            region = config.get('region', 'us-east-1')
            access_key = config.get('access_key') or config.get('aws_access_key_id')
            secret_key = config.get('secret_key') or config.get('aws_secret_access_key')
            profile = config.get('credentials_profile_name')

            if not graph_id:
                print("  WARN: 'graph_identifier' missing from NEPTUNE_ANALYTICS_GRAPH_DB_CONFIG — skipping cleanup")
                print("  (Set NEPTUNE_ANALYTICS_GRAPH_DB_CONFIG with a 'graph_identifier' key to enable cleanup)")
                return

            endpoint_url = f"https://{graph_id}.neptune-graph.{region}.amazonaws.com"
            print(f"  Connecting to Neptune Analytics: {graph_id} ({region})")

            if profile:
                import boto3.session as _bs
                boto_session = _bs.Session(profile_name=profile, region_name=region)
                client = boto_session.client("neptune-graph", region_name=region)
            elif access_key and secret_key:
                client = boto3.client(
                    "neptune-graph",
                    region_name=region,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                )
            else:
                client = boto3.client("neptune-graph", region_name=region)

            client.execute_query(
                graphIdentifier=graph_id,
                queryString="MATCH (n) DETACH DELETE n",
                language="OPEN_CYPHER",
            )
            print("  Deleted all nodes and relationships")
            print("  Graph store cleanup: SUCCESS")

        elif graph_db.lower() == 'cosmos_gremlin':
            # Azure Cosmos DB for Gremlin — drop all vertices (edges deleted automatically)
            url      = config.get('url', 'ws://localhost:8182/gremlin')
            username = config.get('username', '/')
            password = config.get('password', '')
            print(f"  Connecting to Cosmos DB Gremlin: {url}")
            try:
                from gremlin_python.driver import client as gremlin_client, serializer
                gc = gremlin_client.Client(
                    url, 'g',
                    username=username,
                    password=password,
                    message_serializer=serializer.GraphSONSerializersV2d0(),
                )
                result = gc.submitAsync("g.V().drop()").result()
                gc.close()
                print("  Dropped all vertices (and their edges)")
                print("  Graph store cleanup: SUCCESS")
            except Exception as e:
                print(f"  Cosmos DB Gremlin cleanup: FAILED - {e}")
                import traceback; traceback.print_exc()

        elif graph_db.lower() == 'apache_age':
            # Apache AGE — drop and recreate the graph
            host       = config.get('host', 'localhost')
            port       = int(config.get('port', 5434))
            database   = config.get('database', 'flexible_graphrag_age')
            username   = config.get('username', 'postgres')
            password   = config.get('password', 'password')
            graph_name = config.get('graph_name', 'knowledge_graph')
            print(f"  Connecting to Apache AGE: {host}:{port}/{database}")
            try:
                import psycopg2
                conn = psycopg2.connect(
                    host=host, port=port, dbname=database,
                    user=username, password=password,
                )
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("LOAD 'age'")
                    cur.execute("SET search_path = ag_catalog, '$user', public")
                    # Drop the graph (cascade removes all vertices and edges)
                    try:
                        cur.execute(f"SELECT drop_graph('{graph_name}', true)")
                        print(f"  Dropped graph '{graph_name}' (cascade)")
                    except Exception as drop_err:
                        print(f"  Could not drop graph (may not exist): {drop_err}")
                    # Recreate so next ingest works without DDL errors
                    try:
                        cur.execute(f"SELECT create_graph('{graph_name}')")
                        print(f"  Recreated graph '{graph_name}'")
                    except Exception as create_err:
                        print(f"  Could not recreate graph: {create_err}")
                conn.close()
                print("  Graph store cleanup: SUCCESS")
            except Exception as e:
                print(f"  Apache AGE cleanup: FAILED - {e}")
                import traceback; traceback.print_exc()

        elif graph_db.lower() == 'hugegraph':
            # HugeGraph — delete all vertices and edges via REST/Cypher
            host     = config.get('host', 'localhost')
            port     = int(config.get('port', 8082))
            graph    = config.get('database', 'hugegraph')
            username = config.get('username', 'admin')
            password = config.get('password', 'password')
            base_url = f"http://{host}:{port}"
            print(f"  Connecting to HugeGraph: {base_url} (graph: {graph})")
            try:
                import requests as _req
                auth = (username, password) if username else None
                # Use the HugeGraph REST API to clear the graph
                # DELETE /gremlin — drop all edges first, then vertices
                gremlin_url = f"{base_url}/gremlin"
                headers = {"Content-Type": "application/json"}
                for drop_query in ["g.E().drop()", "g.V().drop()"]:
                    resp = _req.post(
                        gremlin_url,
                        json={"gremlin": drop_query, "bindings": {}, "language": "gremlin-groovy", "aliases": {}},
                        auth=auth, headers=headers, timeout=60,
                    )
                    if resp.ok:
                        print(f"  Executed: {drop_query}")
                    else:
                        print(f"  {drop_query} returned {resp.status_code}: {resp.text[:200]}")
                print("  Graph store cleanup: SUCCESS")
            except Exception as e:
                print(f"  HugeGraph cleanup: FAILED - {e}")
                import traceback; traceback.print_exc()

        elif graph_db.lower() == 'surrealdb':
            # SurrealDB — delete all records in every graph_* table
            url       = config.get('url', 'ws://localhost:8010/rpc')
            namespace = config.get('namespace', 'flexible_graphrag')
            database  = config.get('database', 'graphrag')
            username  = config.get('username', 'root')
            password  = config.get('password', 'root')
            print(f"  Connecting to SurrealDB: {url}")
            conn = None
            try:
                from surrealdb.connections.blocking_ws import BlockingWsSurrealConnection
                conn = BlockingWsSurrealConnection(url)
                conn.signin({"username": username, "password": password})
                conn.use(namespace, database)
                # List all tables and delete those belonging to the graph
                info_result = conn.query_raw("INFO FOR DB")
                tables = []
                if info_result and isinstance(info_result, list):
                    tb_dict = info_result[0].get("result", {}).get("tb", {}) if info_result[0] else {}
                    tables = list(tb_dict.keys())
                elif info_result and isinstance(info_result, dict):
                    tables = list(info_result.get("result", {}).get("tb", {}).keys())
                print(f"  Tables found: {tables}")
                deleted = 0
                for tbl in tables:
                    if tbl.startswith(("graph_", "relation_", "Graph_", "Relation_")):
                        conn.query_raw(f"DELETE {tbl}")
                        print(f"  Deleted all records from: {tbl}")
                        deleted += 1
                if deleted == 0:
                    print("  No graph tables found (already clean or nothing ingested yet)")
                print("  Graph store cleanup: SUCCESS")
            except Exception as e:
                print(f"  SurrealDB cleanup: FAILED - {e}")
                import traceback; traceback.print_exc()
            finally:
                # Close the websocket explicitly so the asyncio event loop can
                # shut down cleanly on Windows (avoids ProactorEventLoop noise).
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        elif graph_db.lower() == 'tigergraph':
            # TigerGraph — clear all vertices and edges via GSQL
            host        = config.get('host', 'http://localhost')
            gs_port     = int(config.get('port', 14240))
            restpp_port = int(config.get('restpp_port', 9002))
            graphname   = config.get('database', 'MyGraph')
            username    = config.get('username', 'tigergraph')
            password    = config.get('password', 'tigergraph')
            print(f"  Connecting to TigerGraph: {host} (GSQL port {gs_port}, graph {graphname})")
            try:
                from pyTigerGraph import TigerGraphConnection
                conn = TigerGraphConnection(
                    host=host,
                    graphname=graphname,
                    username=username,
                    password=password,
                    gsPort=gs_port,
                    restppPort=restpp_port,
                )
                conn.ai.nlqs_host = host  # bypass Cloud NLQS requirement for local Docker
                # Drop and recreate the graph — cleanest way to reset all data + schema
                gsql_script = "\n".join([
                    "USE GLOBAL",
                    f"DROP GRAPH {graphname}",
                    f"CREATE GRAPH {graphname}()",
                ])
                result = conn.gsql(gsql_script)
                print(f"  GSQL result: {str(result)[:300]}")
                print("  Graph store cleanup: SUCCESS")
            except Exception as e:
                print(f"  TigerGraph cleanup: FAILED - {e}")
                import traceback; traceback.print_exc()

        elif graph_db.lower() == 'spanner':
            # Google Cloud Spanner Graph — delete all graph nodes and edges via DML.
            # use_flexible_schema=true (default): llama-index-spanner creates tables named
            #   {graph_name}_EDGE and {graph_name}_NODE  (e.g. knowledge_graph_EDGE / _NODE).
            # use_flexible_schema=false (strongly typed): __Entity__ + __Relationship__.
            project_id   = config.get('project_id', '')
            instance_id  = config.get('instance_id', '')
            database_id  = config.get('database_id', '')
            creds_file   = config.get('credentials_file') or config.get('credentials')
            graph_name   = config.get('graph_name', 'knowledge_graph')
            use_flexible = config.get('use_flexible_schema', True)
            if isinstance(use_flexible, str):
                use_flexible = use_flexible.lower() not in ('false', '0', 'no')
            # Auto-detect gcs.json next to flexible-graphrag/ if credentials_file not set.
            if not creds_file:
                _candidate = os.path.join(os.path.dirname(__file__), '..', 'flexible-graphrag', 'gcs.json')
                if os.path.isfile(_candidate):
                    creds_file = os.path.normpath(_candidate)
            if not project_id or not instance_id or not database_id:
                print("  ERROR: spanner config requires project_id, instance_id, database_id")
                return
            print(f"  Connecting to Spanner: projects/{project_id}/instances/{instance_id}/databases/{database_id}")
            # Disable Spanner client-side metrics export to Cloud Monitoring.
            # Outside GCE the client emits "Failed to export metrics" 400 errors
            # because it can't populate the instance_id resource label.
            os.environ["SPANNER_DISABLE_BUILTIN_METRICS"] = "true"
            try:
                from google.cloud import spanner
                from google.api_core.exceptions import PermissionDenied
                if creds_file:
                    from google.oauth2 import service_account as _sa
                    _creds = _sa.Credentials.from_service_account_file(
                        creds_file,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    )
                    spanner_client = spanner.Client(project=project_id, credentials=_creds)
                    print(f"  Using credentials: {creds_file}")
                else:
                    spanner_client = spanner.Client(project=project_id)
                from google.api_core.exceptions import NotFound
                instance = spanner_client.instance(instance_id)
                database = instance.database(database_id)
                # flexible_schema: {graph_name}_EDGE before {graph_name}_NODE (FK constraint).
                # strongly-typed: __Relationship__ before __Entity__.
                if use_flexible:
                    tables = [f"{graph_name}_EDGE", f"{graph_name}_NODE"]
                else:
                    tables = ["__Relationship__", "__Entity__"]
                # Each table in its own batch so a missing table doesn't abort the others.
                # batch.delete() only buffers — the 404 fires at commit() when the context exits.
                any_deleted = False
                for table in tables:
                    try:
                        with database.batch() as batch:
                            batch.delete(table, spanner.KeySet(all_=True))
                        print(f"  Deleted all rows from {table}")
                        any_deleted = True
                    except NotFound:
                        print(f"  Skipped {table}: table does not exist yet (no ingest run)")
                    except Exception as tbl_err:
                        print(f"  Could not delete from {table}: {tbl_err}")
                if any_deleted:
                    print("  Graph store cleanup: SUCCESS")
                else:
                    print("  Graph store cleanup: nothing to delete (tables not yet created by ingest)")
            except PermissionDenied as e:
                print(f"  Spanner cleanup: SKIPPED - IAM permission denied.")
                print(f"  The service account needs 'Cloud Spanner Database User' role")
                print(f"  (roles/spanner.databaseUser) on the database, or at minimum:")
                print(f"    spanner.sessions.create, spanner.databases.beginReadOnlyTransaction,")
                print(f"    spanner.databases.beginOrRollbackReadWriteTransaction")
                print(f"  Grant via GCP Console: IAM & Admin -> IAM -> your service account -> Edit -> Add role")
                print(f"  Or via gcloud: gcloud spanner databases add-iam-policy-binding {database_id}")
                print(f"    --instance={instance_id} --member=serviceAccount:<sa-email>")
                print(f"    --role=roles/spanner.databaseUser")
            except Exception as e:
                print(f"  Spanner cleanup: FAILED - {e}")
                import traceback; traceback.print_exc()

        elif graph_db.lower() == 'falkordb':
            # FalkorDB — delete all nodes and relationships via Cypher
            host     = config.get('host', 'localhost')
            port     = int(config.get('port', 6379))
            password = config.get('password') or config.get('pwd') or None
            graph    = config.get('database', 'knowledge_graph')
            print(f"  Connecting to FalkorDB: {host}:{port} (graph: {graph})")
            try:
                import falkordb
                client = falkordb.FalkorDB(host=host, port=port, password=password)
                g = client.select_graph(graph)
                g.query("MATCH (n) DETACH DELETE n")
                print("  Deleted all nodes and relationships")
                print("  Graph store cleanup: SUCCESS")
            except Exception as e:
                print(f"  FalkorDB cleanup: FAILED - {e}")
                import traceback; traceback.print_exc()

        elif graph_db.lower() == 'memgraph':
            # Memgraph — delete all nodes and relationships via Bolt/Cypher
            host     = config.get('host', 'localhost')
            port     = int(config.get('port', 7687))
            username = config.get('username', '')
            password = config.get('password', '')
            print(f"  Connecting to Memgraph: {host}:{port}")
            try:
                from neo4j import GraphDatabase as _GDB
                driver = _GDB.driver(
                    f"bolt://{host}:{port}",
                    auth=(username, password) if username else ("", ""),
                )
                with driver.session() as session:
                    session.run("MATCH (n) DETACH DELETE n")
                    print("  Deleted all nodes and relationships")
                    # Drop storage mode index if present (Memgraph-specific)
                    try:
                        session.run("DROP INDEX ON :__Node__(id)")
                    except Exception:
                        pass
                driver.close()
                print("  Graph store cleanup: SUCCESS")
            except Exception as e:
                print(f"  Memgraph cleanup: FAILED - {e}")
                import traceback; traceback.print_exc()

        elif graph_db.lower() == 'nebula':
            # NebulaGraph — truncate all Tags and Edge types in the space
            host      = config.get('host', 'localhost')
            port      = int(config.get('port', 9669))
            username  = config.get('username', 'root')
            password  = config.get('password', 'nebula')
            space     = config.get('space', 'flexible_graphrag')
            print(f"  Connecting to NebulaGraph: {host}:{port} (space: {space})")
            try:
                from nebula3.gclient.net import ConnectionPool
                from nebula3.Config import Config as NebulaConfig
                cfg = NebulaConfig()
                pool = ConnectionPool()
                pool.init([(host, port)], cfg)
                session = pool.get_session(username, password)
                session.execute(f"USE {space}")
                # Get all tags and edge types, then TRUNCATE each
                tag_result   = session.execute("SHOW TAGS")
                edge_result  = session.execute("SHOW EDGES")
                tags  = [row.values()[0].as_string() for row in tag_result.rows()]
                edges = [row.values()[0].as_string() for row in edge_result.rows()]
                print(f"  Tags: {tags}  Edge types: {edges}")
                for tag in tags:
                    try:
                        session.execute(f"DELETE TAG {tag} FROM VERTEX *")
                    except Exception:
                        pass
                # Delete all vertices (removes all edges too)
                session.execute("DELETE VERTEX (LOOKUP ON Props__) YIELD VertexID")
                try:
                    session.execute(f"CLEAR SPACE {space}")
                    print(f"  Cleared space '{space}'")
                except Exception:
                    # CLEAR SPACE may not be available — fall back to vertex delete
                    session.execute("DELETE VERTEX * WITH EDGE")
                    print("  Deleted all vertices and edges")
                session.release()
                pool.close()
                print("  Graph store cleanup: SUCCESS")
            except Exception as e:
                print(f"  NebulaGraph cleanup: FAILED - {e}")
                import traceback; traceback.print_exc()

        elif graph_db.lower() == 'ladybug':
            # LadybugDB — delete the .lbug file and any accompanying WAL / temp files.
            # MATCH/DETACH DELETE only removes data; stale table schemas (missing columns)
            # cause "Column embedding does not exist" errors on the next ingest.
            # Ladybug also writes a WAL file (<db>.wal) alongside the main file; if the
            # WAL is left from a previous run with a different database ID, Ladybug raises
            # "Database ID for temporary file does not match" and refuses to start.
            # Deleting all files that share the base name is the safest full reset.
            db_dir  = config.get('db_dir')  or os.getenv('LADYBUG_DB_DIR',  './ladybug_data')
            db_file = config.get('db_file') or os.getenv('LADYBUG_DB_FILE', 'database.lbug')
            import pathlib as _pl
            db_path = _pl.Path(db_dir)
            lbug = db_path / db_file
            # Also remove WAL and any other sidecar files sharing the same stem
            stem = lbug.stem  # e.g. "database"
            print(f"  LadybugDB dir: {db_path}, base: {db_file}")
            try:
                deleted = []
                for candidate in db_path.glob(f"{stem}.*"):
                    candidate.unlink()
                    deleted.append(candidate.name)
                if deleted:
                    print(f"  Deleted: {', '.join(deleted)}")
                else:
                    print(f"  No files found (nothing to clean): {lbug}*")
                print("  Graph store cleanup: SUCCESS")
            except Exception as e:
                print(f"  LadybugDB cleanup: FAILED - {e}")
                import traceback; traceback.print_exc()

        else:
            print(f"  WARNING: No explicit cleanup for '{graph_db}' — skipping.")
            print(f"  Clear data manually via the database's own console/CLI.")
            print(f"  Graph store cleanup: SKIPPED")
        
    except Exception as e:
        print(f"  Graph store cleanup: FAILED - {e}")
        import traceback
        traceback.print_exc()

def cleanup_rdf_stores():
    """Clear all RDF store data via rdf_cleanup.py clear-all"""
    print("\n=== RDF Store Cleanup ===")
    try:
        import subprocess

        rdf_cleanup_path = _SCRIPTS_DIR / "rdf_cleanup.py"

        if not rdf_cleanup_path.exists():
            print(f"  Skipped: rdf_cleanup.py not found at {rdf_cleanup_path}")
            return

        # Build store flags from RDF_GRAPH_DB (new single-store config)
        _RDF_FLAG_MAP = {
            "fuseki":      "--fuseki",
            "graphdb":     "--graphdb",
            "oxigraph":    "--oxigraph",
            "neptune_rdf": "--neptune-rdf",
        }
        store_flags = []
        rdf_graph_db = os.environ.get("RDF_GRAPH_DB", "none").lower().strip()
        if rdf_graph_db in _RDF_FLAG_MAP:
            store_flags.append(_RDF_FLAG_MAP[rdf_graph_db])

        if not store_flags:
            print("  Skipped: no RDF stores enabled in .env.")
            return

        result = subprocess.run(
            [sys.executable, str(rdf_cleanup_path)] + store_flags + ["clear-all", "--yes"],
            capture_output=True,
            text=True
        )
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                print(f"  {line}")
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                print(f"  {line}")
        if result.returncode == 0:
            print("  RDF store cleanup: SUCCESS")
        else:
            print(f"  RDF store cleanup: FAILED (exit code {result.returncode})")

    except Exception as e:
        print(f"  RDF store cleanup: FAILED - {e}")
        import traceback
        traceback.print_exc()


def cleanup_log_files():
    """Delete all *.log files in the flexible-graphrag app directory"""
    print("\n=== Log File Cleanup ===")
    try:
        log_files = [
            f for f in _APP_DIR.iterdir()
            if f.suffix == ".log" and f.is_file()
        ]
        if not log_files:
            print("  No log files found (already clean)")
            return
        deleted = 0
        for log_file in log_files:
            try:
                log_file.unlink()
                print(f"  Deleted: {log_file.name}")
                deleted += 1
            except Exception as e:
                print(f"  Could not delete {log_file.name}: {e}")
        print(f"  Log file cleanup: SUCCESS ({deleted} file(s) deleted)")

    except Exception as e:
        print(f"  Log file cleanup: FAILED - {e}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Flexible GraphRAG cleanup")
    ap.add_argument(
        "--matrix-clean", action="store_true",
        help=(
            "Non-interactive mode for matrix test runner: skips postgres "
            "incremental-update tables and log files; cleans only the "
            "vector/search/graph/RDF stores indicated by env vars."
        ),
    )
    args, _ = ap.parse_known_args()

    if args.matrix_clean:
        # Targeted, non-interactive cleanup for automated matrix runs.
        # When ENABLE_INCREMENTAL_UPDATES=true, also clear the incremental
        # Postgres tables so datasource re-registration starts fresh each run.
        print("=== Matrix clean (vector / search / graph / RDF only) ===")
        cleanup_vector_store()
        cleanup_search_store()
        cleanup_graph_store()
        cleanup_rdf_stores()
        incremental_enabled = os.getenv('ENABLE_INCREMENTAL_UPDATES', 'false').lower()
        if incremental_enabled in ('true', '1', 'yes'):
            print("  ENABLE_INCREMENTAL_UPDATES=true: also clearing incremental Postgres tables...")
            cleanup_postgres()
        print("=== Matrix clean done ===")
        return

    print("=" * 60)
    print("Flexible GraphRAG - Database Cleanup Script")
    print("=" * 60)
    print("\nWARNING: This will DELETE ALL DATA from:")
    print("  - PostgreSQL (document_state, datasource_config)")
    print("  - Vector Store (all embeddings)")
    print("  - Search Store (all fulltext indexes)")
    print("  - Graph Store (all nodes, relationships, constraints, indexes)")
    print("  - RDF Stores (all triples in configured stores)")
    print("  - Log files (all *.log in flexible-graphrag/)")
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
    cleanup_rdf_stores()
    cleanup_log_files()
    
    print("\n" + "=" * 60)
    print("Cleanup complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
