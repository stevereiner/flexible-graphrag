"""adapters.process.kg_extractor_adapter — KGExtractorAdapter ABC and factory."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from config import AppSettings

logger = logging.getLogger(__name__)


class KGExtractorAdapter(ABC):
    """Unified interface for knowledge-graph extraction."""

    @property
    @abstractmethod
    def backend(self) -> str:
        """``'llamaindex'`` or ``'langchain'``."""

    @abstractmethod
    def get_extractors(self) -> List[Any]:
        """Return the list of LlamaIndex extractor transform objects (or empty list)."""

    @abstractmethod
    async def aextract(self, documents: List[Any]) -> List[Any]:
        """Extract graph data from *documents*.

        Returns LlamaIndex ``TextNode`` list (LlamaIndex backend) or
        LangChain ``GraphDocument`` list (LangChain backend).
        """


def build_kg_extractor_adapter(
    config: "AppSettings",
    li_llm=None,
    lc_llm=None,
    extractors: Optional[List[Any]] = None,
    ontology_manager=None,
) -> KGExtractorAdapter:
    """Build a :class:`KGExtractorAdapter` based on ``config.kg_extractor_backend``."""
    backend = getattr(config, "kg_extractor_backend", "llamaindex").lower()
    use_ontology = getattr(config, "use_ontology", False)

    if backend == "langchain":
        from langchain.process.kg_extractor_adapter import LangChainKGExtractorAdapter
        if lc_llm is None:
            from langchain.llm.llm_factory import get_langchain_llm
            lc_llm = get_langchain_llm(config)
        logger.info("KGExtractorAdapter: LangChain backend (LLMGraphTransformer)")
        return LangChainKGExtractorAdapter(lc_llm=lc_llm, ontology_manager=ontology_manager, use_ontology=use_ontology)

    from llamaindex.process.kg_extractor_adapter import LlamaIndexKGExtractorAdapter
    if extractors is None:
        extractors = []
    logger.info(f"KGExtractorAdapter: LlamaIndex backend ({len(extractors)} extractors)")
    return LlamaIndexKGExtractorAdapter(extractors)
