"""LlamaIndex embedding factory — extracted from factories.py."""
from __future__ import annotations

from typing import Dict, Any, Optional
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


def _make_openai_http_client() -> Optional[Any]:
    """Return an httpx.Client configured for the current environment.

    Set ``OPENAI_VERIFY_SSL=false`` to skip TLS certificate verification.
    This is needed in corporate-proxy environments where the proxy re-signs
    HTTPS traffic with a private CA that Python's certifi bundle does not
    trust (but the traffic itself reaches the target host correctly).
    """
    verify_env = os.getenv("OPENAI_VERIFY_SSL", "true").strip().lower()
    if verify_env in ("false", "0", "no"):
        try:
            import httpx
            logger.info(
                "embedding_factory: OPENAI_VERIFY_SSL=false — creating httpx.Client(verify=False)"
            )
            return httpx.Client(verify=False)
        except ImportError:
            logger.debug("httpx not available — OPENAI_VERIFY_SSL ignored")
    return None


def get_embedding_dimension(
    embedding_kind: Optional[str] = None,
    embedding_model: Optional[str] = None,
    embedding_dimension: Optional[int] = None,
) -> int:
    """Return the embedding vector dimension for the given kind+model combination.

    Resolution order (highest to lowest priority):
    1. ``{KIND}_EMBEDDING_DIMENSION`` env var (e.g. ``OPENAI_EMBEDDING_DIMENSION``)
    2. ``embedding_dimension`` argument (set from generic ``EMBEDDING_DIMENSION`` env var)
    3. Model-name-based inference per kind
    """
    # 1. Per-kind dimension env var takes priority over the generic fallback.
    if embedding_kind:
        _kind_dim = int(os.getenv(f"{embedding_kind.upper()}_EMBEDDING_DIMENSION", "0") or "0")
        if _kind_dim:
            logger.info(f"Using {embedding_kind.upper()}_EMBEDDING_DIMENSION: {_kind_dim}")
            return _kind_dim

    # 2. Generic explicit dimension.
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

    elif embedding_kind in ("huggingface", "sentence_transformer"):
        # EMBEDDING_KIND=huggingface uses HuggingFaceEmbedding (any HuggingFace Hub model).
        # sentence_transformer is the legacy name; kept for COCOINDEX_EMBEDDING_KIND compatibility.
        # Default model all-MiniLM-L6-v2 is 384-dim; common alternatives:
        #   all-mpnet-base-v2 → 768, BAAI/bge-large-en → 1024
        m = (embedding_model or "").lower()
        if "mpnet" in m or "bge-large" in m:
            return 768
        if "bge-base" in m:
            return 768
        return 384  # all-MiniLM-L6-v2 and most small HuggingFace models

    else:
        logger.warning(f"Unknown embedding_kind '{embedding_kind}', defaulting to 768")
        return 768


