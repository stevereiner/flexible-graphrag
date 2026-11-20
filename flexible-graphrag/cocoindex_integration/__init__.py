"""
flexible-graphrag CocoIndex 1.x Integration
============================================

Two integration directions:

A. flexible-graphrag as CocoIndex components (external CocoIndex pipelines)
   - ``functions/``  — @coco.fn doc-parsing, chunking, KG-extraction
   - ``connectors/`` — layered connector framework, split by family:
       * ``connectors/flexible/`` — FlexibleVector, FlexiblePropertyGraph,
         FlexibleRDFGraph, FlexibleSearch (wrap fg adapters); FlexibleDataSource
         (wraps all 14 fg datasource adapters)
       * ``connectors/cocoindex/`` — CocoIndex-native connectors
       * ``connectors/rows`` — shared row dataclasses (the convention seam)

B. CocoIndex as optional pipeline backend inside flexible-graphrag
   - ``pipeline/``   — coco.App wrapping the full flexible-graphrag ingest pipeline
   - Set ``GRAPH_BACKEND=cocoindex`` in .env to activate

LLM providers — ``functions.llm`` (reads ``LLM_PROVIDER``)
----------------------------------------------------------
All 11 flexible-graphrag providers: openai, azure, ollama, google, vertex,
bedrock, fireworks, openai_like, litellm, openrouter, requesty, vllm.
``get_llama_index_llm()``, ``get_langchain_llm()``.

Embedding providers — ``functions.embedding`` (reads ``EMBEDDING_KIND``)
-------------------------------------------------------------------------
Independent of LLM_PROVIDER.  Supported: openai, azure, ollama, google,
vertex, bedrock, openai_like, litellm, vllm.
Not supported (LLM-only): fireworks, openrouter, requesty, groq.
``get_llamaindex_embedding()``, ``get_langchain_embedding()``.

For in-pipeline embeddings CocoIndex's built-in connectors are preferred::
  coco.functions.LiteLLM.text_embedding(text=…, model=…)
  coco.functions.SentenceTransformer.encode(text=…, model=…)

KG extraction flags
--------------------
All flexible-graphrag extraction config flags are honoured:
  USE_ONTOLOGY, KG_EXTRACTOR_TYPE, SCHEMA_NAME, STRICT_SCHEMA_VALIDATION,
  DISABLE_PROPERTIES, MAX_TRIPLETS_PER_CHUNK

Target / connector selection
-----------------------------
GRAPH_BACKEND=llamaindex|langchain  → FlexiblePGGraphTarget (fg adapters)
GRAPH_BACKEND=cocoindex             → native CocoIndex connector (neo4j, falkordb, …)

CocoIndex native connectors (source/target classification):
  Source only  : Amazon S3, Google Drive, Local filesystem, OCI Object Storage
  Target only  : Qdrant, LanceDB, Turbopuffer, zvec, Neo4j, FalkorDB,
                 Apache Doris, Valkey
  Both         : Postgres, SQLite, SurrealDB, Kafka, Iggy

State management
-----------------
CocoIndex 1.x open-source uses LMDB for memoisation state.
flexible-graphrag's Postgres ``document_state`` table (cloud-source polling,
UI dashboard) is kept in parallel — the two are complementary.
"""

__all__ = [
    "functions",
    "connectors",
    "pipeline",
]

# NOTE: these imports are deliberately EAGER.
#
# They are the convenience API for direction A (someone writing their own
# CocoIndex pipeline does ``from cocoindex_integration import
# get_llama_index_llm``), but they are also load-bearing for the pipeline
# itself: importing ``connectors.cocoindex`` pulls in every native vector and
# property-graph module, which is what populates COCO_VECTOR_REGISTRY /
# COCO_PG_REGISTRY and registers the native target types with CocoIndex.
#
# Making these lazy (PEP 562 ``__getattr__``) looks harmless — nothing in this
# package imports them from the package root — and cuts ~400 modules off a bare
# ``import cocoindex_integration.monitoring``.  It was tried on 2026-08-15 and
# broke the native pipeline: with the native modules unimported at backend
# start, root mounting failed with
#   [native/qdrant] root collection mount failed: 'flexible-graphrag/qdrant'
#   [native/neo4j]  root table mount failed: 'flexible-graphrag/neo4j'
# and every native vector target (qdrant, lancedb, postgres) plus native neo4j
# failed in the overnight matrix, with no ImportError anywhere to point at the
# cause.  The import side effect IS the registration; do not defer it.
try:
    # LLM text-generation providers (LLM_PROVIDER env var)
    from cocoindex_integration.functions.llm import (
        get_llama_index_llm,
        get_langchain_llm,
        DYNAMIC_LLM_PROVIDERS,
        provider_from_env,
    )
    # Embedding providers (EMBEDDING_KIND env var) — independent of LLM_PROVIDER
    from cocoindex_integration.functions.embedding import (
        get_llamaindex_embedding,
        get_langchain_embedding,
        embedding_kind_from_env,
        supports_embeddings,
        EMBEDDING_ONLY_PROVIDERS,
    )
    from cocoindex_integration.functions.kg_extraction import (
        load_ontology_schema_json,
        load_extractor_config_json,
        extract_kg_llamaindex,
        extract_kg_langchain,
        KGResult,
        KGTriple,
        KGEntity,
    )
    from cocoindex_integration.connectors.flexible.source import FlexibleDataSource
    from cocoindex_integration.pipeline.app import (
        load_config_from_env,
        process_document,
        build_flexible_source_app,
        # A single app_main (flexible_app_main) handles every source; native
        # CocoIndex sources are dispatched via native_apps.NATIVE_READERS.
    )
    from cocoindex_integration.connectors.cocoindex import (
        CocoVectorRow,
        CocoKGTripleRow,
        coco_vector_target,
        coco_pg_target,
        COCO_VECTOR_TARGETS,
        COCO_PG_TARGETS,
    )
except ImportError:
    # Graceful degradation when optional deps are missing
    pass
