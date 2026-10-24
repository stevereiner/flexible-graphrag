"""Which graphs an auto sync builds for one document it ingests (new or changed).

Its data source's graphs (``detector.graphs``, set by the orchestrator; ``detector.skip_graph`` is the
older single flag), overridden graph by graph where a scope rule of the document says (OpenArch
state store, openarch/scope.py), else narrowed by the document's own flags (a graph it was removed
from stays off for it: StateManager.doc_graphs). Shared by every detector's _process_via_backend.
"""
import logging
from typing import List, Optional

from graph_flags import GraphFlags

logger = logging.getLogger(__name__)


def datasource_graphs(detector) -> GraphFlags:
    flags = getattr(detector, "graphs", None)
    if isinstance(flags, GraphFlags):
        return flags
    return GraphFlags.of(bool(getattr(detector, "skip_graph", False)))


async def graphs_for(detector, path: Optional[str] = None, source_id: Optional[str] = None,
                     ancestor_ids: Optional[List[str]] = None) -> Optional[GraphFlags]:
    """The graphs this sync's ingest of the document builds, or None when its scope rules say the
    sync does not follow it (logged)."""
    flags = datasource_graphs(detector)
    sm, config_id = getattr(detector, "state_manager", None), getattr(detector, "config_id", None)
    if not (sm and config_id):
        return flags
    scope = await sm.document_scope(config_id, path, source_id, ancestor_ids)
    if not scope.get("follow", True):
        logger.info(f"SKIP: {path or source_id}: {scope.get('reason')}")
        return None
    rule_graph, rule_rdf = scope.get("graph"), scope.get("rdf")
    if rule_graph is not None or rule_rdf is not None:
        return GraphFlags(flags.graph if rule_graph is None else bool(rule_graph),
                          flags.rdf if rule_rdf is None else bool(rule_rdf))
    if source_id:
        return flags & await sm.doc_graphs(config_id=config_id, source_id=source_id)
    return flags


def synced_times(detector, graphs: GraphFlags, now):
    """(graph_synced_at, rdf_synced_at) for a document the sync just ingested with ``graphs``:
    set only for a graph with a store behind it."""
    config = getattr(getattr(detector, "backend", None), "settings", None)
    built = graphs.built(config)
    return (now if built.graph else None), (now if built.rdf else None)
