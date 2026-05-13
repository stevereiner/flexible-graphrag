"""LlamaIndex LLM factory — extracted from factories.py.

Provides :func:`create_llm` and helper utilities.  ``factories.py`` imports from
here so all existing call-sites continue to work without changes.
"""
from __future__ import annotations

from typing import Dict, Any
import logging
import os

from llama_index.llms.openai import OpenAI
from llama_index.llms.openai_like import OpenAILike
from llama_index.llms.litellm import LiteLLM
from llama_index.llms.openrouter import OpenRouter
from llama_index.core.types import PydanticProgramMode
from llama_index.llms.ollama import Ollama
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.anthropic import Anthropic
from llama_index.llms.bedrock_converse import BedrockConverse
from llama_index.llms.groq import Groq
from llama_index.llms.fireworks import Fireworks
from llama_index.core.base.llms.types import ChatResponse, MessageRole
from llama_index.llms.openai.utils import to_openai_message_dicts

from config import LLMProvider

logger = logging.getLogger(__name__)


class _FireworksStreaming(Fireworks):
    """Fireworks subclass that uses streaming mode for _achat.

    The Fireworks non-streaming API hard-caps max_tokens at 4096. Streaming
    removes this limit (same token budget, just delivered incrementally).
    We reassemble the full response so callers see no difference.
    """

    async def _achat(self, messages, **kwargs) -> ChatResponse:
        aclient = self._get_aclient()
        message_dicts = to_openai_message_dicts(messages, model=self.model)
        model_kwargs = self._get_model_kwargs(**kwargs)

        if self.reuse_client:
            stream = await aclient.chat.completions.create(
                messages=message_dicts, stream=True, **model_kwargs
            )
        else:
            async with aclient:
                stream = await aclient.chat.completions.create(
                    messages=message_dicts, stream=True, **model_kwargs
                )

        content_parts = []
        tool_arg_parts = []
        finish_reason = None
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta:
                if delta.content:
                    content_parts.append(delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.function and tc.function.arguments:
                            tool_arg_parts.append(tc.function.arguments)
            if chunk.choices and chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

        assembled = "".join(content_parts) or "".join(tool_arg_parts)

        from llama_index.core.llms import ChatMessage as _OutMsg
        message = _OutMsg(role=MessageRole.ASSISTANT, content=assembled)
        return ChatResponse(message=message, raw={"finish_reason": finish_reason})


def _resolve_pydantic_program_mode(config: Dict[str, Any]) -> PydanticProgramMode:
    """Resolve PydanticProgramMode from config or LLM_EXTRACTION_MODE env var."""
    mode_str = (
        config.get("extraction_mode")
        or os.getenv("LLM_EXTRACTION_MODE", "function")
    ).lower()

    if mode_str == "function":
        logger.info("LLM extraction mode: function (tool/function calling)")
        return PydanticProgramMode.FUNCTION
    elif mode_str in ("json_schema", "auto"):
        logger.info(f"LLM extraction mode: {mode_str} (structured output / JSON schema)")
        return PydanticProgramMode.DEFAULT
    else:
        logger.warning(
            "Unknown LLM_EXTRACTION_MODE '%s'; falling back to 'function'. "
            "Valid values: function, json_schema, auto.",
            mode_str,
        )
        return PydanticProgramMode.FUNCTION


def create_llm(provider: LLMProvider, config: Dict[str, Any]):
    """Create a LlamaIndex LLM instance based on provider and configuration."""
    logger.info(f"Creating LLM with provider: {provider}")

    if provider == LLMProvider.OPENAI:
        return OpenAI(
            model=config.get("model", "gpt-4o-mini"),
            temperature=config.get("temperature", 0.1),
            api_key=config.get("api_key"),
            max_tokens=config.get("max_tokens", 4000),
            timeout=config.get("timeout", 120.0),
            pydantic_program_mode=_resolve_pydantic_program_mode(config),
        )

    elif provider == LLMProvider.OLLAMA:
        model = config.get("model", "llama3.1:8b")
        base_url = config.get("base_url", "http://localhost:11434")
        timeout = config.get("timeout", 900.0)
        logger.info(f"Configuring Ollama LLM - Model: {model}, Base URL: {base_url}, Timeout: {timeout}s")
        return Ollama(
            model=model,
            base_url=base_url,
            temperature=config.get("temperature", 0.1),
            request_timeout=timeout,
        )

    elif provider == LLMProvider.GEMINI:
        llm = GoogleGenAI(
            model=config.get("model", "gemini-2.5-flash"),
            api_key=config.get("api_key"),
            temperature=config.get("temperature", 0.1),
            pydantic_program_mode=_resolve_pydantic_program_mode(config),
        )
        llm._generation_config["automatic_function_calling"] = {"disable": True}
        return llm

    elif provider == LLMProvider.AZURE_OPENAI:
        return AzureOpenAI(
            engine=config["engine"],
            model=config.get("model", "gpt-4"),
            temperature=config.get("temperature", 0.1),
            azure_endpoint=config["azure_endpoint"],
            api_key=config["api_key"],
            api_version=config.get("api_version", "2024-02-01"),
            timeout=config.get("timeout", 120.0),
            pydantic_program_mode=_resolve_pydantic_program_mode(config),
        )

    elif provider == LLMProvider.ANTHROPIC:
        return Anthropic(
            model=config.get("model", "claude-sonnet-4-5-20250929"),
            api_key=config.get("api_key"),
            temperature=config.get("temperature", 0.1),
            timeout=config.get("timeout", 120.0),
        )

    elif provider == LLMProvider.VERTEX_AI:
        project = config.get("project")
        if not project:
            raise ValueError("Vertex AI requires 'project' parameter (VERTEX_AI_PROJECT)")
        location = config.get("location", "us-central1")
        model = config.get("model", "gemini-2.0-flash-001")
        credentials_path = config.get("credentials_path")
        logger.info(f"Configuring Vertex AI - Project: {project}, Location: {location}, Model: {model}")
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        os.environ["GOOGLE_CLOUD_PROJECT"] = project
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
        llm = GoogleGenAI(
            model=model,
            temperature=config.get("temperature", 0.1),
            vertexai_config={"project": project, "location": location},
            pydantic_program_mode=_resolve_pydantic_program_mode(config),
        )
        llm._generation_config["automatic_function_calling"] = {"disable": True}
        return llm

    elif provider == LLMProvider.BEDROCK:
        region_name = config.get("region_name", "us-east-1")
        model = config.get("model", "anthropic.claude-3-5-sonnet-20241022-v2:0")
        logger.info(f"Configuring Bedrock LLM - Region: {region_name}, Model: {model}")
        aws_credentials: Dict[str, Any] = {}
        for key in ("aws_access_key_id", "aws_secret_access_key", "aws_session_token", "profile_name"):
            if config.get(key):
                aws_credentials[key] = config[key]
        bedrock_params: Dict[str, Any] = {
            "model": model,
            "region_name": region_name,
            "temperature": config.get("temperature", 0.1),
            "timeout": config.get("timeout", 120.0),
            **aws_credentials,
        }
        bedrock_params["pydantic_program_mode"] = _resolve_pydantic_program_mode(config)
        return BedrockConverse(**bedrock_params)

    elif provider == LLMProvider.GROQ:
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("Groq requires 'api_key' parameter (GROQ_API_KEY)")
        model = config.get("model", "llama-3.3-70b-versatile")
        _GROQ_CONTEXT = {
            "openai/gpt-oss-20b": (131072, 65536),
            "openai/gpt-oss-120b": (131072, 65536),
            "llama-3.3-70b-versatile": (131072, 32768),
            "llama-3.1-8b-instant": (131072, 8192),
        }
        ctx_window, default_max = _GROQ_CONTEXT.get(model, (131072, 32768))
        max_tokens = config.get("max_tokens", default_max)
        logger.info(f"Groq context_window={ctx_window}, max_tokens={max_tokens} (model={model})")
        return Groq(
            model=model,
            api_key=api_key,
            temperature=config.get("temperature", 0.1),
            context_window=ctx_window,
            max_tokens=max_tokens,
            timeout=config.get("timeout", 120.0),
            pydantic_program_mode=_resolve_pydantic_program_mode(config),
        )

    elif provider == LLMProvider.FIREWORKS:
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("Fireworks requires 'api_key' parameter (FIREWORKS_API_KEY)")
        model = config.get("model", "accounts/fireworks/models/llama-v3p3-70b-instruct")
        is_fc = config.get("is_function_calling", True)
        max_tokens = config.get("max_tokens", 16384)
        logger.info(f"Fireworks max_tokens={max_tokens} streaming, is_function_calling={is_fc}")
        return _FireworksStreaming(
            model=model,
            api_key=api_key,
            temperature=config.get("temperature", 0.1),
            max_tokens=max_tokens,
            is_function_calling=is_fc,
            pydantic_program_mode=_resolve_pydantic_program_mode(config),
        )

    elif provider == LLMProvider.OPENAI_LIKE:
        api_base = config.get("api_base", "http://localhost:8000/v1")
        model = config.get("model", "local-model")
        is_fc = config.get("is_function_calling_model", True)
        is_chat = config.get("is_chat_model", True)
        context_window = config.get("context_window", 4096)
        logger.info(f"Configuring OpenAI-Like LLM - Model: {model}, API Base: {api_base}, function_calling={is_fc}")
        return OpenAILike(
            model=model,
            api_base=api_base,
            api_key=config.get("api_key", "local"),
            temperature=config.get("temperature", 0.1),
            timeout=config.get("timeout", 120.0),
            context_window=context_window,
            is_chat_model=is_chat,
            is_function_calling_model=is_fc,
            pydantic_program_mode=_resolve_pydantic_program_mode(config) if is_fc else PydanticProgramMode.DEFAULT,
        )

    elif provider == LLMProvider.VLLM:
        model = config.get("model", "Qwen/Qwen2.5-7B-Instruct")
        vllm_mode = config.get("vllm_mode", "server")  # "server" | "inprocess"
        is_chat = config.get("is_chat_model", True)
        is_fc = config.get("is_function_calling_model", False)
        context_window = config.get("context_window", 8192)
        if vllm_mode == "inprocess":
            # vLLM in-process Python package (Linux/macOS only — requires: uv pip install vllm)
            # Set VLLM_MODE=inprocess in .env to activate this path.
            # Lazy import: llama-index-llms-vllm is installed but the underlying vllm CUDA package
            # is Linux-only — importing it at module level would fail on startup on Windows.
            from llama_index.llms.vllm import Vllm  # noqa: PLC0415
            api_url = config.get("api_url", "http://localhost:8002")
            logger.info("Configuring vLLM in-process - Model: %s, API URL: %s", model, api_url)
            return Vllm(
                model=model,
                api_url=api_url,
                temperature=config.get("temperature", 0.1),
                max_new_tokens=config.get("max_new_tokens", 2048),
                is_chat_model=is_chat,
            )
        else:
            # vLLM server mode — VLLM_MODE=server (default)
            # vllm.yaml uses vllm/vllm-openai:latest which exposes an OpenAI-compatible /v1 endpoint.
            # llama-index-llms-vllm also provides VllmServer, but its docstring says:
            #   "If using the OpenAI-API vLLM server, please see the OpenAILike LLM class."
            # VllmServer targets the non-OpenAI /generate endpoint (plain vllm/vllm image only).
            api_base = config.get("api_base", "http://localhost:8002/v1")
            logger.info("Configuring vLLM via OpenAI-compatible API - Model: %s, API Base: %s, function_calling=%s", model, api_base, is_fc)
            return OpenAILike(
                model=model,
                api_base=api_base,
                api_key=config.get("api_key", "local"),
                temperature=config.get("temperature", 0.1),
                timeout=config.get("timeout", 120.0),
                context_window=context_window,
                is_chat_model=is_chat,
                is_function_calling_model=is_fc,
                pydantic_program_mode=_resolve_pydantic_program_mode(config) if is_fc else PydanticProgramMode.DEFAULT,
            )

    elif provider == LLMProvider.LITELLM:
        import litellm
        litellm.drop_params = True
        model = config.get("model", "gpt-4o-mini")
        api_base = config.get("api_base", "http://localhost:4000")
        logger.info(f"Configuring LiteLLM - Model: {model}, API Base: {api_base}")
        return LiteLLM(
            model=model,
            api_base=api_base,
            api_key=config.get("api_key", "local"),
            temperature=config.get("temperature", 0.1),
            pydantic_program_mode=_resolve_pydantic_program_mode(config),
        )

    elif provider == LLMProvider.OPENROUTER:
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("OpenRouter requires 'api_key' parameter (OPENROUTER_API_KEY)")
        model = config.get("model", "openai/gpt-4o-mini")
        logger.info(f"Configuring OpenRouter LLM - Model: {model}")
        return OpenRouter(
            model=model,
            api_key=api_key,
            temperature=config.get("temperature", 0.1),
            context_window=config.get("context_window", 128000),
            max_tokens=config.get("max_tokens", 16384),
            pydantic_program_mode=_resolve_pydantic_program_mode(config),
        )

    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
