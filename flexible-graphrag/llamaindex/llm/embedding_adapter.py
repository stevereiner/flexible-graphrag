"""llamaindex.llm.embedding_adapter — LlamaIndex embedding adapter."""
from __future__ import annotations

import logging

from adapters.llm.llm_adapter import EmbeddingAdapter

logger = logging.getLogger(__name__)


class LlamaIndexEmbeddingAdapter(EmbeddingAdapter):
    """Wraps a LlamaIndex embedding model.

    The LangChain bridge is built lazily via
    ``langchain_community.embeddings.LlamaIndexEmbeddings`` when
    :meth:`get_lc_embedding` is first called.
    """

    def __init__(self, li_embedding):
        self._li_embedding = li_embedding
        self._lc_embedding = None

    @property
    def backend(self) -> str:
        return "llamaindex"

    def get_li_embedding(self):
        return self._li_embedding

    def get_lc_embedding(self):
        """Lazily wrap the LlamaIndex embedding into a LangChain-compatible object."""
        if self._lc_embedding is not None:
            return self._lc_embedding
        try:
            from langchain_community.embeddings import LlamaIndexEmbeddings  # type: ignore
            self._lc_embedding = LlamaIndexEmbeddings(embed_model=self._li_embedding)
            return self._lc_embedding
        except Exception as exc:
            logger.debug("Could not build LangChain bridge for LlamaIndex embedding: %s", exc)
            return None


__all__ = ["LlamaIndexEmbeddingAdapter"]
