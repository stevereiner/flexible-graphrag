"""
Shared incremental update system for backend.
Singleton pattern - created once, reused for all sync operations.
"""

import asyncio
import json
import logging
from typing import Optional
from uuid import uuid4

from incremental_updates.config_manager import ConfigManager
from incremental_updates.state_manager import StateManager
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
        postgres_url: str,
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
            postgres_url: PostgreSQL connection string
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
        
        # Create managers
        self.config_manager = ConfigManager(postgres_url)
        self.state_manager = StateManager(postgres_url)
        
        await self.config_manager.initialize()
        await self.state_manager.initialize()
        
        logger.info("  SUCCESS: State managers initialized")
        
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
        skip_graph: bool = False  # NEW: Skip graph extraction flag
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
            skip_graph: Skip graph extraction for this datasource
        
        Returns:
            config_id: UUID of created datasource config
        """
        if not self._initialized:
            raise RuntimeError("System not initialized")
        
        # Auto-detect enable_change_stream based on source_type if not explicitly set
        if enable_change_stream is None:
            # Sources WITH event streams (polling-based, not real-time push)
            # Note: onedrive/sharepoint removed until Microsoft Graph delta endpoint is fully implemented
            sources_with_events = ['google_drive', 'box', 'alfresco', 'filesystem']
            
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
        
        async with self.config_manager.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO datasource_config 
                (config_id, project_id, source_type, source_name, connection_params, 
                 refresh_interval_seconds, watchdog_filesystem_seconds, enable_change_stream, skip_graph)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
                config_id,
                project_id,
                source_type,
                source_name,
                json.dumps(connection_params),
                refresh_interval_seconds,
                watchdog_filesystem_seconds,
                enable_change_stream,
                skip_graph
            )
        
        logger.info(f"SUCCESS: Added datasource for sync: {source_name} ({config_id}), skip_graph={skip_graph}")
        
        # If orchestrator not running, start it
        if self._orchestrator_task is None or self._orchestrator_task.done():
            await self.start_monitoring()
        
        return config_id
    
    def is_initialized(self) -> bool:
        """Check if system is initialized"""
        return self._initialized
    
    def is_monitoring(self) -> bool:
        """Check if orchestrator is running"""
        return (
            self._orchestrator_task is not None 
            and not self._orchestrator_task.done()
        )
