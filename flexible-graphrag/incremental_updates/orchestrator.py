"""
Incremental Update Orchestrator

Coordinates change detection, batching, and incremental updates
across multiple data sources.
"""

import asyncio
import logging
from typing import Dict, Optional
from collections import defaultdict
from datetime import datetime, timedelta

from .config_manager import ConfigManager, DataSourceConfig
from .state_manager import StateManager
from .detectors import create_detector, ChangeDetector, ChangeEvent
from .engine import IncrementalUpdateEngine

logger = logging.getLogger("flexible_graphrag.incremental.orchestrator")


class SourceUpdater:
    """Manages incremental updates for a single datasource"""
    
    def __init__(
        self,
        config: DataSourceConfig,
        detector: ChangeDetector,
        engine: IncrementalUpdateEngine,
        config_manager: ConfigManager
    ):
        self.config = config
        self.detector = detector
        self.engine = engine
        self.config_manager = config_manager
        self._running = False
        self._tasks = []
    
    async def run(self):
        """Main loop - dual mechanism (periodic refresh + event stream)"""
        self._running = True
        
        try:
            # Start detector
            await self.detector.start()
            
            # Launch tasks
            tasks = [
                asyncio.create_task(self._periodic_refresh()),
            ]
            
            # Add event stream if enabled
            if self.config.enable_change_stream:
                tasks.append(asyncio.create_task(self._watch_changes()))
            
            self._tasks = tasks
            await asyncio.gather(*tasks)
        
        except Exception as e:
            logger.exception(f"Error in source updater for {self.config.source_name}: {e}")
        finally:
            await self.detector.stop()
            self._running = False
    
    async def stop(self):
        """Stop the updater"""
        self._running = False
        for task in self._tasks:
            task.cancel()
    
    async def trigger_manual_sync(self):
        """Trigger an immediate manual sync (for testing/on-demand)"""
        try:
            logger.info(f"MANUAL SYNC: Starting on-demand sync for {self.config.source_name}...")
            
            await self.config_manager.update_sync_status(
                self.config.config_id, 'syncing'
            )
            
            # Perform refresh
            max_ordinal = self.config.last_sync_ordinal or 0
            new_max_ordinal = await self.engine.periodic_refresh(
                self.detector,
                self.config.config_id,
                max_ordinal
            )
            
            # Update last sync info
            await self.config_manager.update_last_sync(
                self.config.config_id,
                new_max_ordinal
            )
            
            await self.config_manager.update_sync_status(
                self.config.config_id, 'idle'
            )
            
            logger.info(f"MANUAL SYNC: Completed for {self.config.source_name}")
            return {"status": "success", "source_name": self.config.source_name}
            
        except Exception as e:
            logger.error(f"MANUAL SYNC: Error for {self.config.source_name}: {e}")
            await self.config_manager.update_sync_status(
                self.config.config_id, 'error', str(e)
            )
            raise
    
    async def _periodic_refresh(self):
        """Periodic full refresh"""
        # Wait for initial delay before first refresh
        # This prevents detecting documents that are currently being ingested
        initial_delay = 10  # 10 seconds for testing (change to 120 for production)
        logger.info(f"   Periodic refresh: waiting {initial_delay}s before first scan...")
        await asyncio.sleep(initial_delay)
        
        while self._running:
            try:
                await self.config_manager.update_sync_status(
                    self.config.config_id, 'syncing'
                )
                
                logger.info(f"SYNC: Starting periodic refresh for {self.config.source_name}...")
                
                # Perform refresh
                max_ordinal = self.config.last_sync_ordinal or 0
                new_max_ordinal = await self.engine.periodic_refresh(
                    self.detector,
                    self.config.config_id,
                    max_ordinal
                )
                
                # Update status
                await self.config_manager.update_sync_status(
                    self.config.config_id,
                    'idle',
                    ordinal=new_max_ordinal
                )
                
                logger.info(f"SUCCESS: Completed refresh for {self.config.source_name}")
            
            except Exception as e:
                logger.exception(f"Error in periodic refresh for {self.config.source_name}: {e}")
                await self.config_manager.update_sync_status(
                    self.config.config_id,
                    'error',
                    error=str(e)
                )
            
            # Wait for next interval
            await asyncio.sleep(self.config.refresh_interval_seconds)
    
    async def _watch_changes(self):
        """Watch for real-time changes using watchdog file system monitor"""
        try:
            logger.info(f"WATCHING: for file changes in {self.config.source_name}...")
            
            # Get the async generator ONCE and reuse it
            change_stream = self.detector.get_changes()
            logger.info(f"WATCH LOOP: change_stream created, starting loop...")
            
            while self._running:
                try:
                    # Wait for next event (blocks until available)
                    event = await change_stream.__anext__()
                    
                    # Skip None events (timeout signals from generator)
                    if event is None:
                        continue
                    
                    logger.info(f"EVENT: Processing change: {event.metadata.path} ({event.change_type.value})")
                    
                    try:
                        # Process immediately (no debouncing/batching)
                        await self.engine.process_batch(
                            [event],
                            self.detector,
                            self.config.config_id
                        )
                        logger.info(f"SUCCESS: Processed {event.metadata.path}")
                        
                        # Set quiet period to ignore our own file changes
                        if hasattr(self.detector, 'set_quiet_period'):
                            self.detector.set_quiet_period(5)  # Ignore changes for 5 seconds
                            
                    except Exception as e:
                        logger.exception(f"Error processing file change {event.metadata.path}: {e}")
                            
                except StopAsyncIteration:
                    # Detector stopped
                    logger.warning(f"WATCH LOOP: Detector stopped (StopAsyncIteration), exiting...")
                    break
                except asyncio.CancelledError:
                    logger.warning(f"WATCH LOOP: Task cancelled, exiting...")
                    raise
                except Exception as e:
                    logger.exception(f"WATCH LOOP: Unexpected error in watch loop: {e}")
                    await asyncio.sleep(1)  # Prevent tight loop on error
        
        except asyncio.CancelledError:
            logger.info(f"WATCH LOOP: Watch task cancelled for {self.config.source_name}")
            raise
        except Exception as e:
            logger.exception(f"WATCH LOOP: Fatal error in _watch_changes for {self.config.source_name}: {e}")
        finally:
            logger.info(f"WATCH LOOP: Exiting watch_changes for {self.config.source_name}")


