"""langchain.llm.llm_adapter — LangChain LLM adapter.

The ABCs and Both* adapters live in :mod:`adapters.llm.llm_adapter`.
The embedding adapter lives in :mod:`langchain.llm.embedding_adapter`.
The LlamaIndex implementations live in :mod:`llamaindex.llm.llm_adapter`.
"""
from __future__ import annotations

from adapters.llm.llm_adapter import LLMAdapter


class LangChainLLMAdapter(LLMAdapter):
    """Wraps a LangChain chat model."""

    def __init__(self, lc_llm):
        self._lc_llm = lc_llm

    @property
    def backend(self) -> str:
        return "langchain"

    def get_li_llm(self):
        return None

    def get_lc_llm(self):
        return self._lc_llm


__all__ = ["LangChainLLMAdapter"]
