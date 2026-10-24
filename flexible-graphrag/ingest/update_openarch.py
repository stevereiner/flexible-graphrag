"""
OpenArch ingest step (ENABLE_OPENARCH): writes each document — its parsed text and its
chunks with their embeddings — into the OpenArch content repository.
"""

import logging
import time

logger = logging.getLogger(__name__)


async def update_openarch(system, nodes: list, documents: list) -> float:
    """Write the documents of ``nodes`` into OpenArch, each with all its chunks (grouped by
    ``ref_doc_id``) and its parsed text from ``documents``.

    Returns elapsed seconds (0.0 if OpenArch is not enabled).
    """
    store = getattr(system, "openarch_store", None)
    if store is None:
        return 0.0
    start = time.time()
    ids = {n.ref_doc_id for n in nodes}
    docs = [d for d in (documents or []) if getattr(d, "doc_id", None) in ids]
    await store.async_add_documents(docs, nodes)
    duration = time.time() - start
    logger.info(f"OpenArch: {len(ids)} document(s), {len(nodes)} chunk(s) in {duration:.2f}s")
    return duration
