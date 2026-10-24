"""Creates the OpenArch store of a Flexible GraphRAG system (ENABLE_OPENARCH)."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# OpenArch's embeddings index has a fixed vector size (opensearch-embeddings-mapping.json)
OPENARCH_DIMENSION = 1024


def build_openarch_store(config: Dict[str, Any], embed_dim: Optional[int] = None):
    """An :class:`~openarch.OpenArchVectorStore` from the OpenArch settings
    (``config.openarch_settings``)."""
    from openarch.client import OpenArchClient
    from openarch.vector_store import OpenArchVectorStore
    from openarch.writer import embedding_type_name

    if embed_dim and embed_dim != OPENARCH_DIMENSION:
        logger.warning(
            "OpenArch indexes %d-dimension vectors only, but the embedding dimension is %s: its "
            "chunks won't be searchable. Set the embedding dimension to %d (for OpenAI "
            "text-embedding-3-*: OPENAI_EMBEDDING_DIMENSION=%d).",
            OPENARCH_DIMENSION, embed_dim, OPENARCH_DIMENSION, OPENARCH_DIMENSION)
    client = OpenArchClient(
        url=config.get("url", "http://localhost:8080"),
        username=config.get("username", "admin"),
        password=config.get("password", "password"),
        repository=config.get("repository", "default"),
        timeout=float(config.get("timeout", 60)),
    )
    embedding_type = config.get("embedding_type") or embedding_type_name(
        config.get("embedding_kind"), config.get("embedding_model"), embed_dim)
    store = OpenArchVectorStore(
        client,
        embedding_type=embedding_type,
        root_path=config.get("root_path", "/fg-sources"),
        max_text_chars=int(config.get("max_text_chars", 64000)),
        write_concurrency=int(config.get("write_concurrency", 4)),
    )
    logger.info("OpenArch: url=%s repository=%s root=%s embedding_type=%s",
                client.url, client.repository, config.get("root_path", "/fg-sources"), embedding_type)
    return store


def remove_ingested(client, root_path: str = "/fg-sources") -> Dict[str, int]:
    """Delete what Flexible GraphRAG ingested under ``root_path``: its documents (those with
    Flexible GraphRAG doc ids) with their chunks, then the folders left empty. Anything else in
    the tree stays. Returns ``{"documents": n, "folders": m}``."""
    from openarch.client import hxql_literal
    from openarch.writer import DOC_IDS_KEY

    root = client.get_by_path("/" + root_path.strip("/"))
    if root is None:
        return {"documents": 0, "folders": 0}
    under = f"sys_ancestorIds = {hxql_literal(root['sys_id'])}"
    removed = 0
    for doc in client.query_all(f"SELECT * FROM SysFile WHERE {under}"):
        if DOC_IDS_KEY not in (doc.get("cin_ingestProperties") or {}):
            continue
        # Chunks first: their deletion with the parent is not guaranteed
        for child in client.query_all(
                f"SELECT * FROM SysEmbeddings WHERE sys_parentId = {hxql_literal(doc['sys_id'])}"):
            client.delete(child["sys_id"])
        client.delete(doc["sys_id"])
        removed += 1
    return {"documents": removed, "folders": remove_empty_folders(client, root_path)}


def remove_empty_folders(client, root_path: str) -> int:
    """Delete the folders under ``root_path`` left with nothing in them, deepest first, then the
    root itself if nothing else is left. Returns how many."""
    from openarch.client import hxql_literal

    root = client.get_by_path("/" + root_path.strip("/"))
    if root is None:
        return 0
    folders = client.query_all(f"SELECT * FROM SysFolder WHERE sys_ancestorIds = {hxql_literal(root['sys_id'])}")
    folders.sort(key=lambda f: str(f.get("sys_path") or "").count("/"), reverse=True)
    deleted = 0
    for folder in folders + [root]:
        if not client.query(f"SELECT * FROM SysContent WHERE sys_parentId = {hxql_literal(folder['sys_id'])}",
                            limit=1)["documents"]:
            client.delete(folder["sys_id"])
            deleted += 1
    return deleted


def setup_openarch(system) -> None:
    """Attach the OpenArch store and its index to ``system`` (``openarch_store``,
    ``openarch_index``) when ENABLE_OPENARCH is on; both stay None otherwise."""
    config = system.config
    system.openarch_store = None
    system.openarch_index = None
    if not getattr(config, "enable_openarch", False):
        return
    from llama_index.core import StorageContext, VectorStoreIndex
    from llamaindex.llm.embedding_factory import get_embedding_dimension

    embed_dim = get_embedding_dimension(
        embedding_kind=getattr(config, "embedding_kind", None),
        embedding_model=getattr(config, "embedding_model", None),
        embedding_dimension=getattr(config, "embedding_dimension", None),
    )
    store = build_openarch_store(config.openarch_config, embed_dim)
    system.openarch_store = store
    system.openarch_index = VectorStoreIndex(
        nodes=[], storage_context=StorageContext.from_defaults(vector_store=store), show_progress=False)
