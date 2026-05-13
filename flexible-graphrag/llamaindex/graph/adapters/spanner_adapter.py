"""LlamaIndex Google Cloud Spanner property graph adapter.

Uses the ``llama-index-spanner`` package (SpannerPropertyGraphStore).
Install: uv pip install llama-index-spanner

Configuration keys (from SPANNER_GRAPH_DB_CONFIG JSON blob or individual vars):
    project_id       GCP project ID (required)
    instance_id      Spanner instance ID (required)
    database_id      Spanner database ID (required)
    graph_name       Graph name inside the database (default "knowledge_graph")
    credentials_file Path to service-account JSON key file (optional; uses ADC if absent)
    use_flexible_schema  true (default) — single GraphNode/GraphEdge tables with JSON
                         properties blob, auto-evolved on first upsert; no DDL needed
                         upfront.  false — one table per entity/relation type (strongly
                         typed columns).

Schema auto-creation:
    ``SpannerPropertyGraphStore`` creates all Spanner tables and the PROPERTY GRAPH
    definition automatically on first ingest.  Do NOT run CREATE TABLE / CREATE PROPERTY
    GRAPH manually — the tables (GraphNode, GraphEdge) must exist before the PROPERTY
    GRAPH DDL can reference them, and the library manages that ordering internally.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

# Spanner Python client exports built-in metrics to Cloud Monitoring by default.
# Outside GCE this produces noisy "Failed to export metrics / missing instance_id"
# 400 errors on every request.  Disable before the spanner module is imported.
os.environ.setdefault("SPANNER_DISABLE_BUILTIN_METRICS", "true")

from llamaindex.graph.pg_adapter import LlamaIndexPGAdapter

logger = logging.getLogger(__name__)

# Relative path checked when credentials_file is not set explicitly.
_DEFAULT_GCS_JSON = os.path.join(os.path.dirname(__file__), "..", "..", "..", "gcs.json")


def _resolve_credentials_file(config: Dict[str, Any]) -> Optional[str]:
    """Return a credentials file path, or None to fall back to ADC.

    Priority:
    1. ``credentials_file`` key in config
    2. ``GOOGLE_APPLICATION_CREDENTIALS`` environment variable
    3. ``flexible-graphrag/gcs.json`` next to the package root (if it exists)
    """
    explicit = config.get("credentials_file") or config.get("credentials")
    if explicit:
        return explicit
    env_var = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_var:
        return env_var
    candidate = os.path.normpath(_DEFAULT_GCS_JSON)
    if os.path.isfile(candidate):
        logger.info("LlamaIndexSpannerAdapter: auto-detected credentials at %s", candidate)
        return candidate
    return None


class LlamaIndexSpannerAdapter(LlamaIndexPGAdapter):
    """LlamaIndex property graph adapter backed by Google Cloud Spanner.

    ``SpannerPropertyGraphStore`` from ``llama-index-spanner`` 0.1.5 is a
    LlamaIndex-native ``PropertyGraphStore`` subclass — no bridging required.

    Schema is created automatically on first ``upsert_nodes`` / ``upsert_relations``
    call; do not pre-create tables or property graph DDL manually.

    Authentication priority:
    1. ``credentials_file`` in config → ``google.oauth2.service_account.Credentials``
    2. ``GOOGLE_APPLICATION_CREDENTIALS`` environment variable
    3. ``flexible-graphrag/gcs.json`` (auto-detected if present)
    4. Application Default Credentials (``gcloud auth application-default login`` /
       GCE metadata server)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        try:
            from llama_index_spanner import SpannerPropertyGraphStore
        except ImportError:
            raise ImportError(
                "llama-index-spanner is required for Spanner graph store. "
                "Install with: uv pip install llama-index-spanner"
            )

        project_id = config.get("project_id") or config.get("project")
        instance_id = config.get("instance_id") or config.get("instance")
        database_id = config.get("database_id") or config.get("database")
        graph_name = config.get("graph_name") or config.get("graph", "knowledge_graph")
        # use_flexible_schema=True: single GraphNode + GraphEdge tables with a JSON
        # properties column.  All entity/relation types share these two tables; the
        # PROPERTY GRAPH definition uses DYNAMIC LABEL / DYNAMIC PROPERTIES.
        # This is the "schemaless" mode and is the recommended default.
        use_flexible = config.get("use_flexible_schema", True)
        if isinstance(use_flexible, str):
            use_flexible = use_flexible.lower() not in ("false", "0", "no")

        if not instance_id:
            raise ValueError("Spanner config requires 'instance_id'")
        if not database_id:
            raise ValueError("Spanner config requires 'database_id'")

        credentials_file = _resolve_credentials_file(config)

        spanner_client = None
        try:
            from google.cloud import spanner as _spanner
            if credentials_file:
                from google.oauth2 import service_account as _sa
                _creds = _sa.Credentials.from_service_account_file(
                    credentials_file,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                logger.info(
                    "LlamaIndexSpannerAdapter: using service-account credentials from %s",
                    credentials_file,
                )
                spanner_client = _spanner.Client(
                    project=project_id, credentials=_creds
                )
            elif project_id:
                logger.info(
                    "LlamaIndexSpannerAdapter: using ADC, project=%s", project_id
                )
                spanner_client = _spanner.Client(project=project_id)
        except ImportError:
            logger.warning(
                "google-cloud-spanner not installed — "
                "SpannerPropertyGraphStore will use its own default client"
            )

        store = SpannerPropertyGraphStore(
            instance_id=instance_id,
            database_id=database_id,
            graph_name=graph_name,
            client=spanner_client,
            use_flexible_schema=use_flexible,
        )
        super().__init__(store)
        logger.info(
            "LlamaIndexSpannerAdapter: instance=%s database=%s graph=%s flexible_schema=%s",
            instance_id, database_id, graph_name, use_flexible,
        )


__all__ = ["LlamaIndexSpannerAdapter"]
