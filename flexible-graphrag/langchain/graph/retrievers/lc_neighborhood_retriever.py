"""langchain.graph.retrievers.lc_neighborhood_retriever — Pure-LC k-hop retriever (Layer 0).

``LCNeighborhoodRetriever`` implements the full graph-expansion logic as a
``langchain_core.BaseRetriever``:

  1. Call ``seed_id_getter(query_str)`` to get seed node IDs (plain str interface).
  2. Call ``neighbor_query_fn(seed_ids, hop_depth)`` to expand N hops.
  3. Deduplicate by node_id, keep highest score, apply top_k.
  4. Return ``Document`` objects with score in ``metadata["score"]``.

The ``seed_id_getter`` here accepts a **plain string query** (not a LlamaIndex
``QueryBundle``).  The LI wrapper ``GraphNeighborhoodRetriever`` adapts its
``QueryBundle``-based getter to this interface at construction time.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from langchain_core.retrievers import BaseRetriever as _LCBase
    from langchain_core.documents import Document as _LCDoc
    from langchain_core.callbacks.manager import (
        CallbackManagerForRetrieverRun,
        AsyncCallbackManagerForRetrieverRun,
    )
    from pydantic import ConfigDict

    class LCNeighborhoodRetriever(_LCBase):
        """Pure LC k-hop neighborhood expansion retriever for property graphs.

        Expands from seed node IDs obtained via ``seed_id_getter(query_str)``
        up to ``hop_depth`` hops using
        ``neighbor_query_fn(seed_ids, hop_depth)``, which must yield tuples of
        ``(node_id, text, score)`` or ``(node_id, text, score, metadata_dict)``.

        Results are deduplicated by ``node_id`` keeping the highest score.
        Each result is returned as a ``Document`` with ``metadata["score"]``
        set for ``_docs_to_nodes`` compatibility.

        Args:
            seed_id_getter:    ``(str) -> Iterable[str]`` — returns seed node
                               IDs from a plain string query.
            neighbor_query_fn: ``(seed_ids, hop_depth) ->
                               Iterable[(id, text, score[, meta])]``
                               — executes the actual graph traversal.
            hop_depth:         Maximum relationship hops to expand.
            top_k:             Maximum number of results to return.
        """

        model_config = ConfigDict(arbitrary_types_allowed=True)

        def __init__(
            self,
            seed_id_getter: Callable[[str], Iterable[str]],
            neighbor_query_fn: Callable[
                [List[str], int], Iterable[Tuple[str, str, float]]
            ],
            hop_depth: int = 2,
            top_k: int = 10,
        ) -> None:
            super().__init__()
            self._seed_id_getter = seed_id_getter
            self._neighbor_query_fn = neighbor_query_fn
            self._hop_depth = hop_depth
            self._top_k = top_k

        # ------------------------------------------------------------------
        # LC BaseRetriever interface
        # ------------------------------------------------------------------

        def _get_relevant_documents(
            self,
            query: str,
            *,
            run_manager: CallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            # 1. Seed IDs
            try:
                seed_ids = list(self._seed_id_getter(query))
            except Exception as e:
                logger.warning("LCNeighborhoodRetriever seed_id_getter error: %s", e)
                return []
            if not seed_ids:
                logger.debug(
                    "LCNeighborhoodRetriever: no seed IDs for query: %s", query[:80]
                )
                return []

            # 2. Expand neighborhood
            try:
                rows = list(self._neighbor_query_fn(seed_ids, self._hop_depth))
            except Exception as e:
                logger.warning(
                    "LCNeighborhoodRetriever neighbor_query_fn error: %s", e
                )
                return []

            # 3. Deduplicate by node_id, keep highest score
            seen: dict = {}  # node_id -> (text, score, extra_meta)
            for row in rows:
                node_id, text, score = row[0], row[1], row[2]
                extra_meta: dict = row[3] if len(row) >= 4 else {}
                if not text:
                    continue
                existing_score = seen.get(node_id, (None, -1.0, {}))[1]
                if float(score) > existing_score:
                    seen[node_id] = (text, float(score), extra_meta)

            # 4. Sort, apply top_k, convert to Documents
            ranked = sorted(
                seen.items(), key=lambda kv: kv[1][1], reverse=True
            )[: self._top_k]

            docs: List[_LCDoc] = []
            for node_id, (text, score, extra_meta) in ranked:
                display_source = extra_meta.get("file_name") or str(node_id)
                meta = {"source": display_source, "score": score, **extra_meta}
                docs.append(_LCDoc(page_content=str(text), metadata=meta))

            logger.debug(
                "LCNeighborhoodRetriever: %d seeds -> %d unique neighbors (top_k=%d): %s",
                len(seed_ids), len(seen), self._top_k, query[:80],
            )
            return docs

        async def _aget_relevant_documents(
            self,
            query: str,
            *,
            run_manager: AsyncCallbackManagerForRetrieverRun,
        ) -> List[_LCDoc]:
            import asyncio
            return await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._get_relevant_documents(query, run_manager=run_manager),
            )

except ImportError:
    class LCNeighborhoodRetriever:  # type: ignore[no-redef]
        """Stub when ``langchain_core`` is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "langchain_core is required for LCNeighborhoodRetriever. "
                "Install with: uv pip install langchain-core"
            )


__all__ = ["LCNeighborhoodRetriever"]
