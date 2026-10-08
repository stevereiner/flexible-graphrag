"""Remove a repository selection's documents from some or all of the stores.

The counterpart of an ingest: the processing tab can take a selected file or folder back out of
the vector and search stores, out of the graphs (property graph and RDF), or out of everything.

``document_state`` is what says which documents a selection stands for: a file row by the
repository's node id (``source_id``, which survives renames and moves), a folder by the
human-readable ``source_path`` of the documents below it.

What happens to the state row depends on who keeps the document in the stores:

* **ingest-only** datasource (``auto_sync = FALSE``): the row's removed targets are cleared,
  the row is forgotten once nothing is left, and a datasource left with no rows is dropped, so
  ingest status stops reporting it.
* **auto-sync** datasource: the row is kept with the targets cleared -- without it the sync
  would see a "new document" and put it straight back. A document removed from every store is
  also gets ``auto_sync = FALSE``: the sync's update events skip it, so it stays out even when it
  changes in the repository. Ingesting it again clears that. A document whose graph is
  removed gets its own ``skip_graph``, so the sync's updates keep leaving the graph out for it
  (a datasource left with no graph on any document is also marked skip_graph).

Only repository sources (Alfresco, Nuxeo) are handled, the same as ingest status.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .ingest_status import Item, _depth_below, normalize_repo_path

TARGET_COLUMNS = {
    "vector": "vector_synced_at",
    "search": "search_synced_at",
    "graph": "graph_synced_at",
}


def configured_stores(settings: Any) -> Dict[str, bool]:
    """Which delete targets have a store behind them; any of them can be ``none`` in .env.
    "graph" counts when either the property graph or the RDF store is configured."""
    def on(name: str) -> bool:
        value = getattr(settings, name, None)
        return str(getattr(value, "value", value) or "none").lower() != "none"
    return {
        "vector": on("vector_db"),
        "search": on("search_db"),
        "graph": on("pg_graph_db") or on("rdf_graph_db"),
    }


def store_names(targets, settings: Any) -> str:
    """The stores behind delete targets, for messages, named like the ingest completion message:
    "Neo4j property graph and Ontotext GraphDB rdf graph". Stores set to "none" are left out."""
    from ingest._helpers import store_labels
    names = store_labels(settings, targets)
    if not names:
        return "the stores"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


@dataclass
class StateRow:
    doc_id: str
    config_id: str
    source_id: Optional[str]
    source_path: str
    synced: Dict[str, bool]  # target -> currently in that store
    auto_sync: bool = True   # follows its datasource's auto sync (document_state.auto_sync)


def row_from_record(rec: Any) -> StateRow:
    return StateRow(
        doc_id=rec["doc_id"],
        config_id=rec["config_id"],
        source_id=rec["source_id"],
        source_path=rec["source_path"] or "",
        synced={t: rec[col] is not None for t, col in TARGET_COLUMNS.items()},
        auto_sync=bool(rec.get("auto_sync", True)) if hasattr(rec, "get") else bool(rec["auto_sync"]),
    )


def item_matches(item: Item, row: StateRow, recursive: bool) -> bool:
    """Whether ``row`` is a document that the selected ``item`` stands for."""
    if not item.is_folder:
        if item.id and row.source_id:
            return item.id == row.source_id
        return normalize_repo_path(row.source_path) == normalize_repo_path(item.path)
    depth = _depth_below(normalize_repo_path(row.source_path), normalize_repo_path(item.path))
    return depth is not None and depth > 0 and (recursive or depth == 1)


def select_rows(items: Sequence[Item], rows: Iterable[StateRow], recursive: bool) -> List[List[StateRow]]:
    """The rows each item stands for, in item order. A row can appear under several items
    (a file and its folder both selected); callers dedupe by doc_id."""
    rows = list(rows)
    return [[r for r in rows if item_matches(item, r, recursive)] for item in items]


def configs_present(items: Sequence[Item], rows: Iterable[StateRow]) -> List[set]:
    """Per item, the datasources that still have one of its documents in some store (a folder:
    any depth below it). Ingest status uses this to stop reporting an ingest-only datasource for a
    selection whose documents were all removed."""
    live = [r for r in rows if any(r.synced.values())]
    return [{r.config_id for r in live if item_matches(item, r, recursive=True)} for item in items]


def stores_holding(item: Item, rows: Iterable[StateRow], recursive: bool) -> Optional[Dict[str, bool]]:
    """Which stores hold any of the documents a selected item stands for (a folder: the
    documents below it, per ``recursive``), or None when it stands for none."""
    matched = [r for r in rows if item_matches(item, r, recursive)]
    if not matched:
        return None
    return {t: any(r.synced[t] for r in matched) for t in TARGET_COLUMNS}


async def fetch_rows(conn, config_ids: List[str]) -> List[StateRow]:
    records = await conn.fetch(
        "SELECT doc_id, config_id, source_id, source_path, vector_synced_at, "
        "search_synced_at, graph_synced_at, auto_sync FROM document_state "
        "WHERE config_id = ANY($1::text[])",
        config_ids,
    )
    return [row_from_record(r) for r in records]


async def record_removal(conn, rows: Iterable[StateRow], targets: Iterable[str],
                         auto_sync_configs: Iterable[str]) -> Dict[str, int]:
    """Clear ``targets`` on each row; forget ingest-only rows left with nothing, then any
    ingest-only datasource left with no rows; mark a datasource left with no graph as
    skip_graph. Returns counts for the response."""
    rows, targets = list(rows), list(targets)
    cols = [TARGET_COLUMNS[t] for t in targets]
    doc_ids = list(dict.fromkeys(r.doc_id for r in rows))
    if not doc_ids or not cols:
        return {"forgotten": 0, "datasources_dropped": 0, "datasources_now_skip_graph": 0}
    sets = ", ".join(f"{c} = NULL" for c in cols)
    await conn.execute(
        f"UPDATE document_state SET {sets}, updated_at = NOW() WHERE doc_id = ANY($1::text[])",
        doc_ids,
    )
    if "graph" in targets:
        # Per document: its sync's updates leave the graph out from now on (until an ingest
        # writes the graph again, which clears it -- see StateManager.save_state).
        await conn.execute(
            "UPDATE document_state SET skip_graph = TRUE WHERE doc_id = ANY($1::text[])",
            doc_ids,
        )
    await conn.execute(
        "UPDATE document_state SET auto_sync = FALSE WHERE doc_id = ANY($1::text[]) "
        "AND config_id = ANY($2::text[]) "
        "AND vector_synced_at IS NULL AND search_synced_at IS NULL AND graph_synced_at IS NULL",
        doc_ids, list(auto_sync_configs),
    )
    forgotten = await conn.fetch(
        "DELETE FROM document_state WHERE doc_id = ANY($1::text[]) "
        "AND NOT (config_id = ANY($2::text[])) "
        "AND vector_synced_at IS NULL AND search_synced_at IS NULL AND graph_synced_at IS NULL "
        "RETURNING config_id",
        doc_ids, list(auto_sync_configs),
    )
    dropped = await conn.fetch(
        """
        DELETE FROM datasource_config dc
        WHERE dc.config_id = ANY($1::text[]) AND dc.auto_sync = FALSE
          AND NOT EXISTS (SELECT 1 FROM document_state ds WHERE ds.config_id = dc.config_id)
        RETURNING config_id
        """,
        list({r["config_id"] for r in forgotten}),
    )
    # skip_graph is a datasource setting, not a per-document one: once a datasource still has
    # documents in vector + search but none with a graph, it is a "vector + search only" one, the same as one
    # ingested with skip_graph. Its sync (if any) then leaves the graph out on later updates,
    # and a re-ingest with the graph turns the setting back off.
    graph_off = []
    if "graph" in targets:
        graph_off = await conn.fetch(
            """
            UPDATE datasource_config dc SET skip_graph = TRUE, updated_at = NOW()
            WHERE dc.config_id = ANY($1::text[]) AND NOT dc.skip_graph
              AND EXISTS (SELECT 1 FROM document_state ds WHERE ds.config_id = dc.config_id
                          AND (ds.vector_synced_at IS NOT NULL OR ds.search_synced_at IS NOT NULL))
              AND NOT EXISTS (SELECT 1 FROM document_state ds
                              WHERE ds.config_id = dc.config_id AND ds.graph_synced_at IS NOT NULL)
            RETURNING config_id
            """,
            list({r.config_id for r in rows}),
        )
    return {"forgotten": len(forgotten), "datasources_dropped": len(dropped),
            "datasources_now_skip_graph": len(graph_off)}


# ── Per-row auto sync (the Processing tab's Auto Sync column) ─────────────────────────────
# A sync belongs to a datasource, whose roots (connection_params: nodeDetails for a multi-
# select, else its path) are what its detector watches. Turning a row's auto sync off sets
# document_state.auto_sync = FALSE on the documents it stands for -- the sync then skips them --
# and, when the row is one of the datasource's roots, takes it off the root list so new files
# there are not picked up either. A datasource left with no roots stops syncing: it becomes
# ingest-only while some of its documents are still in a store (they stay tracked and
# removable), and is deleted with its rows when none is.


def root_matches(item: Item, path: str, node_id: Optional[str]) -> bool:
    """Whether a selected row is this datasource root."""
    if item.id and node_id:
        return item.id == node_id
    return normalize_repo_path(item.path) == normalize_repo_path(path)


def trim_roots(connection_params: Dict[str, Any], items: Sequence[Item]):
    """(new connection_params, roots left, changed) after taking ``items`` off the roots."""
    cp = dict(connection_params or {})
    details = cp.get("nodeDetails") or []
    if details:
        keep = [nd for nd in details if isinstance(nd, dict) and not any(
            root_matches(it, nd.get("path") or "", nd.get("id")) for it in items)]
        if len(keep) == len(details):
            return cp, len(details), False
        ids = {nd.get("id") for nd in keep}
        cp["nodeDetails"] = keep
        if cp.get("nodeIds"):
            cp["nodeIds"] = [i for i in cp["nodeIds"] if i in ids]
        return cp, len(keep), True
    if any(root_matches(it, cp.get("path") or "", None) for it in items):
        return cp, 0, True
    return cp, 1, False


def add_roots(connection_params: Dict[str, Any], items: Sequence[Item]):
    """(new connection_params, roots added) after putting ``items`` (with a node id) back on a
    multi-select datasource's roots. A datasource rooted at its path already watches all of it."""
    cp = dict(connection_params or {})
    details = list(cp.get("nodeDetails") or [])
    if not details:
        return cp, 0
    added = 0
    for it in items:
        if not it.id or any(isinstance(nd, dict) and root_matches(it, nd.get("path") or "", nd.get("id"))
                            for nd in details):
            continue
        details.append({"id": it.id, "name": it.path.rstrip("/").rsplit("/", 1)[-1], "path": it.path,
                        "isFile": not it.is_folder, "isFolder": it.is_folder})
        if cp.get("nodeIds") is not None:
            cp["nodeIds"] = [*cp["nodeIds"], it.id]
        added += 1
    cp["nodeDetails"] = details
    return cp, added


async def set_auto_sync(conn, doc_ids: Iterable[str], value: bool) -> int:
    ids = list(dict.fromkeys(doc_ids))
    if not ids:
        return 0
    await conn.execute("UPDATE document_state SET auto_sync = $2, updated_at = NOW() "
                       "WHERE doc_id = ANY($1::text[])", ids, value)
    return len(ids)


async def retire_datasource(conn, config_id: str) -> str:
    """A datasource with no roots left: 'ingest-only' while documents of it are in a store,
    else 'deleted' (with its rows)."""
    in_store = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM document_state WHERE config_id = $1 AND "
        "(vector_synced_at IS NOT NULL OR search_synced_at IS NOT NULL OR graph_synced_at IS NOT NULL))",
        config_id)
    if in_store:
        await conn.execute("UPDATE datasource_config SET auto_sync = FALSE, is_active = FALSE, "
                           "updated_at = NOW() WHERE config_id = $1", config_id)
        return "ingest-only"
    await conn.execute("DELETE FROM document_state WHERE config_id = $1", config_id)
    await conn.execute("DELETE FROM datasource_config WHERE config_id = $1", config_id)
    return "deleted"
