"""
LangChain LLM Factory

Returns a LangChain chat model that mirrors the LlamaIndex LLM configuration,
using the same .env values (api keys, model names, endpoints).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _kw(**kwargs: Any) -> Dict[str, Any]:
    """Return kwargs with None values removed.

    LangChain constructors fall back to env-var auto-detection when optional
    fields (api_key, azure_endpoint, …) are absent, but passing ``None``
    explicitly overrides that and triggers type errors in basedpyright because
    many of those fields are typed ``SecretStr`` (non-nullable).
    """
    return {k: v for k, v in kwargs.items() if v is not None}


def get_langchain_llm(config: Any) -> Any:
    """Return a LangChain chat model that mirrors the LlamaIndex LLM config.

    Uses the same .env values (api keys, model names, endpoints) so the
    LangChain QA chain uses the same provider configured for ingestion.
    """
    try:
        provider = (
            config.llm_provider.value.lower()
            if hasattr(config.llm_provider, "value")
            else str(config.llm_provider).lower()
        )
        llm_config: Dict[str, Any] = config.llm_config or {}
        logger.info("[LangChain] Creating LLM with provider: %s", provider)

        if provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=llm_config.get("model", "gpt-4o-mini"),
                temperature=llm_config.get("temperature", 0.1),
                **_kw(api_key=llm_config.get("api_key")),
            )

        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model_name=llm_config.get("model", "claude-3-5-sonnet-20241022"),
                temperature=llm_config.get("temperature", 0.1),
                **_kw(api_key=llm_config.get("api_key")),
            )

        if provider == "bedrock":
            from langchain_aws import ChatBedrock
            return ChatBedrock(
                model=llm_config.get("model", "anthropic.claude-3-sonnet-20240229-v1:0"),
                **_kw(region_name=llm_config.get("region_name", "us-east-1")),
            )

        if provider == "ollama":
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=llm_config.get("model", "llama3.1:8b"),
                base_url=llm_config.get("base_url", "http://localhost:11434"),
            )

        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            from google.genai.types import (
                GenerateContentConfig as _GCC,
                AutomaticFunctionCallingConfig as _AFCConfig,
            )
            _AFC_OFF = _AFCConfig(disable=True)

            class _ChatGeminiNoAFC(ChatGoogleGenerativeAI):
                """ChatGoogleGenerativeAI with Automatic Function Calling disabled.

                AFC intercepts every LangChain tool/function call and can hang
                indefinitely ("AFC is enabled with max remote calls: 10").
                We override _build_request_config to always inject
                automatic_function_calling.disable=True into the GenerateContentConfig
                so the google-genai SDK skips the AFC loop entirely.
                """

                def _build_request_config(self, *args: Any, **kwargs: Any) -> _GCC:
                    cfg: _GCC = super()._build_request_config(*args, **kwargs)
                    cfg.automatic_function_calling = _AFC_OFF
                    return cfg

            return _ChatGeminiNoAFC(
                model=llm_config.get("model", "gemini-2.0-flash"),
                temperature=llm_config.get("temperature", 0.1),
                **_kw(google_api_key=llm_config.get("api_key")),
            )

        if provider == "azure_openai":
            from langchain_openai import AzureChatOpenAI
            return AzureChatOpenAI(
                azure_deployment=llm_config.get("engine") or llm_config.get("model", "gpt-4o-mini"),
                api_version=llm_config.get("api_version", "2024-02-01"),
                temperature=llm_config.get("temperature", 0.1),
                **_kw(
                    azure_endpoint=llm_config.get("azure_endpoint"),
                    api_key=llm_config.get("api_key"),
                ),
            )

        if provider == "groq":
            from langchain_groq import ChatGroq
            return ChatGroq(
                model=llm_config.get("model", "llama-3.3-70b-versatile"),
                temperature=llm_config.get("temperature", 0.1),
                **_kw(api_key=llm_config.get("api_key")),
            )

        if provider == "fireworks":
            from langchain_fireworks import ChatFireworks
            return ChatFireworks(
                model=llm_config.get("model", "accounts/fireworks/models/llama-v3p3-70b-instruct"),
                temperature=llm_config.get("temperature", 0.1),
                **_kw(api_key=llm_config.get("api_key")),
            )

        if provider == "vertex_ai":
            # Vertex via the combined langchain-google-genai (ChatGoogleGenerativeAI with
            # vertexai=True) — the same class as the Gemini path. Replaces the deprecated,
            # no-longer-installed langchain-google-vertexai (which also pulled in numexpr).
            from langchain_google_genai import ChatGoogleGenerativeAI
            from google.genai.types import (
                GenerateContentConfig as _GCC,
                AutomaticFunctionCallingConfig as _AFCConfig,
            )
            _AFC_OFF = _AFCConfig(disable=True)

            class _ChatVertexNoAFC(ChatGoogleGenerativeAI):
                """ChatGoogleGenerativeAI (Vertex mode) with Automatic Function Calling disabled."""

                def _build_request_config(self, *args: Any, **kwargs: Any) -> _GCC:
                    cfg: _GCC = super()._build_request_config(*args, **kwargs)
                    cfg.automatic_function_calling = _AFC_OFF
                    return cfg

            return _ChatVertexNoAFC(
                model=llm_config.get("model", "gemini-2.0-flash-001"),
                temperature=llm_config.get("temperature", 0.1),
                vertexai=True,
                location=llm_config.get("location", "us-central1"),
                **_kw(project=llm_config.get("project")),
            )

        if provider == "openai_like":
            from langchain_openai import ChatOpenAI
            # Default 8002/v1 matches the project's vLLM Docker port (avoids clash with backend on 8000).
            api_base = llm_config.get("api_base", "http://localhost:8002/v1")
            # Optional custom auth header (e.g. `api-key` for Azure / APIM gateways that reject
            # `Authorization: Bearer`). Same OPENAI_LIKE_API_KEY_HEADER env var as the LlamaIndex
            # backend, so one setting covers both; unset = normal Bearer auth.
            api_key = llm_config.get("api_key", "local")
            extra_headers = {}
            api_key_header = os.getenv("OPENAI_LIKE_API_KEY_HEADER")
            if api_key_header:
                extra_headers[api_key_header] = api_key
            return ChatOpenAI(
                model=llm_config.get("model", "local-model"),
                temperature=llm_config.get("temperature", 0.1),
                api_key=api_key,
                base_url=api_base,
                default_headers=extra_headers or None,
            )

        if provider == "litellm":
            from langchain_openai import ChatOpenAI
            # Direct by default; base_url/api_key only when a LiteLLM proxy is configured
            # (LITELLM_API_BASE). Both must go through _kw: passing api_key=None
            # explicitly makes langchain_openai build ONLY the async client, and the
            # classic QA chain's ainvoke() falls back to the sync _generate(), which then
            # fails with "Sync client is not available". Omitting them instead lets
            # ChatOpenAI pick up OPENAI_API_KEY from the environment as usual.
            return ChatOpenAI(
                model=llm_config.get("model", "local-model"),
                temperature=llm_config.get("temperature", 0.1),
                **_kw(
                    api_key=llm_config.get("api_key"),
                    base_url=llm_config.get("api_base"),
                ),
            )

        if provider == "vllm":
            # vLLM server mode (VLLM_MODE=server, default) — OpenAI-compatible /v1 endpoint.
            # In-process mode (VLLM_MODE=inprocess) has no LangChain equivalent; falls back to server path.
            from langchain_openai import ChatOpenAI
            api_base = llm_config.get("api_base", "http://localhost:8002/v1")
            return ChatOpenAI(
                model=llm_config.get("model", "Qwen/Qwen2.5-7B-Instruct"),
                temperature=llm_config.get("temperature", 0.1),
                api_key=llm_config.get("api_key", "local"),
                base_url=api_base,
            )

        if provider == "openrouter":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=llm_config.get("model", "openai/gpt-4o-mini"),
                temperature=llm_config.get("temperature", 0.1),
                base_url="https://openrouter.ai/api/v1",
                **_kw(api_key=llm_config.get("api_key")),
            )

        if provider == "requesty":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=llm_config.get("model", "openai/gpt-4o-mini"),
                temperature=llm_config.get("temperature", 0.1),
                base_url=llm_config.get("api_base", "https://router.requesty.ai/v1"),
                **_kw(api_key=llm_config.get("api_key")),
            )

        logger.warning(
            "No LangChain mapping for provider '%s'; falling back to OpenAI gpt-4o-mini. "
            "Install the required langchain-* package and add the mapping to get_langchain_llm().",
            provider,
        )
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o-mini")

    except Exception as e:
        logger.error("Failed to create LangChain LLM: %s", e)
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o-mini")
