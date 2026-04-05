from typing import Dict, Any
import logging
import os

from llama_index.llms.openai import OpenAI
from llama_index.llms.openai_like import OpenAILike
from llama_index.llms.vllm import Vllm
from llama_index.llms.litellm import LiteLLM
from llama_index.llms.openrouter import OpenRouter
from llama_index.core.types import PydanticProgramMode
from llama_index.embeddings.litellm import LiteLLMEmbedding
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.llms.anthropic import Anthropic
# Vertex removed - use GoogleGenAI with vertexai_config instead
from llama_index.llms.bedrock_converse import BedrockConverse
from llama_index.llms.groq import Groq
from llama_index.llms.fireworks import Fireworks
from llama_index.core.base.llms.types import ChatResponse, MessageRole
from llama_index.llms.openai.utils import to_openai_message_dicts

from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
# Vertex embedding removed - use GoogleGenAIEmbedding with vertexai_config instead
from llama_index.embeddings.bedrock import BedrockEmbedding
from llama_index.embeddings.fireworks import FireworksEmbedding
from google.genai.types import EmbedContentConfig
from llama_index.vector_stores.neo4jvector import Neo4jVectorStore
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.vector_stores.elasticsearch import ElasticsearchStore, AsyncBM25Strategy
from llama_index.vector_stores.opensearch import OpensearchVectorStore, OpensearchVectorClient
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.graph_stores.falkordb import FalkorDBPropertyGraphStore
from llama_index.graph_stores.memgraph import MemgraphPropertyGraphStore
from llama_index.graph_stores.nebula.nebula_property_graph import (
    NebulaPropertyGraphStore,
)
from llama_index.graph_stores.neptune.analytics_property_graph import (
    NeptuneAnalyticsPropertyGraphStore,
)
from llama_index.graph_stores.neptune.database_property_graph import (
    NeptuneDatabasePropertyGraphStore,
)

from llama_index.graph_stores.arcadedb import ArcadeDBPropertyGraphStore

from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.storage.docstore import SimpleDocumentStore
from qdrant_client import QdrantClient, AsyncQdrantClient

from config import LLMProvider, VectorDBType, GraphDBType, SearchDBType

# Import Neptune wrapper from separate module
from llamaindex.graph.falkordb_param_patch import ensure_falkordb_stringify_patch
from llamaindex.graph.neptune_database_wrapper import NeptuneDatabaseNoSummaryWrapper


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

        # Reassemble streamed chunks into a single response.
        # DynamicLLMPathExtractor sets _custom_is_function_calling=False so the model
        # should return plain text content, but defensively also capture tool_call
        # argument text in case the model still returns a function call delta.
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

        # Prefer plain text content; fall back to tool_call arguments if content is empty
        assembled = "".join(content_parts) or "".join(tool_arg_parts)

        from llama_index.core.llms import ChatMessage as _OutMsg
        message = _OutMsg(role=MessageRole.ASSISTANT, content=assembled)
        return ChatResponse(message=message, raw={"finish_reason": finish_reason})

logger = logging.getLogger(__name__)


def get_embedding_dimension(embedding_kind: str = None, embedding_model: str = None, embedding_dimension: int = None) -> int:
    """
    Get the embedding dimension based on embedding kind and model.
    Independent of LLM provider - embeddings can be configured separately.
    
    Args:
        embedding_kind: Type of embedding (openai, ollama, google, azure)
        embedding_model: Specific model name
        embedding_dimension: Explicit dimension override (takes precedence)
    
    Returns:
        Embedding dimension
    """
    # If explicit dimension provided, use it
    if embedding_dimension:
        logger.info(f"Using explicit embedding dimension: {embedding_dimension}")
        return embedding_dimension
    
    # Determine dimension based on embedding kind and model
    if not embedding_kind:
        logger.warning("No embedding_kind specified, defaulting to 1536")
        return 1536
    
    embedding_kind = embedding_kind.lower()
    
    if embedding_kind == "openai":
        # OpenAI embedding dimensions by model
        if "text-embedding-3-large" in embedding_model:
            return 3072
        elif "text-embedding-3-small" in embedding_model:
            return 1536
        elif "text-embedding-ada-002" in embedding_model:
            return 1536
        else:
            return 1536  # Default for OpenAI
    
    elif embedding_kind == "ollama":
        # Ollama embedding dimensions by model
        if "mxbai-embed-large" in embedding_model:
            return 1024
        elif "nomic-embed-text" in embedding_model:
            return 768
        elif "all-minilm" in embedding_model:
            return 384
        else:
            logger.warning(f"Unknown Ollama model {embedding_model}, defaulting to 768 (nomic-embed-text)")
            return 768
    
    elif embedding_kind == "google":
        # Google Gemini embeddings support 768, 1536, or 3072 dimensions
        # Default to 1536 for text-embedding-001
        return 1536  # Default for Google embeddings
    
    elif embedding_kind == "azure":
        # Azure OpenAI uses same models as OpenAI
        if "text-embedding-3-large" in embedding_model:
            return 3072
        elif "text-embedding-3-small" in embedding_model:
            return 1536
        else:
            return 1536  # Default for Azure OpenAI
    
    elif embedding_kind == "vertex":
        # Vertex AI uses Google's embedding models
        # text-embedding-004 (default): 768 dimensions
        # text-multilingual-embedding-002: 768 dimensions
        return 768  # Default for Vertex AI embeddings
    
    elif embedding_kind == "bedrock":
        # Amazon Bedrock embedding dimensions by model
        if "amazon.titan-embed-text" in embedding_model:
            if "v2" in embedding_model:
                return 1024  # Titan Embeddings v2
            return 1536  # Titan Embeddings v1
        elif "cohere.embed" in embedding_model:
            if "multilingual" in embedding_model:
                return 1024  # Cohere Embed Multilingual
            return 1024  # Cohere Embed English
        else:
            return 1024  # Default for Bedrock
    
    elif embedding_kind == "fireworks":
        # Fireworks AI embedding dimensions
        if "nomic-ai/nomic-embed-text-v1.5" in embedding_model:
            return 768  # Nomic Embed Text v1.5
        elif "nomic-ai/nomic-embed-text-v1" in embedding_model:
            return 768  # Nomic Embed Text v1
        elif "WhereIsAI/UAE-Large-V1" in embedding_model:
            return 1024  # UAE Large V1
        else:
            return 768  # Default for Fireworks (nomic-embed-text)

    elif embedding_kind in ("openai_like", "litellm"):
        # OpenAI-compatible endpoints (OpenAILikeEmbedding) and LiteLLM proxy (LiteLLMEmbedding).
        # Dimension depends on the model served. Set EMBEDDING_DIMENSION explicitly for unknown models.
        if embedding_model and "nomic" in embedding_model.lower():
            return 768
        elif embedding_model and "bge" in embedding_model.lower():
            return 1024
        elif embedding_model and ("3-small" in embedding_model or "ada" in embedding_model):
            return 1536
        elif embedding_model and "3-large" in embedding_model:
            return 3072
        else:
            logger.warning(f"Unknown model for {embedding_kind} embeddings, defaulting to 1536. Set EMBEDDING_DIMENSION explicitly.")
            return 1536

    else:
        # Default to Ollama nomic-embed-text for unknown embedding kinds
        logger.warning(f"Unknown embedding_kind {embedding_kind}, defaulting to Ollama nomic-embed-text (768)")
        return 768

def _resolve_pydantic_program_mode(config: Dict[str, Any]) -> PydanticProgramMode:
    """Resolve PydanticProgramMode from config or LLM_EXTRACTION_MODE env var.

    Priority (highest first):
      1. ``extraction_mode`` key in the provider's llm_config dict
      2. ``LLM_EXTRACTION_MODE`` environment variable
      3. Hard-coded default: ``function``



    Accepted values (case-insensitive):
      ``function``   — tool/function calling mode (default, most reliable)
      ``json_schema``— structured output / JSON schema mode (PydanticProgramMode.DEFAULT)
      ``auto``       — let LlamaIndex choose per provider (PydanticProgramMode.DEFAULT)
    Unknown values fall back to ``function`` with a warning.
    """
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


