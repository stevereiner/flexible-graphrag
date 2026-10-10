"""Answer from one document or folder only ("Ask AI about this document / folder").

A scope arrives as the stable doc ids of the documents it stands for (``{config_id}:{identity}``,
the ref_doc_id every store keeps on its chunks; main.py resolves a node or folder to them
through document_state). Two layers keep retrieval inside it:

* **In-store filters** -- each store asked to return only those documents, so the usual top-k is
  spent on them (phases 2-4: vector/search metadata filters, property-graph and RDF queries).
* **ScopedRetriever** -- the last step before the LLM: drops every node whose document is not in
  the scope, and every node that names no document at all. Whatever a store could not filter,
  nothing outside the scope reaches the answer.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, List, Optional, Set

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle

logger = logging.getLogger(__name__)


def node_doc_id(n: Any) -> Optional[str]:
    """The stable doc id a retrieved node came from, or None when it names none."""
    node = getattr(n, "node", n)
    ref = getattr(node, "ref_doc_id", None)
    if ref:
        return ref
    meta = getattr(node, "metadata", None) or {}
    return meta.get("doc_id") or meta.get("ref_doc_id") or meta.get("document_id")


def facts_per_document(facts: Iterable[tuple]) -> List[NodeWithScore]:
    """One node per document from ``(score, "A -> REL -> B", doc_id)`` facts, best first --
    the shape an unscoped graph retriever returns. Separate one-fact nodes would each count
    against the hybrid fusion's top-k (crowding out the chunks) and are then dropped from
    search results as bare relation links."""
    from llama_index.core.schema import TextNode
    groups: dict = {}
    for score, text, doc_id in facts:
        g = groups.setdefault(doc_id, [0.0, []])
        g[0] = max(g[0], float(score or 0.0))
        g[1].append(text)
    return [NodeWithScore(node=TextNode(text="\n".join(texts), metadata={"doc_id": d}), score=s)
            for d, (s, texts) in sorted(groups.items(), key=lambda kv: kv[1][0], reverse=True)]


class ScopedRetriever(BaseRetriever):
    """Keeps only nodes from the scope's documents (see the module docstring)."""

    def __init__(self, inner: BaseRetriever, doc_ids: Iterable[str]) -> None:
        self._inner = inner
        self._doc_ids: Set[str] = set(doc_ids)
        super().__init__()

    def _keep(self, nodes: List[NodeWithScore]) -> List[NodeWithScore]:
        kept = [n for n in nodes if node_doc_id(n) in self._doc_ids]
        if len(kept) != len(nodes):
            logger.info(f"Scope: kept {len(kept)} of {len(nodes)} retrieved nodes "
                        f"({len(self._doc_ids)} document(s) in scope)")
        return kept

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return self._keep(self._inner.retrieve(query_bundle))

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return self._keep(await self._inner.aretrieve(query_bundle))


def build_scoped_retriever(system, doc_ids: Iterable[str]) -> BaseRetriever:
    """A retriever for one question, limited to ``doc_ids``.

    A fresh hybrid retriever whose vector / search retrievers filter by doc id inside the store
    (li_retriever_scope_kwargs), behind the ScopedRetriever safety step for everything else.
    """
    from retriever_setup import setup_hybrid_retriever
    doc_ids = list(doc_ids)
    retriever = setup_hybrid_retriever(system, scope_doc_ids=doc_ids)
    if retriever is None:
        raise ValueError("No search indexes available. The databases may be empty or disconnected.")
    return ScopedRetriever(retriever, doc_ids)


# Stores whose LlamaIndex integration filters a query by doc id inside the store. Elasticsearch's
# LI store only does exact-match "term" filters (with a ".keyword" suffix our keyword field does
# not have), so it gets a native "terms" filter through es_filter; Qdrant and OpenSearch take
# LI's IN filter. Any other store is left to ScopedRetriever.
_LI_IN_FILTER_STORES = {"qdrant", "opensearch", "chroma", "postgres", "neo4j"}


