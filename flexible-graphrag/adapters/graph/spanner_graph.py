"""Spanner Graph helpers shared by the LlamaIndex (llama-index-spanner) and LangChain
(langchain-google-spanner) property graph stores.

Both, in their flexible schema, keep a graph in two tables: ``<graph>_NODE`` (key ``id``) and
``<graph>_EDGE`` (key ``id, target_id, label``, interleaved in its source node, with a foreign
key to its target), the node / relationship type in a ``label`` column and every other property
in a JSON ``properties`` column. A chunk node MENTIONS the entities extracted from it.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# (gql, params) -> rows; the caller adds the "GRAPH <name>" prefix
Query = Callable[[str, Dict[str, Any]], List[Dict[str, Any]]]


def credentials_file(config: Dict[str, Any]) -> Optional[str]:
    """``credentials_file`` (or ``credentials`` / ``credentials_path``) in the config, else
    GOOGLE_APPLICATION_CREDENTIALS; None = Application Default Credentials."""
    return (config.get("credentials_file") or config.get("credentials") or config.get("credentials_path")
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or None)


def make_client(config: Dict[str, Any]):
    """A google-cloud-spanner Client for the configured project, with the service-account key
    file when one is configured."""
    from google.cloud import spanner
    project = config.get("project_id") or config.get("project")
    path = credentials_file(config)
    if path:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            path, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return spanner.Client(project=project or creds.project_id, credentials=creds)
    return spanner.Client(project=project)


def _props(raw: Any) -> dict:
    try:
        return json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except (TypeError, ValueError):
        return {}


def _handed(props: dict, chunk: str, heir: str):
    from google.cloud.spanner_v1.data_types import JsonObject
    props = dict(props)
    for k in ("doc_id", "ref_doc_id"):
        if props.get(k) not in (None, ""):
            props[k] = heir
    props["triplet_source_id"] = chunk
    return JsonObject(props)


def _delete_rows(impl: Any, table: str, keys: List[List[Any]]) -> None:
    """Delete rows by key: the store's ``delete`` (llama-index-spanner) or a batch mutation on its
    database (langchain-google-spanner has none)."""
    if hasattr(impl, "delete"):
        impl.delete(table, keys)
        return
    from google.cloud import spanner
    for i in range(0, len(keys), 500):
        with impl.database.batch() as batch:
            batch.delete(table=table, keyset=spanner.KeySet(keys=keys[i:i + 500]))


def delete_document(query: Query, impl: Any, node_table: str, edge_table: Optional[str],
                    doc_id: str, chunk_label: str) -> Dict[str, int]:
    """Delete one document's graph data, leaving what other documents share.

    A relationship two documents produce is one row, and an entity is stamped with one
    document's id. In order: this document's relationships another document's chunk MENTIONS
    both ends of pass to that document, the others go; its entities another document's chunk
    MENTIONS pass to it; its chunks' MENTIONS edges (kept with the chunk) and its chunks go;
    then its entities no edge uses any more (Spanner refuses to delete a node an edge points at).
    ``impl`` is the store's Spanner interface (``insert_or_update``, and ``delete`` or ``database``).
    """
    p = {"d": doc_id}
    mine = "(JSON_VALUE({v}.properties.doc_id) = @d OR JSON_VALUE({v}.properties.ref_doc_id) = @d)"
    others: Dict[str, Dict[str, str]] = {}  # entity -> {another document's chunk MENTIONing it: that document}
    for r in query("MATCH (c)-[m]->(e) WHERE m.label = 'MENTIONS' AND JSON_VALUE(c.properties.ref_doc_id) <> @d "
                   "RETURN c.id AS c, e.id AS e, JSON_VALUE(c.properties.ref_doc_id) AS r", p):
        if r.get("r"):
            others.setdefault(r["e"], {})[r["c"]] = r["r"]

    kept, gone = [], []
    if edge_table:
        for r in query("MATCH (a)-[r]->(b) WHERE r.label <> 'MENTIONS' AND " + mine.format(v="r") +
                       " RETURN a.id AS a, r.label AS l, b.id AS b, TO_JSON_STRING(r.properties) AS p", p):
            both = sorted(set(others.get(r["a"], {})) & set(others.get(r["b"], {})))
            if both:
                c = both[0]
                kept.append([r["a"], r["b"], r["l"], _handed(_props(r["p"]), c, others[r["a"]][c])])
            else:
                gone.append([r["a"], r["b"], r["l"]])
        if kept:
            impl.insert_or_update(edge_table, ("id", "target_id", "label", "properties"), kept)
        if gone:
            _delete_rows(impl, edge_table, gone)

    handed_entities = []
    for r in query(f"MATCH (e) WHERE e.label <> '{chunk_label}' AND " + mine.format(v="e") +
                   " RETURN e.id AS e, TO_JSON_STRING(e.properties) AS p", p):
        heirs = others.get(r["e"], {})
        if heirs:
            c = sorted(heirs)[0]
            handed_entities.append([r["e"], _handed(_props(r["p"]), c, heirs[c])])
    if handed_entities:
        impl.insert_or_update(node_table, ("id", "properties"), handed_entities)

    chunks = [r["c"] for r in query(f"MATCH (c) WHERE c.label = '{chunk_label}' AND "
                                    "JSON_VALUE(c.properties.ref_doc_id) = @d RETURN c.id AS c", p)]
    if chunks and edge_table:
        links = query("MATCH (c)-[m]->(e) WHERE c.id IN UNNEST(@ids) RETURN c.id AS a, m.label AS l, e.id AS b",
                      {"ids": chunks})
        if links:
            _delete_rows(impl, edge_table, [[r["a"], r["b"], r["l"]] for r in links])
    if chunks:
        _delete_rows(impl, node_table, [[c] for c in chunks])

    stamped = [r["e"] for r in query(f"MATCH (e) WHERE e.label <> '{chunk_label}' AND " + mine.format(v="e") +
                                     " RETURN e.id AS e", p)]
    used = {r["i"] for r in query("MATCH (x)-[]-(y) WHERE x.id IN UNNEST(@ids) RETURN DISTINCT x.id AS i",
                                  {"ids": stamped})} if stamped else set()
    unused = [e for e in stamped if e not in used]
    if unused:
        _delete_rows(impl, node_table, [[e] for e in unused])
    return {"relationships_deleted": len(gone), "relationships_kept": len(kept), "chunks": len(chunks),
            "entities_deleted": len(unused), "entities_kept": len(handed_entities)}


def scoped_facts(query: Query, doc_ids: Iterable[str], chunk_label: str,
                 limit: int = 1000) -> List[Tuple[Any, Any, Any, Any]]:
    """(subject, relation, object, doc_id): relationships whose doc_id is in ``doc_ids`` plus
    those between two entities one chunk of those documents MENTIONS."""
    ids = {"ids": list(doc_ids)}
    rows = query("MATCH (a)-[r]->(b) WHERE r.label <> 'MENTIONS' AND (JSON_VALUE(r.properties.doc_id) IN UNNEST(@ids) "
                 "OR JSON_VALUE(r.properties.ref_doc_id) IN UNNEST(@ids)) RETURN a.id AS s, r.label AS rel, b.id AS o, "
                 "COALESCE(JSON_VALUE(r.properties.doc_id), JSON_VALUE(r.properties.ref_doc_id)) AS d "
                 f"LIMIT {int(limit)}", ids)
    rows += query("MATCH (c)-[m1]->(a), (c)-[m2]->(b), (a)-[r]->(b) WHERE c.label = @chunk "
                  "AND m1.label = 'MENTIONS' AND m2.label = 'MENTIONS' AND r.label <> 'MENTIONS' "
                  "AND JSON_VALUE(c.properties.ref_doc_id) IN UNNEST(@ids) RETURN DISTINCT a.id AS s, "
                  f"r.label AS rel, b.id AS o, JSON_VALUE(c.properties.ref_doc_id) AS d LIMIT {int(limit)}",
                  {**ids, "chunk": chunk_label})
    return list(dict.fromkeys((r["s"], r["rel"], r["o"], r["d"]) for r in rows))
