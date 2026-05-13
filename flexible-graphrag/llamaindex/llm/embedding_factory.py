"""LlamaIndex embedding factory — extracted from factories.py."""
from __future__ import annotations

from typing import Dict, Any
import logging
import os

from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.embeddings.bedrock import BedrockEmbedding
from llama_index.embeddings.fireworks import FireworksEmbedding
from llama_index.embeddings.litellm import LiteLLMEmbedding
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from google.genai.types import EmbedContentConfig

from config import LLMProvider

logger = logging.getLogger(__name__)


def get_embedding_dimension(
    embedding_kind: str = None,
    embedding_model: str = None,
    embedding_dimension: int = None,
) -> int:
    """Return the embedding vector dimension for the given kind+model combination."""
    if embedding_dimension:
        logger.info(f"Using explicit embedding dimension: {embedding_dimension}")
        return embedding_dimension

    if not embedding_kind:
        logger.warning("No embedding_kind specified, defaulting to 1536")
        return 1536

    embedding_kind = embedding_kind.lower()

    if embedding_kind == "openai":
        if "text-embedding-3-large" in (embedding_model or ""):
            return 3072
        return 1536

    elif embedding_kind == "ollama":
        if "mxbai-embed-large" in (embedding_model or ""):
            return 1024
        elif "nomic-embed-text" in (embedding_model or ""):
            return 768
        elif "all-minilm" in (embedding_model or ""):
            return 384
        logger.warning(f"Unknown Ollama model {embedding_model}, defaulting to 768")
        return 768

    elif embedding_kind == "google":
        # gemini-embedding-2-preview / gemini-embedding-001 → 768 dims
        # Legacy text-embedding-001 → 768 dims; text-embedding-004 → 768 dims
        # All current Google embedding models are 768 dims (output_dimensionality may
        # reduce further, but the native dimension is 768).
        return 768

    elif embedding_kind == "azure":
        if "text-embedding-3-large" in (embedding_model or ""):
            return 3072
        return 1536

    elif embedding_kind == "vertex":
        return 768

    elif embedding_kind == "bedrock":
        if "amazon.titan-embed-text" in (embedding_model or ""):
            return 1024 if "v2" in (embedding_model or "") else 1536
        elif "cohere.embed" in (embedding_model or ""):
            return 1024
        return 1024

    elif embedding_kind == "fireworks":
        return 768

    elif embedding_kind in ("openai_like", "litellm"):
        m = (embedding_model or "").lower()
        if "nomic" in m:
            return 768
        elif "bge" in m:
            return 1024
        elif "3-small" in m or "ada" in m:
            return 1536
        elif "3-large" in m:
            return 3072
        logger.warning(f"Unknown model for {embedding_kind} embeddings, defaulting to 1536")
        return 1536

    else:
        logger.warning(f"Unknown embedding_kind {embedding_kind}, defaulting to 768")
        return 768


