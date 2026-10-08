"""Replace, rather than duplicate, documents that an earlier ingest already put in the stores.

A document ingested with a ``config_id`` gets a stable id (``{config_id}:{identity}``), so
ingesting the same source again produces the same ids. Inserting them again would add a second
set of chunks, entities and triples next to the first -- every store keys chunks on their own
ids, not the document's. Deleting the previous version first makes a repeat ingest a refresh.

Only ids known to have been ingested before are deleted (from ``document_state``), so a first
ingest of a large folder does not pay a per-document delete in every store.

Used by the default pipeline (ingest_source_documents) and the Langflow document processor.
"""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Set

logger = logging.getLogger(__name__)


async def known_doc_ids(doc_ids: List[str]) -> Optional[Set[str]]:
    """Which of ``doc_ids`` document_state already records, or None when there is no
    incremental registry in this process to ask (e.g. inside the Langflow process)."""
    try:
        from incremental_system import IncrementalSystemManager
    except Exception:
        return None
    mgr = IncrementalSystemManager._instance
    if mgr is None or not mgr.is_initialized() or mgr.state_manager is None:
        return None
    async with mgr.state_manager.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT doc_id FROM document_state WHERE doc_id = ANY($1::text[])", doc_ids
        )
    return {r["doc_id"] for r in rows}


async def delete_previous_versions(system, documents: List, replace_doc_ids: Optional[Iterable[str]] = None) -> int:
    """Delete the stored copy of each document in ``documents`` that was ingested before.

    ``replace_doc_ids`` names the ids known to exist; when omitted they are looked up in this
    process's document_state. Returns how many documents were deleted.
    """
    ids = [d.id_ for d in documents if getattr(d, "id_", None)]
    if not ids:
        return 0
    known = set(replace_doc_ids) if replace_doc_ids is not None else await known_doc_ids(ids)
    targets = [i for i in dict.fromkeys(ids) if known and i in known]
    if not targets:
        return 0
    logger.info("Re-ingest: deleting the previous version of %d document(s) before inserting", len(targets))
    return await delete_doc_ids(system, targets)


async def delete_doc_ids(system, doc_ids: Iterable[str], targets: Optional[Iterable[str]] = None) -> int:
    """Delete each document from every configured store, or only from ``targets`` (see
    engine.DELETE_TARGETS). Returns how many were processed."""
    doc_ids = list(dict.fromkeys(doc_ids))
    if not doc_ids:
        return 0
    # The incremental engine already knows how to delete one document from every configured
    # vector, search, property-graph and RDF store; reuse it rather than a second copy.
    from incremental_updates.engine import IncrementalUpdateEngine
    engine = IncrementalUpdateEngine(
        vector_index=getattr(system, "vector_index", None),
        graph_index=getattr(system, "graph_index", None),
        search_index=getattr(system, "search_index", None),
        doc_processor=None,
        state_manager=None,
        app_config=getattr(system, "config", None),
        hybrid_system=system,
    )
    stores = None if targets is None else list(targets)
    for doc_id in doc_ids:
        logger.info("  deleting %s from %s", doc_id, ", ".join(stores) if stores else "all stores")
        await engine._delete_from_all_indexes(doc_id, stores)
    return len(doc_ids)
