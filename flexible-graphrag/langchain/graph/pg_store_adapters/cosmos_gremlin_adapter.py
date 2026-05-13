"""LangChain Azure Cosmos DB for Gremlin adapter."""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from langchain_community.graphs import GremlinGraph
    # langchain-community < 0.4 used CosmosDBGremlinGraph (renamed to GremlinGraph in 0.4+):
    # from langchain_community.graphs import CosmosDBGremlinGraph
    COSMOS_DB_AVAILABLE = True
except ImportError:
    COSMOS_DB_AVAILABLE = False


def _parse_username(username: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse Cosmos DB username '/dbs/<db>/colls/<graph>' into (db, graph)."""
    m = re.match(r"^/dbs/([^/]+)/colls/([^/]+)$", username.strip())
    if m:
        return m.group(1), m.group(2)
    return None, None


def _extract_account_name(url: str) -> Optional[str]:
    """Extract Cosmos account name from 'wss://<account>.gremlin.cosmos.azure.com:443/'."""
    m = re.match(r"wss?://([^.]+)\.gremlin\.cosmos\.azure\.com", url)
    if m:
        return m.group(1)
    return None


def _ensure_cosmos_graph(
    url: str,
    username: str,
    partition_key_path: str,
    resource_group: Optional[str],
    subscription_id: Optional[str],
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> None:
    """Create Cosmos DB database + Gremlin graph container if they don't exist.

    Uses ``azure-mgmt-cosmosdb`` (management plane) which supports container
    creation — the Gremlin WebSocket client (gremlinpython) cannot create
    containers.  Skips silently if the management SDK is not installed.

    Args:
        url:               Cosmos Gremlin endpoint URL (to extract account name).
        username:          Gremlin username string '/dbs/<db>/colls/<graph>'.
        partition_key_path: Partition key path, e.g. '/partitionKey'.
        resource_group:    Azure resource group name (required for mgmt SDK).
        subscription_id:   Azure subscription ID (required for mgmt SDK).
        tenant_id:         Azure AD tenant ID for ClientSecretCredential (optional).
        client_id:         Service principal app/client ID (optional).
        client_secret:     Service principal client secret (optional).
                           When all three are provided, uses ClientSecretCredential
                           (pure HTTPS) instead of DefaultAzureCredential (which
                           spawns az CLI / PowerShell subprocesses and may trigger
                           antivirus behavioral detection).
    """
    _tenant_id, _client_id, _client_secret = tenant_id, client_id, client_secret
    account_name = _extract_account_name(url)
    db_name, graph_name = _parse_username(username)

    if not account_name or not db_name or not graph_name:
        logger.warning(
            "CosmosDBGremlin: cannot parse account/db/graph from url=%s username=%s — "
            "create the graph container manually in the Azure Portal.",
            url, username,
        )
        return

    if not resource_group or not subscription_id:
        logger.debug(
            "CosmosDBGremlin: resource_group / subscription_id not set — "
            "skipping auto-create (graph container assumed to already exist)."
        )
        return

    logger.info(
        "CosmosDBGremlin: auto-creating graph '%s' in database '%s' (account: %s)",
        graph_name, db_name, account_name,
    )

    try:
        from azure.identity import DefaultAzureCredential  # type: ignore
        from azure.mgmt.cosmosdb import CosmosDBManagementClient  # type: ignore
        from azure.mgmt.cosmosdb.models import (  # type: ignore
            GremlinDatabaseCreateUpdateParameters,
            GremlinDatabaseResource,
            GremlinGraphCreateUpdateParameters,
            GremlinGraphResource,
            ContainerPartitionKey,
        )
    except ImportError:
        logger.info(
            "CosmosDBGremlin: azure-mgmt-cosmosdb not installed — "
            "skipping auto-create. Install with: pip install azure-mgmt-cosmosdb azure-identity\n"
            "Or create the Gremlin graph manually in the Azure Portal:\n"
            "  Cosmos DB account -> Data Explorer -> New Graph\n"
            "  Database id: %s | Graph id: %s | Partition key: %s",
            db_name, graph_name, partition_key_path,
        )
        return

    try:
        # Prefer ClientSecretCredential (service principal) — pure HTTPS, no subprocess
        # spawning. DefaultAzureCredential tries az CLI / PowerShell token providers which
        # can trigger antivirus behavioral detection (e.g. Norton IDP.HELU.PSE73%s_cmd).
        if _tenant_id and _client_id and _client_secret:
            from azure.identity import ClientSecretCredential  # type: ignore
            cred = ClientSecretCredential(_tenant_id, _client_id, _client_secret)
            logger.debug("CosmosDBGremlin: using ClientSecretCredential for management API")
        else:
            cred = DefaultAzureCredential()
            logger.debug("CosmosDBGremlin: using DefaultAzureCredential for management API")
        client = CosmosDBManagementClient(cred, subscription_id)

        # Ensure database exists.
        try:
            client.gremlin_resources.get_gremlin_database(
                resource_group, account_name, db_name
            )
            logger.debug("CosmosDBGremlin: database '%s' already exists", db_name)
        except Exception:
            logger.info("CosmosDBGremlin: creating database '%s'", db_name)
            client.gremlin_resources.begin_create_update_gremlin_database(
                resource_group,
                account_name,
                db_name,
                GremlinDatabaseCreateUpdateParameters(
                    resource=GremlinDatabaseResource(id=db_name)
                ),
            ).result()

        # Ensure graph container exists.
        try:
            client.gremlin_resources.get_gremlin_graph(
                resource_group, account_name, db_name, graph_name
            )
            logger.debug(
                "CosmosDBGremlin: graph '%s' in database '%s' already exists",
                graph_name, db_name,
            )
        except Exception:
            logger.info(
                "CosmosDBGremlin: creating graph '%s' in database '%s' (partition key: %s)",
                graph_name, db_name, partition_key_path,
            )
            client.gremlin_resources.begin_create_update_gremlin_graph(
                resource_group,
                account_name,
                db_name,
                graph_name,
                GremlinGraphCreateUpdateParameters(
                    resource=GremlinGraphResource(
                        id=graph_name,
                        partition_key=ContainerPartitionKey(
                            paths=[partition_key_path],
                            kind="Hash",
                        ),
                    )
                ),
            ).result()
            logger.info("CosmosDBGremlin: graph '%s' created successfully", graph_name)

    except Exception as exc:
        logger.warning(
            "CosmosDBGremlin: auto-create failed (%s). "
            "Create the graph manually in the Azure Portal: "
            "Cosmos DB account -> Data Explorer -> New Graph | "
            "Database id: %s | Graph id: %s | Partition key: %s",
            exc, db_name, graph_name, partition_key_path,
        )


class CosmosDBGremlinAdapter:
    """
    Azure Cosmos DB for Gremlin adapter (also works with local TinkerPop Gremlin Server).

    For local development use ws://localhost:8182/gremlin (no auth needed).
    For Cosmos DB use wss://<account>.gremlin.cosmos.azure.com:443/ with username/password.

    Configuration:
    {
        "url": "ws://localhost:8182/gremlin",
        "username": "/",
        "password": ""
    }
    or for Cosmos DB:
    {
        "url": "wss://my-cosmos.gremlin.cosmos.azure.com:443/",
        "username": "/dbs/mydb/colls/mygraph",
        "password": "primary_key"
    }

    References:
    - https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/
    - https://tinkerpop.apache.org/
    """

    def __init__(self, config: Dict[str, Any]):
        if not COSMOS_DB_AVAILABLE:
            raise ImportError(
                "langchain-community required. "
                "Install: pip install langchain-community gremlinpython"
            )

        self.config = config
        url = config.get("url") or "ws://localhost:8182/gremlin"
        username = config.get("username") or "/"
        password = config.get("password") or ""

        # partition_key_property: the property name matching the container's partition key path
        #   (e.g. container created with /partitionKey -> "partitionKey").
        # partition_key_value: a fixed string written on every vertex so all graph data lands
        #   in the same logical partition, keeping traversals local (no cross-partition queries).
        #   Do NOT use the entity type — that scatters vertices across partitions.
        # Only injected for Cosmos DB (wss://...cosmos.azure.com); ignored for local TinkerPop.
        self._partition_key_prop: str | None = None
        self._partition_key_value: str = "graph"
        if "cosmos.azure.com" in url:
            self._partition_key_prop = config.get("partition_key_property", "partitionKey")
            self._partition_key_value = config.get("partition_key_value", "graph")

            # Auto-create the Gremlin database + graph container if management SDK creds
            # are provided.  Without resource_group + subscription_id this is a no-op.
            # Provide tenant_id + client_id + client_secret to use ClientSecretCredential
            # (pure HTTPS) and avoid DefaultAzureCredential spawning az CLI / PowerShell
            # subprocesses (which can trigger antivirus behavioral detection on Windows).
            pk_path = "/" + (self._partition_key_prop or "partitionKey")
            _ensure_cosmos_graph(
                url=url,
                username=username,
                partition_key_path=pk_path,
                resource_group=config.get("resource_group"),
                subscription_id=config.get("subscription_id"),
                tenant_id=config.get("tenant_id"),
                client_id=config.get("client_id"),
                client_secret=config.get("client_secret"),
            )

        from gremlin_python.driver import serializer as _ser
        # Cosmos DB requires GraphSON V2; local TinkerPop 3.7+ uses GraphBinary V1.
        if "cosmos.azure.com" in url:
            _serializer = _ser.GraphSONSerializersV2d0()
        else:
            _serializer = _ser.GraphBinarySerializersV1()

        # langchain-community 0.4+: GremlinGraph (handles both local TinkerPop and Cosmos DB)
        self.lc_graph = GremlinGraph(
            url=url,
            username=username,
            password=password,
            message_serializer=_serializer,
        )
        # langchain-community < 0.4: CosmosDBGremlinGraph (Cosmos DB only, different constructor)
        # self.lc_graph = CosmosDBGremlinGraph(
        #     url=url,
        #     username=username,
        #     password=password,
        #     database=config.get("database", "graphdb"),
        #     collection=config.get("collection", "graph"),
        # )
        self._install_escape_patch()
        self._install_schema_filter()
        logger.info("Connected to Gremlin server at %s", url)

    def _install_escape_patch(self) -> None:
        """Patch GremlinGraph.build_vertex_query / build_edge_query to escape
        single quotes in property values.  langchain_community embeds values
        directly into single-quoted Groovy strings with no escaping, which
        breaks whenever document content contains apostrophes."""
        from langchain_community.graphs.graph_document import Node as _Node, Relationship as _Rel

        def _esc(value: Any) -> str:
            return str(value).replace("\\", "\\\\").replace("'", r"\'")

        _orig_bvq = self.lc_graph.build_vertex_query
        _orig_beq = self.lc_graph.build_edge_query

        def _safe_build_vertex_query(node: _Node) -> str:
            safe = _Node(
                id=_esc(node.id),
                type=_esc(node.type),
                properties={k: _esc(v) for k, v in node.properties.items()},
            )
            return _orig_bvq(safe)

        def _safe_build_edge_query(rel: _Rel) -> str:
            safe = _Rel(
                source=_Node(id=_esc(rel.source.id), type=_esc(rel.source.type)),
                target=_Node(id=_esc(rel.target.id), type=_esc(rel.target.type)),
                type=_esc(rel.type),
                properties={k: _esc(v) for k, v in rel.properties.items()},
            )
            result = _orig_beq(safe)
            # langchain_community bug: build_edge_query uses a triple-quoted f-string
            # whose content starts with '"g.V()...', so the returned string has a
            # leading double-quote that makes Groovy parse it as a string literal
            # instead of a traversal.  Strip it here.
            return result.lstrip('"')

        self.lc_graph.build_vertex_query = _safe_build_vertex_query
        self.lc_graph.build_edge_query = _safe_build_edge_query

    # Properties we inject for Cosmos DB bookkeeping — must NOT appear in the
    # schema presented to the LLM, or it will try to filter on them by name.
    _INTERNAL_PROPS = frozenset({"partitionKey", "label", "type"})

    def _install_schema_filter(self) -> None:
        """Patch refresh_schema to strip internal bookkeeping properties.

        GremlinGraph.refresh_schema sets self.schema to a string that includes
        a vertex_properties dict:  {'Company': ['id', 'type', 'partitionKey', ...], ...}
        If the LLM sees 'partitionKey', 'label', or 'type' it generates queries like
        has('partitionKey', 'acme') instead of has('id', TextP.containing('Acme')).

        This patch also rewrites the structured_schema['vertice_props'] dict in-place
        so future calls to get_structured_schema are also clean.
        """
        _internal = self._INTERNAL_PROPS
        _orig_refresh = self.lc_graph.refresh_schema

        def _filtered_refresh() -> None:
            _orig_refresh()
            # Filter structured_schema dict (vertex props) in-place.
            vp = self.lc_graph.structured_schema.get("vertice_props", {})
            clean_vp: dict = {}
            for label, props in vp.items():
                if isinstance(props, list):
                    clean_vp[label] = [p for p in props if p not in _internal]
                else:
                    clean_vp[label] = props
            self.lc_graph.structured_schema["vertice_props"] = clean_vp
            # Rebuild the schema string with the filtered props dict.
            vertex_labels = self.lc_graph.structured_schema.get("vertex_labels", [])
            edge_labels = self.lc_graph.structured_schema.get("edge_labels", [])
            self.lc_graph.schema = "\n".join([
                "Vertex labels are the following:",
                ",".join(vertex_labels),
                "Edge labels are the following:",
                ",".join(edge_labels),
                f"Vertices have following properties:\n{clean_vp}",
            ])
            logger.debug("CosmosDBGremlin: schema filtered — removed internal props %s", _internal)

        self.lc_graph.refresh_schema = _filtered_refresh

    def add_graph_documents(self, graph_docs: list, include_source: bool = True) -> None:
        """Write graph documents to Gremlin, escaping single quotes so Groovy scripts
        don't break.  The source text chunk (page_content) is intentionally excluded
        from the graph — only nodes and relationships are written."""
        from langchain_community.graphs.graph_document import (
            GraphDocument as _GD, Node as _N, Relationship as _R,
        )
        from langchain_core.documents import Document as _LCDoc

        def _safe_ref_doc_id(v: str) -> str:
            # Cosmos DB Gremlin rejects backslashes, forward slashes, colons, and other
            # special characters in vertex property values (they appear in the 'id'
            # property internally).  Hash the ref_doc_id to a safe alphanumeric token
            # that can be used as an opaque lookup key for delete operations.
            return hashlib.sha1(v.encode("utf-8")).hexdigest()

        # Cosmos DB Gremlin forbidden characters in vertex id and property values:
        # \ / ? # [ ] @ (these are URL-reserved chars that Cosmos prohibits in ids).
        _COSMOS_FORBIDDEN = str.maketrans({
            "\\": "-", "/": "-", "?": "-", "#": "-",
            "[": "(", "]": ")", "@": "-",
        })

        def _esc(v: Any) -> str:
            # Sanitise the value: replace Cosmos-forbidden chars, then escape
            # single quotes for the Groovy string literal.
            return str(v).translate(_COSMOS_FORBIDDEN).replace("'", r"\'")

        _pk_prop = self._partition_key_prop   # e.g. "partitionKey", or None for local TinkerPop
        _pk_val  = self._partition_key_value  # fixed value — keeps all vertices in one partition

        def _safe_node(n: _N) -> _N:
            props = {}
            for k, v in n.properties.items():
                if k == "ref_doc_id":
                    # Hash the ref_doc_id: Cosmos Gremlin rejects backslashes and other
                    # special path characters in property values, even when escaped.
                    props[k] = _safe_ref_doc_id(str(v))
                else:
                    props[k] = _esc(v)
            # Cosmos DB partition key: inject a fixed value so all vertices land in the same
            # logical partition. Using a fixed value avoids cross-partition graph traversals,
            # which occur whenever a query touches vertices of different types.
            # Without this, Cosmos rejects every vertex write with "partition key has value null".
            if _pk_prop and _pk_prop not in props:
                props[_pk_prop] = _esc(_pk_val)
            return _N(
                id=_esc(n.id),
                type=_esc(n.type),
                properties=props,
            )

        def _safe_rel(r: _R) -> _R:
            return _R(
                source=_safe_node(r.source),
                target=_safe_node(r.target),
                type=_esc(r.type),
                properties={k: _esc(v) for k, v in r.properties.items()},
            )

        def _safe_gd(gd: _GD) -> _GD:
            # Keep a minimal source document so GraphDocument is valid, but we
            # pass include_source=False below so it is never written to Gremlin.
            return _GD(
                nodes=[_safe_node(n) for n in gd.nodes],
                relationships=[_safe_rel(r) for r in gd.relationships],
                source=gd.source,
            )

        # Always skip the source chunk — the full page_content text embeds
        # metadata dicts and arbitrary text whose quotes break Groovy scripts.
        self.lc_graph.add_graph_documents(
            [_safe_gd(gd) for gd in graph_docs],
            include_source=False,
        )

    def create_qa_chain(self, llm: Any):
        """Create Gremlin QA chain."""
        from langchain_community.chains.graph_qa.gremlin import GremlinQAChain
        return GremlinQAChain.from_llm(
            llm=llm,
            graph=self.lc_graph,
            verbose=False,
            allow_dangerous_requests=True,
        )

    def delete(self, ref_doc_id: str) -> None:
        """Delete all vertices tagged with *ref_doc_id* using Gremlin.

        The default ``LangChainPGAdapter.delete`` uses a Cypher DETACH DELETE
        which GremlinGraph does not support.  This override issues a Gremlin
        traversal that drops all vertices with ``ref_doc_id`` property matching
        the given value.

        For Cosmos DB the ``partitionKey`` filter is also applied to keep the
        traversal within the single logical partition used by this adapter.
        """
        # ref_doc_id was hashed on write (Cosmos Gremlin rejects backslashes, forward
        # slashes, colons, and other path characters in property values). Apply the
        # same SHA-1 hash here so the delete filter matches what was stored.
        _rid = hashlib.sha1(ref_doc_id.encode("utf-8")).hexdigest()
        _pk_prop = self._partition_key_prop    # e.g. "partitionKey", or None for local
        _pk_val  = self._partition_key_value   # fixed value e.g. "graph"

        if _pk_prop:
            gremlin = (
                f"g.V().has('{_pk_prop}', '{_pk_val}')"
                f".has('ref_doc_id', '{_rid}').drop()"
            )
        else:
            gremlin = f"g.V().has('ref_doc_id', '{_rid}').drop()"

        try:
            # GremlinGraph.run() / query() executes a Gremlin string and returns results.
            if hasattr(self.lc_graph, "client"):
                # langchain_community GremlinGraph uses a gremlinpython client
                self.lc_graph.client.submit(gremlin).all().result()
            else:
                # Fallback: try generic query()
                self.lc_graph.query(gremlin)
            logger.info("CosmosDBGremlin: deleted vertices for ref_doc_id=%s", ref_doc_id)
        except Exception as exc:
            logger.warning("CosmosDBGremlin delete failed for ref_doc_id=%s: %s", ref_doc_id, exc)

    def get_graph(self):
        return self.lc_graph

    def normalize_entity_names(self) -> None:
        """Cosmos DB: entity names are already stored as the 'id' property.

        The __Entity__ label is a LangChain/Neo4j convention not used in
        Cosmos DB — vertices are written with their actual type labels
        (Person, Company, etc.).  No name normalization is needed here.
        """
        logger.debug("CosmosDBGremlin: normalize_entity_names skipped (id property is already the entity name)")


__all__ = ["CosmosDBGremlinAdapter", "COSMOS_DB_AVAILABLE"]
