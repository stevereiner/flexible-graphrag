# Changelog

All notable changes to this project will be documented in this file.

## [2025-11-26] - Documentation overhaul and MCP server cleanup

### Enhanced
- **Documentation restructuring** - Created dedicated documentation files for better organization:
  - `docs/ARCHITECTURE.md` - Complete system architecture and component relationships
  - `docs/DEPLOYMENT-CONFIGURATIONS.md` - Standalone, hybrid, and full Docker deployment guides
  - `docs/OLLAMA-CONFIGURATION.md` - Comprehensive Ollama setup and optimization instructions
  - `docs/PERFORMANCE.md` - Performance benchmarks and optimization guides (moved from README.md)
- **README.md improvements** - Added comprehensive coverage of all 13 data sources with visual screenshot, detailed document processing options (Docling vs LlamaParse), complete database configuration for search/vector/graph databases with parameters and dashboards, chat interface showcase with Neo4j graph visualization
- **Database configuration documentation** - Expanded database sections in README.md to include detailed configuration parameters, dashboard URLs, and ideal use cases for all search databases (BM25, Elasticsearch, OpenSearch, None), all vector databases (10 options), and all graph databases (9 options plus None)

### Fixed
- **MCP server cleanup** - Removed unused `fastmcp-server.py` and `requirements.txt` from flexible-graphrag-mcp directory, keeping only HTTP-based `main.py` that uses REST API calls to backend

### Added
- **Visual documentation assets** - Added `screen-shots/react/chat-webpage.png` and `screen-shots/react/data-sources-1.jpeg` for README.md visual improvements
- **LLM configuration section** - Added dedicated LLM Configuration section in README.md with details for OpenAI, Ollama, Azure OpenAI, Anthropic, and Google Gemini providers including required/optional parameters

### Documentation
- `README.md` - Major reorganization with data sources showcase, document processing options, comprehensive database configurations, 
- `docs/ARCHITECTURE.md` - New comprehensive architecture documentation
- `docs/DEPLOYMENT-CONFIGURATIONS.md` - New deployment guide for all three modes
- `docs/OLLAMA-CONFIGURATION.md` - New Ollama-specific configuration guide
- `docs/PERFORMANCE.md` - Performance information consolidated from README.md


## [2025-11-16] - Fix timing logging for graph phase, fix falkordb config setup, fix over-write of neo4j config in env-sample.txt

### Fixed
- In hybrid_system.py, fixed to update graph update start time before graph index insert nodes,
and update the graph creation duration after. This fixed on a second run, to have correct non 0 graph phase sub time (total time for all phases was correct without this).
- In env-sample.txt, for falkordb GRAPH_DB_CONFIG, have database name instead of user, password
and in docker-env-sample.txt added example of falkordb config with database name
- In env-sample.txt, commented out Kuzu GRAPH_DB_CONFIG, that was over-writing the default GRAPH_DB_CONFIG for Neo4j
- in factories.py for falkordb, log database name in addition to url


## [2025-11-10] - Azure Blob Storage data source now also fully working

### Fixed
- **Azure Blob Storage temporary file deletion** - Applied same PassthroughExtractor immediate processing fix as Box and Google Drive, preventing "File does not exist" errors when AzStorageBlobReader cleanup deletes temp files before DocumentProcessor can access them

## [2025-11-08] - LlamaParse added as an additional configurable doc processing choice beyond Docling. Box, Google Drive, GCS data sources now fully working, and the custom configured DocProcessor called from a Passthrough Extractor allows the LlamaIndex Readers to be fully leveraged

