"""
Shared incremental update system for backend.
Singleton pattern - created once, reused for all sync operations.
"""

import asyncio
import logging
from typing import Optional
from uuid import uuid4

from incremental_updates.config_manager import ConfigManager, DataSourceConfig
from incremental_updates.state_manager import StateManager
from incremental_updates.stores import new_config_manager, new_state_manager, state_store_label
from incremental_updates.engine import IncrementalUpdateEngine
from incremental_updates.orchestrator import IncrementalUpdateOrchestrator

logger = logging.getLogger("flexible_graphrag.incremental_system")


class IncrementalSystemManager:
    """
    Manages the incremental update system for the backend.
    Singleton pattern - only one instance should exist.
    """
    
    _instance: Optional['IncrementalSystemManager'] = None
    _initialized: bool = False
    _orchestrator_task: Optional[asyncio.Task] = None
    
    def __init__(self):
        if IncrementalSystemManager._instance is not None:
            raise RuntimeError("Use IncrementalSystemManager.get_instance()")
        
        self.config_manager: Optional[ConfigManager] = None
        self.state_manager: Optional[StateManager] = None
        self.engine: Optional[IncrementalUpdateEngine] = None
        self.orchestrator: Optional[IncrementalUpdateOrchestrator] = None
    
    @classmethod
    def get_instance(cls) -> 'IncrementalSystemManager':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = IncrementalSystemManager()
        return cls._instance
    
    async def initialize(
        self,
        postgres_url: Optional[str],
        vector_index,
        graph_index,
        search_index,
        doc_processor,
        app_config,
        hybrid_system,  # Pass hybrid_system for reuse!
        backend  # NEW: Backend instance for detectors to call _process_documents_async
    ):
        """
        Initialize the incremental update system.
        Should be called once at backend startup.
        
        Args:
            postgres_url: PostgreSQL connection string (unused with INCREMENTAL_STATE_STORE=openarch)
            vector_index: Existing vector index from backend
            graph_index: Existing graph index from backend
            search_index: Existing search index from backend
            doc_processor: Existing document processor from backend
            app_config: App configuration
            hybrid_system: HybridSearchSystem instance for reusing ingestion logic
            backend: FlexibleGraphRAGBackend instance for ADD/MODIFY operations
        """
        if self._initialized:
            logger.info("Incremental system already initialized")
            return
        
        logger.info("Initializing incremental update system...")
        
        # Create managers (PostgreSQL or the OpenArch tree: INCREMENTAL_STATE_STORE)
        self.config_manager = new_config_manager(postgres_url)
        self.state_manager = new_state_manager(postgres_url)
        
        await self.config_manager.initialize()
        await self.state_manager.initialize()
        
        logger.info(f"  SUCCESS: State managers initialized ({state_store_label()})")
        
        # Create engine (reuses backend's existing indexes!)
        self.engine = IncrementalUpdateEngine(
            vector_index=vector_index,
            graph_index=graph_index,
            search_index=search_index,
            doc_processor=doc_processor,
            state_manager=self.state_manager,
            app_config=app_config,
            hybrid_system=hybrid_system,  # Pass hybrid_system for reuse!
            config_manager=self.config_manager  # Pass config_manager for datasource config access
        )
        
        logger.info("  SUCCESS: Incremental engine created")
        
        # Create orchestrator (now with backend reference)
        self.orchestrator = IncrementalUpdateOrchestrator(
            self.config_manager,
            self.state_manager,
            self.engine,
            backend  # NEW: Pass backend for detector injection
        )
        
        logger.info("  SUCCESS: Orchestrator created")
        
        self._initialized = True
        logger.info("SUCCESS: Incremental system initialized")
    
    async def start_monitoring(self):
        """
        Start the orchestrator in background.
        Monitors all active datasources for changes.
        """
        if not self._initialized:
            raise RuntimeError("System not initialized - call initialize() first")
        
        if self._orchestrator_task is not None and not self._orchestrator_task.done():
            logger.info("Orchestrator already running")
            return
        
        logger.info("Starting orchestrator in background...")
        self._orchestrator_task = asyncio.create_task(self.orchestrator.run())
        logger.info("SUCCESS: Orchestrator started")
    
    async def stop_monitoring(self):
        """Stop the orchestrator"""
        if self._orchestrator_task is not None and not self._orchestrator_task.done():
            logger.info("Stopping orchestrator...")
            self._orchestrator_task.cancel()
            try:
                await self._orchestrator_task
            except asyncio.CancelledError:
                pass
            logger.info("SUCCESS: Orchestrator stopped")
    
    async def add_datasource_for_sync(
        self,
        source_type: str,
        source_name: str,
        connection_params: dict,
        config_id: str = None,  # NEW: Accept optional config_id for stable doc_id
        project_id: str = "default",
        refresh_interval_seconds: int = 300,  # Default: 5 minutes (better for testing)
        watchdog_filesystem_seconds: int = 60,
        enable_change_stream: bool = None,  # Auto-detect based on source_type
        skip_graph: bool = False,  # the older single flag (both graphs off)
        graphs=None,  # which graphs it builds (graph_flags.GraphFlags); wins over skip_graph
    ) -> str:
        """
        Add a datasource for incremental sync.
        Called when user enables sync in UI.
        
        Args:
            source_type: 'filesystem', 's3', 'alfresco', etc.
            source_name: Human-readable name
            connection_params: Source-specific config
            config_id: Optional pre-generated config_id (for stable doc_id)
            project_id: Project ID (future use)
            refresh_interval_seconds: Periodic scan interval
            watchdog_filesystem_seconds: Filesystem watcher delay
            enable_change_stream: Enable real-time monitoring (None=auto-detect)
            skip_graph: Skip both graphs for this datasource (older flag)
            graphs: Which graphs this datasource builds (property graph, RDF)
        
        Returns:
            config_id: UUID of created datasource config
        """
        if not self._initialized:
            raise RuntimeError("System not initialized")
        from graph_flags import GraphFlags
        flags = graphs if graphs is not None else GraphFlags.of(bool(skip_graph))
        
        # Auto-detect enable_change_stream based on source_type if not explicitly set
        if enable_change_stream is None:
            # Sources WITH event streams (polling-based, not real-time push)
            # onedrive/sharepoint use the Microsoft Graph delta query (resumable deltaLink, polled every
            # polling_interval s) — enabled by default now that the delta endpoint is implemented.
            # This flag drives BOTH the orchestrator's event-stream task AND the detector's
            # enable_change_polling, which must stay in step: the engine skips NEW files in the periodic
            # refresh whenever enable_change_polling is on, so if the stream weren't drained they'd be missed.
            sources_with_events = ['google_drive', 'box', 'alfresco', 'nuxeo', 'filesystem', 'onedrive', 'sharepoint']
            
            # S3 has events only if sqs_queue_url is configured
            if source_type == 's3' and connection_params.get('sqs_queue_url'):
                enable_change_stream = True
            # GCS has events only if pubsub_subscription is configured
            elif source_type == 'gcs' and connection_params.get('pubsub_subscription'):
                enable_change_stream = True
            # Azure Blob: Change Feed is attempted by default in detector
            # The detector will try change feed and fall back to periodic if not available
            # So we enable change_stream and let the detector handle fallback
            elif source_type == 'azure_blob':
                enable_change_stream = True
            elif source_type in sources_with_events:
                enable_change_stream = True
            else:
                # Default: periodic-only (no event stream)
                enable_change_stream = False
            
            logger.info(f"Auto-detected enable_change_stream={enable_change_stream} for {source_type}")
        
        # Use provided config_id or generate new one
        if config_id is None:
            config_id = str(uuid4())
        
        # config_id is a deterministic uuid5 of the datasource identity, so re-ingesting a source
        # that already has sync enabled lands on the same record: create_config upserts the
        # caller's current settings but leaves sync progress (sync_status, last_sync_ordinal,
        # last_sync_completed_at) alone, so a re-registration does not force a full re-ingest.
        await self.config_manager.create_config(DataSourceConfig(
            config_id=config_id,
            project_id=project_id,
            source_type=source_type,
            source_name=source_name,
            connection_params=connection_params,
            refresh_interval_seconds=refresh_interval_seconds,
            watchdog_filesystem_seconds=watchdog_filesystem_seconds,
            enable_change_stream=enable_change_stream,
            skip_graph=flags.none,
            enabled_graph=flags.graph,
            enabled_rdf=flags.rdf,
            is_active=True,
            auto_sync=True,
        ))

        logger.info(f"SUCCESS: Added datasource for sync: {source_name} ({config_id}), {flags.describe()}")
        
        # If orchestrator not running, start it
        if self._orchestrator_task is None or self._orchestrator_task.done():
            await self.start_monitoring()
        
        return config_id
    
    async def register_ingest_only(
        self,
        source_type: str,
        source_name: str,
        connection_params: dict,
        config_id: str,
        skip_graph: bool = False,
        project_id: str = "default",
        graphs=None,
    ) -> None:
        """Record a datasource that was ingested WITHOUT auto change sync.

        The row exists so a later ingest of the same source (same config_id) can find what it
        put in the stores and replace it rather than add a second copy, and so ingest status can
        report it. It is stored inactive with auto_sync = FALSE, so no detector, orchestrator,
        enable-all or CocoIndex loader ever picks it up.

        A source that already has auto change sync keeps its row untouched: an ingest-only
        repeat must not switch a real sync off or overwrite its stored credentials.
        """
        if not self._initialized:
            raise RuntimeError("System not initialized")
        from graph_flags import GraphFlags
        flags = graphs if graphs is not None else GraphFlags.of(bool(skip_graph))
        await self.config_manager.register_ingest_only(DataSourceConfig(
            config_id=config_id,
            project_id=project_id,
            source_type=source_type,
            source_name=source_name,
            connection_params=connection_params,
            skip_graph=flags.none,
            enabled_graph=flags.graph,
            enabled_rdf=flags.rdf,
            is_active=False,
            auto_sync=False,
        ))
        logger.info(f"Recorded ingest-only datasource {source_name} ({config_id})")

    async def get_doc_ids(self, config_id: str) -> list:
        """doc_ids already recorded in document_state for a datasource."""
        if not self._initialized:
            return []
        return await self.state_manager.doc_ids_for_config(config_id)

    async def take_over_other_ingest_copies(self, config_id: str, sync_takeover: bool = False) -> list:
        """Settle documents of ``config_id`` that another datasource also holds; see
        StateManager.resolve_duplicate_copies. Returns the doc_ids the caller must delete from
        the stores."""
        if not self._initialized:
            return []
        return await self.state_manager.resolve_duplicate_copies(config_id, sync_takeover)

    def is_initialized(self) -> bool:
        """Check if system is initialized"""
        return self._initialized
    
    def is_monitoring(self) -> bool:
        """Check if orchestrator is running"""
        return (
            self._orchestrator_task is not None 
            and not self._orchestrator_task.done()
        )
