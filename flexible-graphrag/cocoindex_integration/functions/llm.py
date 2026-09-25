"""
LLM text-generation provider factories for flexible-graphrag / CocoIndex pipelines.

Returns the appropriate LlamaIndex or LangChain **chat/completion** LLM object for
the configured ``LLM_PROVIDER``.  These are used as the backbone of the KG-extraction
``@coco.fn`` functions in ``kg_extraction.py``.

For **embeddings** see ``embedding.py`` in this package — it provides factory
functions for all ``EMBEDDING_KIND`` providers (independent of the LLM provider)
and goes well beyond CocoIndex's built-in LiteLLM connector.

Provider support matrix (LLM text generation only)
---------------------------------------------------
Provider        LLM chat    Notes
-----------     --------    -----
openai          yes
azure           yes         Azure OpenAI deployment
ollama          yes
google          yes         gemini-3-flash-preview, gemini-2.5-flash, …
vertex          yes         gemini-2.5-flash (gemini-3-flash-preview not on Vertex)
bedrock         yes         uses DynamicLLMPathExtractor (Converse API)
fireworks       yes         uses DynamicLLMPathExtractor; no /v1/embeddings
openai_like     yes         uses DynamicLLMPathExtractor; any OpenAI-compat endpoint
litellm         yes         DynamicLLMPathExtractor when model=ollama/*
openrouter      yes         uses DynamicLLMPathExtractor; no /v1/embeddings
requesty        yes         uses DynamicLLMPathExtractor; LLM only here
vllm            yes         uses DynamicLLMPathExtractor; no Python package on Windows
groq            yes         uses DynamicLLMPathExtractor; no /v1/embeddings

Embedding provider support is documented in ``embedding.py``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# LlamaIndex LLM factory
# ─────────────────────────────────────────────────────────────────────────────

def get_llama_index_llm(
    provider: Optional[str] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
):
    """Return a LlamaIndex LLM instance for the configured provider.

    Reads the same env vars that flexible-graphrag uses so existing .env
    files work without change.

    Parameters
    ----------
    provider:
        Override the ``LLM_PROVIDER`` env var (openai, ollama, google, …).
    config_overrides:
        Extra kwargs merged into the provider config (model, temperature, …).

    Returns
    -------
    A LlamaIndex ``BaseLLM`` instance, or ``None`` if flexible-graphrag is not
    importable.
    """
    try:
        from config import Settings, LLMProvider
        from llamaindex.llm.llm_factory import create_llm
    except ImportError as _ie:
        logger.warning(
            "get_llama_index_llm: could not import flexible-graphrag modules — returning None: %s",
            _ie, exc_info=True,
        )
        return None

    cfg = Settings()

    # Resolve provider: argument wins, then env/config.
    _provider_name = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    try:
        _provider = LLMProvider(_provider_name)
    except ValueError:
        logger.warning("get_llama_index_llm: unknown provider %r — falling back to openai", _provider_name)
        _provider = LLMProvider.OPENAI

    # Build the config dict the same way flexible-graphrag does for this provider.
    _llm_cfg = cfg.llm_config or {}
    if config_overrides:
        _llm_cfg = {**_llm_cfg, **config_overrides}

    try:
        llm = create_llm(_provider, _llm_cfg)
        if llm is None:
            logger.warning("get_llama_index_llm: create_llm returned None for provider=%r", _provider_name)
        return llm
    except Exception as exc:
        logger.warning("get_llama_index_llm: create_llm failed — returning None", exc_info=True)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# LangChain LLM factory
# ─────────────────────────────────────────────────────────────────────────────

def get_langchain_llm(
    provider: Optional[str] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
):
    """Return a LangChain ``BaseChatModel`` for the configured provider.

    Same logic as ``get_llama_index_llm`` but uses flexible-graphrag's
    ``langchain/llm/llm_factory.py``.

    Returns
    -------
    A LangChain ``BaseChatModel``, or ``None`` if not importable.
    """
    try:
        from config import Settings, LLMProvider
        from langchain.llm.llm_factory import get_langchain_llm as _build_lc_llm
    except ImportError as _ie:
        logger.warning(
            "get_langchain_llm: could not import flexible-graphrag modules — returning None: %s",
            _ie, exc_info=True,
        )
        return None

    cfg = Settings()

    # Resolve provider: argument wins, then env/config.
    _provider_name = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    try:
        cfg.llm_provider = LLMProvider(_provider_name)
    except ValueError:
        logger.warning("get_langchain_llm: unknown provider %r — falling back to openai", _provider_name)
        cfg.llm_provider = LLMProvider.OPENAI

    if config_overrides:
        for k, v in config_overrides.items():
            try:
                setattr(cfg, k, v)
            except Exception:
                pass

    try:
        # get_langchain_llm(config) takes the full Settings object
        llm = _build_lc_llm(cfg)
        if llm is None:
            logger.warning("get_langchain_llm: returned None for provider=%r", _provider_name)
        return llm
    except Exception as exc:
        logger.warning("get_langchain_llm: failed — returning None", exc_info=True)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Provider name → LlamaIndex provider string (matches flexible-graphrag)
# ─────────────────────────────────────────────────────────────────────────────

#: Providers that must use DynamicLLMPathExtractor instead of SchemaLLMPathExtractor.
#: Mirrors ``hybrid_system.py`` ``switch_to_dynamic_providers``.
DYNAMIC_LLM_PROVIDERS = frozenset({
    "bedrock", "fireworks", "groq", "openai_like", "openrouter", "requesty", "vllm",
    # litellm only when backed by ollama/* (detected at runtime)
})

#: Providers that support LLM chat but NOT the /v1/embeddings endpoint.
LLM_ONLY_PROVIDERS = frozenset({
    "fireworks", "openrouter", "requesty", "groq",
})


def provider_from_env() -> str:
    """Read ``LLM_PROVIDER`` from env, normalised to lowercase."""
    return os.getenv("LLM_PROVIDER", "openai").lower()


def is_dynamic_provider(provider: str) -> bool:
    """True if *provider* must use ``DynamicLLMPathExtractor``."""
    p = provider.lower()
    if p in DYNAMIC_LLM_PROVIDERS:
        return True
    # litellm backed by an ollama model
    if p == "litellm":
        model = os.getenv("LITELLM_MODEL", "")
        return model.startswith("ollama/")
    return False


def supports_embeddings(provider: str) -> bool:
    """True if *provider* also exposes an embeddings endpoint."""
    return provider.lower() not in LLM_ONLY_PROVIDERS