def li_retriever_scope_kwargs(store_type: Any, doc_ids: Iterable[str]) -> dict:
    """Extra ``as_retriever()`` kwargs that keep a LlamaIndex vector / search retriever to
    ``doc_ids`` inside the store, or {} when this store type is not filtered in-store yet."""
    store = str(getattr(store_type, "value", store_type) or "").lower()
    ids = sorted(set(doc_ids))
    if store == "elasticsearch":
        return {"vector_store_kwargs": {"es_filter": [{"terms": {"metadata.doc_id": ids}}]}}
    if store in _LI_IN_FILTER_STORES:
        from llama_index.core.vector_stores.types import (
            FilterOperator, MetadataFilter, MetadataFilters,
        )
        return {"filters": MetadataFilters(filters=[
            MetadataFilter(key="doc_id", value=ids, operator=FilterOperator.IN)])}
    return {}


def scoped_bm25_retriever(system, doc_ids: Iterable[str], top_k: int = 10):
    """BM25 over the scope's chunks only: the local BM25 index has no query-time filter, so
    for one question a small index is built from just those chunks (LlamaIndex or LangChain
    BM25 store alike). None when there is nothing to build it from."""
    from llama_index.core.schema import TextNode
    ids = set(doc_ids)
    store = getattr(system, "search_store", None)
    nodes = []
    docstore = getattr(store, "_docstore", None)
    if docstore is not None and getattr(docstore, "docs", None):  # LlamaIndex BM25 adapter
        nodes = [n for n in docstore.docs.values() if node_doc_id(n) in ids]
    elif getattr(store, "_documents", None):  # LangChain BM25 adapter
        for d in store._documents:
            meta = dict(getattr(d, "metadata", None) or {})
            if meta.get("doc_id") in ids or meta.get("ref_doc_id") in ids:
                nodes.append(TextNode(text=d.page_content, metadata=meta))
    elif getattr(system, "vector_index", None) is not None:
        nodes = [n for n in system.vector_index.docstore.docs.values() if node_doc_id(n) in ids]
    if not nodes:
        logger.info("[scoped bm25] no chunks of the scope in the BM25 index")
        return None
    from llama_index.retrievers.bm25 import BM25Retriever
    logger.info(f"[scoped bm25] {len(nodes)} chunk(s) from {len(ids)} document(s)")
    return BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=min(top_k, len(nodes)))


def _sql_list(ids: List[str]) -> str:
    return ", ".join("'%s'" % d.replace("'", "''") for d in ids)


def _json_list(ids: List[str]) -> str:
    import json
    return ", ".join(json.dumps(d) for d in ids)


def lc_vector_scope_kwargs(store_type: Any, doc_ids: Iterable[str]) -> dict:
    """Extra ``similarity_search_with_score()`` kwargs that keep a LangChain vector store's
    search to ``doc_ids`` (each store's own filter form, on the doc_id every chunk carries in its
    metadata), or {} when this store is not filtered in-store yet."""
    store = str(getattr(store_type, "value", store_type) or "").lower()
    ids = sorted(set(doc_ids))
    if store == "milvus":  # metadata keys are flat top-level fields
        return {"expr": "doc_id in [%s]" % _json_list(ids)}
    if store == "lancedb":  # metadata is one Arrow struct column; the filter is SQL
        return {"filter": "metadata.doc_id IN (%s)" % _sql_list(ids)}
    if store == "weaviate":
        from weaviate.classes.query import Filter
        return {"filters": Filter.by_property("doc_id").contains_any(ids)}
    if store in ("pinecone", "chroma", "postgres", "neo4j"):  # Mongo-style metadata filters
        return {"filter": {"doc_id": {"$in": ids}}}
    if store == "elasticsearch":  # dynamic mapping: the exact value is the .keyword sub-field
        return {"filter": [{"terms": {"metadata.doc_id.keyword": ids}}]}
    if store == "opensearch":
        # Exact scoring over just the scope's chunks: works with any k-NN engine, unlike an
        # efficient filter, and does not lose top-k like a post filter would
        return {"search_type": "script_scoring",
                "pre_filter": {"terms": {"metadata.doc_id.keyword": ids}}}
    if store == "qdrant":
        from qdrant_client import models
        return {"filter": models.Filter(must=[models.FieldCondition(
            key="metadata.doc_id", match=models.MatchAny(any=ids))])}
    return {}


