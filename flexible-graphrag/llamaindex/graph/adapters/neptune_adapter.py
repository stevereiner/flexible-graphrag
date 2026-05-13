"""LlamaIndex Neptune Database property graph adapter."""
from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from llamaindex.graph.pg_adapter import LlamaIndexPGAdapter

logger = logging.getLogger(__name__)


class LlamaIndexNeptuneAdapter(LlamaIndexPGAdapter):
    """LlamaIndex property graph adapter backed by Amazon Neptune Database.

    Configuration keys
    ------------------
    host                    Neptune endpoint hostname (required)
    port                    Port (default ``8182``)
    access_key / secret_key Explicit AWS credentials (optional)
    region                  AWS region (optional)
    credentials_profile_name  Named AWS profile (optional)
    sign                    Sign requests with SigV4 (default ``True``)
    use_https               Use HTTPS (default ``True``)
    """

    def __init__(self, config: Dict[str, Any], embed_dim: Optional[int] = None):
        import boto3
        from botocore.config import Config
        from botocore import UNSIGNED
        from llama_index.graph_stores.neptune.database_property_graph import NeptuneDatabasePropertyGraphStore
        from llamaindex.graph.adapters.neptune_database_wrapper import NeptuneDatabaseNoSummaryWrapper

        host = config.get("host")
        if not host:
            raise ValueError(
                "Neptune host is required (format: <GRAPH NAME>.<CLUSTER ID>.<REGION>.neptune.amazonaws.com)"
            )
        port = config.get("port", 8182)
        access_key = config.get("access_key")
        secret_key = config.get("secret_key")
        region = config.get("region")
        credentials_profile_name = config.get("credentials_profile_name")
        sign = config.get("sign", True)
        use_https = config.get("use_https", True)

        client = None
        if access_key and secret_key:
            logger.info("LlamaIndexNeptuneAdapter: using explicit AWS credentials, region=%s", region)
            session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
            client_params: Dict[str, Any] = {}
            if region:
                client_params["region_name"] = region
            protocol = "https" if use_https else "http"
            client_params["endpoint_url"] = f"{protocol}://{host}:{port}"
            client = (
                session.client("neptunedata", **client_params)
                if sign
                else session.client("neptunedata", **client_params, config=Config(signature_version=UNSIGNED))
            )
        elif credentials_profile_name:
            logger.info("LlamaIndexNeptuneAdapter: using AWS profile=%s", credentials_profile_name)
        elif region:
            logger.info("LlamaIndexNeptuneAdapter: using default credentials, region=%s", region)
        else:
            logger.info("LlamaIndexNeptuneAdapter: using default AWS credentials and region")

        graph_store = NeptuneDatabasePropertyGraphStore(
            host=host, port=port, client=client,
            credentials_profile_name=credentials_profile_name if not client else None,
            region_name=region if not client else None,
            sign=sign, use_https=use_https,
        )
        wrapped = NeptuneDatabaseNoSummaryWrapper(graph_store)
        super().__init__(wrapped)
        logger.info("LlamaIndexNeptuneAdapter: host=%s:%s (wrapped for Summary API)", host, port)


__all__ = ["LlamaIndexNeptuneAdapter"]