class IncrementalUpdateOrchestrator:
    """
    Top-level orchestrator that manages multiple data sources.
    Monitors config changes and spawns/stops updaters dynamically.
    """
    
    def __init__(
        self,
        config_manager: ConfigManager,
        state_manager: StateManager,
        engine: IncrementalUpdateEngine,
        backend=None  # NEW: Backend instance for detector injection
    ):
        self.config_manager = config_manager
        self.state_manager = state_manager
        self.engine = engine
        self.backend = backend  # Store backend reference
        
        self.active_updaters: Dict[str, SourceUpdater] = {}
        self.updater_tasks: Dict[str, asyncio.Task] = {}
    
    async def run(self):
        """Main orchestration loop"""
        logger.info("=" * 60)
        logger.info("  Flexible GraphRAG Incremental Update System")
        logger.info("=" * 60)
        logger.info("")
        logger.info("INFO: Starting orchestrator...")
        
        # Initialize components
        await self.config_manager.initialize()
        await self.state_manager.initialize()
        
        # Start updaters for all active configs
        configs = await self.config_manager.get_all_active_configs()
        
        if not configs:
            logger.info("INFO: No data sources configured for auto-sync")
            logger.info("      Auto-sync is ready - add datasources via UI or API when needed")
        else:
            logger.info(f"INFO: Found {len(configs)} active data source(s) configured for auto-sync")
        
        for config in configs:
            await self._start_updater(config)
        
        # Give updaters a moment to start
        if configs:
            await asyncio.sleep(0.5)
            logger.info(f"INFO: Started {len(self.active_updaters)} auto-sync updater(s)")
        
        # Listen for config changes
        logger.info("INFO: Monitoring for configuration changes...")
        logger.info("")
        
        try:
            async for change in self.config_manager.listen_for_config_changes():
                try:
                    await self._handle_config_change(change)
                except Exception as e:
                    logger.error(f"Error handling config change: {e}")
                    import traceback
                    traceback.print_exc()
        except KeyboardInterrupt:
            logger.info("\nWARNING: Shutdown requested...")
        finally:
            await self._shutdown()
    
    async def _handle_config_change(self, change: Dict):
        """React to datasource config changes"""
        operation = change['operation']
        
        if operation == 'insert':
            config = change['config']
            logger.info(f"INFO: New datasource detected: {config.source_name}")
            await self._start_updater(config)
        
        elif operation == 'update':
            config = change['config']
            config_id = config.config_id
            
            if not config.is_active:
                logger.info(f"INFO: Deactivating datasource: {config.source_name}")
                await self._stop_updater(config_id)
            else:
                logger.info(f"INFO: Restarting datasource: {config.source_name}")
                await self._stop_updater(config_id)
                await self._start_updater(config)
        
        elif operation == 'delete':
            config_id = change['config_id']
            logger.info(f"INFO: Deleting datasource: {config_id}")
            await self._stop_updater(config_id)
    
    async def _start_updater(self, config: DataSourceConfig):
        """Start incremental updater for a datasource"""
        
        try:
            # Check if updater already exists
            if config.config_id in self.active_updaters:
                logger.debug(f"Updater for {config.source_name} already running, skipping...")
                return
            
            logger.info(f"Creating detector for {config.source_name} (type: {config.source_type})...")
            
            # Create detector
            detector = create_detector(
                config.source_type,
                config.connection_params
            )
            
            if detector is None:
                logger.error(f"Cannot create detector for {config.source_type} - source: {config.source_name}")
                logger.error(f"Connection params keys: {list(config.connection_params.keys()) if config.connection_params else 'None'}")
                return
            
            logger.info(f"Detector created successfully for {config.source_name}")
            
            # Inject backend, state_manager, config_id, and skip_graph into detector
            if hasattr(detector, 'backend'):
                detector.backend = self.backend
                detector.state_manager = self.state_manager
                detector.config_id = config.config_id
                detector.skip_graph = config.skip_graph  # NEW: Inject skip_graph
                
                # For MicrosoftGraphDetector, inject enable_change_polling from enable_change_stream
                if hasattr(detector, 'enable_change_polling'):
                    detector.enable_change_polling = config.enable_change_stream
                    logger.info(f"Set enable_change_polling={config.enable_change_stream} for {config.source_name}")
                
                logger.info(f"Injected backend, state_manager, config_id, and skip_graph into detector")
            elif hasattr(detector, 'state_manager'):
                # Fallback for detectors that don't support backend yet
                detector.state_manager = self.state_manager
                detector.config_id = config.config_id
                logger.info(f"Set state_manager and config_id on detector (no backend support)")
            
            # Create updater
            updater = SourceUpdater(
                config,
                detector,
                self.engine,
                self.config_manager
            )
            
            logger.info(f"Starting updater task for {config.source_name}...")
            
            # Start task
            task = asyncio.create_task(updater.run())
            
            self.active_updaters[config.config_id] = updater
            self.updater_tasks[config.config_id] = task
            
            logger.info(f"SUCCESS: Updater started for {config.source_name} ({config.source_type})")
            
            logger.info(f"SUCCESS: Started updater for {config.source_name}")
        
        except Exception as e:
            logger.error(f"ERROR: Failed to start updater for {config.source_name}: {e}")
            import traceback
            traceback.print_exc()
    
    async def _stop_updater(self, config_id: str):
        """Stop incremental updater"""
        if config_id in self.active_updaters:
            updater = self.active_updaters[config_id]
            await updater.stop()
            
            task = self.updater_tasks[config_id]
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            del self.active_updaters[config_id]
            del self.updater_tasks[config_id]
            
            logger.info(f"INFO: Stopped updater for {config_id}")
    
    async def _shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down all updaters...")
        
        # Stop all updaters
        for config_id in list(self.active_updaters.keys()):
            await self._stop_updater(config_id)
        
        # Close connections
        await self.config_manager.close()
        await self.state_manager.close()
        
        logger.info("SUCCESS: Shutdown complete")
    
    async def trigger_sync(self, config_id: str) -> dict:
        """
        Trigger manual sync for a specific datasource.
        Useful for on-demand syncing without waiting for periodic refresh.
        
        Args:
            config_id: UUID of the datasource config
            
        Returns:
            dict with status and details
        """
        if config_id not in self.active_updaters:
            raise ValueError(f"No active updater found for config_id: {config_id}")
        
        updater = self.active_updaters[config_id]
        return await updater.trigger_manual_sync()

