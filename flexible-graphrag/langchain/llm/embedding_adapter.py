"""langchain.llm.embedding_adapter — LangChain embedding adapter."""
from __future__ import annotations

from adapters.llm.llm_adapter import EmbeddingAdapter


class LangChainEmbeddingAdapter(EmbeddingAdapter):
    """Wraps a LangChain ``Embeddings`` object."""

    def __init__(self, lc_embedding):
        self._lc_embedding = lc_embedding

    @property
    def backend(self) -> str:
        return "langchain"

    def get_li_embedding(self):
        return None

    def get_lc_embedding(self):
        return self._lc_embedding


__all__ = ["LangChainEmbeddingAdapter"]