def create_embedding_model(provider: LLMProvider, config: Dict[str, Any], settings):
    """Create a LlamaIndex embedding model based on configuration."""
    logger.info(f"Creating embedding model with LLM provider: {provider}")

    embedding_kind = getattr(settings, "embedding_kind", None)
    embedding_model = getattr(settings, "embedding_model", None)
    embedding_dimension = getattr(settings, "embedding_dimension", None)

    logger.info(f"Embedding kind: {embedding_kind}, Model: {embedding_model}, Dimension: {embedding_dimension}")

    if embedding_kind:
        logger.info(f"Using explicit embedding_kind: {embedding_kind}")

        if embedding_kind == "openai":
            model_name = embedding_model or "text-embedding-3-small"
            api_key = (
                config.get("api_key") if provider == LLMProvider.OPENAI else None
            ) or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI embeddings require OPENAI_API_KEY")
            return OpenAIEmbedding(model_name=model_name, api_key=api_key)

        elif embedding_kind == "ollama":
            model_name = embedding_model or "nomic-embed-text"
            base_url = config.get("ollama_base_url", "http://localhost:11434")
            return OllamaEmbedding(model_name=model_name, base_url=base_url)

        elif embedding_kind == "google":
            model_name = embedding_model or "gemini-embedding-2-preview"
            # When EMBEDDING_KIND=google but LLM_PROVIDER is different, config belongs
            # to that other provider — prefer the explicit Google env vars.
            api_key = (
                os.getenv("GOOGLE_API_KEY")
                or os.getenv("GEMINI_API_KEY")
                or (config.get("api_key") if provider in (LLMProvider.GEMINI, LLMProvider.VERTEX_AI) else None)
            )
            if not api_key:
                raise ValueError("Google embeddings require GOOGLE_API_KEY or GEMINI_API_KEY env var")
            # gemini-embedding-2-preview native dim is 3072. Always pass output_dimensionality
            # to truncate to 768 (our dimension table value) so Qdrant/other stores that
            # create a 768-dim collection receive matching vectors.
            # Explicit EMBEDDING_DIMENSION in env overrides this default.
            target_dim = embedding_dimension or 768
            params: Dict[str, Any] = {
                "model_name": model_name,
                "api_key": api_key,
                # gemini-embedding-2-preview only supports 1 content per embed_content call;
                # batch size > 1 causes the API to return 1 embedding for N texts (zip
                # truncation → KeyError in id_to_embed_map).
                "embed_batch_size": 1,
                "embedding_config": EmbedContentConfig(output_dimensionality=target_dim),
            }
            return GoogleGenAIEmbedding(**params)

        elif embedding_kind == "azure":
            model_name = embedding_model or "text-embedding-3-small"
            if provider == LLMProvider.AZURE_OPENAI:
                azure_endpoint = config.get("azure_endpoint")
                api_key = config.get("api_key")
                api_version = config.get("api_version", "2024-02-01")
            else:
                azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                api_key = os.getenv("AZURE_OPENAI_API_KEY")
                api_version = os.getenv("AZURE_EMBEDDING_API_VERSION") or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
            if not azure_endpoint or not api_key:
                raise ValueError("Azure embeddings require AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY")
            deployment_name = os.getenv("AZURE_EMBEDDING_DEPLOYMENT") or model_name
            return AzureOpenAIEmbedding(
                model=model_name,
                deployment_name=deployment_name,
                azure_endpoint=azure_endpoint,
                api_key=api_key,
                api_version=api_version,
            )

        elif embedding_kind == "vertex":
            model_name = embedding_model or "gemini-embedding-2-preview"
            # When EMBEDDING_KIND=vertex but LLM_PROVIDER is different, config belongs
            # to that other provider — prefer explicit Vertex env vars.
            project = os.getenv("VERTEX_AI_PROJECT") or (config.get("project") if provider == LLMProvider.VERTEX_AI else None)
            location = os.getenv("VERTEX_AI_LOCATION") or (config.get("location") if provider == LLMProvider.VERTEX_AI else None) or "us-central1"
            credentials_path = (
                os.getenv("VERTEX_AI_CREDENTIALS_PATH")
                or (config.get("credentials_path") if provider == LLMProvider.VERTEX_AI else None)
            )
            if credentials_path:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
            if project:
                os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
                os.environ["GOOGLE_CLOUD_PROJECT"] = project
                os.environ["GOOGLE_CLOUD_LOCATION"] = location
            # gemini-embedding-2-preview native dim is 3072. Always pass output_dimensionality
            # to truncate to 768 (our dimension table value) so Qdrant/other stores that
            # create a 768-dim collection receive matching vectors.
            # Explicit EMBEDDING_DIMENSION in env overrides this default.
            target_dim = embedding_dimension or 768
            params: Dict[str, Any] = {
                "model_name": model_name,
                # gemini-embedding-2-preview only supports 1 content per embed_content call.
                "embed_batch_size": 1,
                "embedding_config": EmbedContentConfig(output_dimensionality=target_dim),
            }
            if project:
                params["vertexai_config"] = {"project": project, "location": location}
            return GoogleGenAIEmbedding(**params)

        elif embedding_kind == "bedrock":
            model_name = embedding_model or "amazon.titan-embed-text-v2:0"
            region_name = config.get("region_name") or os.getenv("BEDROCK_REGION", "us-east-1")
            aws_creds: Dict[str, Any] = {}
            for k, env in (
                ("aws_access_key_id", "BEDROCK_ACCESS_KEY"),
                ("aws_secret_access_key", "BEDROCK_SECRET_KEY"),
                ("aws_session_token", "BEDROCK_SESSION_TOKEN"),
                ("profile_name", "BEDROCK_PROFILE_NAME"),
            ):
                val = config.get(k) or os.getenv(env)
                if val:
                    aws_creds[k] = val
            return BedrockEmbedding(model_name=model_name, region_name=region_name, **aws_creds)

        elif embedding_kind == "fireworks":
            model_name = embedding_model or "nomic-ai/nomic-embed-text-v1.5"
            # When EMBEDDING_KIND=fireworks but LLM_PROVIDER is different, config
            # belongs to that other provider — always prefer the env var.
            api_key = os.getenv("FIREWORKS_API_KEY") or config.get("api_key")
            if not api_key:
                raise ValueError("Fireworks embeddings require FIREWORKS_API_KEY")
            return FireworksEmbedding(model_name=model_name, api_key=api_key)

        elif embedding_kind == "openai_like":
            model_name = embedding_model or os.getenv("OPENAI_LIKE_EMBEDDING_MODEL", "local-embedding-model")
            api_base = os.getenv("OPENAI_LIKE_EMBEDDING_API_BASE") or os.getenv("OPENAI_LIKE_API_BASE", "http://localhost:8000/v1")
            api_key = os.getenv("OPENAI_LIKE_API_KEY", "fake")
            return OpenAILikeEmbedding(model_name=model_name, api_base=api_base, api_key=api_key)

        elif embedding_kind == "litellm":
            model_name = embedding_model or os.getenv("LITELLM_EMBEDDING_MODEL", "text-embedding-3-small")
            api_base = os.getenv("LITELLM_EMBEDDING_API_BASE") or os.getenv("LITELLM_API_BASE", "http://localhost:4000")
            api_key = os.getenv("LITELLM_API_KEY", "local")
            return LiteLLMEmbedding(model_name=model_name, api_base=api_base, api_key=api_key)

        else:
            logger.warning(f"Unknown embedding_kind '{embedding_kind}', using provider default")

    # Provider defaults
    if provider in (LLMProvider.OPENAI, LLMProvider.AZURE_OPENAI):
        if provider == LLMProvider.AZURE_OPENAI:
            model_name = embedding_model or "text-embedding-3-small"
            return AzureOpenAIEmbedding(
                model=model_name,
                azure_endpoint=config["azure_endpoint"],
                api_key=config["api_key"],
                api_version=config.get("api_version", "2024-02-01"),
            )
        model_name = embedding_model or "text-embedding-3-small"
        return OpenAIEmbedding(model_name=model_name, api_key=config.get("api_key"))

    elif provider == LLMProvider.OLLAMA:
        model_name = embedding_model or "nomic-embed-text"
        base_url = config.get("base_url", "http://localhost:11434")
        return OllamaEmbedding(model_name=model_name, base_url=base_url)

    elif provider == LLMProvider.GEMINI:
        model_name = embedding_model or "gemini-embedding-2-preview"
        target_dim = embedding_dimension or 768
        params: Dict[str, Any] = {
            "model_name": model_name,
            "api_key": config.get("api_key"),
            # gemini-embedding-2-preview only supports 1 content per embed_content call;
            # batch size > 1 causes the API to return 1 embedding for N texts (zip
            # truncation -> KeyError in id_to_embed_map).
            "embed_batch_size": 1,
            "embedding_config": EmbedContentConfig(output_dimensionality=target_dim),
        }
        return GoogleGenAIEmbedding(**params)

    elif provider == LLMProvider.ANTHROPIC:
        model_name = embedding_model or "nomic-embed-text"
        base_url = config.get("ollama_base_url") or config.get("base_url", "http://localhost:11434")
        return OllamaEmbedding(model_name=model_name, base_url=base_url)

    elif provider == LLMProvider.VERTEX_AI:
        model_name = embedding_model or "gemini-embedding-2-preview"
        project = config.get("project")
        if not project:
            raise ValueError("Vertex AI embeddings require 'project' parameter")
        location = config.get("location", "us-central1")
        credentials_path = config.get("credentials_path")
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        os.environ["GOOGLE_CLOUD_PROJECT"] = project
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
        target_dim = embedding_dimension or 768
        params = {
            "model_name": model_name,
            # gemini-embedding-2-preview only supports 1 content per embed_content call;
            # batch size > 1 causes the API to return 1 embedding for N texts (zip
            # truncation -> KeyError in id_to_embed_map).
            "embed_batch_size": 1,
            "vertexai_config": {"project": project, "location": location},
            "embedding_config": EmbedContentConfig(output_dimensionality=target_dim),
        }
        return GoogleGenAIEmbedding(**params)

    elif provider == LLMProvider.BEDROCK:
        model_name = embedding_model or "amazon.titan-embed-text-v2:0"
        region_name = config.get("region_name", "us-east-1")
        aws_creds = {k: v for k, v in config.items() if k in ("aws_access_key_id", "aws_secret_access_key", "aws_session_token", "profile_name") and v}
        return BedrockEmbedding(model_name=model_name, region_name=region_name, **aws_creds)

    elif provider == LLMProvider.GROQ:
        model_name = embedding_model or "nomic-embed-text"
        base_url = config.get("ollama_base_url") or config.get("base_url", "http://localhost:11434")
        return OllamaEmbedding(model_name=model_name, base_url=base_url)

    elif provider == LLMProvider.FIREWORKS:
        model_name = embedding_model or "nomic-ai/nomic-embed-text-v1.5"
        api_key = config.get("api_key") or os.getenv("FIREWORKS_API_KEY")
        if not api_key:
            raise ValueError("Fireworks embeddings require 'api_key' parameter or FIREWORKS_API_KEY env var")
        return FireworksEmbedding(model_name=model_name, api_key=api_key)

    else:
        model_name = embedding_model or "nomic-embed-text"
        base_url = config.get("ollama_base_url") or config.get("base_url", "http://localhost:11434")
        logger.warning(f"No embedding implementation for {provider}, using Ollama default: {model_name}")
        return OllamaEmbedding(model_name=model_name, base_url=base_url)