class ScopedGraphRetriever(BaseRetriever):
    """Property-graph facts from the scope's documents only (phase 3).

    Every relationship the pipeline writes carries the ``doc_id`` of the document its fact was
    extracted from (entities are shared across documents, so only relationships are reliable).
    Neo4j and FalkorDB filter and rank entirely in the store: relationships whose doc_id is in
    scope, ordered by how close either end's entity embedding is to the question. Any other LlamaIndex
    property-graph store: its own entity vector search, the relationships around those
    entities, and only those whose doc_id is in scope. Each fact comes back tagged with its
    doc_id, so ScopedRetriever keeps it.
    """

    def __init__(self, system, doc_ids: Iterable[str], top_k: int = 10) -> None:
        self._system = system
        self._doc_ids = sorted(set(doc_ids))
        self._top_k = top_k
        super().__init__()

    def _store(self):
        return self._system.graph_index.property_graph_store

    def _store_type(self) -> str:
        v = getattr(self._system.config, "pg_graph_db", "")
        return str(getattr(v, "value", v)).lower()

    def _nodes(self, facts) -> List[NodeWithScore]:
        out, seen = [], set()
        for subj, rel, obj, doc_id, score in facts:
            text = f"{subj} -> {rel} -> {obj}"
            if text in seen or doc_id not in self._doc_ids:
                continue
            seen.add(text)
            out.append((score, text, doc_id))
            if len(out) >= self._top_k:
                break
        logger.info(f"[scoped graph({self._store_type()})] {len(out)} fact(s) from "
                    f"{len(self._doc_ids)} document(s)")
        return facts_per_document(out)

    def _neo4j_facts(self, embedding):
        rows = self._store().structured_query(
            "MATCH (a:__Entity__)-[r]->(b:__Entity__) WHERE r.doc_id IN $doc_ids "
            "WITH a, r, b, "
            "  CASE WHEN a.embedding IS NULL THEN 0.0 ELSE vector.similarity.cosine(a.embedding, $emb) END AS sa, "
            "  CASE WHEN b.embedding IS NULL THEN 0.0 ELSE vector.similarity.cosine(b.embedding, $emb) END AS sb "
            "RETURN a.name AS subj, type(r) AS rel, b.name AS obj, r.doc_id AS doc_id, "
            "  CASE WHEN sa > sb THEN sa ELSE sb END AS score "
            "ORDER BY score DESC LIMIT $limit",
            param_map={"doc_ids": self._doc_ids, "emb": embedding, "limit": self._top_k * 3},
        )
        return [(r["subj"], r["rel"], r["obj"], r["doc_id"], r["score"]) for r in rows or []]

    def _falkordb_facts(self, embedding):
        # FalkorDB stores entity embeddings as vecf32; cosine *distance*, so lower is closer
        rows = self._store().structured_query(
            "MATCH (a:__Entity__)-[r]->(b:__Entity__) WHERE r.doc_id IN $doc_ids "
            "WITH a, r, b, "
            "  CASE WHEN a.embedding IS NULL THEN 2.0 ELSE vec.cosineDistance(a.embedding, vecf32($emb)) END AS da, "
            "  CASE WHEN b.embedding IS NULL THEN 2.0 ELSE vec.cosineDistance(b.embedding, vecf32($emb)) END AS db "
            "WITH a, r, b, CASE WHEN da < db THEN da ELSE db END AS d "
            "RETURN a.name AS subj, type(r) AS rel, b.name AS obj, r.doc_id AS doc_id, 1.0 - d AS score "
            "ORDER BY d ASC LIMIT $limit",
            param_map={"doc_ids": self._doc_ids, "emb": embedding, "limit": self._top_k * 3},
        )
        return [(r["subj"], r["rel"], r["obj"], r["doc_id"], r["score"]) for r in rows or []]

    def _rank_by_embedding(self, rows, embedding):
        """Rows of (subj, rel, obj, doc_id, subj_embedding, obj_embedding), already limited to
        the scope by the store, ranked here by the closer end's cosine similarity."""
        import math
        qn = math.sqrt(sum(x * x for x in embedding)) or 1.0

        def cos(v):
            if not v:
                return 0.0
            vn = math.sqrt(sum(x * x for x in v)) or 1.0
            return sum(a * b for a, b in zip(v, embedding)) / (vn * qn)

        facts = [(sj, rl, ob, d, max(cos(ea), cos(eb))) for sj, rl, ob, d, ea, eb in rows]
        facts.sort(key=lambda f: f[4], reverse=True)
        return facts

    def _quoted_ids(self) -> str:
        return ", ".join("'%s'" % d.replace("\\", "\\\\").replace("'", "\\'") for d in self._doc_ids)

    def _arcadedb_facts(self, embedding):
        # The store's structured_query takes no parameters for Cypher: the ids go in the text.
        rows = self._store().structured_query(
            "MATCH (a)-[r]->(b) WHERE r.doc_id IN [%s] "
            "RETURN a.name AS subj, type(r) AS rel, b.name AS obj, r.doc_id AS doc_id, "
            "a.embedding AS ea, b.embedding AS eb LIMIT 2000" % self._quoted_ids())
        return self._rank_by_embedding(
            [(r.get("subj"), r.get("rel"), r.get("obj"), r.get("doc_id"), r.get("ea"), r.get("eb"))
             for r in rows or [] if isinstance(r, dict)], embedding)

    def _memgraph_facts(self, embedding):
        # Memgraph: Cypher with parameters like Neo4j, but no cosine function -- filter in the
        # store, rank by the closer end's embedding here
        rows = self._store().structured_query(
            "MATCH (a:__Entity__)-[r]->(b:__Entity__) WHERE r.doc_id IN $doc_ids "
            "RETURN a.name AS subj, type(r) AS rel, b.name AS obj, r.doc_id AS doc_id, "
            "a.embedding AS ea, b.embedding AS eb LIMIT 2000",
            param_map={"doc_ids": self._doc_ids},
        )
        return self._rank_by_embedding(
            [(r.get("subj"), r.get("rel"), r.get("obj"), r.get("doc_id"), r.get("ea"), r.get("eb"))
             for r in rows or [] if isinstance(r, dict)], embedding)

    def _ladybug_facts(self, embedding):
        # LadybugDB (Kuzu dialect) keeps no doc_id on relationships, only the id of the chunk the
        # fact came from (triplet_source_id), and its embeddings live on chunks: so the scope's
        # chunks first, the relationships from them, ranked by their source chunk's similarity.
        rows = self._store().structured_query(
            "MATCH (c:Chunk) WHERE c.ref_doc_id IN $doc_ids "
            "MATCH (a)-[r]->(b) WHERE r.triplet_source_id = c.id "
            "RETURN a.name AS subj, r.label AS rel, b.name AS obj, c.ref_doc_id AS doc_id, "
            "c.embedding AS e LIMIT 2000",
            param_map={"doc_ids": self._doc_ids},
        )
        return self._rank_by_embedding(
            [(r.get("subj"), r.get("rel"), r.get("obj"), r.get("doc_id"), r.get("e"), None)
             for r in rows or [] if isinstance(r, dict)], embedding)

    def _nebula_facts(self, embedding, question: str = ""):
        # NebulaGraph: relationships are Relation__ edges carrying doc_id; entities have no
        # embeddings here, so facts are ranked by word overlap with the question (as RDF is)
        rows = self._store().structured_query(
            "MATCH (a:`Entity__`)-[r:`Relation__`]->(b:`Entity__`) WHERE r.doc_id IN $doc_ids "
            "RETURN a.Entity__.name AS subj, r.label AS rel, b.Entity__.name AS obj, "
            "r.doc_id AS doc_id LIMIT 2000",
            param_map={"doc_ids": self._doc_ids},
        )
        q = _words(question)
        facts = [(r.get("subj"), r.get("rel"), r.get("obj"), r.get("doc_id"),
                  len(q & _words(f"{r.get('subj')} {r.get('rel')} {r.get('obj')}")) / max(len(q), 1))
                 for r in rows or [] if isinstance(r, dict)]
        facts.sort(key=lambda f: f[4], reverse=True)
        return facts

    def _generic_facts(self, embedding):
        from llama_index.core.vector_stores.types import VectorStoreQuery
        store = self._store()
        nodes, scores = store.vector_query(
            VectorStoreQuery(query_embedding=embedding, similarity_top_k=self._top_k * 3))
        by_id = {getattr(n, "id", None): s for n, s in zip(nodes or [], scores or [])}
        facts = []
        for subj, rel, obj in store.get_rel_map(nodes or [], depth=1, limit=200):
            doc_id = (getattr(rel, "properties", None) or {}).get("doc_id")
            score = max(by_id.get(getattr(subj, "id", None), 0.0), by_id.get(getattr(obj, "id", None), 0.0))
            facts.append((getattr(subj, "name", subj), getattr(rel, "label", rel),
                          getattr(obj, "name", obj), doc_id, score))
        facts.sort(key=lambda f: f[4], reverse=True)
        return facts

    def _facts(self, embedding, question: str = ""):
        store = self._store_type()
        if store == "nebula":
            return self._nebula_facts(embedding, question)
        if store == "neo4j":
            return self._neo4j_facts(embedding)
        if store == "falkordb":
            return self._falkordb_facts(embedding)
        if store == "arcadedb":
            return self._arcadedb_facts(embedding)
        if store == "memgraph":
            return self._memgraph_facts(embedding)
        if store == "ladybug":
            return self._ladybug_facts(embedding)
        return self._generic_facts(embedding)

    def _safe_facts(self, embedding, question: str):
        # A graph store that cannot answer must not fail the whole question: no graph facts
        try:
            return self._facts(embedding, question)
        except Exception as e:
            logger.warning(f"[scoped graph({self._store_type()})] no graph facts for this question: {e}")
            return []

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        emb = self._system.embed_model.get_query_embedding(query_bundle.query_str)
        return self._nodes(self._safe_facts(emb, query_bundle.query_str))

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        emb = await self._system.embed_model.aget_query_embedding(query_bundle.query_str)
        return self._nodes(self._safe_facts(emb, query_bundle.query_str))


