"""LangChain Google Cloud Spanner Graph adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    from langchain_google_spanner import SpannerGraphStore
    SPANNER_AVAILABLE = True
except ImportError:
    # langchain-google-spanner ≤0.9.0 requires langchain-core<1.0,
    # incompatible with langchain>=1.0.  The adapter falls back to using
    # google-cloud-spanner directly via a minimal wrapper when this import
    # fails.  Install langchain-google-spanner only in a dedicated 0.3.x env.
    SpannerGraphStore = None  # type: ignore[assignment,misc]
    SPANNER_AVAILABLE = False


class SpannerGraphAdapter:
    """
    Google Cloud Spanner Graph adapter.

    Globally distributed, strongly consistent, horizontally scalable.
    Uses GQL (Graph Query Language), similar to Cypher.

    Configuration:
    {
        "project_id": "my-gcp-project",
        "instance_id": "my-spanner-instance",
        "database_id": "my-database",
        "credentials_path": "/path/to/service-account.json"
    }

    References:
    - https://cloud.google.com/spanner/docs/graph/overview
    """

    def __init__(self, config: Dict[str, Any]):
        if not SPANNER_AVAILABLE:
            raise ImportError(
                "langchain-google-spanner is not compatible with langchain>=1.0 "
                "(requires langchain-core<1.0).  "
                "To use Spanner Graph, install in a dedicated langchain 0.3.x environment: "
                "pip install langchain-google-spanner"
            )

        self.config = config
        credentials_path = config.get("credentials_path")
        if credentials_path:
            import os
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        self.lc_graph = SpannerGraphStore(
            project_id=config["project_id"],
            instance_id=config["instance_id"],
            database_id=config["database_id"],
        )
        logger.info("Connected to Spanner Graph in project %s", config["project_id"])

    def create_qa_chain(self, llm: Any):
        """Create GQL QA chain for Spanner (falls back to generic Cypher chain)."""
        logger.warning("Spanner GQL QA chain falls back to generic Cypher chain")
        from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
        return GraphCypherQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )

    def get_graph(self):
        return self.lc_graph

    def normalize_entity_names(self) -> None:
        """Copy id -> name using the Google Cloud Spanner Python client.

        ``SpannerGraphStore`` does not expose a general DML mutation API, but
        the ``google-cloud-spanner`` client supports standard SQL ``UPDATE``
        statements via ``database.run_in_transaction()``.

        GQL (ISO/IEC SQL Property Graph Queries) is available on managed Cloud
        Spanner but not the emulator; plain SQL DML works on both.

        Reference: https://cloud.google.com/python/docs/reference/spanner/latest
        """
        try:
            from google.cloud import spanner  # type: ignore
        except ImportError:
            logger.warning(
                "SpannerGraph normalize_entity_names: google-cloud-spanner not installed. "
                "Install: pip install google-cloud-spanner"
            )
            return

        credentials_path = self.config.get("credentials_path")
        if credentials_path:
            import os
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", credentials_path)

        try:
            client   = spanner.Client(project=self.config.get("project_id"))
            instance = client.instance(self.config["instance_id"])
            database = instance.database(self.config["database_id"])

            sql = "UPDATE Entity SET name = id WHERE name IS NULL AND id IS NOT NULL"

            def _run(transaction):
                return transaction.execute_update(sql)

            updated = database.run_in_transaction(_run)
            logger.debug("Spanner: normalized %d entity names (id -> name)", updated)
        except Exception as exc:
            logger.warning("Spanner normalize_entity_names failed: %s", exc)


__all__ = ["SpannerGraphAdapter", "SPANNER_AVAILABLE"]
