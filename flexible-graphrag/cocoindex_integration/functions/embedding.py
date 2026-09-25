"""
Embedding provider factories for flexible-graphrag / CocoIndex pipelines.

This module extends CocoIndex's built-in embedding support (which only covers
LiteLLM and SentenceTransformer) to the full set of ``EMBEDDING_KIND`` providers
that flexible-graphrag supports.  Together with ``llm.py`` (LLM text generation),
it gives independent, full-coverage control over both roles.

``EMBEDDING_KIND`` and ``LLM_PROVIDER`` are **independent** — the embedding model
and the LLM can come from completely different providers.  A common production
config is ``LLM_PROVIDER=ollama`` (local KG extraction) + ``EMBEDDING_KIND=openai``
(cloud embeddings).

Embedding provider support matrix
-----------------------------------
EMBEDDING_KIND   Supported   Notes
--------------   ---------   -----
openai           yes         text-embedding-3-small/large, ada-002
azure            yes         Azure OpenAI embedding deployment
ollama           yes         nomic-embed-text, all-minilm (256-token limit)
google           yes         gemini-embedding-2-preview (1 per API call — batch_size=1)
vertex           yes         text-embedding-005, gemini-embedding-2-preview
bedrock          yes         amazon.titan-embed-text-v2:0, cohere.embed-*
fireworks        no          LLM API only — no /v1/embeddings
openai_like      yes         any OpenAI-compat endpoint (LM Studio, vLLM, Ollama /v1 …)
litellm          yes         via proxy (model-dependent)
openrouter       no          LLM API only
requesty         no          LLM only here (no requesty EMBEDDING_KIND)
vllm             yes         model-dependent, must expose /v1/embeddings
groq             no          LLM API only

Use ``get_llamaindex_embedding()`` / ``get_langchain_embedding()`` when you need a
LlamaIndex ``BaseEmbedding`` or LangChain ``Embeddings`` object — for example to
feed into LlamaIndex's ``VectorStoreIndex`` or a LangChain vectorstore.  For
bare-vector CocoIndex pipelines where you only need a ``list[float]``, these
factories are still the right choice for providers not covered by CocoIndex's
built-in LiteLLM connector (e.g. Bedrock, Google, Vertex, openai_like).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: EMBEDDING_KIND values that have no /v1/embeddings endpoint.
EMBEDDING_ONLY_PROVIDERS = frozenset({
    "fireworks", "openrouter", "requesty", "groq",
})


def embedding_kind_from_env() -> str:
    """Read ``EMBEDDING_KIND`` from env, normalised to lowercase."""
    return os.getenv("EMBEDDING_KIND", "openai").lower()


def supports_embeddings(kind: str) -> bool:
    """True if *kind* (an EMBEDDING_KIND value) exposes an embeddings endpoint."""
    return kind.lower() not in EMBEDDING_ONLY_PROVIDERS


# ─────────────────────────────────────────────────────────────────────────────
# LlamaIndex embedding factory
# ─────────────────────────────────────────────────────────────────────────────

def get_llamaindex_embedding(
    kind: Optional[str] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
):
    """Return a LlamaIndex embedding model for the configured ``EMBEDDING_KIND``.

    Reads the same env vars that flexible-graphrag uses (``EMBEDDING_KIND``,
    ``EMBEDDING_MODEL``, ``OPENAI_EMBEDDING_MODEL``, etc.) so existing ``.env``
    files work without change.

    Parameters
    ----------
    kind:
        Override ``EMBEDDING_KIND`` env var.
    config_overrides:
        Extra kwargs merged into the embedding config (model, dimension, …).

    Returns
    -------
    A LlamaIndex ``BaseEmbedding`` instance, or ``None`` if not importable.
    """
    try:
        from config import Settings, LLMProvider  # type: ignore[import-untyped]
        from llamaindex.llm.embedding_factory import create_embedding_model
    except ImportError:
        logger.debug("get_llamaindex_embedding: flexible-graphrag not importable")
        return None

    settings = Settings()
    if kind:
        settings.embedding_kind = kind.lower()
    if config_overrides:
        for k, v in config_overrides.items():
            try:
                setattr(settings, k, v)
            except Exception:
                pass

    try:
        provider_str = getattr(settings, "llm_provider", "openai")
        try:
            provider = LLMProvider(provider_str) if isinstance(provider_str, str) else provider_str
        except ValueError:
            provider = LLMProvider.OPENAI
        llm_cfg = getattr(settings, "llm_config", {}) or {}
        return create_embedding_model(provider, llm_cfg, settings)
    except Exception as exc:
        logger.warning("get_llamaindex_embedding failed (%s)", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# LangChain embedding factory
# ─────────────────────────────────────────────────────────────────────────────

def get_langchain_embedding(
    kind: Optional[str] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
):
    """Return a LangChain ``Embeddings`` object for the configured ``EMBEDDING_KIND``.

    Parameters
    ----------
    kind:
        Override ``EMBEDDING_KIND`` env var.
    config_overrides:
        Extra kwargs merged into the embedding config.

    Returns
    -------
    A LangChain ``Embeddings`` instance, or ``None`` if not importable.
    """
    try:
        from config import Settings
        from langchain.llm.embedding_factory import build_lc_embedding
    except ImportError:
        logger.debug("get_langchain_embedding: flexible-graphrag not importable")
        return None

    cfg = Settings()
    if kind:
        cfg.embedding_kind = kind.lower()
    if config_overrides:
        for k, v in config_overrides.items():
            try:
                setattr(cfg, k, v)
            except Exception:
                pass

    try:
        return build_lc_embedding(cfg)
    except Exception as exc:
        logger.warning("get_langchain_embedding failed (%s)", exc)
        return None
