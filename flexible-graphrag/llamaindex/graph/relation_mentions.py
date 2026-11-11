"""MENTIONS links from every relationship's source chunk to its two entities (LlamaIndex stores).

``PropertyGraphIndex._insert_nodes`` drops every extracted entity already in the store, so as not
to embed it again, and a store writes an entity's MENTIONS link (chunk -> entity) only while
writing the entity. A document ingested after another that shares its entities (the same file
from two sources, a graph added back) so gets no MENTIONS to them: the Graph tab's read through
a document's chunks and the delete hand-over (incremental_updates/engine.py) then miss its
relationships. Relationships are never dropped and each carries its chunk (``triplet_source_id``),
so after every ``upsert_relations`` the chunk is linked to both its ends, as the Ladybug store
already does itself.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# store class -> how to write the links; Ladybug writes them itself
_CYPHER_LABELLED = {"Neo4jPropertyGraphStore", "MemgraphPropertyGraphStore"}  # __Node__ has the id index
_CYPHER = {"FalkorDBPropertyGraphStore", "NeptuneDatabasePropertyGraphStore",
           "NeptuneAnalyticsPropertyGraphStore"}


def _rows(relations) -> List[Dict[str, str]]:
    out, seen = [], set()
    for r in relations or []:
        chunk = (getattr(r, "properties", None) or {}).get("triplet_source_id")
        key = (chunk, r.source_id, r.target_id)
        if chunk and key not in seen:
            seen.add(key)
            out.append({"chunk": str(chunk), "source": str(r.source_id), "target": str(r.target_id)})
    return out


def _lit(v: str, quote: str = "'") -> str:
    return quote + v.replace("\\", "\\\\").replace(quote, "\\" + quote) + quote


def _write(store: Any, kind: str, rows: List[Dict[str, str]], upsert=None) -> None:
    if kind == "SpannerPropertyGraphStore":  # MENTIONS edges through the store's own write
        from llama_index.core.graph_stores.types import Relation
        pairs = sorted({(r["chunk"], end) for r in rows for end in (r["source"], r["target"])})
        upsert([Relation(label="MENTIONS", source_id=c, target_id=e) for c, e in pairs])
    elif kind in _CYPHER_LABELLED or kind in _CYPHER:
        label = ":__Node__" if kind in _CYPHER_LABELLED else ""
        store.structured_query(
            "UNWIND $rows AS row "
            f"MATCH (c{label} {{id: row.chunk}}) MATCH (a{label} {{id: row.source}}) "
            f"MATCH (b{label} {{id: row.target}}) "
            "MERGE (c)-[:MENTIONS]->(a) MERGE (c)-[:MENTIONS]->(b)",
            param_map={"rows": rows})
    elif kind == "ArcadeDBPropertyGraphStore":
        # no query parameters, writes go as a command, and entities have no id: the store keys
        # them by their normalized name (chunks are TextChunk vertices with an id)
        norm = getattr(store, "_normalize_and_deduplicate_entity", lambda n: n)
        for r in rows:
            store._db.query("opencypher",
                            f"MATCH (c:TextChunk {{id: {_lit(r['chunk'])}}}), (a {{name: {_lit(norm(r['source']))}}}), "
                            f"(b {{name: {_lit(norm(r['target']))}}}) MERGE (c)-[:MENTIONS]->(a) MERGE (c)-[:MENTIONS]->(b)",
                            is_command=True)
    elif kind == "NebulaPropertyGraphStore":  # its own MENTIONS edge (store vids are the ids)
        pairs = {(r["chunk"], end) for r in rows for end in (r["source"], r["target"])}
        store.structured_query("INSERT EDGE `MENTIONS` () VALUES " + ", ".join(
            f"{_lit(c, chr(34))}->{_lit(e, chr(34))}:()" for c, e in sorted(pairs)))


def add_relation_mentions(store: Any) -> None:
    """Wrap ``store.upsert_relations`` (this store object only) to also write the MENTIONS links."""
    known = _CYPHER_LABELLED | _CYPHER | {"ArcadeDBPropertyGraphStore", "NebulaPropertyGraphStore",
                                          "SpannerPropertyGraphStore"}
    inner = getattr(store, "_wrapped", store)  # Neptune: NeptuneDatabaseNoSummaryWrapper
    kind = next((c.__name__ for c in type(inner).__mro__ if c.__name__ in known), None)
    if kind is None:
        return
    if getattr(store, "_fg_relation_mentions", False):
        return
    original = store.upsert_relations

    def upsert_relations(relations, *args, **kwargs):
        result = original(relations, *args, **kwargs)
        rows = _rows(relations)
        if rows:
            try:
                _write(store, kind, rows, original)
            except Exception as e:  # never fail an ingest over these
                logger.warning(f"Could not link {len(rows)} relationship chunk(s) to their entities: {e}")
        return result

    store.upsert_relations = upsert_relations
    store._fg_relation_mentions = True
