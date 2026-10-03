"""Configuration loading for the CocoIndex pipeline.

Reads flexible-graphrag's ``.env`` (already loaded by :mod:`bootstrap`) into two
forms:

* :func:`_load_app_settings` — the flexible-graphrag ``Settings`` object (cached),
  used by target selectors that need ``app_config.pg_graph_db`` etc.
* :func:`load_config_from_env` — a plain ``dict`` of every pipeline-relevant env
  var, serialised into CocoIndex memo keys so changing a value invalidates the
  right cache entries.

No CocoIndex imports here — this module only reads environment variables.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from process.document_processor import get_parser_type_from_env

_app_settings_singleton: Optional[Any] = None


def _load_app_settings():
    """Try to load flexible-graphrag's Settings (reads .env via Pydantic BaseSettings).

    Returns the Settings object on success, or a lightweight env-var namespace
    when flexible-graphrag is not importable (e.g. standalone CocoIndex run).

    The result is cached so Pydantic env-var parsing only runs once per process.
    """
    global _app_settings_singleton
    if _app_settings_singleton is not None:
        return _app_settings_singleton

    # flexible-graphrag uses the class name ``Settings`` (not ``AppSettings``)
    for _cls_name in ("Settings", "AppSettings"):
        try:
            import importlib
            _mod = importlib.import_module("config")
            _cls = getattr(_mod, _cls_name, None)
            if _cls is not None:
                _app_settings_singleton = _cls()
                return _app_settings_singleton
        except Exception:
            pass
    # Fallback: expose env vars as object attributes so targets can use
    # getattr(app_config, "pg_graph_db", "none") safely.
    class _EnvFallback:
        pg_graph_db = os.getenv("PG_GRAPH_DB", "none").lower()
        vector_db = os.getenv("VECTOR_DB", "none").lower()
        search_db = os.getenv("SEARCH_DB", "none").lower()
        rdf_graph_db = os.getenv("RDF_GRAPH_DB", "none").lower()
        graph_db_config: Dict[str, Any] = {}
        vector_db_config: Dict[str, Any] = {}
        search_db_config: Dict[str, Any] = {}
    _app_settings_singleton = _EnvFallback()
    return _app_settings_singleton


def load_config_from_env() -> Dict[str, Any]:
    """Read all relevant flexible-graphrag env vars into a plain dict.

    The result is passed to pipeline functions and serialised as part of
    CocoIndex's memo key — changing any value invalidates the right cache entries.
    """
    vector_db = os.getenv("VECTOR_DB", "qdrant").lower()
    pg_graph_db = os.getenv("PG_GRAPH_DB", "neo4j").lower()
    graph_backend = os.getenv("GRAPH_BACKEND", "llamaindex").lower()
    vector_backend = os.getenv("VECTOR_BACKEND", "llamaindex").lower()
    search_db = os.getenv("SEARCH_DB", "none").lower()
    rdf_graph_db = os.getenv("RDF_GRAPH_DB", "none").lower()
    llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()

    # Per-store DB config vars (matches config.py precedence)
    _vec_var = f"{vector_db.upper().replace('-', '_')}_VECTOR_DB_CONFIG"
    _pg_var = f"{pg_graph_db.upper().replace('-', '_')}_GRAPH_DB_CONFIG"
    _srch_var = f"{search_db.upper().replace('-', '_')}_SEARCH_DB_CONFIG"

    # ── Embedding resolution (computed before the dict so values can reference each other) ──
    # COCOINDEX_EMBEDDING_KIND overrides the shared EMBEDDING_KIND so the CocoIndex pipeline
    # and the main flexible-graphrag pipeline can use different embedding providers without
    # interfering with each other.
    #   sentence_transformer  — CocoIndex SentenceTransformerEmbedder (local GPU, no API key)
    #   openai | ollama | google | vertex | azure | bedrock | fireworks | openai_like | litellm
    _coco_emb_kind: str = os.getenv("COCOINDEX_EMBEDDING_KIND", "").lower()
    _main_emb_kind: str = os.getenv("EMBEDDING_KIND", "").lower()
    _resolved_emb_kind: str = _coco_emb_kind or _main_emb_kind

    # Per-kind model env var (e.g. OPENAI_EMBEDDING_MODEL when kind=openai)
    _kind_model_var: str = {
        "openai":      "OPENAI_EMBEDDING_MODEL",
        "ollama":      "OLLAMA_EMBEDDING_MODEL",
        "google":      "GOOGLE_EMBEDDING_MODEL",
        "vertex":      "VERTEX_EMBEDDING_MODEL",
        "azure":       "AZURE_EMBEDDING_MODEL",
        "bedrock":     "BEDROCK_EMBEDDING_MODEL",
        "fireworks":   "FIREWORKS_EMBEDDING_MODEL",
        "openai_like": "OPENAI_LIKE_EMBEDDING_MODEL",
        "litellm":     "LITELLM_EMBEDDING_MODEL",
    }.get(_resolved_emb_kind, "")
    _resolved_emb_model: str = (
        (os.getenv(_kind_model_var, "") if _kind_model_var else "")
        or os.getenv("COCOINDEX_EMBEDDING_MODEL", "")
        or os.getenv("EMBEDDING_MODEL", "")
    )

    # Per-kind dimension resolution:
    #   COCOINDEX_EMBEDDING_DIMENSION > {KIND}_EMBEDDING_DIMENSION > EMBEDDING_DIMENSION > 0
    # NOTE: If the CocoIndex pipeline uses a different embedder than the main pipeline,
    # the vector store collection dimension MUST match.  Use separate collection names
    # (or the same embedder in both) to avoid dimension-mismatch errors.
    _kind_dim_var: str = (
        f"{_resolved_emb_kind.upper()}_EMBEDDING_DIMENSION" if _resolved_emb_kind else ""
    )
    _resolved_emb_dim: int = int(
        os.getenv("COCOINDEX_EMBEDDING_DIMENSION", "0")
        or (os.getenv(_kind_dim_var, "0") if _kind_dim_var else "0")
        or os.getenv("EMBEDDING_DIMENSION", "0")
        or "0"
    )
    # ─────────────────────────────────────────────────────────────────────────

    return {
        # ── Source ──────────────────────────────────────────────────────────
        "data_source": os.getenv("DATA_SOURCE", "filesystem").lower(),
        #   source_backend: "flexible" (default) | "cocoindex"
        #     flexible  → always FlexibleDataSource (even filesystem) — DEFAULT
        #     cocoindex → native Coco source where wired (localfs), else flexible
        "source_backend": os.getenv("SOURCE_BACKEND", "flexible").lower(),
        # ── Document processing ─────────────────────────────────────────────
        # Internal key ``parser_type``; value from DOCUMENT_PARSER env (same as main app).
        "parser_type": get_parser_type_from_env(),
        # Docling options — mirrored to Settings fields in build_parse_cfg_json
        "docling_device": os.getenv("DOCLING_DEVICE", "auto"),
        "docling_ocr": os.getenv("DOCLING_OCR", "false").lower() == "true",
        "docling_ocr_engine": os.getenv("DOCLING_OCR_ENGINE", "auto"),
        "docling_timeout": int(os.getenv("DOCLING_TIMEOUT", "600")),
        "docling_cancel_check_interval": float(os.getenv("DOCLING_CANCEL_CHECK_INTERVAL", "0.5")),
        "parser_format_for_extraction": os.getenv("PARSER_FORMAT_FOR_EXTRACTION", "auto"),
        "save_parsing_output": os.getenv("SAVE_PARSING_OUTPUT", "false").lower() == "true",
        # LlamaParse options
        "llamaparse_tier": os.getenv("LLAMAPARSE_MODE", "cost_effective"),
        "llama_cloud_api_key": os.getenv("LLAMA_CLOUD_API_KEY") or os.getenv("LLAMAPARSE_API_KEY", ""),
        "llamaparse_language": os.getenv("LLAMAPARSE_LANGUAGE", "en"),
        "llamaparse_custom_prompt": os.getenv("LLAMAPARSE_CUSTOM_PROMPT", ""),
        # ── Chunking ────────────────────────────────────────────────────────
        "chunker_backend": os.getenv("CHUNKER_BACKEND", "llamaindex"),
        "lc_splitter_type": os.getenv("LC_SPLITTER_TYPE", "recursive"),
        "cocoindex_splitter_type": os.getenv("COCOINDEX_SPLITTER_TYPE", "recursive"),
        "cocoindex_language": os.getenv("COCOINDEX_LANGUAGE", ""),
        "cocoindex_separators": os.getenv("COCOINDEX_SEPARATORS", ""),
        "chunk_size": int(os.getenv("CHUNK_SIZE", "1024")),
        "chunk_overlap": int(os.getenv("CHUNK_OVERLAP", "128")),
        # ── LLM / Embedding provider ────────────────────────────────────────
        "llm_provider": llm_provider,
        "llm_model": (
            # Per-provider model env var (same priority as config.py)
            os.getenv("OPENAI_MODEL", "") if llm_provider == "openai" else
            os.getenv("OLLAMA_MODEL", "") if llm_provider == "ollama" else
            os.getenv("ANTHROPIC_MODEL", "") if llm_provider == "anthropic" else
            os.getenv("GEMINI_MODEL", "") if llm_provider == "gemini" else
            os.getenv("VERTEX_MODEL", "") if llm_provider == "vertex_ai" else
            os.getenv("AZURE_OPENAI_MODEL", "") if llm_provider == "azure_openai" else
            os.getenv("BEDROCK_MODEL", "") if llm_provider == "bedrock" else
            os.getenv("GROQ_MODEL", "") if llm_provider == "groq" else
            os.getenv("FIREWORKS_MODEL", "") if llm_provider == "fireworks" else
            os.getenv("OPENAI_LIKE_MODEL", "") if llm_provider == "openai_like" else
            os.getenv("VLLM_MODEL", "") if llm_provider == "vllm" else
            os.getenv("LITELLM_MODEL", "") if llm_provider == "litellm" else
            os.getenv("OPENROUTER_MODEL", "") if llm_provider == "openrouter" else
            os.getenv("REQUESTY_MODEL", "") if llm_provider == "requesty" else
            ""
        ) or os.getenv("LLM_MODEL", ""),
        "llm_config_json": "{}",
        # embedding_kind / model / dimension resolved from env vars above the dict.
        "embedding_kind": _resolved_emb_kind,
        "embedding_model": _resolved_emb_model,
        "embedding_dimension": _resolved_emb_dim,
        # Sentence-transformer model (used when embedding_kind == "sentence_transformer").
        # Priority: COCOINDEX_EMBEDDING_MODEL > EMBEDDING_MODEL > "all-MiniLM-L6-v2" (default in _embed_chunks_cached).
        "cocoindex_embedding_model": os.getenv("COCOINDEX_EMBEDDING_MODEL", "") or os.getenv("EMBEDDING_MODEL", ""),
        # ── KG extraction ───────────────────────────────────────────────────
        "enable_knowledge_graph": os.getenv("ENABLE_KNOWLEDGE_GRAPH", "true").lower() == "true",
        "kg_extractor_backend": os.getenv("KG_EXTRACTOR_BACKEND", "llamaindex"),
        "kg_extractor_type": os.getenv("KG_EXTRACTOR_TYPE", "schema"),
        # Entity-name de-duplication applied to one document's extracted triples.
        #   none      (default) — unchanged behaviour, no extra dependency
        #   normalize — folds accents/case/punctuation; pure Python, no extra deps
        #   llm       — also merges "Bob" into "Bob Smith"; REQUIRES
        #               uv pip install "cocoindex[entity_resolution]" (faiss).
        #               Without it, degrades to normalize with a warning rather
        #               than failing the ingest.
        "entity_resolution": os.getenv("ENTITY_RESOLUTION", "none").lower(),
        "schema_name": os.getenv("SCHEMA_NAME", ""),
        "strict_schema_validation": os.getenv("STRICT_SCHEMA_VALIDATION", "false").lower() == "true",
        "max_triplets_per_chunk": int(os.getenv("MAX_TRIPLETS_PER_CHUNK", "20")),
        "disable_properties": os.getenv("DISABLE_PROPERTIES", "false").lower() == "true",
        # ── Ontology ────────────────────────────────────────────────────────
        "use_ontology": os.getenv("USE_ONTOLOGY", "false").lower() == "true",
        "ontology_paths": os.getenv("ONTOLOGY_PATHS", ""),
        "ontology_dir": os.getenv("ONTOLOGY_DIR", ""),
        # ── Backend framework selectors ──────────────────────────────────────
        #   graph_backend:  "llamaindex" | "langchain" → FlexiblePGTarget
        #                   "cocoindex"                → CocoIndex native connector
        "graph_backend": graph_backend,
        #   vector_backend: "llamaindex" | "langchain" → FlexibleVectorTarget
        #                   "cocoindex"                → CocoIndex native connector
        "vector_backend": vector_backend,
        # ── Stores ──────────────────────────────────────────────────────────
        "vector_db": vector_db,
        "vector_db_config_json": os.getenv(_vec_var, os.getenv("VECTOR_DB_CONFIG", "{}")),
        "pg_graph_db": pg_graph_db,
        "pg_graph_db_config_json": os.getenv(_pg_var, os.getenv("GRAPH_DB_CONFIG", "{}")),
        "rdf_graph_db": rdf_graph_db,
        "search_db": search_db,
        "search_db_config_json": os.getenv(_srch_var, os.getenv("SEARCH_DB_CONFIG", "{}")),
    }
