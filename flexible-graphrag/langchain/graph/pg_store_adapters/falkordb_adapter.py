"""LangChain FalkorDB property graph adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    from langchain_community.graphs import FalkorDBGraph
    FALKORDB_AVAILABLE = True
except ImportError:
    FALKORDB_AVAILABLE = False


class FalkorDBAdapter:
    """
    FalkorDB property graph adapter.

    FalkorDB is a Redis-compatible sparse-matrix property graph database
    with Cypher query support.

    Configuration:
    {
        "host": "localhost",
        "port": 6379,
        "database": "falkor"
    }

    References:
    - https://www.falkordb.com/
    - https://python.langchain.com/docs/integrations/graphs/falkordb
    """

    def __init__(self, config: Dict[str, Any]):
        if not FALKORDB_AVAILABLE:
            raise ImportError(
                "langchain-community required. "
                "Install: pip install langchain-community falkordb"
            )

        self.config = config
        # Config may come as {host, port, database} or {url, database}
        # Parse url if host not explicitly provided
        host = config.get("host")
        port = config.get("port")
        if not host:
            url = config.get("url", "falkor://localhost:6379")
            # Strip scheme (falkor://, redis://, etc.)
            netloc = url.split("://", 1)[-1]
            parts = netloc.rsplit(":", 1)
            host = parts[0] if parts else "localhost"
            try:
                port = int(parts[1]) if len(parts) > 1 else 6379
            except ValueError:
                port = 6379
        host = host or "localhost"
        port = int(port or 6379)
        database = config.get("database", "falkor")
        self.lc_graph = FalkorDBGraph(
            host=host,
            port=port,
            database=database,
        )
        logger.info(
            "Connected to FalkorDB at %s:%s (database=%s)",
            host, port, database,
        )

    def create_qa_chain(self, llm: Any):
        """Create Cypher QA chain for FalkorDB."""
        try:
            from langchain_community.chains.graph_qa.falkordb import FalkorDBQAChain
            return FalkorDBQAChain.from_llm(
                llm=llm,
                graph=self.lc_graph,
                verbose=False,
                allow_dangerous_requests=True,
            )
        except ImportError:
            from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
            return GraphCypherQAChain.from_llm(
                llm=llm,
                graph=self.lc_graph,
                verbose=False,
                allow_dangerous_requests=True,
            )

    def get_graph(self):
        return self.lc_graph

    def add_graph_documents(self, graph_documents, include_source: bool = False, **kwargs) -> None:
        """Write graph documents to FalkorDB, inlining properties as literals.

        FalkorDB's ``add_graph_documents`` uses ``SET n += $properties`` with a
        dict parameter, which FalkorDB cannot serialize when the dict is non-empty.
        This override writes each property as ``n.key = 'value'`` directly in the
        Cypher string, avoiding the parameterized-dict limitation.
        """
        def _escape(v: str) -> str:
            return str(v).replace("'", "\\'").replace("\\", "\\\\")

        def _props_clause(prefix: str, props: dict) -> str:
            if not props:
                return ""
            pairs = ", ".join(
                f"{prefix}.`{k}` = '{_escape(v)}'" for k, v in props.items()
                if v is not None
            )
            return f"SET {pairs} " if pairs else ""

        for document in graph_documents:
            for node in document.nodes:
                props = _props_clause("n", node.properties or {})
                self.lc_graph.query(
                    f"MERGE (n:`{node.type}` {{id: '{_escape(node.id)}'}}) "
                    f"{props}"
                    f"RETURN distinct 'done' AS result"
                )

            for rel in document.relationships:
                rel_type = rel.type.replace(" ", "_").upper()
                props = _props_clause("r", rel.properties or {})
                self.lc_graph.query(
                    f"MATCH (a:`{rel.source.type}` {{id: '{_escape(rel.source.id)}'}}), "
                    f"(b:`{rel.target.type}` {{id: '{_escape(rel.target.id)}'}}) "
                    f"MERGE (a)-[r:`{rel_type}`]->(b) "
                    f"{props}"
                    f"RETURN distinct 'done' AS result"
                )

    def normalize_entity_names(self) -> None:
        """SET name = id on entity nodes (FalkorDB Cypher)."""
        try:
            self.lc_graph.query(
                "MATCH (n:__Entity__) WHERE n.name IS NULL AND n.id IS NOT NULL "
                "SET n.name = n.id"
            )
            logger.debug("FalkorDB: normalized entity names (id -> name)")
        except Exception as exc:
            logger.warning("FalkorDB normalize_entity_names failed: %s", exc)

    # ------------------------------------------------------------------
    # Native FalkorDB vector index — chunk nodes with embeddings
    # ------------------------------------------------------------------

    def _connection_kwargs(self) -> Dict[str, Any]:
        """Return the connection kwargs shared by FalkorDBVector calls."""
        return {
            "host": self.config.get("host", "localhost"),
            "port": int(self.config.get("port", 6379)),
            "database": self.config.get("database", "falkor"),
        }

    def store_chunk_embeddings(
        self,
        lc_documents: list,
        embedding,
        node_label: str = "Chunk",
        text_property: str = "text",
    ) -> None:
        """Write text chunks as vector-indexed nodes in FalkorDB.

        FalkorDBVector.add_embeddings uses UNWIND $data with a list-of-dicts
        parameter.  FalkorDB server rejects the nested-map parameter when it
        contains a vecf32 array, producing: ``Invalid input at end of input:
        expected '=' … errCtx: CYPHER data``.

        This method bypasses FalkorDBVector entirely for writes:
        1. Embeds texts with the supplied embedding model.
        2. Creates the vector index via the raw FalkorDB client.
        3. Writes each node with scalar $text/$chunk_id params and the
           embedding vector inlined as a ``vecf32([...])`` literal so no
           nested-map parameter is needed.

        ``get_chunk_vector_store`` still uses FalkorDBVector.from_existing_index
        for reads, which passes the query vector as a plain $embedding list.
        """
        if not lc_documents:
            logger.debug("FalkorDB store_chunk_embeddings: no documents, skipping")
            return

        from hashlib import md5

        texts = [d.page_content for d in lc_documents]
        try:
            embeddings = embedding.embed_documents(texts)
        except Exception as exc:
            logger.warning("FalkorDB store_chunk_embeddings: embed_documents failed: %s", exc)
            return

        dim = len(embeddings[0]) if embeddings else 0
        if not dim:
            logger.warning("FalkorDB store_chunk_embeddings: zero-dim embeddings, skipping")
            return

        # Create the vector index.  "already indexed" means a prior run
        # already created it — safe to ignore.
        try:
            raw_graph = self.lc_graph._graph
            raw_graph.create_node_vector_index(
                node_label, "embedding", dim=dim, similarity_function="cosine",
            )
            logger.debug(
                "FalkorDB: created vector index for %s.embedding (dim=%d)", node_label, dim,
            )
        except Exception as exc:
            if "already indexed" not in str(exc).lower():
                logger.debug("FalkorDB: vector index creation: %s", exc)

        stored = 0
        for doc, emb in zip(lc_documents, embeddings):
            node_id = md5(doc.page_content.encode("utf-8")).hexdigest()
            emb_str = "[" + ",".join(str(v) for v in emb) + "]"
            try:
                self.lc_graph.query(
                    f"MERGE (c:`{node_label}` {{id: $chunk_id}}) "
                    f"SET c.`{text_property}` = $text, c.embedding = vecf32({emb_str})",
                    params={"chunk_id": node_id, "text": doc.page_content},
                )
                stored += 1
            except Exception as exc:
                logger.warning("FalkorDB store_chunk_embeddings: chunk %d write failed: %s", stored, exc)

        logger.info(
            "FalkorDB: stored %d/%d chunk(s) with embeddings (node_label=%s)",
            stored, len(lc_documents), node_label,
        )

    def get_chunk_vector_store(
        self,
        embedding,
        node_label: str = "Chunk",
        text_property: str = "text",
    ):
        """Return a FalkorDBVector instance over the existing chunk index.

        Returns ``None`` if the index does not exist yet (e.g. before first
        ingest) so callers can gracefully skip vector retrieval.
        """
        try:
            from langchain_community.vectorstores.falkordb_vector import FalkorDBVector
        except ImportError:
            logger.debug("FalkorDBVector not available")
            return None

        try:
            store = FalkorDBVector.from_existing_index(
                embedding,
                node_label=node_label,
                **self._connection_kwargs(),
            )
            logger.info(
                "FalkorDB: connected to existing chunk vector index (node_label=%s)",
                node_label,
            )
            return store
        except Exception as exc:
            logger.debug("FalkorDB get_chunk_vector_store: index not ready: %s", exc)
            return None


__all__ = ["FalkorDBAdapter", "FALKORDB_AVAILABLE"]
