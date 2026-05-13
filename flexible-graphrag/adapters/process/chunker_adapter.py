"""adapters.process.chunker_adapter — ChunkerAdapter ABC and factory."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from config import AppSettings

logger = logging.getLogger(__name__)


class ChunkerAdapter(ABC):
    """Unified interface for splitting documents into chunks."""

    @property
    @abstractmethod
    def backend(self) -> str:
        """``'llamaindex'`` or ``'langchain'``."""

    @abstractmethod
    def split_text(self, text: str) -> List[str]:
        """Split *text* into a list of chunk strings."""

    @abstractmethod
    def split_documents(self, documents: List[Any]) -> List[Any]:
        """Split a list of document objects into smaller document objects."""

    @abstractmethod
    def get_splitter(self) -> Any:
        """Return the underlying splitter object."""


def build_chunker_adapter(config: "AppSettings") -> ChunkerAdapter:
    """Build a :class:`ChunkerAdapter` from ``config.chunker_backend``."""
    backend = getattr(config, "chunker_backend", "llamaindex").lower()
    chunk_size = getattr(config, "chunk_size", 1024)
    chunk_overlap = getattr(config, "chunk_overlap", 128)

    if backend == "langchain":
        from langchain.process.chunker_adapter import LangChainChunkerAdapter
        splitter_type = getattr(config, "lc_splitter_type", "recursive")
        logger.info(f"ChunkerAdapter: LangChain backend, splitter={splitter_type}, chunk_size={chunk_size}, overlap={chunk_overlap}")
        return LangChainChunkerAdapter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, splitter_type=splitter_type)

    from llamaindex.process.chunker_adapter import LlamaIndexChunkerAdapter
    logger.info(f"ChunkerAdapter: LlamaIndex backend (SentenceSplitter), chunk_size={chunk_size}, overlap={chunk_overlap}")
    return LlamaIndexChunkerAdapter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
