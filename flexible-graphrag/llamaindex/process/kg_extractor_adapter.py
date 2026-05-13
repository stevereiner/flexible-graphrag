"""llamaindex.process.kg_extractor_adapter — LlamaIndexKGExtractorAdapter."""
from __future__ import annotations

from typing import Any, List
import logging

from adapters.process.kg_extractor_adapter import KGExtractorAdapter

logger = logging.getLogger(__name__)


class LlamaIndexKGExtractorAdapter(KGExtractorAdapter):
    """Wraps the existing LlamaIndex extractor list.

    Callers should continue to build extractors via the existing
    ``_create_extractors()`` / ``_make_dynamic_extractor()`` pipeline in
    ``hybrid_system.py``; this adapter is primarily a type-level container.
    """

    def __init__(self, extractors: List[Any]):
        self._extractors = extractors

    @property
    def backend(self) -> str:
        return "llamaindex"

    def get_extractors(self) -> List[Any]:
        return self._extractors

    async def aextract(self, documents: List[Any]) -> List[Any]:
        """Run LlamaIndex extractors on documents and return TextNode list."""
        from llama_index.core.ingestion import IngestionPipeline
        pipeline = IngestionPipeline(transformations=self._extractors)
        return await pipeline.arun(documents=documents)
