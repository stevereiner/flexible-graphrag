# Changelog

All notable changes to this project will be documented in this file.

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

