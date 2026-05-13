"""langchain.llm — LangChain LLM and embedding implementations.

ABCs and Both* adapters are in :mod:`adapters.llm.llm_adapter`.
LlamaIndex implementations are in :mod:`llamaindex.llm.llm_adapter`.

Files
-----
llm_adapter        LangChainLLMAdapter
llm_factory        get_langchain_llm
embedding_adapter  LangChainEmbeddingAdapter
embedding_factory  build_lc_embedding
"""
from .llm_adapter import LangChainLLMAdapter
from .llm_factory import get_langchain_llm
from .embedding_adapter import LangChainEmbeddingAdapter
from .embedding_factory import build_lc_embedding
from adapters.llm.llm_adapter import (
    LLMAdapter,
    EmbeddingAdapter,
    BothLLMAdapter,
    BothEmbeddingAdapter,
    build_llm_adapter,
    build_embedding_adapter,
)

__all__ = [
    # LLM
    "LangChainLLMAdapter",
    "get_langchain_llm",
    # Embedding
    "LangChainEmbeddingAdapter",
    "build_lc_embedding",
    # ABCs + Both adapters + factories (from adapters.llm)
    "LLMAdapter",
    "EmbeddingAdapter",
    "BothLLMAdapter",
    "BothEmbeddingAdapter",
    "build_llm_adapter",
    "build_embedding_adapter",
]