class LLMFactory:
    """Factory for creating LLM instances based on configuration"""
    
    @staticmethod
    def create_llm(provider: LLMProvider, config: Dict[str, Any]):
        """Create LLM instance based on provider and configuration"""
        
        logger.info(f"Creating LLM with provider: {provider}")
        
        if provider == LLMProvider.OPENAI:
            # Use FUNCTION mode (tool/function calling) instead of DEFAULT (structured output).
            # OpenAI's structured output mode requires `additionalProperties: false` in JSON schemas,
            # which LlamaIndex's dynamic Pydantic models don't generate. Function calling sends
            # the schema as tool parameters instead, which has no such constraint - enabling
            # full property extraction (entity and relation properties) with OpenAI.
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
            timeout = config.get("timeout", 900.0)  # 15 minutes for graph extraction
            logger.info(f"Configuring Ollama LLM - Model: {model}, Base URL: {base_url}, Timeout: {timeout}s")
            
            # Note: Ollama internally creates AsyncClient with request_timeout
            # See llama_index/llms/ollama/base.py line 204
            return Ollama(
                model=model,
                base_url=base_url,
                temperature=config.get("temperature", 0.1),
                request_timeout=timeout
            )
        
        elif provider == LLMProvider.GEMINI:
            llm = GoogleGenAI(
                model=config.get("model", "gemini-2.5-flash"),
                api_key=config.get("api_key"),
                temperature=config.get("temperature", 0.1),
                pydantic_program_mode=_resolve_pydantic_program_mode(config),
            )
            # Disable AFC (Automatic Function Calling) — AFC intercepts LlamaIndex tool calls
            # before Gemini responds, causing SchemaLLMPathExtractor to get 0 entities.
            # Injected directly into _generation_config dict to avoid SDK Pydantic model_dump()
            # leaking the default maximum_remote_calls=10 which triggers a contradictory warning.
            llm._generation_config["automatic_function_calling"] = {"disable": True}
            return llm
        
        elif provider == LLMProvider.AZURE_OPENAI:
            # Same FUNCTION mode workaround as OpenAI above
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
                timeout=config.get("timeout", 120.0)
            )
        
        elif provider == LLMProvider.VERTEX_AI:
            # Vertex AI via GoogleGenAI package (modern approach)
            project = config.get("project")
            if not project:
                raise ValueError("Vertex AI requires 'project' parameter (VERTEX_AI_PROJECT)")
            
            location = config.get("location", "us-central1")
            model = config.get("model", "gemini-2.0-flash-001")
            credentials_path = config.get("credentials_path")
            
            logger.info(f"Configuring Vertex AI - Project: {project}, Location: {location}, Model: {model}")
            
            # Set credentials if provided
            if credentials_path:
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
                logger.info(f"Using Vertex AI credentials from: {credentials_path}")
            
            # Set environment variables for Vertex AI mode
            os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'true'
            os.environ['GOOGLE_CLOUD_PROJECT'] = project
            os.environ['GOOGLE_CLOUD_LOCATION'] = location
            logger.info(f"Set environment variables: GOOGLE_GENAI_USE_VERTEXAI=true, GOOGLE_CLOUD_PROJECT={project}, GOOGLE_CLOUD_LOCATION={location}")
            
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
            context_size = config.get("context_size")
            
            logger.info(f"Configuring Bedrock LLM - Region: {region_name}, Model: {model}")
            if context_size:
                logger.info(f"Using explicit context_size: {context_size}")
            
            # Build AWS credentials dict - only include provided values
            aws_credentials = {}
            if config.get("aws_access_key_id"):
                aws_credentials["aws_access_key_id"] = config.get("aws_access_key_id")
            if config.get("aws_secret_access_key"):
                aws_credentials["aws_secret_access_key"] = config.get("aws_secret_access_key")
            if config.get("aws_session_token"):
                aws_credentials["aws_session_token"] = config.get("aws_session_token")
            if config.get("profile_name"):
                aws_credentials["profile_name"] = config.get("profile_name")
            
            if aws_credentials:
                logger.info(f"Using explicit AWS credentials for Bedrock (keys provided: {list(aws_credentials.keys())})")
            else:
                logger.info("Using default AWS credentials for Bedrock (from environment, IAM role, or ~/.aws/credentials)")
            
            # Build BedrockConverse parameters (new Converse API)
            bedrock_params = {
                "model": model,
                "region_name": region_name,
                "temperature": config.get("temperature", 0.1),
                "timeout": config.get("timeout", 120.0),
                **aws_credentials
            }
            
            # Note: BedrockConverse doesn't need context_size parameter
            # The Converse API handles context automatically
            
            # Use FUNCTION mode: Bedrock is a FunctionCallingLLM subclass but DEFAULT mode
            # can trigger structured output schema validation issues. FUNCTION mode uses
            # native tool calling (achat_with_tools) which is more reliable.
            bedrock_params["pydantic_program_mode"] = _resolve_pydantic_program_mode(config)
            return BedrockConverse(**bedrock_params)
        
        elif provider == LLMProvider.GROQ:
            api_key = config.get("api_key")
            if not api_key:
                raise ValueError("Groq requires 'api_key' parameter (GROQ_API_KEY)")

            model = config.get("model", "llama-3.3-70b-versatile")
            logger.info(f"Configuring Groq LLM - Model: {model}")

            # LlamaIndex's OpenAI model lookup doesn't know Groq-specific models, so it
            # falls back to DEFAULT_NUM_OUTPUTS=3900 as the context window — far too small.
            # Actual Groq context windows (2026-03-17, developer plan):
            #   gpt-oss-20b / gpt-oss-120b : 131072 input, 65536 max completion
            #   llama-3.3-70b-versatile    : 131072 input, 32768 max completion
            #   llama-3.1-8b-instant       : 131072 input, 131072 max completion
            _GROQ_CONTEXT = {
                "openai/gpt-oss-20b": (131072, 65536),
                "openai/gpt-oss-120b": (131072, 65536),
                "llama-3.3-70b-versatile": (131072, 32768),
                "llama-3.1-8b-instant": (131072, 131072),
            }
            ctx_window, default_max = _GROQ_CONTEXT.get(model, (131072, 32768))
            max_tokens = config.get("max_tokens", default_max)
            logger.info(f"Groq context_window={ctx_window}, max_tokens={max_tokens} (model={model})")

            # Groq.__init__ passes **kwargs to the parent Pydantic model so pydantic_program_mode
            # can be passed through the constructor.
            # Note: SchemaLLMPathExtractor doesn't work with Groq — OpenAI.astructured_predict
            # conflicts with FunctionCallingProgram internals causing silent 0-entity extraction.
            # Groq is in the switch_to_dynamic_providers list and auto-switches to DynamicLLMPathExtractor.
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
            logger.info(f"Configuring Fireworks LLM - Model: {model}")
            
            # All Fireworks serverless models filtered to function-calling support all have
            # is_function_calling=True. However, DynamicLLMPathExtractor uses llm.apredict()
            # (plain text), not tool calls — if is_function_calling=True, achat() returns a
            # tool_call response with content=None and apredict() collapses to ''.
            # _make_dynamic_extractor() in hybrid_system.py sets _custom_is_function_calling=False
            # on the extractor's LLM instance to fix this. The factory sets True here so
            # SchemaLLMPathExtractor (which does use tool calls) works correctly if ever needed.
            # Users can override with is_function_calling=False via config if needed.
            is_fc = config.get("is_function_calling", True)
            logger.info(f"Fireworks function calling: is_function_calling={is_fc} (model={model})")

            # Fireworks non-streaming API caps max_tokens at 4096 (BAD_REQUEST if higher).
            # _FireworksStreaming subclass overrides _achat to use stream=True, which removes
            # this limit. Default to 16384 — well within the 65536 max completion budget.
            max_tokens = config.get("max_tokens", 16384)
            logger.info(f"Fireworks max_tokens={max_tokens} (streaming mode, model={model})")

            return _FireworksStreaming(
                model=model,
                api_key=api_key,
                temperature=config.get("temperature", 0.1),
                max_tokens=max_tokens,
                is_function_calling=is_fc,
                pydantic_program_mode=_resolve_pydantic_program_mode(config),
                # Note: Fireworks doesn't support timeout parameter (overrides __init__)
            )
        
        elif provider == LLMProvider.OPENAI_LIKE:
            # Generic OpenAI-compatible API: LM Studio, LocalAI, Llamafile, Jan, Tabby, etc.
            # OpenAILike extends OpenAI/FunctionCallingLLM but defaults is_function_calling_model=False.
            # We default to True since most modern local servers support tool calling.
            # Use FUNCTION mode so structured prediction goes through tool calling, not JSON schema mode.
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
            # vLLM - high-performance local inference engine with native LlamaIndex class.
            # Note: Vllm class does NOT extend FunctionCallingLLM (no tool calling support).
            # It uses LLMTextCompletionProgram (text + output parser) for structured prediction.
            # This works fine for KG extraction - no FUNCTION mode needed.
            model = config.get("model", "facebook/opt-125m")
            api_url = config.get("api_url", "http://localhost:8000")
            is_chat = config.get("is_chat_model", True)
            logger.info(f"Configuring vLLM - Model: {model}, API URL: {api_url}, chat_model={is_chat}")
            return Vllm(
                model=model,
                api_url=api_url,
                temperature=config.get("temperature", 0.1),
                max_new_tokens=config.get("max_new_tokens", 512),
                is_chat_model=is_chat,
            )

        elif provider == LLMProvider.LITELLM:
            # LiteLLM - native LlamaIndex class (FunctionCallingLLM subclass).
            # is_function_calling_model=True by default, uses DEFAULT mode (FunctionCallingProgram).
            # We explicitly set FUNCTION mode for consistency with other providers.
            # drop_params=True: silently drop unsupported params (e.g. parallel_tool_calls for Ollama).
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
            # OpenRouter - native LlamaIndex class (extends OpenAILike).
            # is_function_calling_model=False by default (conservative), but OpenRouter
            # supports tool calling for all major models. We force FUNCTION mode.
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
    
    @staticmethod
    def create_embedding_model(provider: LLMProvider, config: Dict[str, Any], settings):
        """Create embedding model based on configuration
        
        Settings object contains:
        - embedding_kind: "openai", "ollama", "google", "azure" (overrides provider default)
        - embedding_model: Model name
        - embedding_dimension: Explicit dimension (optional, for configurable models like Google)
        """
        
        logger.info(f"Creating embedding model with LLM provider: {provider}")
        
        # Get embedding config from settings object
        embedding_kind = getattr(settings, 'embedding_kind', None)
        embedding_model = getattr(settings, 'embedding_model', None)
        embedding_dimension = getattr(settings, 'embedding_dimension', None)
        
        logger.info(f"Embedding kind: {embedding_kind}, Model: {embedding_model}, Dimension: {embedding_dimension}")
        
        if embedding_kind:
            logger.info(f"Using explicit embedding_kind: {embedding_kind}")
            
            if embedding_kind == "openai":
                model_name = embedding_model or "text-embedding-3-small"
                logger.info(f"Using OpenAI embeddings - Model: {model_name}")
                
                # OpenAI embeddings can be used with any LLM provider
                # If LLM provider is NOT OpenAI, must use OPENAI_API_KEY environment variable
                if provider == LLMProvider.OPENAI:
                    api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
                else:
                    # For non-OpenAI LLM providers, get OpenAI key from environment only
                    api_key = os.getenv("OPENAI_API_KEY")
                
                if not api_key:
                    raise ValueError("OpenAI embeddings require OPENAI_API_KEY environment variable when not using openai LLM provider")
                
                return OpenAIEmbedding(
                    model_name=model_name,
                    api_key=api_key
                )
            
            elif embedding_kind == "ollama":
                model_name = embedding_model or "nomic-embed-text"
                base_url = config.get("ollama_base_url", "http://localhost:11434")
                logger.info(f"Using Ollama embeddings - Model: {model_name}, Base URL: {base_url}")
                return OllamaEmbedding(
                    model_name=model_name,
                    base_url=base_url
                )
            
            elif embedding_kind == "google":
                model_name = embedding_model or "text-embedding-001"
                embed_dim = embedding_dimension or 1536
                logger.info(f"Using Google embeddings - Model: {model_name}, Dimensions: {embed_dim}")
                
                # Google embeddings can be used with any LLM provider
                # If LLM provider is Gemini/Vertex, use config API key; otherwise use GOOGLE_API_KEY env var
                if provider in [LLMProvider.GEMINI, LLMProvider.VERTEX_AI]:
                    api_key = config.get("api_key") or os.getenv("GOOGLE_API_KEY")
                else:
                    # For non-Google LLM providers, get Google key from environment only
                    api_key = os.getenv("GOOGLE_API_KEY")
                
                if not api_key:
                    raise ValueError("Google embeddings require GOOGLE_API_KEY environment variable when not using gemini/vertex_ai LLM provider")
                
                return GoogleGenAIEmbedding(
                    model_name=model_name,
                    api_key=api_key,
                    embedding_config=EmbedContentConfig(
                        output_dimensionality=embed_dim
                    )
                )
            
            elif embedding_kind == "azure":
                model_name = embedding_model or "text-embedding-3-small"
                logger.info(f"Using Azure OpenAI embeddings - Model: {model_name}")
                
                # Azure embeddings can be used with any LLM provider
                # If LLM provider is Azure, get config from llm_config; otherwise use environment variables
                if provider == LLMProvider.AZURE_OPENAI:
                    azure_endpoint = config.get("azure_endpoint")
                    api_key = config.get("api_key")
                    api_version = config.get("api_version", "2024-02-01")
                else:
                    # For non-Azure LLM providers, get all Azure config from environment
                    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                    api_key = os.getenv("AZURE_OPENAI_API_KEY")
                    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
                
                if not azure_endpoint or not api_key:
                    raise ValueError("Azure embeddings require AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY environment variables when not using azure_openai LLM provider")
                
                # Use EMBEDDING_MODEL as deployment name (common pattern: deployment name = model name)
                # Allow override with AZURE_EMBEDDING_DEPLOYMENT if deployment name differs from model
                deployment_name = os.getenv("AZURE_EMBEDDING_DEPLOYMENT") or model_name
                
                return AzureOpenAIEmbedding(
                    model=model_name,
                    deployment_name=deployment_name,
                    azure_endpoint=azure_endpoint,
                    api_key=api_key,
                    api_version=api_version
                )
            
            elif embedding_kind == "vertex":
                # Vertex AI via GoogleGenAIEmbedding (modern approach)
                model_name = embedding_model or "text-embedding-004"
                project = config.get("project") or os.getenv("VERTEX_AI_PROJECT")
                location = config.get("location") or os.getenv("VERTEX_AI_LOCATION", "us-central1")
                credentials_path = config.get("credentials_path") or os.getenv("VERTEX_AI_CREDENTIALS_PATH")
                
                logger.info(f"Using Vertex AI embeddings - Model: {model_name}, Project: {project}, Location: {location}")
                
                # Set credentials if provided
                if credentials_path:
                    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
                    logger.info(f"Using Vertex AI credentials from: {credentials_path}")
                
                # Set environment variables for Vertex AI mode
                if project:
                    os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'true'
                    os.environ['GOOGLE_CLOUD_PROJECT'] = project
                    os.environ['GOOGLE_CLOUD_LOCATION'] = location
                    logger.info(f"Set environment variables: GOOGLE_GENAI_USE_VERTEXAI=true, GOOGLE_CLOUD_PROJECT={project}, GOOGLE_CLOUD_LOCATION={location}")
                
                # Build embedding parameters
                embedding_params = {
                    "model_name": model_name,
                    "embed_batch_size": 100
                }
                
                # Add vertexai_config if project is provided
                if project:
                    embedding_params["vertexai_config"] = {
                        "project": project,
                        "location": location
                    }
                
                # Add embedding_config for dimension control
                if embedding_dimension:
                    embedding_params["embedding_config"] = EmbedContentConfig(
                        output_dimensionality=embedding_dimension
                    )
                
                return GoogleGenAIEmbedding(**embedding_params)
            
            elif embedding_kind == "bedrock":
                model_name = embedding_model or "amazon.titan-embed-text-v2:0"
                region_name = config.get("region_name") or os.getenv("BEDROCK_REGION", "us-east-1")
                
                logger.info(f"Using Bedrock embeddings - Model: {model_name}, Region: {region_name}")
                
                # Build AWS credentials dict - only include provided values
                aws_credentials = {}
                access_key = config.get("aws_access_key_id") or os.getenv("BEDROCK_ACCESS_KEY")
                secret_key = config.get("aws_secret_access_key") or os.getenv("BEDROCK_SECRET_KEY")
                session_token = config.get("aws_session_token") or os.getenv("BEDROCK_SESSION_TOKEN")
                profile_name = config.get("profile_name") or os.getenv("BEDROCK_PROFILE_NAME")
                
                if access_key:
                    aws_credentials["aws_access_key_id"] = access_key
                if secret_key:
                    aws_credentials["aws_secret_access_key"] = secret_key
                if session_token:
                    aws_credentials["aws_session_token"] = session_token
                if profile_name:
                    aws_credentials["profile_name"] = profile_name
                
                if aws_credentials:
                    logger.info(f"Using explicit AWS credentials for Bedrock embeddings (keys provided: {list(aws_credentials.keys())})")
                else:
                    logger.info("Using default AWS credentials for Bedrock embeddings")
                
                return BedrockEmbedding(
                    model_name=model_name,
                    region_name=region_name,
                    **aws_credentials
                )
            
            elif embedding_kind == "fireworks":
                model_name = embedding_model or "nomic-ai/nomic-embed-text-v1.5"
                api_key = config.get("api_key") or os.getenv("FIREWORKS_API_KEY")
                
                logger.info(f"Using Fireworks embeddings - Model: {model_name}")
                
                if not api_key:
                    raise ValueError("Fireworks embeddings require FIREWORKS_API_KEY environment variable or api_key in config")
                
                return FireworksEmbedding(
                    model_name=model_name,
                    api_key=api_key
                )

            elif embedding_kind == "openai_like":
                # Any OpenAI-compatible /v1/embeddings endpoint: LM Studio, LocalAI, vLLM, Llamafile, etc.
                # Uses OpenAILikeEmbedding class.
                model_name = embedding_model or os.getenv("OPENAI_LIKE_EMBEDDING_MODEL", "local-embedding-model")
                api_base = os.getenv("OPENAI_LIKE_EMBEDDING_API_BASE") or os.getenv("OPENAI_LIKE_API_BASE", "http://localhost:8000/v1")
                api_key = os.getenv("OPENAI_LIKE_API_KEY", "fake")
                logger.info(f"Using OpenAI-Like embeddings - Model: {model_name}, API Base: {api_base}")
                return OpenAILikeEmbedding(
                    model_name=model_name,
                    api_base=api_base,
                    api_key=api_key,
                )

            elif embedding_kind == "litellm":
                # LiteLLM proxy embeddings - routes to any backend (OpenAI, Ollama, Bedrock, etc.)
                # Uses LiteLLMEmbedding class.
                model_name = embedding_model or os.getenv("LITELLM_EMBEDDING_MODEL", "text-embedding-3-small")
                api_base = os.getenv("LITELLM_EMBEDDING_API_BASE") or os.getenv("LITELLM_API_BASE", "http://localhost:4000")
                api_key = os.getenv("LITELLM_API_KEY", "local")
                logger.info(f"Using LiteLLM embeddings - Model: {model_name}, API Base: {api_base}")
                return LiteLLMEmbedding(
                    model_name=model_name,
                    api_base=api_base,
                    api_key=api_key,
                )

            else:
                # Unknown embedding_kind - fall through to provider defaults
                logger.warning(f"Unknown embedding_kind '{embedding_kind}', using provider default")
        
        # No explicit embedding_kind (or unknown kind) - use provider defaults
        if provider in [LLMProvider.OPENAI, LLMProvider.AZURE_OPENAI]:
            if provider == LLMProvider.AZURE_OPENAI:
                model_name = embedding_model or "text-embedding-3-small"
                logger.info(f"Using Azure OpenAI embeddings (provider default) - Model: {model_name}")
                return AzureOpenAIEmbedding(
                    model=model_name,
                    azure_endpoint=config["azure_endpoint"],
                    api_key=config["api_key"],
                    api_version=config.get("api_version", "2024-02-01")
                )
            else:
                model_name = embedding_model or "text-embedding-3-small"
                logger.info(f"Using OpenAI embeddings (provider default) - Model: {model_name}")
                return OpenAIEmbedding(
                    model_name=model_name,
                    api_key=config.get("api_key")
                )
        
        elif provider == LLMProvider.OLLAMA:
            model_name = embedding_model or "nomic-embed-text"
            base_url = config.get("base_url", "http://localhost:11434")
            logger.info(f"Using Ollama embeddings (provider default) - Model: {model_name}, Base URL: {base_url}")
            return OllamaEmbedding(
                model_name=model_name,
                base_url=base_url
            )
        
        elif provider == LLMProvider.GEMINI:
            # Gemini: Use Google embeddings by default
            model_name = embedding_model or "text-embedding-001"
            embed_dim = embedding_dimension or 1536
            logger.info(f"Using Google embeddings (Gemini provider default) - Model: {model_name}, Dimensions: {embed_dim}")
            
            return GoogleGenAIEmbedding(
                model_name=model_name,
                api_key=config.get("api_key"),
                embedding_config=EmbedContentConfig(
                    output_dimensionality=embed_dim
                )
            )
        
        elif provider == LLMProvider.ANTHROPIC:
            # Anthropic: Use Ollama embeddings by default (nomic-embed-text, 768 dims)
            # Allows local, private embeddings with Claude reasoning
            model_name = embedding_model or "nomic-embed-text"
            base_url = config.get("ollama_base_url") or config.get("base_url", "http://localhost:11434")
            logger.info(f"Using Ollama embeddings (Anthropic provider default) - Model: {model_name}, Base URL: {base_url}")
            return OllamaEmbedding(
                model_name=model_name,
                base_url=base_url
            )
        
        elif provider == LLMProvider.VERTEX_AI:
            # Vertex AI: Use Vertex embeddings by default (via GoogleGenAIEmbedding)
            model_name = embedding_model or "text-embedding-004"
            project = config.get("project")
            location = config.get("location", "us-central1")
            credentials_path = config.get("credentials_path")
            
            if not project:
                raise ValueError("Vertex AI embeddings require 'project' parameter (VERTEX_AI_PROJECT)")
            
            logger.info(f"Using Vertex AI embeddings (provider default) - Model: {model_name}, Project: {project}, Location: {location}")
            
            # Set credentials if provided
            if credentials_path:
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
            
            # Set environment variables for Vertex AI mode
            os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'true'
            os.environ['GOOGLE_CLOUD_PROJECT'] = project
            os.environ['GOOGLE_CLOUD_LOCATION'] = location
            
            embedding_params = {
                "model_name": model_name,
                "embed_batch_size": 100,
                "vertexai_config": {
                    "project": project,
                    "location": location
                }
            }
            
            # Add embedding_config for dimension control
            if embedding_dimension:
                embedding_params["embedding_config"] = EmbedContentConfig(
                    output_dimensionality=embedding_dimension
                )
            
            return GoogleGenAIEmbedding(**embedding_params)
        
        elif provider == LLMProvider.BEDROCK:
            # Bedrock: Use Bedrock embeddings by default
            model_name = embedding_model or "amazon.titan-embed-text-v2:0"
            region_name = config.get("region_name", "us-east-1")
            
            logger.info(f"Using Bedrock embeddings (provider default) - Model: {model_name}, Region: {region_name}")
            
            # Build AWS credentials dict
            aws_credentials = {}
            if config.get("aws_access_key_id"):
                aws_credentials["aws_access_key_id"] = config.get("aws_access_key_id")
            if config.get("aws_secret_access_key"):
                aws_credentials["aws_secret_access_key"] = config.get("aws_secret_access_key")
            if config.get("aws_session_token"):
                aws_credentials["aws_session_token"] = config.get("aws_session_token")
            if config.get("profile_name"):
                aws_credentials["profile_name"] = config.get("profile_name")
            
            return BedrockEmbedding(
                model_name=model_name,
                region_name=region_name,
                **aws_credentials
            )
        
        elif provider == LLMProvider.GROQ:
            # Groq: No native embeddings - use Ollama embeddings by default
            model_name = embedding_model or "nomic-embed-text"
            base_url = config.get("ollama_base_url") or config.get("base_url", "http://localhost:11434")
            logger.info(f"Using Ollama embeddings (Groq provider default) - Model: {model_name}, Base URL: {base_url}")
            logger.info("Note: Groq doesn't provide embeddings - using local Ollama for privacy")
            return OllamaEmbedding(
                model_name=model_name,
                base_url=base_url
            )
        
        elif provider == LLMProvider.FIREWORKS:
            # Fireworks: Use Fireworks embeddings by default
            model_name = embedding_model or "nomic-ai/nomic-embed-text-v1.5"
            api_key = config.get("api_key")
            
            logger.info(f"Using Fireworks embeddings (provider default) - Model: {model_name}")
            
            if not api_key:
                raise ValueError("Fireworks embeddings require 'api_key' parameter (FIREWORKS_API_KEY)")
            
            return FireworksEmbedding(
                model_name=model_name,
                api_key=api_key
            )
        
        else:
            # Default to Ollama nomic-embed-text for unknown providers
            model_name = embedding_model or "nomic-embed-text"
            base_url = config.get("ollama_base_url") or config.get("base_url", "http://localhost:11434")
            logger.warning(f"No embedding model implementation for {provider}, using Ollama default: {model_name}")
            return OllamaEmbedding(
                model_name=model_name,
                base_url=base_url
            )

