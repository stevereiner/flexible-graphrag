"""
Node ingestion pipeline builder for Flexible GraphRAG.

Provides a single canonical IngestionPipeline (split + embed) that every
processing path (vector index, property graph, RDF export) shares, ensuring
consistent chunk boundaries and metadata across the whole system.
"""

from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
import logging

logger = logging.getLogger(__name__)


def build_ingestion_pipeline(config, embed_model) -> IngestionPipeline:
    """Build the canonical IngestionPipeline for all processing paths.

    Uses config.chunk_size and config.chunk_overlap so every downstream
    consumer (vector index, property graph, RDF export) operates on the
    same pre-chunked node list.

    Args:
        config: AppSettings instance
        embed_model: LlamaIndex embedding model

    Returns:
        Configured IngestionPipeline (not yet run)
    """
    # tokenizer=list makes chunk_size/chunk_overlap count *characters* instead of
    # tokens (default tiktoken). CHUNK_SIZE=2048 → 2048 chars, matching LangChain's
    # RecursiveCharacterTextSplitter behaviour — no mental token arithmetic needed.
    transformations = [
        SentenceSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            tokenizer=list,
        ),
        embed_model,
    ]
    return IngestionPipeline(transformations=transformations)


def build_embed_only_pipeline(embed_model) -> IngestionPipeline:
    """Build an IngestionPipeline that only embeds, without splitting.

    Used when ``CHUNKER_BACKEND=langchain``: the LangChain splitter has
    already produced ``TextNode`` objects, so we only need to run the
    embedding transformation before downstream consumers receive the nodes.

    Args:
        embed_model: LlamaIndex embedding model

    Returns:
        Configured IngestionPipeline with embed_model as the sole transform
    """
    return IngestionPipeline(transformations=[embed_model])
