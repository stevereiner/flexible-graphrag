"""Create the Weaviate collection with a vector index before a LlamaIndex or LangChain store does.

Weaviate 1.40+ gives a collection created without vector settings no vector index at all. The
LlamaIndex and LangChain Weaviate stores create their collection that way, so every insert was
rejected ("configured without a vector index, but received a vector") and every search failed
('index for target vector "" not found'). Here the collection gets one vector that we provide (no
vectorizer, HNSW index), which works with Weaviate 1.24+. A collection that already exists is left
as it is, except an empty one without a vector index, which is made again.
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_VECTOR_CONFIG = {"default": {"vectorizer": {"none": {}}, "vectorIndexType": "hnsw"}}


def ensure_weaviate_collection(client: Any, name: str, properties: List[Dict[str, Any]]) -> None:
    """Make collection *name* with *properties* and a vector index, unless a usable one exists.

    *client* is a sync weaviate v4 client.
    """
    if client.collections.exists(name):
        collection = client.collections.get(name)
        config = collection.config.get()
        if config.vector_config or config.vector_index_config:
            return
        if len(collection) > 0:
            logger.error(
                "Weaviate collection %s has no vector index, so vector inserts and searches fail. "
                "Delete it (it holds no vectors) and ingest again.",
                name,
            )
            return
        logger.info("Weaviate collection %s is empty and has no vector index: making it again", name)
        client.collections.delete(name)
    client.collections.create_from_dict(
        {
            "class": name,
            "description": f"Class for {name}",
            "properties": properties,
            "vectorConfig": _VECTOR_CONFIG,
        }
    )
    logger.info("Weaviate collection %s created with a vector index", name)
