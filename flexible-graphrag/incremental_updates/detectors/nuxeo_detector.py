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
        # switched to the backend's own account after these credentials were rejected
        self._using_backend_account = False
        self.path = config.get("path", "/")
        self.recursive = config.get("recursive", False)
        # The selected documents (a multi-select), else the whole path is followed
        self.node_details = config.get("nodeDetails") or None
        self.node_ids = config.get("nodeIds") or None
        self._root_paths: Dict[str, str] = {}
        self._root_paths_at = 0.0

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

        # Dedup by the live doc's dc:modified, path and name (keyed by uid): collapses the
        # per-save burst (documentCreated-version + documentModified all share one dc:modified)
        # while still processing SEPARATE saves, which each bump dc:modified, and moves, which
        # don't. A time window would wrongly drop legitimate edits made within the window.
        self._last_seen_modified: Dict[str, tuple] = {}

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

    async def _credentials_status(self) -> Optional[int]:
        """HTTP status of GET /api/v1/me with this sync's credentials (None: Nuxeo not reachable)."""
        import httpx
        headers: Dict[str, str] = {}
        auth = None
        access_token = (self.oauth2 or {}).get("access_token") if isinstance(self.oauth2, dict) else None
        if self.token:
            headers["X-Authentication-Token"] = self.token
        elif access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        elif self.username and self.password:
            auth = httpx.BasicAuth(self.username, self.password)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{(self.url or '').rstrip('/')}/api/v1/me", headers=headers, auth=auth)
                return res.status_code
        except Exception as e:
            logger.warning(f"Nuxeo sync: could not check its credentials at {self.url}: {e}")
            return None

    async def _use_backend_account_if_rejected(self) -> bool:
        """Credentials that stopped working (a revoked token, say): switch this sync to the backend's own account,
        for the backend's own server (sources/nuxeo_accounts.py). True when it switched."""
        if self._using_backend_account:
            return False
        status = await self._credentials_status()
        if status not in (401, 403):
            return False
        from sources.nuxeo_accounts import backend_account
        account = backend_account(self.url)
        if account is None:
            logger.error(f"Nuxeo sync {self.config_id}: its credentials were rejected ({status}) by {self.url}, and "
                         "the backend has no account there (NUXEO_URL / NUXEO_USERNAME ...): it can't read Nuxeo "
                         "until it is registered again with working credentials")
            return False
        self.auth_method = account.get("auth_method", "basic")
        self.username = account.get("username")
        self.password = account.get("password")
        self.token = account.get("token")
        self.oauth2 = account.get("oauth2")
        self._source = None
        self._using_backend_account = True
        logger.warning(f"Nuxeo sync {self.config_id}: its credentials were rejected ({status}) by {self.url}; "
                       "using the backend's own Nuxeo account from now on")
        return True

    def _get_source(self):
        """Lazily build a reusable NuxeoSource (for path→uid resolution and listing)."""
        if self._source is None:
            from sources.nuxeo import NuxeoSource
            cfg = self._base_source_config()
            cfg["path"] = self.path
            cfg["recursive"] = self.recursive
            if self.node_details:
                cfg["nodeDetails"] = self.node_details
            if self.node_ids:
                cfg["nodeIds"] = self.node_ids
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

    def _root_ids(self) -> List[str]:
        ids = [nd.get("id") for nd in self.node_details or [] if isinstance(nd, dict) and nd.get("id")]
        return ids + [i for i in self.node_ids or [] if i not in ids]

    async def _in_roots(self, uid: str, doc_path: str) -> bool:
        """Whether an event's document is in what this sync follows: one of its selected documents
        (nodeDetails / nodeIds) -- a file itself, a folder's direct children, or any depth below it
        when recursive -- else its path the same way (_in_scope). Selected folders are matched by
        their current paths (they may have been moved since)."""
        roots = self._root_ids()
        if not roots:
            return self._in_scope(doc_path)
        if uid in roots:
            return True
        if not doc_path:
            return False
        import time
        if time.monotonic() - self._root_paths_at > 10:
            source = self._get_source()
            loop = asyncio.get_event_loop()
            paths = {}
            for rid in roots:
                try:
                    doc = await loop.run_in_executor(None, lambda r=rid: source.nuxeo.documents.get(uid=r))
                    paths[rid] = doc.path
                except Exception as e:
                    logger.debug(f"Could not look up selected document {rid}: {e}")
            self._root_paths, self._root_paths_at = paths, time.monotonic()
        for base in self._root_paths.values():
            base = (base or "").rstrip("/")
            if base and doc_path.startswith(base + "/"):
                if self.recursive or "/" not in doc_path[len(base) + 1:]:
                    return True
        return False

    async def _tracked(self, uid: str):
        if not (self.state_manager and self.config_id):
            return None
        try:
            return await self.state_manager.get_state(f"{self.config_id}:nuxeo://{uid}")
        except Exception as e:
            logger.debug(f"state check failed for nuxeo://{uid}: {e}")
            return None

    async def _follow_folder_change(self, folder_path: str) -> None:
        """A folder in what this sync follows was moved (or moved in): its files' paths changed
        with no events of their own. Re-ingest the files this sync follows under their new paths,
        and ingest the ones that came in with it."""
        from .. import sync_jobs
        from ..recovery import comparable_path
        prefix = comparable_path(folder_path) + "/"
        try:
            files = [f for f in await self.list_all_files()
                     if comparable_path((f.extra or {}).get("file_path") or "").startswith(prefix)]
        except Exception as e:
            logger.warning(f"Folder {folder_path} moved, but its files could not be listed ({e}): "
                           f"the periodic refresh will take them")
            return
        for f in files:
            extra = f.extra or {}
            state = await self._tracked(extra["node_id"])
            if state and comparable_path(state.source_path or "") == comparable_path(extra["file_path"]):
                continue
            logger.info(f"NUXEO EVENT: folder {folder_path} was moved or renamed -- "
                        f"{'re-ingesting' if state else 'ingesting'} {extra['file_path']}")
            try:
                with sync_jobs.updating():
                    await self._process_via_backend(extra["node_id"], extra.get("name") or extra["node_id"],
                                                    extra["file_path"])
            except Exception as e:
                logger.error(f"Failed to ingest {extra['file_path']} after its folder moved: {e}")

    # --------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        if self._running:
            logger.warning("NuxeoDetector already running")
            return
        logger.info(f"Starting NuxeoDetector for {self.url}{self.path}")
        self._running = True
        await self._use_backend_account_if_rejected()
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
        document — never a version — so we always ingest with the live uid. A folder's path
        lists its children instead: that is None too (the caller handles folders), never a child
        taken for the folder.
        """
        from ..recovery import comparable_path
        try:
            source = self._get_source()
            loop = asyncio.get_event_loop()
            files = await loop.run_in_executor(None, lambda: source._process_folder_by_path(doc_path))
            if files and comparable_path(files[0].get("path") or "") == comparable_path(doc_path):
                return files[0]  # the file at that very path
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

                if not await self._in_roots(doc_uuid, doc_path):
                    # A document it follows that moved out of them is no longer its to keep
                    from ..recovery import moved_out
                    if change_type in ("UPDATE", "MOVE") and moved_out(await self._tracked(doc_uuid), doc_path):
                        logger.info(f"NUXEO EVENT: {doc_path} moved out of this sync's folders -- removing it")
                        yield ChangeEvent(
                            metadata=FileMetadata(source_type="nuxeo", path=f"nuxeo://{doc_uuid}",
                                                  ordinal=int(datetime.now(timezone.utc).timestamp() * 1_000_000),
                                                  extra={"node_id": doc_uuid}),
                            change_type=ChangeType.DELETE, timestamp=None)
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
                    # a folder (or an unsupported document) moved -- or renamed, which comes as an
                    # UPDATE: its files' paths changed with no events of their own
                    if change_type in ("MOVE", "UPDATE"):
                        await self._follow_folder_change(doc_path)
                    else:
                        logger.info(f"NUXEO EVENT: {change_type} {doc_path} not a supported live file - skipping")
                    continue

                uid = file_info["id"]
                filename = file_info["name"]
                modified = str(file_info.get("modified_at") or "")

                # Dedup by dc:modified + place (collapses the per-save burst; lets separate saves
                # and moves through)
                seen = (modified, file_info.get("path"), filename)
                if modified and self._last_seen_modified.get(uid) == seen:
                    logger.info(f"NUXEO EVENT: dedup {change_type} for {doc_path} (modified unchanged)")
                    continue
                self._last_seen_modified[uid] = seen

                # New vs existing → CREATE (process directly) or UPDATE (DELETE + re-ingest)
                exists = await self._tracked(uid) is not None

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
        loop = asyncio.get_event_loop()
        try:
            files = await loop.run_in_executor(None, self._get_source().list_files)
        except Exception:
            # credentials that stopped working: once more with the backend's account, if it has one there
            if not await self._use_backend_account_if_rejected():
                raise
            files = await loop.run_in_executor(None, self._get_source().list_files)
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
    async def _process_via_backend(self, uid: str, filename: str, file_path: str, _retry: bool = True) -> None:
        """Ingest a single Nuxeo doc via the backend pipeline (nodeDetails mode)."""
        if not self.backend:
            logger.error("Backend not injected into NuxeoDetector - cannot process")
            return

        # The data source's graphs, as its own / its folders' scope rules or this document's own
        # flags have them (incremental_updates/doc_graphs.py); None: the rules say not to follow it
        from incremental_updates.doc_graphs import graphs_for
        graphs = await graphs_for(self, file_path, uid)
        if graphs is None:
            return
        from .. import sync_jobs
        processing_id = sync_jobs.processing_id("nuxeo", uid)

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
            graphs=graphs,
            nuxeo_config=nuxeo_config,
        )

        from backend import PROCESSING_STATUS
        if PROCESSING_STATUS.get(processing_id, {}).get("status") == "failed":
            # credentials that stopped working: once more with the backend's account, if it has one there
            if _retry and await self._use_backend_account_if_rejected():
                await self._process_via_backend(uid, filename, file_path, _retry=False)
                return
            logger.error(f"Backend ingest failed for {filename} ({uid}); not recording document_state")
            return

        logger.info(f"Successfully ingested {filename} ({uid}) via backend pipeline")

        if self.state_manager:
            try:
                await self._create_document_state_from_processing_status(processing_id, filename, uid, file_path, graphs=graphs)
            except Exception as e:
                logger.error(f"Failed to create document_state for {filename}: {e}")

    async def _create_document_state_from_processing_status(
        self, processing_id: str, filename: str, uid: str, file_path: str,
        graphs=None
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
        from incremental_updates.doc_graphs import datasource_graphs, synced_times
        graph_at, rdf_at = synced_times(self, graphs if graphs is not None else datasource_graphs(self), now)
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
            graph_synced_at=graph_at,
            rdf_synced_at=rdf_at,
        )
        await self.state_manager.save_state(doc_state)
        logger.info(f"Created document_state for {filename}: {doc_id}")
