"""LlamaIndex Neptune Analytics property graph adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging
import os

from llamaindex.graph.pg_adapter import LlamaIndexPGAdapter

logger = logging.getLogger(__name__)


class LlamaIndexNeptuneAnalyticsAdapter(LlamaIndexPGAdapter):
    """LlamaIndex property graph adapter backed by Amazon Neptune Analytics.

    Configuration keys
    ------------------
    graph_identifier        Neptune Analytics graph ID (required)
    access_key / secret_key Explicit AWS credentials (optional)
    region                  AWS region (optional)
    credentials_profile_name  Named AWS profile (optional)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        from llama_index.graph_stores.neptune.analytics_property_graph import NeptuneAnalyticsPropertyGraphStore

        graph_identifier = config.get("graph_identifier")
        if not graph_identifier:
            raise ValueError("Neptune Analytics graph_identifier is required")
        access_key = config.get("access_key")
        secret_key = config.get("secret_key")
        region = config.get("region")
        credentials_profile_name = config.get("credentials_profile_name")

        if access_key and secret_key:
            logger.info("LlamaIndexNeptuneAnalyticsAdapter: using explicit AWS credentials, region=%s", region)
            os.environ["AWS_ACCESS_KEY_ID"] = access_key
            os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
            if region:
                os.environ["AWS_DEFAULT_REGION"] = region
            store = NeptuneAnalyticsPropertyGraphStore(
                graph_identifier=graph_identifier,
                region_name=region,
            )
        elif credentials_profile_name:
            logger.info("LlamaIndexNeptuneAnalyticsAdapter: using AWS profile=%s", credentials_profile_name)
            store = NeptuneAnalyticsPropertyGraphStore(
                graph_identifier=graph_identifier,
                credentials_profile_name=credentials_profile_name,
                region_name=region,
            )
        else:
            logger.info("LlamaIndexNeptuneAnalyticsAdapter: using default AWS credentials, region=%s", region)
            store = NeptuneAnalyticsPropertyGraphStore(
                graph_identifier=graph_identifier,
                region_name=region,
            )
        super().__init__(store)
        logger.info("LlamaIndexNeptuneAnalyticsAdapter: graph_id=%s", graph_identifier)


__all__ = ["LlamaIndexNeptuneAnalyticsAdapter"]
