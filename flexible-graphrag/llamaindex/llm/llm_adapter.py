"""llamaindex.llm.llm_adapter — LlamaIndex LLM adapter.

The embedding adapter lives in :mod:`llamaindex.llm.embedding_adapter`.
"""
from __future__ import annotations

import logging

from adapters.llm.llm_adapter import LLMAdapter

logger = logging.getLogger(__name__)


class LlamaIndexLLMAdapter(LLMAdapter):
    """Wraps a LlamaIndex LLM.  LangChain model is lazily bridged on demand."""

    def __init__(self, li_llm):
        self._li_llm = li_llm
        self._lc_llm = None

    @property
    def backend(self) -> str:
        return "llamaindex"

    def get_li_llm(self):
        return self._li_llm

    def get_lc_llm(self):
        """Return a LangChain-compatible wrapper around the LlamaIndex LLM."""
        if self._lc_llm is not None:
            return self._lc_llm
        try:
            from langchain_community.llms import LlamaIndexLLM  # type: ignore
            self._lc_llm = LlamaIndexLLM(llm=self._li_llm)
            return self._lc_llm
        except Exception as exc:
            logger.debug("Could not build LangChain bridge for LlamaIndex LLM: %s", exc)
            return None


__all__ = ["LlamaIndexLLMAdapter"]