class ScopedLCGraphRetriever(BaseRetriever):
    """Property-graph facts from the scope's documents only, for the LangChain graph backend.

    The LangChain ingest writes no doc id on relationships, but a source node per document
    (Document / __Chunk__, carrying ref_doc_id) that MENTIONS its entities. Cypher stores
    (Neo4j, Memgraph, FalkorDB, ArcadeDB, Apache AGE, HugeGraph): relationships between two
    entities the scope's source nodes mention. ArangoDB: relationships whose source_id is a
    scope source -- exact provenance. Ranked by word overlap with the question. Stores with no
    document link (TigerGraph, Cosmos/Gremlin, SurrealDB) give no graph facts for a scoped
    question.
    """

    _CYPHER = {"neo4j", "memgraph", "falkordb", "arcadedb", "apache_age", "hugegraph"}

    def __init__(self, system, doc_ids: Iterable[str], top_k: int = 10) -> None:
        self._system = system
        self._doc_ids = sorted(set(doc_ids))
        self._top_k = top_k
        super().__init__()

    def _store_type(self) -> str:
        v = getattr(self._system.config, "pg_graph_db", "")
        return str(getattr(v, "value", v)).lower()

    def _rows(self) -> List[tuple]:
        store = self._store_type()
        adapter = getattr(self._system, "pg_adapter", None)
        graph = adapter.get_lc_graph() if adapter is not None else None
        if graph is None:
            return []
        store_adapter = getattr(adapter, "_store_adapter", None)
        if hasattr(store_adapter, "scoped_facts"):  # the store knows how (SurrealDB, Gremlin)
            return list(store_adapter.scoped_facts(self._doc_ids))
        if store in self._CYPHER:
            # Several of these stores take no query parameters: the ids go in the text
            ids = "[%s]" % ", ".join("'%s'" % d.replace("\\", "\\\\").replace("'", "\\'")
                                     for d in self._doc_ids)
            rows = graph.query(
                "MATCH (d)-[:MENTIONS]->(a) WHERE d.ref_doc_id IN %s OR d.doc_id IN %s "
                "MATCH (d)-[:MENTIONS]->(b) MATCH (a)-[r]->(b) "
                "RETURN coalesce(a.name, a.id) AS subj, type(r) AS rel, coalesce(b.name, b.id) AS obj, "
                "coalesce(d.ref_doc_id, d.doc_id) AS doc_id LIMIT 1000" % (ids, ids))
            if not rows:
                # No source nodes (e.g. Memgraph's LangChain store writes none): relationships
                # whose two entities carry a scope doc id -- best effort, since an entity keeps
                # the ref_doc_id of the last document that wrote it
                rows = graph.query(
                    "MATCH (a)-[r]->(b) WHERE a.ref_doc_id IN %s AND b.ref_doc_id IN %s "
                    "RETURN coalesce(a.name, a.id) AS subj, type(r) AS rel, coalesce(b.name, b.id) AS obj, "
                    "a.ref_doc_id AS doc_id LIMIT 1000" % (ids, ids))

            def plain(v):  # Apache AGE returns agtype strings still JSON-quoted
                if isinstance(v, str) and len(v) > 1 and v[0] == v[-1] == '"':
                    import json
                    try:
                        return json.loads(v)
                    except ValueError:
                        return v
                return v

            keys = ("subj", "rel", "obj", "doc_id")
            out = []
            for r in rows or []:
                if isinstance(r, dict) and "error" not in r:
                    out.append(tuple(plain(r.get(k)) for k in keys))
                elif isinstance(r, (list, tuple)) and len(r) >= 4:  # FalkorDB: positional rows
                    out.append(tuple(plain(v) for v in r[:4]))
            return out
        if store in ("ladybug", "nebula"):
            ids = "[%s]" % ", ".join('"%s"' % d.replace("\\", "\\\\").replace('"', '\\"') for d in self._doc_ids)
            if store == "ladybug":  # Kuzu dialect: Chunk -MENTIONS-> entities, label(r)
                q = ("MATCH (c:Chunk)-[:MENTIONS]->(a) WHERE c.ref_doc_id IN %s "
                     "MATCH (c)-[:MENTIONS]->(b) MATCH (a)-[r]->(b) "
                     "RETURN a.id AS subj, label(r) AS rel, b.id AS obj, c.ref_doc_id AS doc_id LIMIT 1000" % ids)
            else:  # NebulaGraph (LangChain store): every edge carries doc_id; vids are names
                q = ("MATCH (a:`Props__`)-[r]->(b) WHERE r.doc_id IN %s OR r.ref_doc_id IN %s "
                     "RETURN id(a) AS subj, type(r) AS rel, id(b) AS obj, "
                     "CASE WHEN r.doc_id IN %s THEN r.doc_id ELSE r.ref_doc_id END AS doc_id LIMIT 1000"
                     % (ids, ids, ids))
            rows = graph.query(q) or []
            out = []
            for r in rows:
                if isinstance(r, dict):
                    out.append((r.get("subj"), r.get("rel"), r.get("obj"), r.get("doc_id")))
            if not out and isinstance(rows, dict):  # column-major results {col: [values]}
                cols = [rows.get(k) or [] for k in ("subj", "rel", "obj", "doc_id")]
                out = list(zip(*cols))
            return out
        if store == "tigergraph":  # each edge's source attribute holds its document's id
            conn = getattr(graph, "conn", None)
            ids = set(self._doc_ids)
            return [(e.get("from_id"), (e.get("attributes") or {}).get("rel_type"), e.get("to_id"),
                     (e.get("attributes") or {}).get("source"))
                    for e in (conn.getEdgesByType("__Relationship__") or [] if conn is not None else [])
                    if (e.get("attributes") or {}).get("source") in ids]
        if store == "arangodb":
            name = ((getattr(getattr(adapter, "_store_adapter", None), "config", None) or {})
                    .get("graph_name", "knowledge_graph"))
            db = getattr(graph, "_ArangoGraph__db", None)
            cursor = db.aql.execute(
                "FOR s IN @@src FILTER s.ref_doc_id IN @ids OR s.doc_id IN @ids "
                "FOR e IN @@links FILTER e.source_id == s._key LIMIT 1000 "
                "RETURN {subj: DOCUMENT(e._from).text, rel: e.type, obj: DOCUMENT(e._to).text, "
                "doc_id: NOT_NULL(s.ref_doc_id, s.doc_id)}",
                bind_vars={"@src": f"{name}_SOURCE", "@links": f"{name}_LINKS_TO", "ids": self._doc_ids})
            return [(r["subj"], r["rel"], r["obj"], r["doc_id"]) for r in cursor]
        return []

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        from llama_index.core.schema import TextNode
        try:
            rows = self._rows()
        except Exception as e:
            logger.warning(f"[scoped lc graph({self._store_type()})] no graph facts for this question: {e}")
            return []
        q = _words(query_bundle.query_str)
        scored, seen = [], set()
        for subj, rel, obj, doc_id in rows:
            text = f"{subj} -> {rel} -> {obj}"
            if text in seen or doc_id not in self._doc_ids:
                continue
            seen.add(text)
            scored.append((len(q & _words(text)) / max(len(q), 1), text, doc_id))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = scored[: self._top_k]
        logger.info(f"[scoped lc graph({self._store_type()})] {len(out)} fact(s) of {len(rows)} "
                    f"from {len(self._doc_ids)} document(s)")
        return facts_per_document(out)

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        import asyncio
        return await asyncio.get_running_loop().run_in_executor(None, self._retrieve, query_bundle)