def create_embedding_model(provider: LLMProvider, config: Dict[str, Any], settings):
    """Create a LlamaIndex embedding model based on configuration."""
    logger.debug(f"[EmbFactory] Creating embedding model with LLM provider: {provider}")

    embedding_kind = getattr(settings, "embedding_kind", None) if settings else None
    embedding_model = getattr(settings, "embedding_model", None) if settings else None
    embedding_dimension = getattr(settings, "embedding_dimension", None) if settings else None

    logger.debug(f"[EmbFactory] From settings - kind: {embedding_kind}, model: {embedding_model}, dim: {embedding_dimension}")

    if embedding_kind:
        logger.info(f"[LlamaIndex] Creating embedding model, embedding_kind: {embedding_kind}")

        if embedding_kind == "openai":
            model_name = embedding_model or "text-embedding-3-small"
            api_key = (
                config.get("api_key") if provider == LLMProvider.OPENAI else None
            ) or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI embeddings require OPENAI_API_KEY")
            _http = _make_openai_http_client()
            # text-embedding-3-* can return shorter vectors (OPENAI_EMBEDDING_DIMENSION /
            # EMBEDDING_DIMENSION, e.g. 1024 for OpenArch); older models have a fixed size
            _dims = {}
            if model_name.startswith("text-embedding-3"):
                _native = 3072 if "large" in model_name else 1536
                _target = get_embedding_dimension("openai", model_name, embedding_dimension)
                if _target and _target != _native:
                    _dims = {"dimensions": _target}
                    logger.info(f"[EmbFactory] OpenAI {model_name}: {_target} dimensions (native {_native})")
            emb = OpenAIEmbedding(
                    model_name=model_name, api_key=api_key, **_dims,
                    **({"http_client": _http} if _http is not None else {}))
            logger.debug(f"[EmbFactory] Created OpenAIEmbedding")
            return emb

        elif embedding_kind == "ollama":
            model_name = embedding_model or "nomic-embed-text"
            base_url = config.get("ollama_base_url", "http://localhost:11434")
            return OllamaEmbedding(model_name=model_name, base_url=base_url)

        elif embedding_kind == "google":
            model_name = embedding_model or "gemini-embedding-001"
            # When EMBEDDING_KIND=google but LLM_PROVIDER is different, config belongs
            # to that other provider — prefer the explicit Google env vars.
            api_key = (
                os.getenv("GOOGLE_API_KEY")
                or os.getenv("GEMINI_API_KEY")
                or (config.get("api_key") if provider in (LLMProvider.GEMINI, LLMProvider.VERTEX_AI) else None)
            )
            if not api_key:
                raise ValueError("Google embeddings require GOOGLE_API_KEY or GEMINI_API_KEY env var")
            # Resolve dim via get_embedding_dimension so {KIND}_EMBEDDING_DIMENSION is respected.
            target_dim = get_embedding_dimension("google", model_name, embedding_dimension)
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
            _http = _make_openai_http_client()
            return AzureOpenAIEmbedding(
                model=model_name,
                deployment_name=deployment_name,
                azure_endpoint=azure_endpoint,
                api_key=api_key,
                api_version=api_version,
                **({"http_client": _http} if _http is not None else {}),
            )

        elif embedding_kind == "vertex":
            model_name = embedding_model or "gemini-embedding-001"
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
            # Resolve dim via get_embedding_dimension so {KIND}_EMBEDDING_DIMENSION is respected.
            target_dim = get_embedding_dimension("vertex", model_name, embedding_dimension)
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
            # The openai SDK defaults encoding_format to "base64" when unset; some
            # OpenAI-compatible gateways (e.g. an Azure APIM proxy) don't support base64
            # and reject the request (often with a misleading "unknown_model" 400). Send
            # "float" by default for maximum compatibility; override via
            # OPENAI_LIKE_EMBEDDING_ENCODING_FORMAT (e.g. "base64" to restore the SDK default).
            encoding_format = os.getenv("OPENAI_LIKE_EMBEDDING_ENCODING_FORMAT", "float")
            # Same custom auth-header support as the openai_like LLM (see llm_factory):
            # gateways like Azure API Management (and native Azure OpenAI) require the key in
            # an `api-key` header rather than `Authorization: Bearer`. Reuses the same
            # OPENAI_LIKE_API_KEY_HEADER env var so setting it once covers LLM + embeddings.
            extra_headers = {}
            api_key_header = os.getenv("OPENAI_LIKE_API_KEY_HEADER")
            if api_key_header:
                extra_headers[api_key_header] = api_key
            return OpenAILikeEmbedding(
                model_name=model_name,
                api_base=api_base,
                api_key=api_key,
                additional_kwargs={"encoding_format": encoding_format},
                default_headers=extra_headers or None,
            )

        elif embedding_kind == "litellm":
            model_name = embedding_model or os.getenv("LITELLM_EMBEDDING_MODEL", "text-embedding-3-small")
            # Only use api_base when explicitly configured.
            # Without it, LiteLLMEmbedding calls litellm directly (no proxy required — Windows-safe).
            # Set LITELLM_EMBEDDING_API_BASE or LITELLM_API_BASE only when routing through a proxy server.
            api_base = os.getenv("LITELLM_EMBEDDING_API_BASE") or os.getenv("LITELLM_API_BASE") or None
            api_key = os.getenv("LITELLM_API_KEY") or None
            kwargs: dict = {"model_name": model_name}
            if api_base:
                kwargs["api_base"] = api_base
            if api_key:
                kwargs["api_key"] = api_key
            return LiteLLMEmbedding(**kwargs)

        elif embedding_kind in ("huggingface", "sentence_transformer"):
            try:
                from llama_index.embeddings.huggingface import HuggingFaceEmbedding  # noqa: PLC0415
            except ImportError:
                raise ImportError(
                    "EMBEDDING_KIND=huggingface requires llama-index-embeddings-huggingface "
                    "and sentence-transformers. Install with: "
                    'uv pip install -e ".[huggingface]"  '
                    "# or: uv pip install llama-index-embeddings-huggingface sentence-transformers"
                ) from None
            model_name = embedding_model or "all-MiniLM-L6-v2"
            logger.info("huggingface LI embedding: model=%s", model_name)
            return HuggingFaceEmbedding(model_name=model_name)

        else:
            logger.warning(f"Unknown embedding_kind '{embedding_kind}', using provider default")

    # Provider defaults
    logger.info(f"[EmbFactory] Using provider defaults for {provider}")
    if provider in (LLMProvider.OPENAI, LLMProvider.AZURE_OPENAI):
        if provider == LLMProvider.AZURE_OPENAI:
            model_name = embedding_model or "text-embedding-3-small"
            emb = AzureOpenAIEmbedding(
                model=model_name,
                azure_endpoint=config["azure_endpoint"],
                api_key=config["api_key"],
                api_version=config.get("api_version", "2024-02-01"),
            )
            logger.info(f"[EmbFactory] Returning AzureOpenAIEmbedding: {type(emb).__name__}")
            return emb
        model_name = embedding_model or "text-embedding-3-small"
        emb = OpenAIEmbedding(model_name=model_name, api_key=config.get("api_key"))
        logger.info(f"[EmbFactory] Returning OpenAIEmbedding (provider default): {type(emb).__name__}")
        return emb

    elif provider == LLMProvider.OLLAMA:
        model_name = embedding_model or "nomic-embed-text"
        base_url = config.get("base_url", "http://localhost:11434")
        return OllamaEmbedding(model_name=model_name, base_url=base_url)

    elif provider == LLMProvider.GEMINI:
        model_name = embedding_model or "gemini-embedding-001"
        target_dim = get_embedding_dimension("google", model_name, embedding_dimension)
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
        model_name = embedding_model or "gemini-embedding-001"
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
        target_dim = get_embedding_dimension("vertex", model_name, embedding_dimension)
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
