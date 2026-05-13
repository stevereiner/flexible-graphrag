"""adapters.llm.llm_adapter — LLMAdapter / EmbeddingAdapter ABCs, Both variants, and factories."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from config import AppSettings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM ABC
# ---------------------------------------------------------------------------

class LLMAdapter(ABC):
    """Unified interface for an LLM (LlamaIndex or LangChain or both)."""

    @property
    @abstractmethod
    def backend(self) -> str:
        """``'llamaindex'``, ``'langchain'``, or ``'both'``."""

    @abstractmethod
    def get_li_llm(self) -> Optional[Any]:
        """Return LlamaIndex LLM instance (or None)."""

    @abstractmethod
    def get_lc_llm(self) -> Optional[Any]:
        """Return LangChain BaseChatModel instance (or None)."""


class BothLLMAdapter(LLMAdapter):
    """Holds a native LlamaIndex LLM and a native LangChain chat model.

    Use for mixed pipelines where both must be available simultaneously.
    """

    def __init__(self, li_llm, lc_llm):
        self._li_llm = li_llm
        self._lc_llm = lc_llm

    @property
    def backend(self) -> str:
        return "both"

    def get_li_llm(self):
        return self._li_llm

    def get_lc_llm(self):
        return self._lc_llm


# ---------------------------------------------------------------------------
# Embedding ABC
# ---------------------------------------------------------------------------

class EmbeddingAdapter(ABC):
    """Unified interface for an embedding model (LlamaIndex or LangChain or both)."""

    @property
    @abstractmethod
    def backend(self) -> str:
        """``'llamaindex'``, ``'langchain'``, or ``'both'``."""

    @abstractmethod
    def get_li_embedding(self) -> Optional[Any]:
        """Return LlamaIndex BaseEmbedding instance (or None)."""

    @abstractmethod
    def get_lc_embedding(self) -> Optional[Any]:
        """Return LangChain Embeddings instance (or None)."""


class BothEmbeddingAdapter(EmbeddingAdapter):
    """Holds native LlamaIndex and LangChain embedding models simultaneously."""

    def __init__(self, li_embedding, lc_embedding):
        self._li_embedding = li_embedding
        self._lc_embedding = lc_embedding

    @property
    def backend(self) -> str:
        return "both"

    def get_li_embedding(self):
        return self._li_embedding

    def get_lc_embedding(self):
        return self._lc_embedding


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def build_llm_adapter(config: "AppSettings") -> LLMAdapter:
    """Build the appropriate :class:`LLMAdapter` based on ``config.llm_backend``."""
    from factories import LLMFactory
    from langchain.llm.llm_factory import get_langchain_llm

    backend = getattr(config, "llm_backend", "llamaindex").lower()
    provider = config.llm_provider
    llm_cfg = config.llm_config or {}

    if backend == "langchain":
        from langchain.llm.llm_adapter import LangChainLLMAdapter
        return LangChainLLMAdapter(get_langchain_llm(config))

    if backend == "both":
        from llamaindex.llm.llm_adapter import LlamaIndexLLMAdapter
        li_llm = LLMFactory.create_llm(provider, llm_cfg)
        lc_llm = get_langchain_llm(config)
        return BothLLMAdapter(li_llm, lc_llm)

    from llamaindex.llm.llm_adapter import LlamaIndexLLMAdapter
    return LlamaIndexLLMAdapter(LLMFactory.create_llm(provider, llm_cfg))


def build_embedding_adapter(config: "AppSettings") -> EmbeddingAdapter:
    """Build the appropriate :class:`EmbeddingAdapter` based on ``config.embedding_backend``."""
    from factories import LLMFactory
    from langchain.llm.embedding_factory import build_lc_embedding
    from langchain.llm.embedding_adapter import LangChainEmbeddingAdapter

    backend = getattr(config, "embedding_backend", "llamaindex").lower()
    provider = config.llm_provider
    llm_cfg = config.llm_config or {}

    if backend == "langchain":
        return LangChainEmbeddingAdapter(build_lc_embedding(config))

    if backend == "both":
        from llamaindex.llm.embedding_adapter import LlamaIndexEmbeddingAdapter
        li_emb = LLMFactory.create_embedding_model(provider, llm_cfg, config)
        return BothEmbeddingAdapter(li_emb, build_lc_embedding(config))

    from llamaindex.llm.embedding_adapter import LlamaIndexEmbeddingAdapter
    return LlamaIndexEmbeddingAdapter(LLMFactory.create_embedding_model(provider, llm_cfg, config))
