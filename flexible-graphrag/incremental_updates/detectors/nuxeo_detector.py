"""
Nuxeo change detector — real-time via the Nuxeo audit Kafka stream.

Mirrors AlfrescoDetector's event mode, but consumes doc-change events from the
`nuxeo-audit-audit` Kafka topic (via NuxeoAuditConsumer) instead of ActiveMQ STOMP.

Flow:
  - NuxeoAuditConsumer decodes audit LogEntry JSON and fans {change_type, uid, path}
    events into this detector's thread-safe queue.
  - get_changes() drains the queue: CREATE/UPDATE resolve the LIVE doc by path (so a
    version's docUUID never leaks in), then ingest via backend; DELETE is yielded for
    the engine to remove from the stores. The periodic refresh (list_all_files) is the
    backstop for anything the event stream misses (e.g. downtime).
"""

import asyncio
import logging
import queue
from datetime import datetime, timezone
from typing import Dict, Optional, AsyncGenerator, List

from .base import ChangeDetector, ChangeType, ChangeEvent, FileMetadata
from .nuxeo_audit import NuxeoAuditConsumer

logger = logging.getLogger("flexible_graphrag.incremental.detectors.nuxeo")


class NuxeoDetector(ChangeDetector):
    """Real-time Nuxeo change detector backed by the audit Kafka stream."""

    def __init__(self, config: Dict):
        super().__init__(config)

        # Connection / auth (same shape as NuxeoConfig / NuxeoSource)
        self.url = config.get("url")
        self.auth_method = (config.get("auth_method") or "basic").lower()
        self.username = config.get("username")
        self.password = config.get("password")
        self.token = config.get("token")
        self.oauth2 = config.get("oauth2")
        self.path = config.get("path", "/")
        self.recursive = config.get("recursive", False)

        # Kafka
        import os
        self.kafka_bootstrap_servers = (
            config.get("kafka_bootstrap_servers")
            or os.getenv("NUXEO_KAFKA_BOOTSTRAP_SERVERS")
            or "localhost:9092"
        )
        self.audit_topic = config.get("audit_topic") or os.getenv("NUXEO_AUDIT_TOPIC") or "nuxeo-audit-audit"

        # Periodic refresh cadence (engine drives it; event stream is primary)
        self.polling_interval = config.get("polling_interval", 300)

        # Injected by the orchestrator
        self.state_manager = None
        self.config_id: Optional[str] = None
        self.backend = None

        # Event plumbing
        self._event_queue_sync: "queue.Queue" = queue.Queue()
        self._consumer: Optional[NuxeoAuditConsumer] = None
        self._running = False

        # Dedup by the live doc's dc:modified (keyed by uid): collapses the per-save burst
        # (documentCreated-version + documentModified all share one dc:modified) while still
        # processing SEPARATE saves, which each bump dc:modified. A time window would wrongly
        # drop legitimate edits made within the window.
        self._last_seen_modified: Dict[str, str] = {}

        # Cached NuxeoSource for path→uid resolution and listing
        self._source = None

        if not self.url:
            raise ValueError("NuxeoDetector requires 'url' in config")

        logger.info(f"NuxeoDetector initialized - url={self.url}, path={self.path}, "
                    f"recursive={self.recursive}, kafka={self.kafka_bootstrap_servers}, topic={self.audit_topic}")

    # ------------------------------------------------------------------ config
    def _base_source_config(self) -> Dict:
        cfg = {"url": self.url, "auth_method": self.auth_method}
        if self.username:
            cfg["username"] = self.username
        if self.password:
            cfg["password"] = self.password
        if self.token:
            cfg["token"] = self.token
        if self.oauth2:
            cfg["oauth2"] = self.oauth2
        return cfg

    def _get_source(self):
        """Lazily build a reusable NuxeoSource (for path→uid resolution and listing)."""
        if self._source is None:
            from sources.nuxeo import NuxeoSource
            cfg = self._base_source_config()
            cfg["path"] = self.path
            cfg["recursive"] = self.recursive
            self._source = NuxeoSource(cfg)
        return self._source

    def _in_scope(self, doc_path: str) -> bool:
        """Is the event's docPath within the monitored path (respecting recursive)?"""
        if not doc_path:
            return False
        base = self.path or "/"
        if base in ("/", ""):
            return True
        base = base.rstrip("/")
        if not doc_path.startswith(base + "/"):
            return False
        if self.recursive:
            return True
        # non-recursive: only direct children (no extra '/' after base/)
        remainder = doc_path[len(base) + 1:]
        return "/" not in remainder

    # --------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        if self._running:
            logger.warning("NuxeoDetector already running")
            return
        logger.info(f"Starting NuxeoDetector for {self.url}{self.path}")
        self._running = True
        # Register with the shared audit consumer (starts the Kafka consumer thread once)
        loop = asyncio.get_event_loop()
        self._consumer = await loop.run_in_executor(
            None, lambda: NuxeoAuditConsumer.get_instance(self.kafka_bootstrap_servers, self.audit_topic)
        )
        self._consumer.register_detector(self)
        logger.info("NuxeoDetector event mode active - real-time audit stream")

    async def stop(self) -> None:
        logger.info("Stopping NuxeoDetector")
        self._running = False
        if self._consumer:
            try:
                self._consumer.unregister_detector(self)
            except Exception as e:
                logger.warning(f"Error unregistering from audit consumer: {e}")
            self._consumer = None

    # ------------------------------------------------------------- resolution
    async def _resolve_live(self, doc_path: str) -> Optional[dict]:
        """Resolve a docPath to the LIVE supported file's info dict, or None.

        Uses NuxeoSource path mode (documents.get by path), which returns the current
        document — never a version — so we always ingest with the live uid.
        """
        try:
            source = self._get_source()
            loop = asyncio.get_event_loop()
            files = await loop.run_in_executor(None, lambda: source._process_folder_by_path(doc_path))
            if files:
                return files[0]  # single-file path yields exactly one entry
        except Exception as e:
            logger.warning(f"Failed to resolve live doc at {doc_path}: {e}")
        return None

    # --------------------------------------------------------------- changes
    async def get_changes(self) -> AsyncGenerator[Optional[ChangeEvent], None]:
        if not self._running:
            logger.warning("NuxeoDetector not started - call start() first")
            return
        logger.info("Starting Nuxeo change monitoring (EVENT MODE - Kafka audit stream)")
        while self._running:
            try:
                try:
                    event = self._event_queue_sync.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(1.0)
                    yield None
                    continue

                change_type = event["change_type"]
                doc_path = event["path"]
                doc_uuid = event["uid"]

                if not self._in_scope(doc_path):
                    continue

                if change_type == "DELETE":
                    logger.info(f"NUXEO EVENT: DELETE for {doc_path} (uid={doc_uuid})")
                    metadata = FileMetadata(
                        source_type="nuxeo",
                        path=f"nuxeo://{doc_uuid}",
                        ordinal=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
                        extra={"node_id": doc_uuid},
                    )
                    yield ChangeEvent(metadata=metadata, change_type=ChangeType.DELETE, timestamp=None)
                    continue

                # A trashed doc's path becomes "<name>._<ts>_.trashed"; the DELETE (documentTrashed)
                # event removes it by uid, so skip CREATE/UPDATE here to avoid re-ingesting it.
                if ".trashed" in doc_path:
                    logger.info(f"NUXEO EVENT: {change_type} for trashed path {doc_path} - skipping")
                    continue

                # Resolve the LIVE doc (skips versions and non-supported docs/folders)
                file_info = await self._resolve_live(doc_path)
                if not file_info:
                    logger.info(f"NUXEO EVENT: {change_type} {doc_path} not a supported live file - skipping")
                    continue

                uid = file_info["id"]
                filename = file_info["name"]
                modified = str(file_info.get("modified_at") or "")

                # Dedup by dc:modified (collapses the per-save burst; lets separate saves through)
                if modified and self._last_seen_modified.get(uid) == modified:
                    logger.info(f"NUXEO EVENT: dedup {change_type} for {doc_path} (modified unchanged)")
                    continue
                self._last_seen_modified[uid] = modified

                # New vs existing → CREATE (process directly) or UPDATE (DELETE + re-ingest)
                exists = False
                if self.state_manager and self.config_id:
                    try:
                        st = await self.state_manager.get_state(f"{self.config_id}:nuxeo://{uid}")
                        exists = st is not None
                    except Exception as e:
                        logger.debug(f"state check failed for nuxeo://{uid}: {e}")

                if not exists:
                    logger.info(f"NUXEO EVENT: CREATE for {doc_path} (uid={uid}) - ingesting via backend")
                    try:
                        await self._process_via_backend(uid, filename, doc_path)
                    except Exception as e:
                        logger.error(f"Failed to process CREATE for {doc_path}: {e}")
                else:
                    logger.info(f"NUXEO EVENT: UPDATE for {doc_path} (uid={uid}) - DELETE + re-ingest")

                    async def add_callback(_uid=uid, _fn=filename, _fp=doc_path):
                        logger.info(f"UPDATE: DELETE completed, re-ingesting {_fp}")
                        try:
                            await self._process_via_backend(_uid, _fn, _fp)
                        except Exception as e:
                            logger.error(f"Failed to re-ingest {_fp}: {e}")

                    metadata = FileMetadata(
                        source_type="nuxeo",
                        path=f"nuxeo://{uid}",
                        ordinal=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
                        extra={"node_id": uid},
                    )
                    yield ChangeEvent(
                        metadata=metadata,
                        change_type=ChangeType.DELETE,
                        timestamp=None,
                        is_modify_delete=True,
                        modify_callback=add_callback,
                    )

            except asyncio.CancelledError:
                logger.info("NuxeoDetector monitoring cancelled")
                self._running = False
                break
            except Exception as e:
                logger.exception(f"Error in Nuxeo change detection: {e}")
                await asyncio.sleep(5)
                yield None

    # ------------------------------------------------------------- listing
    async def list_all_files(self) -> List[FileMetadata]:
        """List all supported files under the monitored path (periodic/backstop sync)."""
        logger.info("Listing all files in Nuxeo repository...")
        source = self._get_source()
        loop = asyncio.get_event_loop()
        files = await loop.run_in_executor(None, source.list_files)
        result: List[FileMetadata] = []
        for fi in files:
            uid = fi["id"]
            modified = fi.get("modified_at")
            modified_ts = self.parse_timestamp(modified)
            ordinal = int(modified_ts.timestamp() * 1_000_000) if modified_ts else int(
                datetime.now(timezone.utc).timestamp() * 1_000_000)
            result.append(FileMetadata(
                source_type="nuxeo",
                path=f"nuxeo://{uid}",  # matches doc_id (config_id:nuxeo://uid)
                ordinal=ordinal,
                mime_type=fi.get("content_type"),
                modified_timestamp=str(modified) if modified else None,
                extra={"node_id": uid, "name": fi["name"], "file_path": fi.get("path")},
            ))
        logger.info(f"Listed {len(result)} files from Nuxeo")
        return result

    # ------------------------------------------------------------- ingest
    async def _process_via_backend(self, uid: str, filename: str, file_path: str) -> None:
        """Ingest a single Nuxeo doc via the backend pipeline (nodeDetails mode)."""
        if not self.backend:
            logger.error("Backend not injected into NuxeoDetector - cannot process")
            return

        skip_graph = getattr(self, "skip_graph", False)
        # ...or just this document's graph was removed (document_state.skip_graph)
        if not skip_graph and self.state_manager and self.config_id:
            skip_graph = await self.state_manager.doc_skip_graph(
                config_id=self.config_id, source_id=uid)
        processing_id = f"incremental_nuxeo_{uid[:8]}"

        nuxeo_config = self._base_source_config()
        nuxeo_config.update({
            "path": self.path,
            "recursive": False,
            "nodeDetails": [{
                "id": uid, "name": filename, "path": file_path,
                "isFile": True, "isFolder": False,
            }],
        })

        await self.backend._process_documents_async(
            processing_id=processing_id,
            data_source="nuxeo",
            config_id=self.config_id,
            skip_graph=skip_graph,
            nuxeo_config=nuxeo_config,
        )

        from backend import PROCESSING_STATUS
        if PROCESSING_STATUS.get(processing_id, {}).get("status") == "failed":
            logger.error(f"Backend ingest failed for {filename} ({uid}); not recording document_state")
            return

        logger.info(f"Successfully ingested {filename} ({uid}) via backend pipeline")

        if self.state_manager:
            try:
                await self._create_document_state_from_processing_status(processing_id, filename, uid, file_path, skip_graph=skip_graph)
            except Exception as e:
                logger.error(f"Failed to create document_state for {filename}: {e}")

    async def _create_document_state_from_processing_status(
        self, processing_id: str, filename: str, uid: str, file_path: str,
        skip_graph: Optional[bool] = None
    ) -> None:
        from backend import PROCESSING_STATUS
        from incremental_updates.state_manager import DocumentState, StateManager

        await asyncio.sleep(0.5)
        status_dict = PROCESSING_STATUS.get(processing_id, {})
        if status_dict.get("status") != "completed":
            logger.warning(f"Processing not completed for {filename}, skipping document_state")
            return
        documents = status_dict.get("documents", [])
        if not documents:
            logger.warning(f"No documents in PROCESSING_STATUS for {filename}")
            return

        doc = documents[0]
        source_id = doc.metadata.get("nuxeo_id") or uid
        stable_path = doc.metadata.get("stable_file_path") or f"nuxeo://{source_id}"
        doc_id = f"{self.config_id}:{stable_path}"

        modified_timestamp = self.parse_timestamp(doc.metadata.get("modified_at"))
        content_hash = None
        if hasattr(doc, "text") and doc.text:
            content_hash = StateManager.compute_content_hash(doc.text)

        ordinal = doc.metadata.get("ordinal")
        if not ordinal and modified_timestamp and isinstance(modified_timestamp, datetime):
            ordinal = int(modified_timestamp.timestamp() * 1_000_000)
        if not ordinal:
            ordinal = int(datetime.now(timezone.utc).timestamp() * 1_000_000)

        now = datetime.now(timezone.utc)
        doc_state = DocumentState(
            doc_id=doc_id,
            config_id=self.config_id,
            source_path=file_path,       # human-readable Nuxeo path
            ordinal=ordinal,
            content_hash=content_hash,
            source_id=source_id,         # uid (matches periodic delete-detection identifier)
            modified_timestamp=modified_timestamp,
            vector_synced_at=now,
            search_synced_at=now,
            graph_synced_at=now if not (getattr(self, "skip_graph", False) if skip_graph is None else skip_graph) else None,
        )
        await self.state_manager.save_state(doc_state)
        logger.info(f"Created document_state for {filename}: {doc_id}")