### Fixed
- **LlamaParse parse_page_without_llm mode error** - Changed result_type to "text" for parse_page_without_llm mode (was hardcoded "markdown" causing 404 errors), added conditional result_type logic in document_processor.py
- **Box, Google Drive, and Azure Blob temporary file deletion** - Modified PassthroughExtractor to accept doc_processor parameter and process files immediately while they exist in temp directory, preventing "File does not exist" errors when LlamaIndex readers cleanup temp directories after load_data() returns
- **GCS permissions and configuration** - Fixed by granting "Storage Object Viewer" role (Storage Legacy Bucket Reader was insufficient), removed redundant project_id field (already in service account JSON)
- **UI progress indicators for Box/S3** - Fixed React/Vue progress bars by stripping type field from enterpriseConfig/cloudConfig before sending to backend, added fallback for completed files in getFileProgressData
- **S3 region_name configuration** - Changed from hardcoded "us-east-2" to None with fallback to "us-east-1" standard AWS region, fixed None/"None" string handling
- **'NoneType' object is not callable error** - Added safety checks in _process_with_llamaparse for check_cancellation parameter (S3/cloud sources don't pass it)

### Enhanced
- **File count vs chunk count tracking** - Updated BaseDataSource.get_documents_with_progress() to return tuple (file_count, documents) instead of just List[Document], all 13 data sources return proper file counts, IngestionManager stores file_count/chunk_count in PROCESSING_STATUS when they differ, hybrid_system.py completion logic uses stored file_count in both code paths (ingest_documents and _process_documents_direct)
- **LlamaParse filename display in LlamaCloud** - Changed from memory-intensive BytesIO approach to efficient temp file creation with original names at download time, updated process_documents_from_metadata() to use original filename directly, updated Alfresco/CMIS _download_document() to use original filenames
- **Box authentication modes** - Implemented 4-mode authentication UI across all frontends: developer token, CCG with user_id, CCG with enterprise_id, CCG with both, uses BoxClient with BoxDeveloperTokenAuth/BoxCCGAuth and CCGConfig
- **GCS non-recursive file listing** - Added recursive=False to GCSReader initialization to prevent subdirectory traversal, allows prefix-based filtering without recursion
- **Parser type configuration** - Created BaseDataSource._get_document_processor() centralized method ensuring consistent parser_type and Settings across all data sources

### Added
- **GCS UI improvements** - Removed unused folder_name field from all 3 frontends, standardized field ordering (Bucket Name, Prefix, Credentials) across React/Vue/Angular
- **LlamaParse configuration documentation** - Updated env-sample.txt with mode-specific output format clarification (text for parse_page_without_llm, markdown for with_llm and with_agent modes)

### Dependencies
- **llama-index-readers-file** - Added to prevent warnings in Box/Google Drive PassthroughExtractor
- **box-sdk-gen** - Added for Box CCG authentication (BoxClient, BoxCCGAuth, CCGConfig)

## [2025-10-22] - All 10 vector databases working: Pinecone, Weaviate working now, Chroma now supports both http, embedded

### Added
- **Added Chroma HTTP mode**
  - In `factories.py` create_vector_store now also supports chroma http mode in addition to local embedded, and uses what is in vector_db_config to determine which one to setup
  - In `env-sample.txt` has added example for http mode chroma
  - `test_basic.py` has added basic instantiation test for chroma http mode

### Changed
**Pinecone config parameters changed, working now**
  -In `factories.py` create_vector_store now sets up pinecone with a different set of config values
(now cloud, region, metric  instead of environment, namespace). 
  - In `pinecone.yaml`, comments changed to reflect new config paramters, only mention official dashboard, and simpler startup for our pinecone-info datashboard
  - In `env-sample.txt` pinecone config sample updated to use new config parameters (now cloud, region, metric  instead of environment, namespace).
  - In `docker/pinecone-info/index.html` this information dashboard was updated to show the
new config setup parameters, just point to the official dashboard, and an unneeded section was removed 
  - In `requirements.txt` pinecone package added as a requirement
  - test_basic.py has pinecone test updated to use new config parameters

**Weaviate now working**
  - In `weaviate.yaml`, weaviate was changed to get not have errors and work: the image was changed
to be :latest and not an older version, and having the gRPC port added back in by taking the commnent off it.

### Documentation
- `README.md` updated with info on Chroma HTTP mode in addition to local embedded mode,
updated with different vector_db_config parameters that pinecone support needs
- `docs/chroma-deployment-modes.md` added covering setup of the local embedded and http based version of chroma 
(docker chroma.yaml sets local with its data local or in external server) use of rest api to manage the http version 
- `docs/default-usernames-passwords.md`, `docs/vector-database-integration.md`, and `docs/vector-dimensions.md` updated
with pinecone changes, and added http mode chroma


## [2025-10-16] - Amazon Neptune, Neptune Analytics, Graph Explorer now working, .env + docker.env now no duplication

### Added
- Amazon Neptune and Amazon Neptune Analytics graph databases are now working with flexible graphrag
- A local Graph Explorer https://github.com/aws/graph-explorer in a docker works and can be used to query and visualize with both Amazon Neptune and Amazon Neptune Analytics. This is in neptune.yaml
- added docker-env-sample.txt to copy to docker.env
- added neptune-env-sample.txt top copy to neptune.env to provide keys, region to graph explorer in neptune.yaml docker

### Enhanced
- Previously had to repeat all config in app-stack.yaml flexible-graphrag-backend environment: section, Now use env_file: and include standalone backend flexible-graphrag/.env and override with include of docker.env with just the configs that need urls with host.docker.internal instead of localhost inside docker
- env-sample.txt used as a template for backend .env (and now included in app-stack.yaml for docker) was updated with configs for Amazon Neptune and Amazon Neptune Analytics
- factories.py was updated to get working creation of property graph stores for Neptune and Neptune Analytics
- neptune_analytics_wrapper.py has a wrapper class that works around some vector issues Neptune Analytics Property Graph Store and LlamaIndex have
- hybrid_system disables doing vector embeddings with Neptune Analytics

### Documentation
- In docker dir, new DOCKER-ENV-SETUP.md document way to configure docker with the new flexible-graphrag/.env + docker.env, and neptune.eny
- README.md that covers all dockers for the databases, backend/frontends was update to also have coverage of the new two part env config



## [2025-10-10] - S3 Data Source is now fully working and Docling processing added for S3 files

### Enhanced
- **S3 Data Source Rewrite**
  - In `sources/s3.py` was rewritten to use s3fs directly and not use llamaindex S3Reader
  - Downloads S3 files and gives them to DocumentProcessor (which processes with Docling)
  - Sets up llamaindex documents for llamaindex pipeline integration
  - Progress feedback callbacks are also setup in s3.py
  - Fixed to give feedback in terms of number of documents not count of chunks as doc count

- **Backend S3 Progress Handling**
  - In `backend.py` handling of S3 progressing status was setup
  - Removed 2 un-needed processing status updating in general

- **Progress Feedback Improvements**
  - In `ingest/manager.py` was changed to give better doc count progress feedback
  - In `hybrid_system.py` was changed to give specific feedback for YouTube to be one document not chunk for doc count

- **Frontend S3 Integration**
  - In `ProcessingTab.tsx` for React, `ProcessingTab.vue` for Vue, and `processing-tab.ts` for Angular
  - Code was added to get the progress bar and other feedback to work for S3

### Added
- **S3 Configuration**
  - In `env-sample.txt` configuration for S3 default parameters can be set
  - In `requirements.txt` include boto3 and s3fs for dealing with S3 instead of using llamaindex S3Reader


## [2025-10-08] - Fixed standalone on Linux and Mac, fixed docker with app-stack on Mac

### Fixed
- **Docker Build Issues on Mac**
  - In Dockerfile use full python so can build on Mac when include app-stack.yaml
- **Standalone Backend Issues on Linux and Mac**
  - In start.py, added loop='asyncio' so don't get nest_asyncio errors on linux and mac
  - In start.py changed reload = false in general (not just windows) to simplify 


## [2025-10-04] - 3 frontends and backend can now work in docker in addition to in standalone mode

### Added
- **Complete Docker Frontend Support**
  - All three frontends (React, Vue, Angular) now work in Docker with nginx proxy
  - Dual access capability: direct container ports AND nginx proxy routing
  - React: `localhost:3000/ui/react/` and `localhost:8070/ui/react/`
  - Vue: `localhost:5173/ui/vue/` and `localhost:8070/ui/vue/`
  - Angular: `localhost:4200/` and `localhost:8070/ui/angular/`

### Fixed
- **Vue Docker Frontend API Routing**
  - Added proxy configuration to `vite.docker.config.ts` routing `/api` to backend
  - Resolved 404 errors on `/api/upload` endpoint in Docker environment
  - Vue frontend now processes files correctly in Docker deployment

- **Angular Docker Frontend Issues**
  - Fixed blank page issues by switching from static file serving to Angular dev server
  - Added `proxy.docker.conf.json` with backend routing configuration
  - Updated Dockerfile to use `npm run start` instead of static file serving
  - Implemented nginx `sub_filter` to dynamically inject correct base href for dual access

### Enhanced
- **Docker Configuration**
  - Environment variables configured in `app-stack.yaml` instead of `.env` for Docker backend
  - Default Ollama configuration (for OpenAI, update commented/uncommented sections and add API key)
  - Enabled nginx proxy with `proxy.yaml` included in docker-compose configuration

- **Angular Environment Configuration**
  - Added `environment.docker.ts` with Docker-specific settings
  - Updated `api.service.ts` to use `apiUrl = environment.apiUrl` instead of hardcoded `/api`
  - Added Docker build configuration section to `angular.json`
  - Removed obsolete `build:docker` script from `package.json`

### Maintained
- **Standalone Mode Compatibility**
  - All three frontends continue to work in standalone development mode
  - React: `localhost:3000`, Vue: `localhost:5173`, Angular: `localhost:4200`
  - Separate configuration files ensure no conflicts between Docker and standalone modes

### Technical Implementation
- Vue uses separate `vite.docker.config.ts` with backend proxy configuration
- Angular uses environment-based configuration with Docker-specific proxy setup
- React maintains existing dual access capability (already working)
- nginx `sub_filter` dynamically modifies Angular base href for proxy access compatibility

## [2025-09-28] - Kuzu can now do structured schema if enabled in config, code cleanup

### Enhanced
- env-samples.txt graph_db_config for kuzu now has use_structured_schema and use_vector_index parameters
- in factories.py create_graph_store, for kuzu, use use_structured_schema and use_vector_index config parameters to setup KuzuPropertyGraphStore to set use_vector_index, and set use_structured_schema (and give a relationship_schema if so)

### Fixed
- Previous code was always setting use_structured_schema to false

### Removed
- removed separate kuzu_use_vector_index independent configuration item from config.py
- in hybrid_system.py ingest_document(), code cleanup:
  - took out for kuzu setting external vector store in graph_index_kwargs
  - took out for kuzu calling graph_store.init_schema()
  - took out for memgraph unneeded code setting up a SchemaLLMPathExtractor with a hard coded schema to get relationship to have all relationship types with all caps and "_"


## [2025-09-26] - Fixed MemGraph issues, fixed issues with everything in docker compose included

### Fixed
- **MemGraph Cypher Relation Error**
  - Upgraded MemGraph Docker image to version 3.5.0
  - Resolved Cypher relation errors during graph building
  - Improved stability and compatibility with latest MemGraph features

- **Docker Port Conflicts**
  - Fixed Kuzu API server port conflict with NebulaGraph Studio (7001 → 7002)
  - Renamed postgres-pgvector service to avoid conflict with Alfresco postgres
  - Updated PORT-MAPPINGS.md with accurate conflict documentation

- **Angular Production Build Issues**
  - Increased Angular budget limits from 1MB to 5MB for Docker production builds
  - Resolved build failures with Angular Material components in Docker environment
  - Updated angular.json configuration for proper containerized deployment

- **Docker Backend AsyncIO Compatibility**
  - Added `--loop asyncio` flag to uvicorn in Docker to support nest_asyncio.apply()
  - Upgraded Docker Python version from 3.11 to 3.12 for ArcadeDB compatibility
  - Resolved uvloop/nest_asyncio conflicts in containerized environment

### Enhanced
- **Docker Compose Configuration**
  - Updated app-stack.yaml with improved Ollama model defaults
  - Added embedding configuration for both OpenAI and Ollama providers
  - Commented out ArcadeDB in env-sample.txt to reflect Neo4j default setup

### Removed
- **Code Cleanup**
  - Removed unused `_init_nebula_schema()` function from hybrid_system.py
  - Proper NebulaGraph setup now documented in NEBULA-SETUP.md

### Notes
- Backend successfully runs in Docker via app-stack.yaml
- Frontend containers in app-stack.yaml currently have issues - recommend standalone frontend with Docker databases
- Full Docker stack functional for databases, selective deployment recommended for UI components

## [2025-09-25] - Vector Database Expansion and Dashboard Integration

### Added
- **6 Additional Vector Databases**
  - Chroma, Milvus, Weaviate, Pinecone, PostgreSQL+pgvector, LanceDB support
  - Complete Docker configurations with port conflict resolution
  - Factory implementations following LlamaIndex patterns
  - Total vector database support expanded from 4 to 10 databases

- **4 Additional Graph Databases**
  - ArcadeDB, MemGraph, NebulaGraph, Amazon Neptune/Neptune Analytics support
  - Multi-model capabilities and distributed graph database options
  - Complete configuration examples and Docker integration
  - Total graph database support expanded to 9 databases

- **Comprehensive Dashboard Integration**
  - Dashboard coverage for all vector databases (ports 3000-3008)
  - Working solutions: MemGraph Lab, NebulaGraph Studio, Milvus Attu, LanceDB Viewer
  - Info pages for managed services (Pinecone, Neptune)
  - Systematic testing and accurate status documentation

- **10 New Modular Data Sources**
  - Web, Wikipedia, YouTube, S3, GCS, Azure Blob, OneDrive, SharePoint, Box, Google Drive
  - Modular architecture with BaseDataSource pattern and IngestionManager
  - Progress tracking and LlamaIndex Hub reader integration
  - Total data sources expanded from 3 to 13

### Enhanced
- **Dynamic Embedding Dimension Detection**
  - Replaced hardcoded dimensions with provider-aware detection
  - OpenAI (1536/3072), Ollama (384/768/1024), Azure support
  - Centralized get_embedding_dimension() function across all databases

- **Docker Network Simplification**
  - Eliminated external network dependencies and multiple network creation
  - Single flexible-graphrag_default network for all services
  - Fixed "network declared as external, but could not be found" errors

- **Comprehensive Documentation**
  - Complete vector database deletion guide for embedding model switching
  - Port mappings documentation with conflict resolution
  - Dashboard status indicators (✅ working, ❌ CORS issues, ⚠️ complex)

### Fixed
- **Dashboard Connection Issues**
  - MemGraph Lab Docker entrypoint configuration
  - NebulaGraph Studio internal Docker service connection
  - Pinecone info page nginx file permissions (403 Forbidden)
  - Chroma API endpoints updated from v1 to v2

- **UI Consistency and Progress Tracking**
  - Angular dark mode text visibility across all components
  - Vue SharePoint form missing authentication fields
  - Processing tab message panel clearing when switching data sources
  - Cross-frontend repository file handling and progress bars

- **Data Source Integration**
  - Angular web/cloud data source configuration parameter mapping
  - SharePoint 422 validation errors with complete Azure authentication
  - Wikipedia URL parsing to preserve page titles with hyphens
  - YouTube transcript processing with proper time-based chunking

### Performance Results
- **Vector Database Scaling**: 10 databases with consistent factory patterns
- **Graph Database Coverage**: 9 databases including distributed and managed options
- **Data Source Expansion**: 13 total sources with modular processing architecture
- **Dashboard Reliability**: Systematic testing identified working vs problematic solutions

## [2025-09-23] - Wikipedia Data Source Enhancement and Performance Logging Fixes

### Enhanced
- **Wikipedia Data Source**: Improved Wikipedia page resolution with search-based fallback for special characters (e.g., "Nasdaq-100")
  - Reordered loading methods: LlamaIndex WikipediaReader primary, direct wikipedia library fallback
  - Added content length limit (100,000 characters) following Neo4j LLM Graph Builder approach
  - Enhanced URL parsing with proper handling of hyphens and underscores

### Fixed
- **Performance Logging**: Fixed inaccurate graph extraction timing measurements in performance summary logs
  - Resolved variable scope issues causing "Graph: 0.00s" display errors
  - Both processing methods now show accurate timing for all phases (Pipeline, Vector, Graph)

## [2025-09-23] - Angular Data Source Integration and UI Consistency Fixes

### Fixed
- **Angular Web Data Source Configuration**
  - Fixed missing web_config parameter passing in Angular processing tab
  - Angular web sources now work consistently with React and Vue frontends
  - Resolved "configuration is required" errors for web data sources

- **Angular Cloud Data Source Validation Errors**
  - Fixed 422 "Unprocessable Content" errors for cloud storage data sources
  - Corrected configuration parameter mapping to send only relevant configs per data source
  - SharePoint form enhanced with required Azure authentication fields (client_id, client_secret, tenant_id)

- **Wikipedia Data Source Special Characters**
  - Improved URL parsing across all frontends to preserve page titles with hyphens
  - Added fallback mechanisms for Wikipedia pages with special characters
  - Enhanced error handling and logging for Wikipedia API interactions

### Enhanced
- **Cross-Frontend Consistency**
  - All three frontends (React, Vue, Angular) now have identical data source support
  - Consistent cloud storage configuration validation and error handling
  - Unified Wikipedia URL parsing logic across all frontends

- **Angular UI Improvements**
  - Enhanced SharePoint form with complete Azure app registration fields
  - Improved cloud data source form layouts and validation
  - Better error messages and user guidance for data source configuration


## [2025-09-23] - Data Source Alignment and Progress Tracking Fixes

### Fixed
- **Critical Progress Bar Issues for New Data Sources**
  - New modular sources (Web, Wikipedia, YouTube, cloud storage) now display progress bars correctly
  - Fixed missing individual_files data structure and main PROCESSING_STATUS updates
  - YouTube field name mismatch resolved (backend 'video_url' vs frontend 'url')
  - All 13 data sources now have consistent progress tracking

### Enhanced
- **Cloud Storage Data Source Improvements**
  - Azure Blob Storage: Updated to Method 1 (Account Key Authentication)
  - Microsoft OneDrive: Added required user_principal_name field
  - Amazon S3: Removed legacy bucket_url field, streamlined to bucket_name approach
  - Microsoft SharePoint: Updated to use site_name and folder_id field names
  - Added comprehensive autocomplete prevention for sensitive fields

### Added
- **10 New Modular Data Sources**
  - Web sources: Web Page, Wikipedia, YouTube
  - Cloud storage: Amazon S3, Google Cloud Storage, Azure Blob Storage
  - Enterprise cloud: Microsoft OneDrive, SharePoint, Box, Google Drive
  - Complete UI forms and backend integration for all new sources
  - Expanded from 3 legacy sources to 13 total data sources

### Enhanced
- **Cross-Frontend UI Consistency**
  - Ported React's modular source form components to Vue and Angular
  - BaseSourceForm inheritance pattern with dynamic component rendering
  - Complete feature parity across all three frontends (React, Vue, Angular)
  - Fixed Vue dropdown styling issues and Angular compilation errors

## [2025-09-23] - YouTube Fix and Cloud Storage Organizational Fields

### Fixed
- **YouTube Data Source**
  - Switched from LlamaIndex wrapper to direct youtube_transcript_api usage
  - Implemented proper 60-second time-based chunking with timestamp metadata
  - Resolved parameter errors and achieved 21 document chunks from videos

### Enhanced
- **Google Drive Authentication**
  - Fixed authentication using proper service_account_key parameter
  - Added JSON credential parsing from UI form
  - Resolved "Must specify client_config or service_account_key" error

### Added
- **Cloud Storage Organizational Fields**
  - Azure Blob: Added prefix field separate from blob_name
  - Box: Added folder_id field for specific folder access
  - Amazon S3: Added bucket name + prefix fields (marked bucket_url as legacy)
  - OneDrive: Added folder_path and folder_id fields
  - Google Cloud Storage: Added prefix and folder_name fields
  - SharePoint: Added document_library and folder_path fields
  - Fixed 422 "Unprocessable Content" errors by updating backend API models

## [2025-09-23] - UI Fixes and Backend Integration

### Fixed
- **Critical Configuration Flow Issue**
  - Web sources (Web, Wikipedia, YouTube) failing with "configuration is required" errors
  - Added 5 new state variables in App.tsx for web/cloud/enterprise configs
  - Fixed complete data flow: UI Form → SourcesTab → App.tsx → ProcessingTab → API → Backend

### Enhanced
- **Async/Await Backend Integration**
  - Made get_documents_with_progress() methods async for all new modular sources
  - Fixed "object list can't be used in 'await' expression" errors
  - Enhanced Azure Blob Storage form with 3 missing fields (blob_name, account_name, account_key)

## [2025-09-23] - Data Source Migration and Progress Tracking

### Added
- **Complete Data Source Migration**
  - Migrated all three legacy sources (Filesystem, Alfresco, CMIS) to modular architecture
  - BaseDataSource inheritance with IngestionManager orchestration
  - Unified progress tracking across all data sources

### Fixed
- **File Upload Progress Issues**
  - Fixed missing top area progress feedback for filesystem source
  - Resolved progress reset issue where completion status appeared then reset
  - All sources now have consistent progress feedback (top/middle/bottom areas)

### Enhanced
- **Completion Messages**
  - Improved order: Vector → Search → Knowledge Graph
  - Dynamic database types (e.g., "Qdrant vector index, Elasticsearch search, Neo4J knowledge graph")
  - Proper grammar without duplicate "and"

### Removed
- Deprecated sources.py file and old ingest_cmis/ingest_alfresco methods
- Cleaned up codebase while preserving ingest_documents (API/MCP) and ingest_text (MCP server)

## [2025-09-08] - FalkorDB Integration and Configuration Optimization

### Added
- **FalkorDB Graph Database Support**
  - Complete integration with GraphDBType enum, factories.py, requirements.txt
  - Docker support with falkordb.yaml include and browser (port 3001)
  - Performance testing: 21.74s for 6 docs (3.62s/doc), fastest search (1.199s)
  - Superior entity extraction quality (PERSON, ORGANIZATION, TECHNOLOGY)

### Enhanced
- **Configurable Extraction Limits**
  - MAX_TRIPLETS_PER_CHUNK and MAX_PATHS_PER_CHUNK environment variables
  - Default increased from 10-20 to 100 for better entity extraction
  - Resolves generic __entity__ issues with dense content

### Fixed
- **File Upload Dialog Performance**
  - requestAnimationFrame optimization for React, Vue, Angular frontends
  - Proper input clearing only after successful processing
  - Dialog now matches drag/drop speed

### Performance Results
- **FalkorDB + OpenAI**: 21.74s ingestion, 1.199s search, 2.133s Q&A (6 docs)
- **FalkorDB + Ollama**: Working configuration found (100 max triplets, 16k context)
- **Resolved Issue**: space-station.txt + FalkorDB + Ollama now works with optimized settings

### Documentation
- **Performance Documentation**: docs/PERFORMANCE.md with complete test matrix
- **README.md**: Concise 6-doc performance comparison table
- **Port Conflicts**: FalkorDB browser moved to port 3001 (Vue client stays 3000)

## [2025-09-04] - Comprehensive Performance Testing and Optimization

### Added
- **Complete Performance Benchmarking Matrix**
  - Tested all combinations: Neo4j/Kuzu × OpenAI/Ollama
  - Performance table in README.md with detailed metrics
  - Infrastructure configuration documentation (AMD 5950x, 64GB RAM, 4090 GPU)

### Enhanced
- **Ollama Parallel Processing Optimization**
  - Removed artificial worker limitations (1→4 workers)
  - Enabled async PropertyGraphIndex processing
  - Parallel Docling document conversion
  - 94% pipeline performance improvement (37s→2s)

### Fixed
- **DynamicLLMPathExtractor vs SchemaLLMPathExtractor Issues**
  - DynamicLLMPathExtractor fails with Ollama (creates only Chunk nodes)
  - SchemaLLMPathExtractor works excellently with both Neo4j and Kuzu
  - Kuzu schema configuration fixed (has_structured_schema=False)

### Performance Results
- **OpenAI**: 3.7x faster than Ollama across both databases
- **Neo4j + OpenAI**: 14.39s for 2 docs (best overall)
- **Kuzu + OpenAI**: 14.79s for 2 docs (nearly identical)
- **Both Ollama options**: ~54s for 2 docs (viable for local processing)


## [2025-08-29] - Kuzu Schema Integration and Performance Analysis

### Added
- **Complete Kuzu Graph Database Integration**
  - Comprehensive validation schema with 35+ relationship combinations
  - Entity types: PERSON, ORGANIZATION, TECHNOLOGY, PROJECT, LOCATION
  - Outstanding performance: 3.52s per document average

### Fixed
- **Kuzu Schema Validation Errors**
  - "Query node c violates schema" and "Table Entity does not exist" resolved
  - Evolution from LlamaIndex exact schema to comprehensive validation
  - strict=False, max_triplets_per_chunk=100 for maximum flexibility

### Enhanced
- **Performance Optimization Discovery**
  - KeywordExtractor/SummaryExtractor removal for Ollama (94% improvement)
  - Neo4j scaling: 90% efficiency, 18.93s per doc consistency
  - Kuzu scaling: 253% slower at 2 docs → only 11% slower at 6 docs


## [2025-08-27] - Ollama Optimization and Docker Configuration

### Added
- **Comprehensive Ollama Parallel Processing**
  - OLLAMA_NUM_PARALLEL=4 and OLLAMA_MAX_LOADED_MODELS=4 support
  - Async PropertyGraphIndex with use_async=True
  - Parallel Docling document processing with asyncio.gather()
  - Increased kg_batch_size from 10 to 20 chunks

### Enhanced
- **Docker Compose Modularization**
  - Separate Kuzu API (port 7001) and Explorer (port 7000) services
  - Bind mounts to flexible-graphrag/kuzu_db/ for data sharing
  - Health checks and proper container monitoring

### Fixed
- **Async Event Loop Stability**
  - Reduced workers for Ollama to prevent conflicts
  - Enhanced error logging with better exception handling
  - Schema logging errors resolved


## [2025-08-26] - Performance Analysis and Query Timing

### Added
- **Comprehensive Query Timing Implementation**
  - Search, Q&A, and hybrid retrieval timing logs
  - Detailed deduplication flow tracking (12 → 8 → 5 results)
  - Enhanced document storage logging with breakdown

### Fixed
- **File Count Logging Mismatch**
  - Corrected "(7/6 files)" display to show accurate completion status
  - ASCII-only text previews to prevent emoji encoding issues
  - Unicode arrow character encoding errors on Windows console

### Performance Results
- **OpenAI + Kuzu**: 32.17s for 6 docs (first time), 23.81s (with indexes)
- **Query Performance**: Search 1.079s, Q&A 2.231s (sub-2.5s production ready)
- **Index Creation Impact**: 23% performance gain with existing indexes


## [2025-08-25] - Docker Compose Documentation Updates

### Enhanced
- **Docker Compose Command Standardization**
  - Added `-p flexible-graphrag` project name flag to all commands
  - Reordered flags: `-f` before `-p` throughout documentation
  - Updated single docker-compose.yaml file structure references

### Added
- **Stopping Services Documentation**
  - Dedicated section for proper service shutdown
  - Volume removal warnings and best practices
  - Modular include system explanation


## [2025-08-23] - Screenshot Organization and Documentation Updates

### Changed
- **README Screenshot Organization**
  - **Vue and Angular**: Moved existing screenshots to framework-specific subdirectories (`screen-shots/vue/`, `screen-shots/angular/`)
  - **React**: Completely redone with both dark and light theme versions in `screen-shots/react/`
    - Removed chat greeting and Q&A query screenshots from display
    - Now shows hybrid search instead of Q&A query in search tab
    - Added separate collapsible section for React Light Theme screenshots
  - Added theme indicators to all frontend sections: Angular (Light Theme), Vue (Light Theme), React (Dark Theme + Light Theme)

### Enhanced
- **Documentation Clarity**
  - Clear theme identification for each frontend in README
  - Improved screenshot organization for better navigation
  - Consistent screenshot presentation across all three frontends


## [2025-08-23] - File State Management and Theme Fixes

### Fixed
- **Filename Reuse Between Upload Methods**
  - Fixed issue preventing same filename reuse between regular file upload and repository upload
  - Resolved frontend file state conflicts when switching between data sources
  - All frontends now properly clear previous file state when switching upload methods

- **Repository Display Issues**
  - Fixed React ProcessingTab showing old filenames when switching to repository source
  - Fixed Angular ProcessingTab displaying stale file data until processing starts
  - Fixed Vue ProcessingTab showing previous upload files instead of repository path
  - All frontends now immediately display correct repository path upon configuration

- **Dark/Light Theme Styling Issues**
  - Angular: Fixed dark mode configure processing button text visibility
  - Vue: Fixed light mode text color above "Go to Sources" button for proper contrast
  - React: Fixed dark mode "No Data Source Configured" panel background (now dark gray instead of light blue)

### Enhanced
- **Cross-Data Source Compatibility**
  - Improved handling of file upload → repository source transitions
  - Enhanced repository → file upload source transitions  
  - Better support for CMIS ↔ Alfresco source switching
  - Consistent filename conflict prevention across all upload methods


## [2025-08-22] - Comprehensive UI/UX Fixes and Repository File Handling

### Added
- **Enhanced Display Area Usage**
  - Chat interface now takes advantage of extra display area on 4K and QHD monitors
  - Responsive viewport calculations with framework-specific height offsets
  - Integrated help text into chat input placeholders
  - Removed redundant "Chat Interface" headers to save vertical space

- **Full Path Display**
  - Complete repository path display across all frontends (e.g., "/Shared/GraphRAG/cmispress.txt")
  - Enhanced filename extraction from repository paths
  - Flexible column layouts with 30% width allocation for filenames

### Fixed
- **Repository File Handling Issues**
  - Vue: Fixed inability to re-add repository files after removal
  - Vue: Fixed progress bars showing "0% - Ready" instead of actual progress
  - React: Added missing "X" remove buttons for repository files
  - Angular: Enhanced repository file display and removal functionality
  - All clients: Fixed repository path configuration for single file vs directory processing

- **Progress Bar and Status Issues**
  - Fixed progress text wrapping ("100% - Completed" on multiple lines)
  - Applied consistent flexbox layout for progress columns across all frontends
  - Enhanced completion status retention for repository files
  - Fixed progress lookup using correct file identifiers

- **Cross-Frontend UI Consistency**
  - Standardized button styling: red outline for Cancel/Remove Selected, green for Completed status
  - Implemented blue checkboxes with white checks across all clients
  - Fixed Angular dark theme visibility for tabs, dropdowns, chat elements, form fields
  - Removed confusing guide lines and borders from chat interfaces
  - Enhanced chat auto-scroll functionality across all frontends

- **Chat Interface Improvements**
  - Fixed Vue chat auto-scroll using proper DOM element access
  - Improved chat input field visibility in light mode
  - Optimized button alignment and spacing
  - Enhanced message display and interaction patterns

### Enhanced
- **State Management**
  - Implemented `repositoryItemsHidden` pattern for proper file removal/re-add capability
  - Enhanced configuration timestamp tracking for state updates
  - Improved fallback mechanisms for preserving file information after cancellation

---

## [2025-08-21] - React Frontend Modularization and Cross-Frontend Styling

### Added
- **React Frontend Modularization**
  - Extracted components from monolithic App.tsx to dedicated files (SourcesTab, ProcessingTab, SearchTab, ChatTab)
  - Implemented "lift state up" pattern for centralized state management
  - Created comprehensive TypeScript interfaces in types/api.ts and types/theme.ts
  - Added component export aggregation with index.ts

- **Repository File Enhancement**
  - Individual file display from statusData.individual_files for CMIS/Alfresco sources
  - Enhanced filename extraction from full paths with multiple fallback levels
  - Proper completion status retention (100% progress, green "completed" status)

### Fixed
- **React Functionality Issues**
  - Fixed checkboxes not pre-selecting after source configuration
  - Fixed "Remove Selected" and individual "X" buttons not removing items
  - Restored commented-out "Graph" tab for future features
  - Converted all tab labels to ALL CAPS for consistency

- **Vue Frontend Issues**
  - Fixed dark gray processing status panel with white text in dark theme
  - Resolved TypeScript compilation errors (function calls, $el access, event emission names)
  - Enhanced repository functionality with proper filename handling
  - Fixed drop area styling with consistent hover effects

- **Angular Dark Mode Issues**
  - Fixed tab labels with white text and blue active backgrounds
  - Improved form field and typography contrast
  - Enhanced Sources tab with white text on gray backgrounds
  - Standardized drop zone styling to match other frontends

### Enhanced
- **Cross-Frontend Consistency**
  - Standardized drop area styling: blue background with white text, black hover
  - Implemented consistent state management patterns across frameworks
  - Enhanced repository handling with unified approach to file display and removal
  - Improved theme support consistency across all frontends

- **State Persistence**
  - Prevented data loss during tab navigation through proper state lifting
  - Enhanced component communication patterns
  - Improved error handling and user feedback

---

## [2025-08-21] - Dark/Light Theme Support Implementation

### Added
- **Comprehensive Theme Switching**
  - React: Dark theme by default with proper theme persistence
  - Vue: Light theme by default with proper theme persistence  
  - Angular: Light theme by default with proper theme persistence
  - All frontends: localStorage theme preference saving

### Fixed
- **React Frontend Theme Issues**
  - Fixed search field white background causing vertical shift and input issues
  - Updated chat input field styling for proper theme compatibility
  - Resolved theme-aware input field backgrounds for both light and dark modes

- **Vue Frontend Theme Issues**
  - Fixed search method picker tabs white background in dark theme
  - Corrected chat wording from "Press Enter to send or click arrow to send" to "Press Enter or click arrow to send"
  - Fixed theme switcher layout: slider → icon → text with proper spacing
  - Improved processing button text visibility during processing
  - Hidden all processing table paging UI elements
  - Added visible border for chat area in light mode

- **Angular Frontend Theme Issues**
  - Implemented complete dark/light theme CSS with Material component overrides
  - Fixed theme switcher layout and replaced Material slide toggle with custom HTML/CSS widget
  - Corrected main tabs and search sub-tabs text visibility in dark mode
  - Fixed app width to expand to full window width like other frontends
  - Updated button styling: Remove Selected and Clear History buttons now use outlined style
  - Fixed chat wording to match other frontends

### Technical
- Added theme-aware CSS for all Material Design components
- Implemented custom toggle widget to replace stubborn Material slide toggle
- Applied responsive width across all frontends removing fixed max-width constraints
- Enhanced dark mode styling with proper contrast ratios for accessibility

---

## [2025-08-20] - Updated with screenshots for the new tab UI, readme updated

### Screenshots Updateed
- Removed 3 screenshots with old UI design
- Added screenshots of each of 4 tabs for all 3 clients in /screen-shots/

### Readme Updated
- Updated readme.md with new screenshots, usage updated for new UI for each of the four tabs
- Updated LLM usage note about using LlamaIndex with Ollama models and performance issues
- Updated docker section that new file upload can be used in docker where old filesystem datasource couldn't



## [2025-08-20] - Tabbed UI Implementation Across All Frontends

### Added
- **Vue Frontend Tabbed UI**
  - Implemented 5-tab navigation: Sources, Processing, Search, Chat, Graph
  - File upload with drag/drop functionality using Vuetify components
  - Processing table with checkboxes, progress bars, and bulk operations
  - Chat interface with auto-scroll and message history
  - Backend integration with axios for upload/processing/search operations

- **Angular Frontend Tabbed UI**
  - Implemented 5-tab navigation using Angular Material components
  - File upload with drag/drop functionality and Material Design styling
  - Processing table with selection, progress indicators, and bulk operations
  - Chat interface with auto-scroll and message threading
  - Backend integration with HttpClient and RxJS Observables

### Fixed
- **React UI Visual Issues**
  - Sources tab drag/drop area text changed from gray to white for visibility
  - Chat tab welcome message text visibility (was white-on-white)
  - Main tabs updated to blue background theme for consistency

- **Angular Auto-Scroll**
  - Restructured chat HTML with dedicated scroll-container inside mat-card
  - Disabled tab slide animations to prevent horizontal sliding in search interface

- **Vue Auto-Scroll**
  - Fixed v-card component reference using $el fallback for proper DOM access

### Enhanced
- **UI Consistency**
  - All button texts standardized to ALL CAPS across frontends
  - Main tabs use blue backgrounds with white text
  - Search sub-tabs use underline-only styling
  - Consistent file upload and processing experiences

- **Cross-Framework Functionality**
  - Identical file upload with progress tracking in all frontends
  - Real-time processing status updates and cancellation
  - Hybrid and Q&A search modes with consistent result formatting
  - Auto-scrolling chat interfaces with message history

## [2025-08-18] - Docker Rebuild & Async Event Loop Resolution

### Fixed
- **Critical Async Event Loop Errors**
  - Resolved "Event object bound to different event loop" errors during file processing
  - Fixed "Detected nested async" errors with Ollama, especially for Office files requiring Docling
  - Implemented hybrid async approach with run_in_executor for all LlamaIndex operations
  - Proper event loop handling with nest_asyncio.apply() and RuntimeError catching

- **React Docker UI Issues**
  - Fixed old UI display by forcing Docker rebuild with --no-cache flag
  - Added API routing for both direct (port 3000) and proxied (port 8070) React UI
  - Added proxy configuration to vite.docker.config.ts and nginx location block

- **File Upload Management**
  - Fixed file overwriting instead of renaming (e.g., cmispress.txt vs cmispress_34.txt)
  - Added cleanup functionality via /api/cleanup-uploads endpoint
  - Fixed minor UI bugs like dollar sign in "Remove Selected" button

### Enhanced
- **Docker Configuration**
  - Updated to use gpt-5-oss:20b instead of llama3.1:8b for better quality
  - Fixed Angular ES module __dirname issues with fileURLToPath
  - Added --esm flag to ts-node commands

### Validated
- **End-to-End Testing**
  - File upload (PDF, Office docs, text) working
  - CMIS and Alfresco repository integration functional
  - Search/query/chat functionality operational across all data sources

## [2025-08-17] - Tab UI Redesign & File Processing Table (React UI Only)

### Added
- **5-Tab Navigation System (React UI)**
  - Sources: Data source configuration and file upload
  - Processing: File management table with progress tracking
  - Search: Quick search functionality
  - Chat: Interactive Q&A and search conversations
  - Graph: Placeholder for future graph visualization

- **Processing Table Implementation (React UI)**
  - Single-row-per-file design with wide progress bar column (400px+)
  - Multi-select functionality with bulk operations
  - Windows-style file size formatting
  - Real-time per-file progress tracking within table rows

### Enhanced
- **File Management Features (React UI)**
  - Individual file remove buttons and select all/individual checkboxes
  - "Delete Selected (N)" button with proper state management
  - Drag-and-drop upload integration with table display
  - Color-coded status chips and progress phase information

- **Per-File Progress Tracking**
  - Backend per-file progress tracking with _initialize_file_progress and _update_file_progress
  - Fixed completion status timing by moving final callback to hybrid_system.py
  - Enhanced React frontend with individual file progress cards
  - Persistent debug panel with localStorage and performance logging

### Fixed
- **File Upload Progress Bar Issues (React UI)**
  - Root cause: Filename mismatch between UI (original names) and backend (saved names with duplicates)
  - Solution: Updated selectedFiles and configuredFiles with saved filenames after upload
  - Progress bars now display correctly with blue bars and real-time updates

### Note
- Vue and Angular frontends maintain previous UI design pending future updates

## [2025-08-16] - Documentation & Deployment Improvements

### Enhanced
- **README.md Updates**
  - Fixed Python backend setup with proper project directory paths
  - Updated environment configuration to copy env-sample.txt instead of creating empty .env
  - Restructured Frontend Setup section to clarify production vs development modes
  - Enhanced Project Structure section with missing directories (/docker, /docs, /scripts, /tests)

- **Docker Service Configuration**
  - Comprehensive service comment-out guide for docker-compose.yaml
  - Detailed guidance for customizing all services (neo4j, kuzu, qdrant, elasticsearch, opensearch, alfresco)
  - Removed "Recommended" from Docker Deployment header
  - Added app-stack.yaml environment configuration guidance

### Documentation
- **Deployment Clarity**
  - Clear separation between Docker and standalone deployment approaches
  - Updated frontend deployment section noting Docker limitations for filesystem sources
  - Added reference to docs/ENVIRONMENT-CONFIGURATION.md for detailed setup

## [2025-08-15] - Frontend Environment Variables & Vector Database Validation

### Fixed
- **Frontend Environment Variable Issues**
  - Vue frontend template compilation errors with `import.meta.env` expressions
  - React JSX environment variable resolution using computed placeholders  
  - Angular production environment forcing Docker URLs for standalone deployments
  - TypeScript compilation errors for window environment declarations

### Enhanced
- **Flexible Environment Configuration**
  - Vue: Computed properties with fallback defaults for environment variables
  - React: useMemo hooks for optimized environment resolution
  - Angular: Runtime environment service supporting both standalone and Docker modes
  - Production builds no longer require Docker infrastructure

### Validated
- **Complete Vector Database Support**
  - Qdrant: Dedicated vector store with external container configuration
  - Elasticsearch: Dual-purpose vector and fulltext search with separate indexes
  - Neo4j: Vector database support with separate VECTOR_DB_CONFIG requirements
  - OpenSearch: Hybrid search with single index and pipeline-based score fusion
  - BM25: Local filesystem storage without external SEARCH_DB_CONFIG

### Documentation
- Updated Neo4j vector index cleanup commands (`hybrid_search_vector` vs `vector`)
- Clarified BM25 configuration requirements and local storage approach
- Simplified Neo4j cleanup instructions using `SHOW INDEXES` commands

## [2025-08-14] - Environment Configuration & Documentation

### Added
- **Comprehensive Environment Configuration System**
  - Complete `docs/ENVIRONMENT-CONFIGURATION.md` with 5-section structure guide
  - Clean separation of schema, database, and source configurations  
  - Database switching patterns and configuration best practices
  - Missing Kuzu configuration with proper JSON format examples

### Enhanced
- **Environment File Organization**
  - Moved schema configuration to dedicated section in `env-sample.txt`
  - Fixed Neo4j default URI from incorrect port 7689 to standard 7687
  - Added proper DB_CONFIG examples with JSON format for all database types
  - Organized into logical sections for easy database switching

### Documentation
- Created supporting documentation: `SOURCE-PATH-EXAMPLES.md`, `TIMEOUT-CONFIGURATIONS.md`
- Updated `docs/SCHEMA-EXAMPLES.md` to focus purely on schema examples
- Established clean separation of concerns with cross-referenced documentation
- Maintained backward compatibility while improving organization

## [2025-08-13] - Kuzu Integration & Docker Full-Stack

### Added
- **Complete Kuzu Graph Database Integration**
  - Kuzu support as alternative to Neo4j using Approach 2 (separate vector stores)
  - Dual schema system: KUZU_SCHEMA for Kuzu, SAMPLE_SCHEMA for Neo4j
  - LLM provider awareness for embedding models (OpenAI/Ollama/Azure)
  - Graph API endpoint `/api/graph` for programmatic access to Kuzu data

- **Docker Infrastructure Overhaul**  
  - Fixed all Docker networking issues with Node.js 24 updates
  - NGINX proxy configuration with proper upstream routing
  - Standardized port allocation resolving conflicts
  - Frontend Docker configurations with internal networking support

### Enhanced
- **Database Architecture Flexibility**
  - Clean separation: Kuzu for graphs, Qdrant for vectors, Elasticsearch for search
  - Schema validation system with `has_structured_schema=False` for Kuzu
  - Identical search performance across Neo4j and Kuzu backends
  - Multiple visualization options: Kuzu Explorer, Neo4j Browser, API access

## [2025-08-12] - Async Processing & Event Loop Resolution

### Fixed
- **Ollama Event Loop Issues**
  - Comprehensive async approach with global `nest_asyncio.apply()`
  - Consistent async methods: `aquery()`, `aretrieve()` for all LLM providers
  - Windows event loop policy fixes with `WindowsSelectorEventLoopPolicy`
  - Simplified architecture removing complex fallback mechanisms

### Enhanced
- **Unified Async Architecture**
  - Applied async patterns to all LLM providers, not just Ollama
  - LlamaIndex integration following library recommendations
  - Removed thread isolation in favor of proper async handling

## [2025-08-11] - OpenSearch Native Hybrid Search

### Added
- **OpenSearch Native Hybrid Search Implementation**
  - Single retriever using `VectorStoreQueryMode.HYBRID` 
  - Eliminated async connection conflicts from dual retrievers
  - Native OpenSearch score fusion instead of manual combination
  - Automated pipeline creation with `scripts/create_opensearch_pipeline.py`

### Enhanced
- **Search Architecture Improvements**
  - Hybrid mode detection in factories.py for OpenSearch
  - Fulltext-only mode using `VectorStoreQueryMode.TEXT_SEARCH`
  - Re-enabled async support in QueryFusionRetriever
  - Better relevance than manual fusion approaches

## [2025-08-10] - Database Integration & Hybrid Search Testing

### Added
- **Comprehensive Hybrid Search System**
  - Dual-index Elasticsearch hybrid search (vector + fulltext)
  - Working configurations for Qdrant+Elasticsearch+Kibana combinations
  - OpenSearch factory configuration with `OpensearchVectorClient`
  - Pure RAG mode with `ENABLE_KNOWLEDGE_GRAPH=false`

### Fixed
- **BM25 Standalone Search Issues**
  - Document storage overwriting preventing proper indexing
  - Early exit logic incorrectly assuming BM25 required vector docstore
  - Zero-relevance filtering to exclude irrelevant results
  - Direct retriever usage for single-modality scenarios

### Enhanced
- **UI Client Improvements**
  - Zero results feedback across all frontend clients (Vue, Angular, React)
  - Accumulative document storage across multiple ingestions
  - Professional "No results found" messages with search term display

## [2025-08-09] - MCP Server and Async Processing

### Added
- **MCP Server Implementation**
  - FastMCP-based Model Context Protocol server for Claude Desktop integration
  - HTTP and stdio transport modes (`--transport http`, `--http`, `--serve` flags)
  - Command-line argument parsing for host, port, and transport configuration
  - Multiple installation methods: pipx, uvx, direct Python execution
  - Platform-specific Claude Desktop configurations (Windows/macOS)
  - MCP Inspector debugging support with dedicated configurations
- **MCP Tools**
  - `get_system_status`, `ingest_documents`, `ingest_text`, `search_documents`
  - `query_documents`, `test_with_sample`, `check_processing_status`
  - `get_python_info`, `health_check`
- **Asynchronous Processing Pattern**
  - Background task processing with processing ID system
  - Real-time progress updates with percentage, current file, and phase information
  - Dynamic time estimation based on content size and file count
  - Processing cancellation support with graceful cleanup
  - Server-Sent Events (SSE) endpoints for real-time UI updates
- **UI Enhancements**
  - Progress bars with 0-100% completion tracking across all clients
  - Cancel processing buttons with proper state management
  - Time estimation displays and file-level progress indicators
  - Phase tracking (docling, chunking, indexing, kg_extraction)
  - Auto-clearing status messages and manual dismiss options

### Fixed
- **Asyncio Event Loop Conflicts**
  - Added `nest_asyncio` support to handle nested event loops
  - Wrapped LlamaIndex operations in `loop.run_in_executor()` 
  - Resolved `asyncio.run() cannot be called from a running event loop` errors
- **Neo4j Compatibility Issues**
  - Added `refresh_schema=False` to prevent APOC `apoc.meta.data` calls during initialization
  - Fixed Cypher syntax incompatibility between Neo4j 25.x and LlamaIndex 0.5.0
  - Updated cleanup commands to include `entity` index and LlamaIndex constraints
- **Package Installation Issues**
  - Fixed `pyproject.toml` from `packages = ["."]` to `py-modules = ["main"]` for uvx support
  - Added proper script entry points for system-wide command availability
- **Processing State Management**
  - Implemented intelligent cleanup that preserves functional systems after cancellation
  - Fixed search functionality after completed ingestion followed by cancelled operation
- **UI Client Issues**
  - Fixed Angular compilation errors (MatProgressBarModule, RxJS imports, TypeScript types)
  - Corrected snackbar duration and auto-clearing logic
  - Added proper async status polling in all three UI frameworks

### Changed
- **API Response Format**
  - Ingestion endpoints now return immediate `AsyncProcessingResponse` with `processing_id`
  - Added `/api/processing-status/{id}` and `/api/processing-events/{id}` endpoints
  - Separated `/api/test-sample` (default) and `/api/ingest-text` (custom content) endpoints
  - Enhanced `/api/status` to include `search_db` configuration
- **Configuration Management**
  - Made sample text configurable via `SAMPLE_TEXT` environment variable
  - Organized Claude Desktop configs by platform (windows/, macos/)
  - Separated MCP Inspector configs by transport (stdio/HTTP)
  - Added Unicode environment variables for Windows compatibility

### Documentation
- Comprehensive README.md with multiple installation methods
- QUICK-USAGE-GUIDE.md for streamlined setup
- Platform-specific configuration examples and troubleshooting guides
- Ready-to-use Claude Desktop JSON configurations
- MCP Inspector configs for both stdio and HTTP modes
- Test scripts for installation validation (PowerShell and Bash)

## [2025-08-07] - UI Client Updates and Data Sources

### Added
- React and Vue client modifications to match Angular's data source selection capabilities
- Hybrid search with results list (in addition to Q&A AI query mode)
- CMIS and Alfresco data sources beyond filesystem (Alfresco uses CMIS for getObjectByPath)
- Support for additional document formats that Docling supports

### Changed
- Updated screen images to reflect new hybrid search functionality

## [2025-08-06] - LlamaIndex Integration and Configuration

### Added
- **LlamaIndex Integration**
  - Replaced LangChain with LlamaIndex for document processing
  - VectorStoreIndex and PropertyGraphIndex implementation
  - IngestionPipeline with SentenceSplitter, KeywordExtractor, SummaryExtractor
- **Configurable Architecture**
  - Vector database, graph database, and search database configuration
  - Support for multiple database backends (Neo4j, Qdrant, etc.)
  - Environment-based configuration management
- **Hybrid Search System**
  - Combined vector similarity, BM25 full-text search, and graph traversal
  - AI Q&A mode alongside hybrid search results
  - Configurable retrieval strategies
- **Multi-Source Data Ingestion**
  - Filesystem, CMIS, and Alfresco data source support
  - Docling integration for PDF and Microsoft Office documents
  - Smart table-to-markdown conversion with fallback to text extraction
- **Document Processing**
  - Support for 12+ file formats via Docling
  - Intelligent chunking and metadata extraction
  - Knowledge graph entity and relationship extraction

### Changed
- **Architecture Migration**
  - Migrated from cmis-graphrag/langchain/neo4j-graphrag stack
  - Unified configuration system across all components
  - Angular dialog updates (React and Vue clients pending similar changes)

### Fixed
- Document format support alignment with Docling capabilities
- Filesystem data source integration (CMIS and Alfresco integration planned)

### Technical
- Tested with Neo4j as graph and vector database
- LlamaIndex BM25 as full-text search engine
- Elasticsearch and OpenSearch integration marked for future development

## [2025-08-05] - Initial Project Setup

### Added
- Flexible GraphRAG initial project structure
- Reorganized from cmis-graphrag-ui with frontends moved to flexible-graphrag-ui subdirectory
- Backend moved to flexible-graphrag subdirectory