_STOPWORDS = {"the", "and", "for", "are", "was", "who", "what", "which", "how", "does", "did",
              "with", "from", "that", "this", "about", "into", "its", "their", "there", "when",
              "where", "why", "has", "have", "had", "can", "you", "your"}


def _words(text: str) -> Set[str]:
    import re
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in _STOPWORDS}


def _iri_name(value: str) -> str:
    tail = (value or "").rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    return tail.replace("_", " ")


_DOCS_FOR_IRIS = """PREFIX onto: <https://integratedsemantics.org/flexible-graphrag/ontology#>
SELECT ?d (COUNT(*) AS ?n) WHERE {
  VALUES ?x { %s }
  { GRAPH ?g { << ?x ?p ?o >> onto:ref_doc_id ?d } } UNION { GRAPH ?g { << ?s ?p ?x >> onto:ref_doc_id ?d } }
} GROUP BY ?d ORDER BY DESC(?n) LIMIT %d"""


def rdf_doc_ids_for_iris(config, iris: Iterable[str], limit: int = 10) -> List[str]:
    """The documents RDF entities came from, most facts first: the onto:ref_doc_id annotation on
    the triples they take part in. Names the sources of an unscoped text-to-SPARQL answer."""
    from rdf.store.rdf_store_factory import RDFStoreFactory
    iris = [i for i in dict.fromkeys(iris) if i and ">" not in i and " " not in i]
    cfg = config.get_rdf_store_config() if iris else None
    if not cfg:
        return []
    try:
        adapter = RDFStoreFactory.create(cfg.get("type", cfg.get("name")), cfg.get("config", {}))
        rows = adapter.query_sparql(_DOCS_FOR_IRIS % (" ".join(f"<{i}>" for i in iris), limit)) or []
    except Exception as e:
        logger.warning(f"[rdf sources] lookup failed, the answer is shown without its documents: {e}")
        return []
    return [r["d"] for r in rows if r.get("d")]


