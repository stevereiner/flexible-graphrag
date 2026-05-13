"""LangChain Amazon Neptune property graph adapters (OpenCypher).

Note: The Neptune *RDF* (SPARQL) adapter lives in neptune_rdf_adapter.py.
These adapters cover Neptune *property graph* mode via OpenCypher.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from langchain_aws.graphs import NeptuneAnalyticsGraph, NeptuneGraph
    from langchain_aws.chains import create_neptune_opencypher_qa_chain
    NEPTUNE_PG_AVAILABLE = True
except ImportError:
    NEPTUNE_PG_AVAILABLE = False


def _safe_label(s: str) -> str:
    """Strip backticks and normalise a label/rel-type for use in Cypher."""
    return re.sub(r"[`\\]", "", str(s))


class _NeptuneGraphWithWrite:
    """
    Thin proxy around NeptuneGraph that adds add_graph_documents.

    langchain-aws NeptuneGraph is a read/QA wrapper only — it exposes
    get_schema() and query() but not add_graph_documents().  This wrapper
    delegates all attribute access to the underlying graph and implements
    write support via OpenCypher MERGE statements.
    """

    def __init__(self, graph: "NeptuneGraph") -> None:
        self._graph = graph

    # --- proxy all reads to the underlying NeptuneGraph ---
    def __getattr__(self, name: str) -> Any:
        return getattr(self._graph, name)

    def query(self, query: str, params: dict = {}) -> List[Dict[str, Any]]:  # noqa: B006
        return self._graph.query(query, params=params)

    @property
    def get_schema(self) -> str:  # type: ignore[override]
        return self._graph.get_schema  # type: ignore[return-value]

    # --- write support ---
    def add_graph_documents(
        self,
        graph_documents: List[Any],
        include_source: bool = False,
        **kwargs: Any,
    ) -> None:
        """Write GraphDocument nodes and relationships to Neptune via OpenCypher."""
        for doc in graph_documents:
            # --- nodes ---
            for node in doc.nodes:
                label = _safe_label(node.type or "Entity")
                props: Dict[str, Any] = {
                    k: str(v)[:4096]
                    for k, v in (node.properties or {}).items()
                }
                props["id"] = node.id
                cypher = (
                    f"MERGE (n:__Entity__:`{label}` {{id: $id}}) "
                    "SET n += $props"
                )
                try:
                    self._graph.query(cypher, params={"id": node.id, "props": props})
                except Exception as exc:
                    logger.warning("Neptune node upsert failed (%s): %s", node.id, exc)

            # --- relationships ---
            for rel in doc.relationships:
                rel_type = _safe_label(
                    re.sub(r"[^A-Za-z0-9_]", "_", rel.type).upper()
                )
                r_props: Dict[str, Any] = {
                    k: str(v)[:4096]
                    for k, v in (rel.properties or {}).items()
                }
                cypher = (
                    f"MATCH (s:__Entity__ {{id: $src_id}}) "
                    f"MATCH (t:__Entity__ {{id: $tgt_id}}) "
                    f"MERGE (s)-[r:`{rel_type}`]->(t) "
                    "SET r += $props"
                )
                try:
                    self._graph.query(
                        cypher,
                        params={
                            "src_id": rel.source.id,
                            "tgt_id": rel.target.id,
                            "props": r_props,
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "Neptune rel upsert failed (%s->%s): %s",
                        rel.source.id, rel.target.id, exc,
                    )

            # --- source chunk node ---
            if include_source and doc.source:
                meta = doc.source.metadata or {}
                chunk_id = (
                    meta.get("doc_id")
                    or meta.get("ref_doc_id")
                    or str(hash(doc.source.page_content))
                )
                chunk_props = {
                    "text": doc.source.page_content[:10000],
                    "file_name": meta.get("file_name", ""),
                    "file_type": meta.get("file_type", ""),
                }
                try:
                    self._graph.query(
                        "MERGE (c:Chunk {id: $id}) SET c += $props",
                        params={"id": str(chunk_id), "props": chunk_props},
                    )
                    for node in doc.nodes:
                        self._graph.query(
                            "MATCH (c:Chunk {id: $cid}) "
                            "MATCH (n:__Entity__ {id: $nid}) "
                            "MERGE (c)-[:MENTIONS]->(n)",
                            params={"cid": str(chunk_id), "nid": node.id},
                        )
                except Exception as exc:
                    logger.warning("Neptune chunk/MENTIONS upsert failed: %s", exc)


class NeptunePropertyGraphAdapter:
    """
    Amazon Neptune Database property graph adapter (OpenCypher).

    Neptune "OneGraph" — same data accessible via SPARQL (RDF) or OpenCypher.

    Configuration:
    {
        "host": "my-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com",
        "port": 8182,
        "region": "us-east-1",
        "use_iam_auth": true,
        "use_https": true
    }

    References:
    - https://docs.aws.amazon.com/neptune/latest/userguide/access-graph-opencypher.html
    """

    def __init__(self, config: Dict[str, Any]):
        if not NEPTUNE_PG_AVAILABLE:
            raise ImportError(
                "langchain-aws required. Install: pip install langchain-aws boto3"
            )

        self.config = config
        # langchain-aws NeptuneGraph uses `sign=True` instead of the old
        # `use_iam_auth` parameter. Explicit key args are SecretStr-typed.
        from pydantic import SecretStr

        access_key = config.get("access_key") or config.get("aws_access_key_id")
        secret_key = config.get("secret_key") or config.get("aws_secret_access_key")
        profile = config.get("credentials_profile_name")

        _raw = NeptuneGraph(  # type: ignore[possibly-unbound]
            host=config["host"],
            port=config.get("port", 8182),
            use_https=config.get("use_https", True),
            sign=config.get("use_iam_auth", True),
            region_name=config.get("region", "us-east-1"),
            aws_access_key_id=SecretStr(access_key) if access_key else None,
            aws_secret_access_key=SecretStr(secret_key) if secret_key else None,
            credentials_profile_name=profile,
        )
        self.lc_graph = _NeptuneGraphWithWrite(_raw)
        logger.info("Connected to Neptune property graph at %s", config["host"])

    def create_qa_chain(self, llm: Any):
        """Create Neptune OpenCypher QA chain."""
        return create_neptune_opencypher_qa_chain(  # type: ignore[possibly-unbound]
            llm=llm,
            graph=self.lc_graph._graph,  # raw NeptuneGraph satisfies BaseNeptuneGraph
            return_intermediate_steps=True,
            allow_dangerous_requests=True,
        )

    def get_graph(self):
        return self.lc_graph

    def normalize_entity_names(self) -> None:
        """SET name = id on __Entity__ nodes (Neptune OpenCypher)."""
        _CYPHER = (
            "MATCH (n:__Entity__) WHERE n.name IS NULL AND n.id IS NOT NULL "
            "SET n.name = n.id"
        )
        try:
            # NeptuneGraph exposes query() for arbitrary openCypher
            self.lc_graph.query(_CYPHER)
            logger.debug("Neptune: normalized entity names (id -> name)")
        except Exception as exc:
            logger.warning("Neptune normalize_entity_names failed: %s", exc)


class NeptuneAnalyticsAdapter:
    """
    Amazon Neptune Analytics serverless graph adapter.

    Optimized for analytics workloads with built-in graph algorithms.
    Pay-per-query pricing; OpenCypher query language.

    Configuration:
    {
        "graph_identifier": "g-abcdef12345",
        "region": "us-east-1"
    }

    References:
    - https://docs.aws.amazon.com/neptune-analytics/latest/userguide/
    """

    def __init__(self, config: Dict[str, Any]):
        if not NEPTUNE_PG_AVAILABLE:
            raise ImportError(
                "langchain-aws required. Install: pip install langchain-aws boto3"
            )

        self.config = config
        _ak = config.get("access_key")
        _sk = config.get("secret_key")
        _graph_kwargs: Dict[str, Any] = {
            "graph_identifier": config["graph_identifier"],
            "region_name": config.get("region", "us-east-1"),
        }
        if _ak and _sk:
            from pydantic import SecretStr as _SS
            _graph_kwargs["aws_access_key_id"] = _SS(_ak)
            _graph_kwargs["aws_secret_access_key"] = _SS(_sk)
            logger.info("NeptuneAnalyticsAdapter: using explicit AWS credentials")
        _raw = NeptuneAnalyticsGraph(**_graph_kwargs)  # type: ignore[possibly-unbound]
        # NeptuneAnalyticsGraph is read-only — wrap it with add_graph_documents support.
        self.lc_graph = _NeptuneGraphWithWrite(_raw)
        logger.info("Connected to Neptune Analytics graph %s", config["graph_identifier"])

    def create_qa_chain(self, llm: Any):
        """Create Neptune Analytics OpenCypher QA chain."""
        return create_neptune_opencypher_qa_chain(  # type: ignore[possibly-unbound]
            llm=llm,
            graph=self.lc_graph._graph,  # raw NeptuneAnalyticsGraph satisfies BaseNeptuneGraph
            return_intermediate_steps=True,
            allow_dangerous_requests=True,
        )

    def get_graph(self):
        return self.lc_graph

    def normalize_entity_names(self) -> None:
        """SET name = id on __Entity__ nodes (Neptune Analytics OpenCypher)."""
        _CYPHER = (
            "MATCH (n:__Entity__) WHERE n.name IS NULL AND n.id IS NOT NULL "
            "SET n.name = n.id"
        )
        try:
            self.lc_graph.query(_CYPHER)
            logger.debug("Neptune Analytics: normalized entity names (id -> name)")
        except Exception as exc:
            logger.warning("Neptune Analytics normalize_entity_names failed: %s", exc)


__all__ = ["NeptunePropertyGraphAdapter", "NeptuneAnalyticsAdapter", "NEPTUNE_PG_AVAILABLE"]