class DatabaseFactory:
    """Factory for creating database connections"""
    
    @staticmethod
    def create_vector_store(db_type: VectorDBType, config: Dict[str, Any], llm_provider: LLMProvider = None, llm_config: Dict[str, Any] = None, app_config=None):
        """Create vector store based on database type"""
        
        logger.info(f"Creating vector store with type: {db_type}")
        
        # Get embedding dimension - now independent of LLM provider
        # Extract embedding configuration from app_config (Settings object)
        embedding_kind = getattr(app_config, 'embedding_kind', None) if app_config else None
        embedding_model = getattr(app_config, 'embedding_model', None) if app_config else None
        embedding_dimension = getattr(app_config, 'embedding_dimension', None) if app_config else None
        
        embed_dim = get_embedding_dimension(
            embedding_kind=embedding_kind,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension
        )
        logger.info(f"Detected embedding dimension: {embed_dim} (kind: {embedding_kind}, model: {embedding_model})")
        
        if db_type == VectorDBType.NONE:
            logger.info("Vector search disabled - no vector store created")
            return None
        
        elif db_type == VectorDBType.QDRANT:
            client = QdrantClient(
                host=config.get("host", "localhost"),
                port=config.get("port", 6333),
                api_key=config.get("api_key"),
                https=config.get("https", False),  # Default to HTTP for local instances
                check_compatibility=False  # Skip version compatibility check
            )
            aclient = AsyncQdrantClient(
                host=config.get("host", "localhost"),
                port=config.get("port", 6333),
                api_key=config.get("api_key"),
                https=config.get("https", False),  # Default to HTTP for local instances
                check_compatibility=False  # Skip version compatibility check
            )
            collection_name = config.get("collection_name", "hybrid_search")
            logger.info(f"Creating Qdrant vector store - Collection: {collection_name}, Embed dim: {embed_dim}")
            
            return QdrantVectorStore(
                client=client,
                aclient=aclient,
                collection_name=collection_name
            )
        
        elif db_type == VectorDBType.NEO4J:
            url = config.get("url", "bolt://localhost:7687")
            index_name = config.get("index_name", "hybrid_search_vector")
            logger.info(f"Creating Neo4j vector store - URL: {url}, Index: {index_name}, Embed dim: {embed_dim}")
            
            return Neo4jVectorStore(
                username=config.get("username", "neo4j"),
                password=config["password"],
                url=url,
                embedding_dimension=embed_dim,
                database=config.get("database", "neo4j"),
                index_name=index_name
            )
        
        elif db_type == VectorDBType.ELASTICSEARCH:
            from llama_index.vector_stores.elasticsearch import AsyncDenseVectorStrategy
            
            index_name = config.get("index_name", "hybrid_search_vector")
            es_url = config.get("url", "http://localhost:9200")
            logger.info(f"Creating Elasticsearch vector store - Index: {index_name}, URL: {es_url}, Embed dim: {embed_dim}")
            
            return ElasticsearchStore(
                index_name=index_name,
                es_url=es_url,
                es_user=config.get("username"),
                es_password=config.get("password"),
                retrieval_strategy=AsyncDenseVectorStrategy()  # Pure vector search (fix query parsing issue)
            )
        
        elif db_type == VectorDBType.OPENSEARCH:
            from llama_index.vector_stores.opensearch import OpensearchVectorClient
            
            # Create OpenSearch vector client with hybrid search pipeline
            logger.info(f"Creating OpenSearch vector store with embedding dimension: {embed_dim}")
            
            client = OpensearchVectorClient(
                endpoint=config.get("url", "http://localhost:9201"),
                index=config.get("index_name", "hybrid_search_vector"),
                dim=embed_dim,
                embedding_field=config.get("embedding_field", "embedding"),
                text_field=config.get("text_field", "content"),
                search_pipeline=config.get("search_pipeline"),  # Optional pipeline (None by default)
                http_auth=(config.get("username"), config.get("password")) if config.get("username") else None
            )
            
            return OpensearchVectorStore(client)
        
        elif db_type == VectorDBType.CHROMA:
            from llama_index.vector_stores.chroma import ChromaVectorStore
            import chromadb
            
            collection_name = config.get("collection_name", "hybrid_search")
            
            # Check if HTTP client configuration is provided
            host = config.get("host")
            port = config.get("port")
            
            if host and port:
                # HTTP Client mode - connect to remote ChromaDB server
                logger.info(f"Creating Chroma vector store (HTTP) - Host: {host}:{port}, Collection: {collection_name}, Embed dim: {embed_dim}")
                chroma_client = chromadb.HttpClient(host=host, port=port)
            else:
                # Persistent Client mode - local file-based storage (default)
                persist_directory = config.get("persist_directory", "./chroma_db")
                logger.info(f"Creating Chroma vector store (Local) - Collection: {collection_name}, Persist dir: {persist_directory}, Embed dim: {embed_dim}")
                chroma_client = chromadb.PersistentClient(path=persist_directory)
            
            chroma_collection = chroma_client.get_or_create_collection(collection_name)
            
            return ChromaVectorStore(chroma_collection=chroma_collection)
        
        elif db_type == VectorDBType.MILVUS:
            from llama_index.vector_stores.milvus import MilvusVectorStore
            
            host = config.get("host", "localhost")
            port = config.get("port", 19530)
            collection_name = config.get("collection_name", "hybrid_search")
            
            # Use URI format for proper connection to Milvus server
            uri = f"http://{host}:{port}"
            logger.info(f"Creating Milvus vector store - URI: {uri}, Collection: {collection_name}, Embed dim: {embed_dim}")
            
            return MilvusVectorStore(
                uri=uri,
                collection_name=collection_name,
                dim=embed_dim,
                user=config.get("username"),
                password=config.get("password"),
                token=config.get("token"),  # For cloud Milvus
                overwrite=config.get("overwrite", False)
            )
        
        elif db_type == VectorDBType.WEAVIATE:
            from llama_index.vector_stores.weaviate import WeaviateVectorStore
            import weaviate
            import asyncio
            
            url = config.get("url", "http://localhost:8081")
            index_name = config.get("index_name", "HybridSearch")  # Must start with capital letter
            logger.info(f"Creating Weaviate vector store - URL: {url}, Index: {index_name}, Embed dim: {embed_dim}")
            
            # Create Weaviate ASYNC client using v4 API for async operations
            if config.get("api_key"):
                # For authenticated instances, use use_async_with_custom (REST-only async)
                from weaviate.classes.init import Auth, AdditionalConfig, Timeout
                async_client = weaviate.use_async_with_custom(
                    http_host=url.replace("http://", "").replace("https://", "").replace(":8081", ""),
                    http_port=8081,
                    http_secure=False,
                    grpc_host="localhost",  # Required parameter but won't be used
                    grpc_port=50051,       # Required parameter but won't be used  
                    grpc_secure=False,
                    skip_init_checks=True,  # Skip all health checks - REST-only mode
                    additional_config=AdditionalConfig(
                        timeout=Timeout(init=60, query=60, insert=180)
                    ),
                    auth_credentials=Auth.api_key(config.get("api_key")),
                    headers=config.get("additional_headers", {})
                )
            else:
                # For local unauthenticated instances (REST-only async)
                from weaviate.classes.init import AdditionalConfig, Timeout
                async_client = weaviate.use_async_with_custom(
                    http_host=url.replace("http://", "").replace("https://", "").replace(":8081", ""),
                    http_port=8081,
                    http_secure=False,
                    grpc_host="localhost",  # Required parameter but won't be used
                    grpc_port=50051,       # Required parameter but won't be used
                    grpc_secure=False,
                    skip_init_checks=True,  # Skip all health checks - REST-only mode
                    additional_config=AdditionalConfig(
                        timeout=Timeout(init=60, query=60, insert=180)
                    ),
                    headers=config.get("additional_headers", {})
                )
            
            # Connect the async client synchronously during initialization
            # This is safe because we're not in an async context yet
            try:
                # Try to get existing event loop
                try:
                    loop = asyncio.get_running_loop()
                    # Loop is running - we can't block, will connect lazily on first use
                    logger.warning("Event loop already running during Weaviate init - async client will connect on first use")
                except RuntimeError:
                    # No running loop - safe to create one
                    asyncio.run(async_client.connect())
                    logger.info("Weaviate async client connected successfully")
            except Exception as e:
                logger.warning(f"Could not pre-connect Weaviate async client: {e} - will connect on first use")
            
            return WeaviateVectorStore(
                weaviate_client=async_client,
                index_name=index_name,
                text_key=config.get("text_key", "content")
            )
        
        elif db_type == VectorDBType.PINECONE:
            from llama_index.vector_stores.pinecone import PineconeVectorStore
            from pinecone import Pinecone, ServerlessSpec
            
            api_key = config.get("api_key")
            region = config.get("region", "us-east-1")
            cloud = config.get("cloud", "aws")
            index_name = config.get("index_name", "hybrid-search")
            metric = config.get("metric", "cosine")
            
            logger.info(f"Creating Pinecone vector store - Index: {index_name}, Cloud: {cloud}, Region: {region}, Metric: {metric}, Embed dim: {embed_dim}")
            
            if not api_key:
                raise ValueError("Pinecone API key is required")
            
            # Initialize Pinecone client
            pc = Pinecone(api_key=api_key)
            
            # Create or get index
            existing_indexes = [index.name for index in pc.list_indexes()]
            if index_name not in existing_indexes:
                logger.info(f"Creating new Pinecone index: {index_name} with dimension: {embed_dim}")
                pc.create_index(
                    name=index_name,
                    dimension=embed_dim,  # Auto-detected from embedding model
                    metric=metric,
                    spec=ServerlessSpec(cloud=cloud, region=region)
                )
            else:
                logger.info(f"Using existing Pinecone index: {index_name}")
            
            pinecone_index = pc.Index(index_name)
            
            return PineconeVectorStore(
                pinecone_index=pinecone_index,
                namespace=config.get("namespace")
            )
        
        elif db_type == VectorDBType.POSTGRES:
            from llama_index.vector_stores.postgres import PGVectorStore
            
            connection_string = config.get("connection_string")
            if not connection_string:
                # Build connection string from components
                host = config.get("host", "localhost")
                port = config.get("port", 5432)
                database = config.get("database", "postgres")
                username = config.get("username", "postgres")
                password = config.get("password")
                connection_string = f"postgresql://{username}:{password}@{host}:{port}/{database}"
            
            table_name = config.get("table_name", "hybrid_search_vectors")
            logger.info(f"Creating PostgreSQL vector store - Table: {table_name}, Embed dim: {embed_dim}")
            
            return PGVectorStore.from_params(
                database=config.get("database", "postgres"),
                host=config.get("host", "localhost"),
                password=config.get("password"),
                port=config.get("port", 5432),
                user=config.get("username", "postgres"),
                table_name=table_name,
                embed_dim=embed_dim
            )
        
        elif db_type == VectorDBType.LANCEDB:
            from llama_index.vector_stores.lancedb import LanceDBVectorStore
            import lancedb
            
            uri = config.get("uri", "./lancedb")
            table_name = config.get("table_name", "hybrid_search")
            logger.info(f"Creating LanceDB vector store - URI: {uri}, Table: {table_name}, Embed dim: {embed_dim}")
            
            # Connect to LanceDB
            db = lancedb.connect(uri)
            
            return LanceDBVectorStore(
                uri=uri,
                table_name=table_name,
                vector_column_name=config.get("vector_column_name", "vector"),
                text_column_name=config.get("text_column_name", "text")
            )
        
        else:
            raise ValueError(f"Unsupported vector database: {db_type}")
    
    @staticmethod
    def create_graph_store(db_type: GraphDBType, config: Dict[str, Any], schema_config: Dict[str, Any] = None, has_separate_vector_store: bool = False, llm_provider: LLMProvider = None, llm_config: Dict[str, Any] = None, app_config=None):
        """Create graph store based on database type"""
        
        logger.info(f"Creating graph store with type: {db_type}")
        
        if db_type == GraphDBType.NONE:
            logger.info("Graph search disabled - no graph store created")
            return None
        
        elif db_type == GraphDBType.NEO4J:
            return Neo4jPropertyGraphStore(
                username=config.get("username", "neo4j"),
                password=config["password"],
                url=config.get("url", "bolt://localhost:7687"),
                database=config.get("database", "neo4j"),
                refresh_schema=False  # Disable APOC schema refresh to avoid apoc.meta.data calls
            )
        
        elif db_type == GraphDBType.LADYBUG:
            import os
            from llama_index.graph_stores.ladybug import LadybugPropertyGraphStore
            import real_ladybug as lb

            db_dir = config.get("db_dir", "./ladybug")
            db_file = config.get("db_file", "database.lbug")
            db_path = os.path.join(db_dir, db_file)
            use_vector_index = config.get("use_vector_index", True)
            has_structured_schema = config.get("has_structured_schema", False)
            strict_schema = config.get("strict_schema", False)

            # Ensure the directory exists
            os.makedirs(db_dir, exist_ok=True)

            ladybug_db = lb.Database(db_path)

            # Build relationship_schema — priority order:
            #   1. USE_ONTOLOGY=true → OntologyManager.validation_schema (domain/range from .ttl files)
            #   2. Named schema (SCHEMA_NAME != 'default') → schema_config["validation_schema"]
            #   3. schema_name == 'default' → LlamaIndex DEFAULT_VALIDATION_SCHEMA (built-in types)
            #   4. Anything else → unstructured mode (has_structured_schema forced False)
            # Note: Entity, Chunk, LINKS, MENTIONS are always created by Ladybug's init_schema —
            # relationship_schema only needs to list the custom entity/relation triples.
            relationship_schema = None

            use_ontology = (
                app_config is not None
                and getattr(app_config, "use_ontology", False)
            )
            if use_ontology:
                try:
                    from rdf.api_rdf_enhancements import ontology_manager as _om
                    if _om and _om.validation_schema:
                        relationship_schema = list(_om.validation_schema)
                        logger.info(
                            f"Ladybug: using ontology relationship_schema "
                            f"({len(relationship_schema)} domain/range triplets from .ttl)"
                        )
                    elif _om:
                        # Ontology loaded but no domain/range constraints — derive from entities × relations
                        entities = list(_om.entities.keys())
                        relations = list(_om.relations.keys())
                        relationship_schema = [
                            (e, r, e2)
                            for r in relations
                            for e in entities
                            for e2 in entities
                        ] if entities and relations else None
                        if relationship_schema:
                            logger.info(
                                f"Ladybug: ontology has no domain/range constraints; "
                                f"derived {len(relationship_schema)} permutations"
                            )
                        else:
                            logger.info("Ladybug: ontology loaded but empty — using unstructured mode")
                except (ImportError, AttributeError) as exc:
                    logger.debug(f"Ladybug: could not load ontology manager: {exc}")

            if relationship_schema is None and schema_config and schema_config.get("validation_schema"):
                raw = schema_config["validation_schema"]
                if isinstance(raw, dict) and "relationships" in raw:
                    raw = raw["relationships"]
                if isinstance(raw, list):
                    relationship_schema = []
                    for item in raw:
                        if isinstance(item, (list, tuple)) and len(item) == 3:
                            relationship_schema.append(tuple(item))
                        else:
                            logger.warning(f"Skipping invalid Ladybug relationship schema item: {item}")
                    logger.info(
                        f"Ladybug: using schema_config relationship_schema "
                        f"({len(relationship_schema)} triplets)"
                    )

            # Fallback: schema_name == 'default' → use LlamaIndex built-in schema
            # (PRODUCT/MARKET/TECHNOLOGY/EVENT/CONCEPT/ORGANIZATION/PERSON/LOCATION/TIME/MISCELLANEOUS
            #  with USED_BY/USED_FOR/LOCATED_IN/PART_OF/WORKED_ON/HAS/IS_A/BORN_IN/DIED_IN/HAS_ALIAS)
            if relationship_schema is None and has_structured_schema:
                schema_name = getattr(app_config, "schema_name", "default") if app_config else "default"
                if schema_name == "default":
                    try:
                        from llama_index.core.indices.property_graph.transformations.schema_llm import (
                            DEFAULT_VALIDATION_SCHEMA,
                        )
                        relationship_schema = list(DEFAULT_VALIDATION_SCHEMA)
                        logger.info(
                            f"Ladybug: schema_name='default' — using LlamaIndex built-in schema "
                            f"({len(relationship_schema)} triples: PERSON/ORG/PRODUCT/... with WORKED_ON/PART_OF/...)"
                        )
                    except ImportError:
                        logger.warning("Ladybug: could not import DEFAULT_VALIDATION_SCHEMA from LlamaIndex — falling back to unstructured mode")
                        has_structured_schema = False
                else:
                    logger.warning(
                        f"Ladybug: LADYBUG_STRUCTURED_SCHEMA=true but no schema could be derived "
                        f"for schema_name='{schema_name}' — falling back to unstructured mode"
                    )
                    has_structured_schema = False

            # Resolve embedding model
            if llm_provider and llm_config:
                embed_model = LLMFactory.create_embedding_model(llm_provider, llm_config, settings=app_config)
                provider_name = llm_provider.value if hasattr(llm_provider, "value") else str(llm_provider)
                logger.info(f"Ladybug embedding model: {provider_name}")
            else:
                from llama_index.embeddings.openai import OpenAIEmbedding
                embed_model = OpenAIEmbedding(model_name="text-embedding-3-small")
                logger.warning("No LLM provider specified for Ladybug, falling back to OpenAI embeddings")

            embed_dim = (
                getattr(embed_model, "embed_dim", None)
                or getattr(embed_model, "dimensions", None)
                or getattr(embed_model, "output_dimensionality", None)
            )
            if embed_dim is None:
                # OpenAI and most LlamaIndex embed models: detect by running a test embedding
                try:
                    test = embed_model.get_text_embedding("hello")
                    embed_dim = len(test)
                    logger.info(f"Ladybug: detected embed_dim={embed_dim} via test embedding")
                except Exception as e:
                    logger.warning(f"Ladybug: could not detect embed_dim: {e}")
            logger.info(
                f"Ladybug configuration: use_vector_index={use_vector_index}, "
                f"has_structured_schema={has_structured_schema}, "
                f"strict_schema={strict_schema}, "
                f"embed_dim={embed_dim}, "
                f"relationship_schema_count={len(relationship_schema) if relationship_schema else 0}"
            )

            graph_store = LadybugPropertyGraphStore(
                ladybug_db,
                relationship_schema=relationship_schema if has_structured_schema else None,
                has_structured_schema=has_structured_schema,
                strict_schema=strict_schema,
                use_vector_index=use_vector_index,
                embed_model=embed_model,
                embed_dimension=embed_dim,
            )
            return graph_store

        elif db_type == GraphDBType.FALKORDB:
            url = config.get("url", "falkor://localhost:6379")
            database = config.get("database", "falkor")
            logger.info(f"Creating FalkorDB graph store - URL: {url} database: {database}")

            ensure_falkordb_stringify_patch()

            # Use standard FalkorDB store (indexes are the key optimization)
            graph_store = FalkorDBPropertyGraphStore(
                url=url,
                database=database,
                refresh_schema=False,  # Disable expensive schema refresh on init
                sanitize_query_output=True
            )
            
            # Create indexes for better performance
            try:
                logger.info("Creating FalkorDB indexes for optimization...")
                # Index on entity names for faster lookups
                graph_store.client.query("CREATE INDEX FOR (e:__Entity__) ON (e.name)")
                # Index on entity IDs
                graph_store.client.query("CREATE INDEX FOR (e:__Entity__) ON (e.id)")
                # Index on chunks
                graph_store.client.query("CREATE INDEX FOR (c:Chunk) ON (c.id)")
                logger.info("FalkorDB indexes created successfully")
            except Exception as e:
                logger.warning(f"Index creation failed (may already exist): {e}")
            
            return graph_store
        
        elif db_type == GraphDBType.ARCADEDB:
            host = config.get("host", "localhost")
            port = config.get("port", 2480)
            username = config.get("username", "root")
            password = config.get("password", "playwithdata")
            database = config.get("database", "flexible_graphrag")
            include_basic_schema = config.get("include_basic_schema", True)
            
            # Get embedding dimension from centralized function
            # Extract embedding configuration from app_config (Settings object)
            embedding_kind = getattr(app_config, 'embedding_kind', None) if app_config else None
            embedding_model = getattr(app_config, 'embedding_model', None) if app_config else None
            embedding_dimension = getattr(app_config, 'embedding_dimension', None) if app_config else None
            
            embed_dim = get_embedding_dimension(
                embedding_kind=embedding_kind,
                embedding_model=embedding_model,
                embedding_dimension=embedding_dimension
            )
            logger.info(f"Detected embedding dimension for ArcadeDB: {embed_dim} (kind: {embedding_kind}, model: {embedding_model})")

            # Embedded mode — triggered by setting mode="embedded" in config
            mode = config.get("mode", "remote")
            if mode == "embedded":
                db_path = config.get("db_path", "./arcadedb_data")
                embedded_server = config.get("embedded_server", False)
                embedded_server_port = config.get("embedded_server_port", 2482)
                embedded_server_password = config.get("embedded_server_password", None)
                logger.info(
                    f"Creating ArcadeDB embedded graph store - db_path: {db_path}, "
                    f"database: {database}, embedded_server: {embedded_server}, "
                    f"port: {embedded_server_port}, embed_dim: {embed_dim}"
                )
                return ArcadeDBPropertyGraphStore(
                    mode="embedded",
                    db_path=db_path,
                    database=database,
                    embedded_server=embedded_server,
                    embedded_server_port=embedded_server_port,
                    embedded_server_password=embedded_server_password,
                    embedding_dimension=embed_dim,
                    include_basic_schema=include_basic_schema,
                )

            logger.info(f"Creating ArcadeDB graph store - Host: {host}:{port}, Database: {database}, Include basic schema: {include_basic_schema}, Embed dim: {embed_dim}")

            return ArcadeDBPropertyGraphStore(
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
                embedding_dimension=embed_dim,
                include_basic_schema=include_basic_schema
            )
        
        elif db_type == GraphDBType.MEMGRAPH:
            username = config.get("username", "")
            password = config.get("password", "")
            url = config.get("url", "bolt://localhost:7688")  # Default MemGraph port
            database = config.get("database", "memgraph")
            
            logger.info(f"Creating MemGraph graph store - URL: {url}, Database: {database}")
            logger.info("Using MemGraph-specific configuration to avoid relationship naming issues")
            
            return MemgraphPropertyGraphStore(
                username=username,
                password=password,
                url=url,
                database=database,
                refresh_schema=False  # Bypass schema validation to avoid naming conflicts
            )
        
        elif db_type == GraphDBType.NEBULA:
            # Handle both 'space' and 'space_name' for backward compatibility
            space = config.get("space") or config.get("space_name", "flexible_graphrag")
            overwrite = config.get("overwrite", True)
            
            # Connection parameters using correct parameter names
            username = config.get("username", "root")
            password = config.get("password", "nebula")
            # Build URL from address and port, or use provided URL
            if "url" in config:
                url = config["url"]
            else:
                address = config.get("address", "localhost")
                port = config.get("port", 9669)
                url = f"nebula://{address}:{port}"
            
            # Custom props schema including all required columns for LlamaIndex
            # Based on the error, LlamaIndex tries to insert these specific properties
            CUSTOM_PROPS_SCHEMA = "`source` STRING, `conversion_method` STRING, `file_type` STRING, `file_name` STRING, `_node_content` STRING, `_node_type` STRING, `document_id` STRING, `doc_id` STRING, `ref_doc_id` STRING, `triplet_source_id` STRING, `file_path` STRING, `file_size` INT, `creation_date` STRING, `last_modified_date` STRING"
            
            logger.info(f"Creating NebulaGraph graph store - Space: {space}, URL: {url}, Overwrite: {overwrite}")
            logger.info("Using custom props schema to include all required LlamaIndex properties")
            logger.info(f"Props schema: {CUSTOM_PROPS_SCHEMA}")
            
            return NebulaPropertyGraphStore(
                space=space,
                username=username,
                password=password,
                url=url,
                overwrite=overwrite,
                props_schema=CUSTOM_PROPS_SCHEMA
            )
        
        elif db_type == GraphDBType.NEPTUNE:
            import boto3
            from botocore.config import Config
            from botocore import UNSIGNED
            
            host = config.get("host")
            port = config.get("port", 8182)
            
            # AWS Credentials - support both explicit credentials and profile-based
            access_key = config.get("access_key")
            secret_key = config.get("secret_key")
            region = config.get("region")
            credentials_profile_name = config.get("credentials_profile_name")
            
            sign = config.get("sign", True)  # Default to True for SigV4 signing
            use_https = config.get("use_https", True)  # Default to True for HTTPS
            
            if not host:
                raise ValueError("Neptune host is required (format: <GRAPH NAME>.<CLUSTER ID>.<REGION>.neptune.amazonaws.com)")
            
            logger.info(f"Creating Neptune graph store - Host: {host}:{port}")
            
            # Create boto3 client with explicit credentials if provided
            client = None
            if access_key and secret_key:
                logger.info(f"Using explicit AWS credentials with region: {region}")
                
                # Create session with explicit credentials
                session = boto3.Session(
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    region_name=region
                )
                
                # Create client parameters
                client_params = {}
                if region:
                    client_params["region_name"] = region
                
                protocol = "https" if use_https else "http"
                client_params["endpoint_url"] = f"{protocol}://{host}:{port}"
                
                # Create Neptune client
                if sign:
                    client = session.client("neptunedata", **client_params)
                else:
                    client = session.client(
                        "neptunedata",
                        **client_params,
                        config=Config(signature_version=UNSIGNED),
                    )
            elif credentials_profile_name:
                logger.info(f"Using AWS credentials profile: {credentials_profile_name}")
            elif region:
                logger.info(f"Using default AWS credentials with region: {region}")
            else:
                logger.info("Using default AWS credentials and region")
            
            graph_store = NeptuneDatabasePropertyGraphStore(
                host=host,
                port=port,
                client=client,  # Pass pre-configured client if we created one
                credentials_profile_name=credentials_profile_name if not client else None,
                region_name=region if not client else None,
                sign=sign,
                use_https=use_https
            )
            
            # Wrap the store to handle Summary API errors gracefully
            wrapped_store = NeptuneDatabaseNoSummaryWrapper(graph_store)
            logger.info("Neptune Database: Store wrapped to handle Summary API limitations")
            return wrapped_store
            # return graph_store

        elif db_type == GraphDBType.NEPTUNE_ANALYTICS:
            import boto3
            from botocore.config import Config
            
            graph_identifier = config.get("graph_identifier")
            
            # AWS Credentials - support both explicit credentials and profile-based
            access_key = config.get("access_key")
            secret_key = config.get("secret_key")
            region = config.get("region")
            credentials_profile_name = config.get("credentials_profile_name")
            
            if not graph_identifier:
                raise ValueError("Neptune Analytics graph_identifier is required")
            
            logger.info(f"Creating Neptune Analytics graph store - Graph ID: {graph_identifier}, Region: {region}")
            # Debug logging (commented out to avoid exposing credentials in logs)
            # logger.info(f"Neptune Analytics raw config received: {config}")
            # logger.info(f"Neptune Analytics config keys: {list(config.keys())}")
            # logger.info(f"Neptune Analytics: access_key present: {bool(access_key)}, secret_key present: {bool(secret_key)}")
            
            # WORKAROUND: Due to a bug in LlamaIndex Neptune Analytics client creation
            # (line 143 in neptune.py: client = client instead of client = provided_client)
            # we cannot pass a pre-configured client. Instead, we set environment variables
            # and let Neptune Analytics create its own client.
                        
            if access_key and secret_key:
                logger.info(f"Using explicit AWS credentials with region: {region}")
                
                # WORKAROUND for LlamaIndex bug: Set credentials as environment variables
                # The bug at neptune.py line 143 prevents passing a client directly
                # So we must set env vars for boto3.Session() to pick up
                import os
                os.environ['AWS_ACCESS_KEY_ID'] = access_key
                os.environ['AWS_SECRET_ACCESS_KEY'] = secret_key
                if region:
                    os.environ['AWS_DEFAULT_REGION'] = region
                
                logger.info(f"Neptune Analytics: Set AWS credentials in environment for region: {region}")
                # Debug logging (commented out to avoid exposing credentials)
                # logger.info(f"Neptune Analytics: AWS_ACCESS_KEY_ID = {access_key[:10]}... (length: {len(access_key)})")
                
                try:
                    # Don't pass client (bug prevents it from working)
                    # Don't pass credentials_profile_name (let it be None to use env vars)
                    graph_store = NeptuneAnalyticsPropertyGraphStore(
                        graph_identifier=graph_identifier,
                        region_name=region
                    )
                    logger.info("Neptune Analytics: PropertyGraphStore created successfully")
                except Exception as e:
                    logger.error(f"Neptune Analytics: Failed to create PropertyGraphStore: {e}")
                    logger.error(f"Neptune Analytics: This may indicate boto3 cannot access environment variables")
                    raise
            elif credentials_profile_name:
                logger.info(f"Using AWS credentials profile: {credentials_profile_name}")
                graph_store = NeptuneAnalyticsPropertyGraphStore(
                    graph_identifier=graph_identifier,
                    credentials_profile_name=credentials_profile_name,
                    region_name=region
                )
            else:
                logger.info(f"Using default AWS credentials with region: {region}")
                graph_store = NeptuneAnalyticsPropertyGraphStore(
                    graph_identifier=graph_identifier,
                    region_name=region
                )
            
            logger.info("Neptune Analytics: Returning graph store object of type: {type(graph_store)}")
            logger.info("Note: your Neptune Analytics graph database needs to be created with a vector dimension, your embedding dimension and its dimension need to match")
            return graph_store
        
        else:
            raise ValueError(f"Unsupported graph database: {db_type}")
    
    @staticmethod
    def create_search_store(db_type: SearchDBType, config: Dict[str, Any], vector_db_type: VectorDBType = None, llm_provider: LLMProvider = None, llm_config: Dict[str, Any] = None, app_config=None):
        """Create search store for full-text search"""
        
        logger.info(f"Creating search store with type: {db_type}")
        
        # Get embedding dimension from centralized function
        # Extract embedding configuration from app_config (Settings object)
        embedding_kind = getattr(app_config, 'embedding_kind', None) if app_config else None
        embedding_model = getattr(app_config, 'embedding_model', None) if app_config else None
        embedding_dimension = getattr(app_config, 'embedding_dimension', None) if app_config else None
        
        embed_dim = get_embedding_dimension(
            embedding_kind=embedding_kind,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension
        )
        logger.info(f"Detected embedding dimension for search store: {embed_dim} (kind: {embedding_kind}, model: {embedding_model})")
        
        if db_type == SearchDBType.NONE:
            logger.info("Full-text search disabled - no search store created")
            return None
        
        elif db_type == SearchDBType.BM25:
            # BM25 is handled differently - it's a retriever, not a store
            # We'll return None and handle it in the hybrid system
            logger.info("BM25 search selected - will be handled by BM25Retriever")
            return None
        
        elif db_type == SearchDBType.ELASTICSEARCH:
            from llama_index.vector_stores.elasticsearch import AsyncBM25Strategy
            
            index_name = config.get("index_name", "hybrid_search_fulltext")
            es_url = config.get("url", "http://localhost:9200")
            logger.info(f"Creating Elasticsearch search store - Index: {index_name}, URL: {es_url}, Embed dim: {embed_dim}")
            
            return ElasticsearchStore(
                index_name=index_name,
                es_url=es_url,
                es_user=config.get("username"),
                es_password=config.get("password"),
                retrieval_strategy=AsyncBM25Strategy()  # Explicit BM25 for keyword-only search
            )
        
        elif db_type == SearchDBType.OPENSEARCH:
            from llama_index.vector_stores.opensearch import OpensearchVectorStore, OpensearchVectorClient
            
            # Create OpenSearch vector client for fulltext search
            logger.info(f"Creating OpenSearch search store with embedding dimension: {embed_dim}")
            
            client = OpensearchVectorClient(
                endpoint=config.get("url", "http://localhost:9201"),
                index=config.get("index_name", "hybrid_search_fulltext"),
                dim=embed_dim,
                embedding_field=config.get("embedding_field", "embedding"),
                text_field=config.get("text_field", "content"),
                http_auth=(config.get("username"), config.get("password")) if config.get("username") else None
            )
            
            logger.info("OpenSearch search store created for fulltext-only search (VectorStoreQueryMode.TEXT_SEARCH)")
            return OpensearchVectorStore(client)
        
        else:
            raise ValueError(f"Unsupported search database: {db_type}")
    
    @staticmethod
    def create_bm25_retriever(docstore, config: Dict[str, Any] = None):
        """Create BM25 retriever with optional persistence"""
        
        logger.info("Creating BM25 retriever")
        
        if config is None:
            config = {}
        
        # Create BM25 retriever
        bm25_retriever = BM25Retriever.from_defaults(
            docstore=docstore,
            similarity_top_k=config.get("similarity_top_k", 10)
        )
        
        # Handle persistence if configured
        persist_dir = config.get("persist_dir")
        if persist_dir:
            # Ensure directory exists
            os.makedirs(persist_dir, exist_ok=True)
            logger.info(f"BM25 index will be persisted to: {persist_dir}")
            
            # The BM25Retriever uses the docstore which is already configured for persistence
            # The docstore will handle the actual persistence when the vector index is persisted
        
        return bm25_retriever