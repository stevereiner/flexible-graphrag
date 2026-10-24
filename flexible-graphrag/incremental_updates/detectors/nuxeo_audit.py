"""
Nuxeo audit → Kafka consumer for real-time change detection.

Nuxeo (with kafka.enabled=true and nuxeo.stream.audit.enabled=true) publishes audit
entries to the Kafka topic `nuxeo-audit-audit`. Each message value is a Nuxeo Stream
`Record` (small binary/avro-single-object header) with the audit LogEntry embedded as
plain UTF-8 JSON. We extract that JSON directly (no Avro Record decoding needed).

`NuxeoAuditConsumer` is a singleton per (bootstrap_servers, topic): one background
Kafka consumer thread fans doc-change events out to all registered NuxeoDetectors,
each of which filters by its monitored path. This mirrors AlfrescoEventBroadcaster.
"""

import json
import logging
import threading
from typing import Dict, Optional, Set

logger = logging.getLogger("flexible_graphrag.incremental.detectors.nuxeo_audit")

try:
    from kafka import KafkaConsumer
    KAFKA_AVAILABLE = True
except ImportError:
    KafkaConsumer = None
    KAFKA_AVAILABLE = False
    logging.warning("kafka-python-ng not installed - Nuxeo real-time (Kafka) detection unavailable. "
                    "Install with: uv pip install kafka-python-ng")

# Nuxeo audit eventId -> our change type
_EVENT_MAP = {
    "documentCreated": "CREATE",
    "documentModified": "UPDATE",
    "documentRemoved": "DELETE",
    "documentTrashed": "DELETE",
    "documentUntrashed": "CREATE",
    "documentMoved": "MOVE",  # a file's or a folder's new place (NuxeoDetector)
}


def extract_audit_json(value: bytes) -> Optional[dict]:
    """Extract the embedded audit LogEntry JSON from a nuxeo-audit-audit Record value.

    The value is a Stream Record whose `data` field is the audit entry serialized as
    UTF-8 JSON, preceded by a short binary header and followed by a 1-byte flag. We
    locate the first '{' and parse one JSON object from there (raw_decode ignores the
    trailing flag byte), which is robust across the header's variable-length varints.
    """
    if not value:
        return None
    start = value.find(b"{")
    if start < 0:
        return None
    text = value[start:].decode("utf-8", "replace")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text)
        return obj
    except Exception:
        return None


class NuxeoAuditConsumer:
    """Singleton Kafka consumer that fans Nuxeo audit doc-change events to detectors."""

    _instances: Dict[str, "NuxeoAuditConsumer"] = {}
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, bootstrap_servers: str, topic: str = "nuxeo-audit-audit") -> "NuxeoAuditConsumer":
        key = f"{bootstrap_servers}|{topic}"
        with cls._lock:
            inst = cls._instances.get(key)
            if inst is None:
                inst = cls(bootstrap_servers, topic)
                cls._instances[key] = inst
                inst.start()
            return inst

    def __init__(self, bootstrap_servers: str, topic: str):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self._consumer = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._detectors: Set = set()
        self._detectors_lock = threading.Lock()

    # --- detector registry -------------------------------------------------
    def register_detector(self, detector) -> None:
        with self._detectors_lock:
            self._detectors.add(detector)
        logger.info(f"NuxeoAuditConsumer: registered detector (path={getattr(detector, 'path', '?')}), "
                    f"total={len(self._detectors)}")

    def unregister_detector(self, detector) -> None:
        with self._detectors_lock:
            self._detectors.discard(detector)
        logger.info(f"NuxeoAuditConsumer: unregistered detector, remaining={len(self._detectors)}")

    @property
    def detector_count(self) -> int:
        return len(self._detectors)

    @property
    def is_connected(self) -> bool:
        return self._running and self._consumer is not None

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if not KAFKA_AVAILABLE:
            raise ImportError("kafka-python-ng is required for Nuxeo real-time detection")
        logger.info(f"NuxeoAuditConsumer: starting consumer on {self.topic} @ {self.bootstrap_servers}")
        self._consumer = KafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers.split(","),
            auto_offset_reset="latest",          # only new events (periodic refresh is the backstop)
            enable_auto_commit=True,
            group_id="flexible-graphrag-nuxeo-audit",
            consumer_timeout_ms=1000,            # let the loop check _running
            value_deserializer=None,             # keep raw bytes; we extract JSON ourselves
        )
        self._running = True
        self._thread = threading.Thread(target=self._run, name="nuxeo-audit-consumer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._consumer is not None:
            try:
                self._consumer.close()
            except Exception as e:
                logger.warning(f"Error closing Kafka consumer: {e}")
            self._consumer = None

    # --- consume loop ------------------------------------------------------
    def _run(self) -> None:
        logger.info("NuxeoAuditConsumer: consume loop started")
        while self._running:
            try:
                for msg in self._consumer:
                    if not self._running:
                        break
                    entry = extract_audit_json(msg.value)
                    if not entry:
                        continue
                    event = self._to_event(entry)
                    if event:
                        self._broadcast(event)
            except Exception as e:
                if self._running:
                    logger.error(f"NuxeoAuditConsumer: error in consume loop: {e}")
                    import time
                    time.sleep(2)
        logger.info("NuxeoAuditConsumer: consume loop exited")

    @staticmethod
    def _to_event(entry: dict) -> Optional[dict]:
        """Map an audit LogEntry dict to a compact change-event dict, or None to ignore."""
        change_type = _EVENT_MAP.get(entry.get("eventId"))
        if not change_type:
            return None
        doc_path = entry.get("docPath")
        doc_uuid = entry.get("docUUID")
        if not doc_path or not doc_uuid:
            return None
        return {
            "change_type": change_type,
            "uid": doc_uuid,
            "path": doc_path,
            "docType": entry.get("docType"),
            "eventId": entry.get("eventId"),
            "eventDate": entry.get("eventDate"),
        }

    def _broadcast(self, event: dict) -> None:
        with self._detectors_lock:
            detectors = list(self._detectors)
        for det in detectors:
            q = getattr(det, "_event_queue_sync", None)
            if q is not None:
                try:
                    q.put_nowait(event)
                except Exception as e:
                    logger.warning(f"Failed to enqueue event to detector: {e}")
