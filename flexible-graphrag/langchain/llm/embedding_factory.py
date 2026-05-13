"""langchain.llm.embedding_factory — Build LangChain Embeddings from config.

Maps every :class:`~config.LLMProvider` / ``embedding_kind`` value to the
corresponding ``langchain_*`` Embeddings class.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import AppSettings

logger = logging.getLogger(__name__)


def build_lc_embedding(config: "AppSettings"):
    """Build a LangChain ``Embeddings`` instance from *config*.

    Resolution order: ``embedding_kind`` (explicit) > ``llm_provider`` (fallback).

    CRITICAL: When ``embedding_kind`` is set explicitly it ALWAYS wins, regardless of
    ``llm_provider``.  Provider-based fallbacks only fire when ``embedding_kind`` is
    absent (empty string / None).  This prevents e.g. ``EMBEDDING_KIND=ollama`` +
    ``LLM_PROVIDER=openai`` from accidentally routing through ``OpenAIEmbeddings``.
    """
    from config import LLMProvider

    provider = config.llm_provider
    embedding_kind = getattr(config, "embedding_kind", None)
    embedding_model = getattr(config, "embedding_model", None)
    llm_cfg = config.llm_config or {}
    kind = (embedding_kind or "").lower()

    logger.info(
        "build_lc_embedding: kind=%r model=%r provider=%r",
        kind, embedding_model, provider,
    )

    # Helper: True when embedding_kind is either explicitly set to X, OR not set and
    # the LLM provider is X (provider-as-fallback only when kind is absent).
    def _match(kind_name: str, prov) -> bool:
        if kind:
            return kind == kind_name
        return provider == prov

    if _match("openai", LLMProvider.OPENAI):
        from langchain_openai import OpenAIEmbeddings
        # When LLM_PROVIDER is ALSO openai, use llm_cfg api_key directly.
        # When LLM_PROVIDER is a DIFFERENT provider (e.g. ollama, anthropic), llm_cfg
        # belongs to THAT provider — always read OPENAI_API_KEY from the environment.
        if provider == LLMProvider.OPENAI:
            _openai_key = llm_cfg.get("api_key") or os.getenv("OPENAI_API_KEY")
        else:
            _openai_key = os.getenv("OPENAI_API_KEY")
        return OpenAIEmbeddings(
            model=embedding_model or "text-embedding-3-small",
            **({} if _openai_key is None else {"api_key": _openai_key}),
        )

    if _match("ollama", LLMProvider.OLLAMA):
        try:
            from langchain_ollama import OllamaEmbeddings
        except ImportError:
            logger.warning("build_lc_embedding: langchain-ollama not installed; install with: uv pip install langchain-ollama")
            raise
        base_url = (
            os.getenv("OLLAMA_BASE_URL")
            or (llm_cfg.get("base_url") if provider == LLMProvider.OLLAMA else None)
            or "http://localhost:11434"
        )
        return OllamaEmbeddings(
            model=embedding_model or "nomic-embed-text",
            base_url=base_url,
        )

    if _match("google", LLMProvider.GEMINI):
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
        except ImportError:
            logger.warning("build_lc_embedding: langchain-google-genai not installed; install with: uv pip install langchain-google-genai")
            raise
        # Prefer explicit Google env vars; llm_cfg key only valid when provider IS gemini.
        _google_key = (
            os.getenv("GOOGLE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or (llm_cfg.get("api_key") if provider == LLMProvider.GEMINI else None)
        )
        # gemini-embedding-2-preview native dim is 3072; truncate to 768 to match our
        # dimension tables and existing vector collections.
        _dim = getattr(config, "embedding_dimension", None) or 768
        return GoogleGenerativeAIEmbeddings(
            model=embedding_model or "models/gemini-embedding-2-preview",
            google_api_key=_google_key,
            output_dimensionality=int(_dim),
        )

    if _match("vertex", LLMProvider.VERTEX_AI):
        # langchain-google-vertexai is not always installed (it needs langchain-core<1.0
        # in some versions).  Use langchain-google-genai with Vertex AI backend instead
        # — same SDK, no extra package needed.
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        _project = (
            os.getenv("VERTEX_AI_PROJECT")
            or (llm_cfg.get("project") if provider == LLMProvider.VERTEX_AI else None)
        )
        _location = (
            os.getenv("VERTEX_AI_LOCATION")
            or (llm_cfg.get("location") if provider == LLMProvider.VERTEX_AI else None)
            or "us-central1"
        )
        _creds_path = (
            os.getenv("VERTEX_AI_CREDENTIALS_PATH")
            or (llm_cfg.get("credentials_path") if provider == LLMProvider.VERTEX_AI else None)
        )
        if _creds_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _creds_path
        if _project:
            os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _project)
            os.environ.setdefault("GOOGLE_CLOUD_LOCATION", _location)
            os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
        # gemini-embedding-2-preview native dim is 3072; truncate to 768 to match our
        # dimension tables and existing vector collections.
        _dim = getattr(config, "embedding_dimension", None) or 768
        return GoogleGenerativeAIEmbeddings(
            model=embedding_model or "models/gemini-embedding-2-preview",
            output_dimensionality=int(_dim),
        )

    if _match("azure", LLMProvider.AZURE_OPENAI):
        from langchain_openai import AzureOpenAIEmbeddings
        _az_endpoint = (
            os.getenv("AZURE_OPENAI_ENDPOINT")
            or (llm_cfg.get("azure_endpoint") if provider == LLMProvider.AZURE_OPENAI else None)
        )
        _az_key = (
            os.getenv("AZURE_OPENAI_API_KEY")
            or (llm_cfg.get("api_key") if provider == LLMProvider.AZURE_OPENAI else None)
        )
        _az_ver = os.getenv("AZURE_EMBEDDING_API_VERSION") or (
            llm_cfg.get("api_version") if provider == LLMProvider.AZURE_OPENAI else None
        ) or "2024-02-01"
        return AzureOpenAIEmbeddings(
            azure_deployment=embedding_model or "text-embedding-3-small",
            azure_endpoint=_az_endpoint,
            api_key=_az_key,
            api_version=_az_ver,
        )

    if _match("bedrock", LLMProvider.BEDROCK):
        from langchain_aws import BedrockEmbeddings
        _region = (
            os.getenv("BEDROCK_REGION") or os.getenv("AWS_DEFAULT_REGION")
            or (llm_cfg.get("region_name") if provider == LLMProvider.BEDROCK else None)
            or "us-east-1"
        )
        # Mirror the LI factory: bedrock uses BEDROCK_ACCESS_KEY / BEDROCK_SECRET_KEY
        # (not the standard AWS_ACCESS_KEY_ID) so boto3 can't find them automatically.
        # Pass them explicitly when available.
        _aws_kwargs: dict = {}
        _ak = (os.getenv("BEDROCK_ACCESS_KEY")
               or (llm_cfg.get("aws_access_key_id") if provider == LLMProvider.BEDROCK else None))
        _sk = (os.getenv("BEDROCK_SECRET_KEY")
               or (llm_cfg.get("aws_secret_access_key") if provider == LLMProvider.BEDROCK else None))
        _st = (os.getenv("BEDROCK_SESSION_TOKEN")
               or (llm_cfg.get("aws_session_token") if provider == LLMProvider.BEDROCK else None))
        if _ak:
            _aws_kwargs["aws_access_key_id"] = _ak
        if _sk:
            _aws_kwargs["aws_secret_access_key"] = _sk
        if _st:
            _aws_kwargs["aws_session_token"] = _st
        return BedrockEmbeddings(
            model_id=embedding_model or "amazon.titan-embed-text-v2:0",
            region_name=_region,
            **_aws_kwargs,
        )

    if _match("fireworks", LLMProvider.FIREWORKS):
        # Prefer env var — when EMBEDDING_KIND=fireworks with a different LLM_PROVIDER,
        # llm_cfg holds that other provider's credentials.
        _fw_key = os.getenv("FIREWORKS_API_KEY") or llm_cfg.get("api_key")
        _fw_model = embedding_model or "nomic-ai/nomic-embed-text-v1.5"
        try:
            from langchain_fireworks import FireworksEmbeddings
            return FireworksEmbeddings(
                model=_fw_model,
                fireworks_api_key=_fw_key,
            )
        except ImportError:
            # langchain-fireworks not installed — use OpenAI-compatible endpoint.
            # Fireworks exposes a /v1/embeddings endpoint that is OpenAI-API compatible.
            from langchain_openai import OpenAIEmbeddings
            logger.info(
                "langchain-fireworks not installed; using OpenAI-compatible endpoint "
                "for Fireworks embeddings (api.fireworks.ai/inference/v1)"
            )
            return OpenAIEmbeddings(
                model=_fw_model,
                api_key=_fw_key,
                base_url="https://api.fireworks.ai/inference/v1",
            )

    if kind in ("openai_like", "litellm"):
        from langchain_openai import OpenAIEmbeddings
        is_litellm = kind == "litellm"
        if is_litellm:
            # For litellm, check config attributes that Pydantic auto-populates from LITELLM_* env vars.
            _cfg_api_base = getattr(config, "litellm_embedding_api_base", None)
        else:
            # For openai_like, do NOT fall back to litellm_embedding_api_base — that's a different
            # service (LiteLLM proxy). Only use the openai_like-specific config attribute.
            _cfg_api_base = getattr(config, "openai_like_embedding_api_base", None)
        api_base = (
            _cfg_api_base
            or os.getenv("LITELLM_EMBEDDING_API_BASE" if is_litellm else "OPENAI_LIKE_EMBEDDING_API_BASE")
            or os.getenv("LITELLM_API_BASE" if is_litellm else "OPENAI_LIKE_API_BASE")
            or ("http://localhost:4000/v1" if is_litellm else "http://localhost:8002/v1")
        )
        _api_key = (
            os.getenv("LITELLM_API_KEY" if is_litellm else "OPENAI_LIKE_API_KEY")
            or "local"
        )
        logger.info(
            "build_lc_embedding [%s]: api_base=%r model=%r",
            kind, api_base, embedding_model,
        )
        # check_embedding_ctx_length=False: prevents langchain_openai from tokenising the
        # input into integer token IDs before sending — Ollama and most openai-like servers
        # only accept plain string inputs, not integer arrays.
        return OpenAIEmbeddings(
            model=embedding_model or "text-embedding-3-small",
            api_key=_api_key,
            base_url=api_base,
            check_embedding_ctx_length=False,
        )

    logger.warning(
        "build_lc_embedding: no match for kind=%r provider=%r — falling back to OpenAI text-embedding-3-small. "
        "Check that the langchain provider package is installed (e.g. langchain-ollama, langchain-google-genai).",
        kind, provider,
    )
    import traceback
    logger.debug("build_lc_embedding fallback traceback:\n%s", "".join(traceback.format_stack()))
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model="text-embedding-3-small")


# Well-known embedding dimensions — avoids an extra API round-trip on first init.
_KNOWN_DIMS: dict = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "text-embedding-004": 768,              # Google (deprecated)
    "gemini-embedding-2-preview": 768,      # Google recommended
    "gemini-embedding-001": 768,            # Google stable GA
    "nomic-embed-text": 768,               # Ollama / Fireworks default
    "nomic-ai/nomic-embed-text-v1.5": 768, # Fireworks model ID
    "amazon.titan-embed-text-v2:0": 1024,
}


def get_lc_embedding_dimension(config: "AppSettings") -> int:
    """Return the embedding vector dimension for *config* without an API call.

    Falls back to ``config.embedding_dimension`` if set, then to well-known
    model dimension table, then to a kind-specific default, then to 1536.
    """
    explicit = getattr(config, "embedding_dimension", None)
    if explicit:
        return int(explicit)
    model = (getattr(config, "embedding_model", None) or "").lower()
    for name, dim in _KNOWN_DIMS.items():
        if name in model:
            return dim
    # Kind-based fallbacks for when no model name is configured yet
    kind = (getattr(config, "embedding_kind", None) or "").lower()
    _KIND_DEFAULTS = {
        "google": 768, "vertex": 768, "fireworks": 768,
        "ollama": 768, "bedrock": 1024,
    }
    if kind in _KIND_DEFAULTS:
        return _KIND_DEFAULTS[kind]
    return 1536


__all__ = ["build_lc_embedding", "get_lc_embedding_dimension"]
