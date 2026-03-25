"""
LangChain LLM Factory

Returns a LangChain chat model that mirrors the LlamaIndex LLM configuration,
using the same .env values (api keys, model names, endpoints).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from config import AppSettings

logger = logging.getLogger(__name__)


def get_langchain_llm(config: "AppSettings"):
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

        if provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=llm_config.get("model", "gpt-4o-mini"),
                temperature=llm_config.get("temperature", 0.1),
                api_key=llm_config.get("api_key"),
            )

        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=llm_config.get("model", "claude-3-5-sonnet-20241022"),
                temperature=llm_config.get("temperature", 0.1),
                api_key=llm_config.get("api_key"),
            )

        if provider == "bedrock":
            from langchain_aws import ChatBedrock
            return ChatBedrock(
                model_id=llm_config.get("model", "anthropic.claude-3-sonnet-20240229-v1:0"),
                region_name=llm_config.get("region_name", "us-east-1"),
            )

        if provider == "ollama":
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=llm_config.get("model", "llama3.1:8b"),
                base_url=llm_config.get("base_url", "http://localhost:11434"),
            )

        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=llm_config.get("model", "gemini-2.0-flash"),
                temperature=llm_config.get("temperature", 0.1),
                google_api_key=llm_config.get("api_key"),
            )

        if provider == "azure_openai":
            from langchain_openai import AzureChatOpenAI
            return AzureChatOpenAI(
                azure_deployment=llm_config.get("engine") or llm_config.get("model", "gpt-4o-mini"),
                azure_endpoint=llm_config.get("azure_endpoint"),
                api_key=llm_config.get("api_key"),
                api_version=llm_config.get("api_version", "2024-02-01"),
                temperature=llm_config.get("temperature", 0.1),
            )

        if provider == "groq":
            from langchain_groq import ChatGroq
            return ChatGroq(
                model=llm_config.get("model", "llama-3.3-70b-versatile"),
                temperature=llm_config.get("temperature", 0.1),
                api_key=llm_config.get("api_key"),
            )

        if provider == "fireworks":
            from langchain_fireworks import ChatFireworks
            return ChatFireworks(
                model=llm_config.get("model", "accounts/fireworks/models/llama-v3p3-70b-instruct"),
                temperature=llm_config.get("temperature", 0.1),
                api_key=llm_config.get("api_key"),
            )

        if provider == "vertex_ai":
            from langchain_google_vertexai import ChatVertexAI
            return ChatVertexAI(
                model_name=llm_config.get("model", "gemini-2.0-flash-001"),
                project=llm_config.get("project"),
                location=llm_config.get("location", "us-central1"),
                temperature=llm_config.get("temperature", 0.1),
            )

        if provider == "openai_like":
            from langchain_openai import ChatOpenAI
            # Default 8002/v1 matches the project's vLLM Docker port (avoids clash with backend on 8000).
            api_base = llm_config.get("api_base", "http://localhost:8002/v1")
            return ChatOpenAI(
                model=llm_config.get("model", "local-model"),
                temperature=llm_config.get("temperature", 0.1),
                api_key=llm_config.get("api_key", "local"),
                base_url=api_base,
            )

        if provider == "litellm":
            from langchain_openai import ChatOpenAI
            # LiteLLM proxy default port is 4000.
            api_base = llm_config.get("api_base", "http://localhost:4000/v1")
            return ChatOpenAI(
                model=llm_config.get("model", "local-model"),
                temperature=llm_config.get("temperature", 0.1),
                api_key=llm_config.get("api_key", "local"),
                base_url=api_base,
            )

        if provider == "vllm":
            # vLLM exposes an OpenAI-compatible /v1 endpoint — use ChatOpenAI.
            # VLLM_API_URL is the base server URL (e.g. http://localhost:8002);
            # append /v1 to form the OpenAI-compatible base_url.
            # Port 8002 is the project convention (Docker: 8002:8000; avoids clash with backend on 8000).
            from langchain_openai import ChatOpenAI
            api_url = llm_config.get("api_url", "http://localhost:8002")
            base_url = api_url.rstrip("/") + "/v1"
            return ChatOpenAI(
                model=llm_config.get("model", "facebook/opt-125m"),
                temperature=llm_config.get("temperature", 0.1),
                api_key=llm_config.get("api_key", "local"),
                base_url=base_url,
            )

        if provider == "openrouter":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=llm_config.get("model", "openai/gpt-4o-mini"),
                temperature=llm_config.get("temperature", 0.1),
                api_key=llm_config.get("api_key"),
                base_url="https://openrouter.ai/api/v1",
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