class ScopedRdfRetriever(BaseRetriever):
    """RDF facts from the scope's documents only (phase 4).

    Each relationship triple is stored with an RDF-star annotation naming the document it came
    from (``<< s p o >> onto:ref_doc_id "<doc_id>"``), the same marker the RDF delete uses. The
    store returns only triples annotated with a scope doc_id (VALUES); they are ranked by word
    overlap with the question (RDF has no embeddings here) and tagged with their doc_id.
    """

    _QUERY = """PREFIX onto: <https://integratedsemantics.org/flexible-graphrag/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?s ?p ?o ?sl ?ol ?d WHERE {
  VALUES ?d { %s }
  GRAPH ?g { << ?s ?p ?o >> onto:ref_doc_id ?d }
  OPTIONAL { GRAPH ?g1 { ?s rdfs:label ?sl } }
  OPTIONAL { GRAPH ?g2 { ?o rdfs:label ?ol } }
} LIMIT 2000"""

    def __init__(self, config, doc_ids: Iterable[str], top_k: int = 10) -> None:
        self._config = config
        self._doc_ids = sorted(set(doc_ids))
        self._top_k = top_k
        super().__init__()

    def _rows(self) -> List[dict]:
        from rdf.store.rdf_store_factory import RDFStoreFactory
        cfg = self._config.get_rdf_store_config()
        if not cfg:
            return []
        adapter = RDFStoreFactory.create(cfg.get("type", cfg.get("name")), cfg.get("config", {}))
        values = " ".join('"%s"' % d.replace("\\", "\\\\").replace('"', '\\"') for d in self._doc_ids)
        return adapter.query_sparql(self._QUERY % values) or []

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        from llama_index.core.schema import TextNode
        q = _words(query_bundle.query_str)
        scored, seen = [], set()
        try:
            rows = self._rows()
        except Exception as e:
            logger.warning(f"[scoped rdf] query failed, no RDF facts for this question: {e}")
            return []
        for r in rows:
            subj = r.get("sl") or _iri_name(r.get("s", ""))
            obj = r.get("ol") or _iri_name(r.get("o", ""))
            text = f"{subj} -> {_iri_name(r.get('p', ''))} -> {obj}"
            if text in seen:
                continue
            seen.add(text)
            overlap = len(q & _words(text))
            if overlap:
                scored.append((overlap / max(len(q), 1), text, r.get("d")))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = scored[: self._top_k]
        logger.info(f"[scoped rdf] {len(out)} fact(s) of {len(rows)} from {len(self._doc_ids)} document(s)")
        return facts_per_document(out)

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        import asyncio
        return await asyncio.get_running_loop().run_in_executor(None, self._retrieve, query_bundle)
