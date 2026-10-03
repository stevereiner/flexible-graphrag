"""
@coco.fn KG extraction with ontology-first design.

Quick-start::

    from cocoindex_integration.functions.kg_extraction import (
        load_ontology_schema_json,
        load_extractor_config_json,
        extract_kg_llamaindex,
    )

    # Once per pipeline run — loads .ttl files, result is a stable JSON string
    schema_json   = load_ontology_schema_json()   # reads ONTOLOGY_PATHS / ONTOLOGY_DIR
    extractor_cfg = load_extractor_config_json()  # reads KG_EXTRACTOR_TYPE etc.

    # Per chunk — CocoIndex caches on (chunk_text, schema_json, extractor_cfg, …)
    kg = await extract_kg_llamaindex(
        chunk_text,
        schema_json=schema_json,
        extractor_config_json=extractor_cfg,
    )

Ontology auto-detection
------------------------
``load_ontology_schema_json()`` reads ``USE_ONTOLOGY``, ``ONTOLOGY_PATHS``, and
``ONTOLOGY_DIR`` from the environment (same as flexible-graphrag's main pipeline):

  USE_ONTOLOGY=true + ONTOLOGY_PATHS=../schemas/company_classes.ttl,...
    → ontology loaded; extraction guided by entity/relation types in the .ttl files.
  USE_ONTOLOGY=false  (or no .ttl files configured)
    → schema_json="{}" returned; extractor uses free-form or built-in schema.

Extraction modes  (``KG_EXTRACTOR_TYPE``)
------------------------------------------
LlamaIndex backend (``extract_kg_llamaindex``):

  ``schema`` (default)
      SchemaLLMPathExtractor — ontology entity/relation types constrain the
      LLM via structured tool calling.  ``STRICT_SCHEMA_VALIDATION=true`` rejects
      triples that don't match the schema.  Cap: ``MAX_TRIPLETS_PER_CHUNK``.

  ``dynamic``
      DynamicLLMPathExtractor — ontology types used as *guidance* (not hard
      constraints); allows the LLM to discover types not in the schema.
      Automatically selected for providers that don't support
      ``tool_choice=required`` (bedrock, fireworks, groq, openai_like, vllm, …).
      Cap: ``MAX_TRIPLETS_PER_CHUNK``.

  ``simple``
      SimpleLLMPathExtractor — fully free-form; no ontology or schema guidance.
      Cap: ``MAX_PATHS_PER_CHUNK`` (this extractor uses *paths*, not *triplets*).

LangChain backend (``extract_kg_langchain``):

  ``LLMGraphTransformer`` — single extractor type; no simple/dynamic/schema split.
  When an ontology is present: ``allowed_nodes`` / ``allowed_relationships`` set.
  ``STRICT_SCHEMA_VALIDATION=true`` maps to ``strict_mode=True``.
  **No** per-chunk limit — extracts however many triples the LLM returns.
  ``MAX_TRIPLETS_PER_CHUNK`` and ``MAX_PATHS_PER_CHUNK`` are both ignored.

``extractor_config_json``
--------------------------
A fingerprint-friendly JSON string of the remaining env-driven flags.  Build it
once with ``load_extractor_config_json()`` and pass it to every extraction call.
When any flag changes, CocoIndex invalidates the extraction cache automatically.

  KG_EXTRACTOR_TYPE         schema | dynamic | simple  (default: schema)
  SCHEMA_NAME               named built-in schema used without an ontology
  STRICT_SCHEMA_VALIDATION  reject triples outside the schema  (default: false)
  DISABLE_PROPERTIES        skip datatype property extraction   (default: false)
  MAX_TRIPLETS_PER_CHUNK    cap for schema / dynamic extractors (default: 20)
  MAX_PATHS_PER_CHUNK       cap for simple extractor only       (default: 20)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import cocoindex as coco
    _COCO_AVAILABLE = True
except ImportError:
    _COCO_AVAILABLE = False

    class _FnShim:
        def __call__(self, fn=None, **kw):
            if fn is not None:
                return fn
            def decorator(f): return f
            return decorator

    class _CocoShim:
        fn = _FnShim()
    coco = _CocoShim()  # type: ignore[assignment]


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KGTriple:
    """A (subject, predicate, object) triple."""
    subject: str
    predicate: str
    obj: str
    subject_type: str = ""
    obj_type: str = ""
    relation_properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KGEntity:
    """An entity node."""
    label: str
    entity_type: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KGResult:
    """Extraction result for one chunk."""
    triples: List[KGTriple] = field(default_factory=list)
    entities: List[KGEntity] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Public loaders — call these once per pipeline run
# ─────────────────────────────────────────────────────────────────────────────

def load_ontology_schema_json(
    ontology_paths: Optional[str] = None,
    ontology_dir: Optional[str] = None,
    use_ontology: Optional[bool] = None,
) -> str:
    """Load the domain ontology and return it as a JSON string.

    This is the **primary** way to guide KG extraction.  Pass the returned
    string as ``schema_json`` to every ``extract_kg_*`` call.  Because
    CocoIndex fingerprints all function arguments, changing any ontology file
    automatically invalidates the extraction cache for every affected chunk —
    no manual cache clearing needed.

    Parameters
    ----------
    ontology_paths:
        Comma-separated ``.ttl`` file paths.
        Falls back to ``ONTOLOGY_PATHS`` env var.
    ontology_dir:
        Directory of ``.ttl`` files.
        Falls back to ``ONTOLOGY_DIR`` env var.
    use_ontology:
        Explicit override for ``USE_ONTOLOGY`` env var (default False).

    Returns
    -------
    JSON string with keys ``entity_types``, ``relation_types``,
    ``entity_props``, ``relation_props``.  Returns ``"{}"`` when no
    ontology is configured or ``use_ontology`` is False.

    Example
    -------
    ::

        # .env: ONTOLOGY_PATHS=../schemas/company_classes.ttl,../schemas/company_props.ttl
        schema_json = load_ontology_schema_json()
        # schema_json now contains 16 entity types, 22 relation types …
    """
    _use = (
        use_ontology
        if use_ontology is not None
        else os.getenv("USE_ONTOLOGY", "false").lower() == "true"
    )
    if not _use:
        return "{}"

    paths_str = ontology_paths or os.getenv("ONTOLOGY_PATHS", "")
    odir = ontology_dir or os.getenv("ONTOLOGY_DIR", "")
    if not paths_str and not odir:
        return "{}"

    try:
        from rdf.ontology_manager import OntologyManager
        mgr = OntologyManager()

        if paths_str:
            path_list = [p.strip() for p in paths_str.split(",") if p.strip()]
            if hasattr(mgr, "load_ontology_files"):
                mgr.load_ontology_files(path_list)
            else:
                for p in path_list:
                    mgr.load_ontology(p)

        if odir:
            if hasattr(mgr, "load_ontology_dir"):
                mgr.load_ontology_dir(odir)
            else:
                import glob as _g
                for fp in _g.glob(os.path.join(odir, "*.ttl")):
                    mgr.load_ontology(fp)

        entity_types: List[str] = getattr(mgr, "get_entities_literal", lambda: [])() or []
        relation_types: List[str] = getattr(mgr, "get_relations_literal", lambda: [])() or []
        entity_props: List[List[str]] = []
        relation_props: List[List[str]] = []

        if hasattr(mgr, "get_entity_props"):
            entity_props = [[str(n), str(t)] for n, t in (mgr.get_entity_props() or [])]  # type: ignore[attr-defined]
        elif hasattr(mgr, "get_xsd_type_map"):
            entity_props = [[k, v] for k, v in (mgr.get_xsd_type_map() or {}).items()]
        if hasattr(mgr, "get_relation_props"):
            relation_props = [[str(n), str(t)] for n, t in (mgr.get_relation_props() or [])]  # type: ignore[attr-defined]

        logger.debug(
            "Ontology: %d entity types, %d relation types, "
            "%d entity props, %d relation props",
            len(entity_types), len(relation_types),
            len(entity_props), len(relation_props),
        )
        return json.dumps({
            "entity_types": entity_types,
            "relation_types": relation_types,
            "entity_props": entity_props,
            "relation_props": relation_props,
        })

    except Exception as exc:
        logger.warning("load_ontology_schema_json failed (%s) — no ontology guidance", exc)
        return "{}"


def load_extractor_config_json() -> str:
    """Read KG extractor flags from env and return them as a JSON string.

    Pass this as ``extractor_config_json`` to ``extract_kg_*``.
    CocoIndex fingerprints it so changing any flag automatically invalidates
    the extraction cache for every affected chunk.

    Reads
    -----
    ``KG_EXTRACTOR_TYPE``        schema | dynamic | simple  (default: schema)
    ``SCHEMA_NAME``              named built-in schema (used without ontology)
    ``STRICT_SCHEMA_VALIDATION`` bool  (default: false)
    ``DISABLE_PROPERTIES``       bool  (default: false)
    ``MAX_TRIPLETS_PER_CHUNK``   int — cap for *schema* and *dynamic* extractors
                                 (SchemaLLMPathExtractor / DynamicLLMPathExtractor)
    ``MAX_PATHS_PER_CHUNK``      int — cap for the *simple* extractor only
                                 (SimpleLLMPathExtractor uses paths, not triplets)

    LangChain note
    --------------
    ``LLMGraphTransformer`` has **no** equivalent limit parameter — it extracts
    as many triples as the LLM returns.  Both ``max_triplets`` and
    ``max_paths`` are therefore LlamaIndex-only and silently ignored on the
    LangChain path.
    """
    return json.dumps({
        "extractor_type": os.getenv("KG_EXTRACTOR_TYPE", "schema"),
        "schema_name": os.getenv("SCHEMA_NAME", ""),
        "strict_schema_validation": os.getenv("STRICT_SCHEMA_VALIDATION", "false").lower() == "true",
        "disable_properties": os.getenv("DISABLE_PROPERTIES", "false").lower() == "true",
        # schema / dynamic extractor limit
        "max_triplets": int(os.getenv("MAX_TRIPLETS_PER_CHUNK", "20")),
        # simple extractor limit (SimpleLLMPathExtractor only)
        "max_paths": int(os.getenv("MAX_PATHS_PER_CHUNK", "20")),
    }, sort_keys=True)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json(s: str) -> Dict[str, Any]:
    if not s or s.strip() in ("{}", ""):
        return {}
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {}


def _props_to_tuples(raw: List[List[str]], disabled: bool) -> List[Tuple[str, str]]:
    if disabled:
        return []
    return [(str(r[0]), str(r[1]) if len(r) > 1 else "str") for r in raw]


#: Providers that must use DynamicLLMPathExtractor (mirrors hybrid_system.py).
_DYNAMIC_PROVIDERS = frozenset({
    "bedrock", "fireworks", "groq", "openai_like", "openrouter", "requesty", "vllm",
})
_KG_TIMEOUT = int(os.getenv("KG_EXTRACTION_TIMEOUT", "120"))


def _effective_extractor_type(provider: str, requested: str) -> str:
    p = provider.lower()
    if p == "litellm" and os.getenv("LITELLM_MODEL", "").startswith("ollama/"):
        return "dynamic"
    if p in _DYNAMIC_PROVIDERS:
        return "dynamic"
    return requested


# ─────────────────────────────────────────────────────────────────────────────
# LlamaIndex extraction core
# ─────────────────────────────────────────────────────────────────────────────

async def _extract_li_async(
    chunk_text: str,
    schema: Dict[str, Any],          # parsed ontology (may be empty)
    exc_cfg: Dict[str, Any],         # parsed extractor_config_json
    llm,
    provider: str,
) -> KGResult:
    has_ontology = bool(schema)
    eff_type = _effective_extractor_type(
        provider, exc_cfg.get("extractor_type", "schema")
    )
    disable_props = exc_cfg.get("disable_properties", False)
    strict = exc_cfg.get("strict_schema_validation", False)
    max_triplets = exc_cfg.get("max_triplets", 20)
    max_paths = exc_cfg.get("max_paths", 20)
    schema_name = exc_cfg.get("schema_name", "")

    entity_types: List[str] = schema.get("entity_types", []) if has_ontology else []
    relation_types: List[str] = schema.get("relation_types", []) if has_ontology else []
    entity_props = _props_to_tuples(schema.get("entity_props", []), disable_props)
    relation_props = _props_to_tuples(schema.get("relation_props", []), disable_props)

    # Build extractor directly from LlamaIndex primitives.
    # (flexible-graphrag's make_kg_extractor expects a full system object with
    # schema_manager / llm attached — not suitable for the CocoIndex fn context.)
    extractor = _build_extractor(
        llm, eff_type, entity_types, relation_types,
        entity_props, relation_props,
        max_triplets, max_paths, schema_name, strict,
    )

    if extractor is None:
        return KGResult()

    try:
        from llama_index.core.schema import TextNode
        node = TextNode(text=chunk_text)

        async def _do():
            if hasattr(extractor, "acall"):
                return await extractor.acall([node])
            return extractor([node])

        nodes = await asyncio.wait_for(_do(), timeout=_KG_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("KG extraction timed out (%ds)", _KG_TIMEOUT)
        return KGResult()
    except Exception as exc:
        logger.warning("KG extraction error: %s", exc, exc_info=True)
        return KGResult()

    result = _li_nodes_to_result(nodes)
    logger.debug(
        "_extract_li_async: nodes=%d triples=%d entities=%d",
        len(nodes or []), len(result.triples), len(result.entities),
    )
    return result


def _build_extractor(
    llm, eff_type: str,
    entity_types: List[str], relation_types: List[str],
    entity_props: List[Tuple[str, str]], relation_props: List[Tuple[str, str]],
    max_triplets: int, max_paths: int, schema_name: str, strict: bool,
):
    """Build the appropriate LlamaIndex KG path extractor.

    Extractor                   limit param          when used
    ─────────────────────────── ──────────────────── ────────────────────────────
    SimpleLLMPathExtractor      max_paths_per_chunk  eff_type == "simple"
    DynamicLLMPathExtractor     max_triplets_per_…   eff_type == "dynamic"
    SchemaLLMPathExtractor      max_triplets_per_…   eff_type == "schema" (default)
    """
    try:
        if eff_type == "simple":
            # SimpleLLMPathExtractor: free-form path extraction, no schema guidance.
            # Uses max_paths_per_chunk (MAX_PATHS_PER_CHUNK env var).
            from llama_index.core.indices.property_graph import SimpleLLMPathExtractor
            return SimpleLLMPathExtractor(llm=llm, max_paths_per_chunk=max_paths)

        if eff_type == "dynamic":
            # DynamicLLMPathExtractor: ontology-guided, dynamic schema.
            # Uses max_triplets_per_chunk (MAX_TRIPLETS_PER_CHUNK env var).
            from llama_index.core.indices.property_graph import DynamicLLMPathExtractor
            kw: Dict[str, Any] = {"llm": llm, "max_triplets_per_chunk": max_triplets}
            if entity_types: kw["allowed_entity_types"] = entity_types
            if relation_types: kw["allowed_relation_types"] = relation_types
            return DynamicLLMPathExtractor(**kw)

        # "schema" (default): structured extraction with explicit type lists.
        # Uses max_triplets_per_chunk (MAX_TRIPLETS_PER_CHUNK env var).
        from llama_index.core.indices.property_graph import SchemaLLMPathExtractor
        kw = {"llm": llm, "max_triplets_per_chunk": max_triplets, "strict": strict}
        if entity_types: kw["possible_entities"] = entity_types
        if relation_types: kw["possible_relations"] = relation_types
        if entity_props: kw["possible_entity_props"] = entity_props
        if relation_props: kw["possible_relation_props"] = relation_props
        if schema_name and not entity_types:
            logger.debug("No ontology — using built-in schema '%s'", schema_name)
        return SchemaLLMPathExtractor(**kw)
    except Exception as exc:
        logger.warning("_build_extractor failed: %s", exc)
        return None


def _li_nodes_to_result(nodes) -> KGResult:
    """Convert LlamaIndex extracted nodes to KGResult using duck-typed access.

    Uses getattr throughout so this works regardless of the exact LlamaIndex
    version (EntityNode / Relation class paths change between versions).

    LlamaIndex stores KG results in node metadata under the constants
    KG_RELATIONS_KEY = "__relations__" and KG_NODES_KEY = "__nodes__".
    The extractor modifies the input TextNode's metadata in-place and returns it.
    """
    # Import the actual LlamaIndex metadata key constants; fall back to string
    # literals so this still works if the import path changes between versions.
    try:
        from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY
    except ImportError:
        # LlamaIndex 0.10+: "nodes" / "relations"
        KG_NODES_KEY = "nodes"
        KG_RELATIONS_KEY = "relations"

    triples, entities = [], []

    # First pass: collect all entity nodes and build a name → type lookup.
    # LlamaIndex Relation.source_id / target_id are entity-name strings;
    # entity TYPE lives on EntityNode.label, not on the Relation.
    entity_type_map: Dict[str, str] = {}
    for node in (nodes or []):
        meta = getattr(node, "metadata", {})
        for en in meta.get(KG_NODES_KEY, []):
            name = getattr(en, "name", None)
            if name is None:
                continue
            etype = str(getattr(en, "label", "") or "")
            entity_type_map[str(name)] = etype
            entities.append(KGEntity(
                label=str(name or ""),
                entity_type=etype,
                properties=dict(getattr(en, "properties", {}) or {}),
            ))

    # Second pass: build triples, resolving entity types via the map.
    for node in (nodes or []):
        meta = getattr(node, "metadata", {})
        for rel in meta.get(KG_RELATIONS_KEY, []):
            src = getattr(rel, "source_id", None)
            tgt = getattr(rel, "target_id", None)
            if src is None and tgt is None:
                continue
            # source_id / target_id are entity-name strings in LlamaIndex.
            src_name = str(getattr(src, "name", src) or "")
            tgt_name = str(getattr(tgt, "name", tgt) or "")
            triples.append(KGTriple(
                subject=src_name,
                predicate=str(getattr(rel, "label", "") or ""),
                obj=tgt_name,
                subject_type=entity_type_map.get(src_name, ""),
                obj_type=entity_type_map.get(tgt_name, ""),
                relation_properties=dict(getattr(rel, "properties", {}) or {}),
            ))

    return KGResult(triples=triples, entities=entities)


# ─────────────────────────────────────────────────────────────────────────────
# LangChain extraction core
# ─────────────────────────────────────────────────────────────────────────────

async def _extract_lc_async(
    chunk_text: str,
    schema: Dict[str, Any],
    exc_cfg: Dict[str, Any],
    lc_llm,
) -> KGResult:
    has_ontology = bool(schema)
    strict = exc_cfg.get("strict_schema_validation", False)

    entity_types: List[str] = schema.get("entity_types", []) if has_ontology else []
    relation_types: List[str] = schema.get("relation_types", []) if has_ontology else []

    try:
        from langchain_experimental.graph_transformers import LLMGraphTransformer  # type: ignore[import-untyped]
        kw: Dict[str, Any] = {"llm": lc_llm}
        if entity_types: kw["allowed_nodes"] = entity_types
        if relation_types: kw["allowed_relationships"] = relation_types
        if strict: kw["strict_mode"] = True
        transformer = LLMGraphTransformer(**kw)
    except ImportError:
        logger.warning("langchain_experimental not installed")
        return KGResult()

    try:
        from langchain_core.documents import Document as LCDoc  # type: ignore[import-untyped]
        def _transform():
            return transformer.convert_to_graph_documents([LCDoc(page_content=chunk_text)])
        graph_docs = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _transform),
            timeout=_KG_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("LangChain KG extraction timed out (%ds)", _KG_TIMEOUT)
        return KGResult()
    except Exception as exc:
        logger.warning("LangChain KG extraction error: %s", exc)
        return KGResult()

    triples, entities = [], []
    for gd in (graph_docs or []):
        for node in getattr(gd, "nodes", []):
            entities.append(KGEntity(
                label=str(node.id or ""),
                entity_type=str(node.type or ""),
                properties=dict(node.properties or {}),
            ))
        for rel in getattr(gd, "relationships", []):
            triples.append(KGTriple(
                subject=str(getattr(rel.source, "id", "") or ""),
                predicate=str(rel.type or ""),
                obj=str(getattr(rel.target, "id", "") or ""),
                subject_type=str(getattr(rel.source, "type", "") or ""),
                obj_type=str(getattr(rel.target, "type", "") or ""),
            ))
    return KGResult(triples=triples, entities=entities)


# ─────────────────────────────────────────────────────────────────────────────
# @coco.fn public API — ontology-first, simple signatures
# ─────────────────────────────────────────────────────────────────────────────

def _kg_result_to_json(result: KGResult) -> str:
    """Serialise a KGResult to a JSON string safe for CocoIndex memoization.

    CocoIndex's type system cannot handle ``Dict[str, Any]`` fields in
    dataclasses (the ``Any`` annotation is opaque to its introspection).
    Returning a plain ``str`` avoids that constraint while keeping full
    fidelity — callers use ``_kg_result_from_json()`` to reconstruct.
    """
    return json.dumps({
        "triples": [
            {
                "subject": t.subject,
                "predicate": t.predicate,
                "obj": t.obj,
                "subject_type": t.subject_type,
                "obj_type": t.obj_type,
                "relation_properties": t.relation_properties,
            }
            for t in result.triples
        ],
        "entities": [
            {
                "label": e.label,
                "entity_type": e.entity_type,
                "properties": e.properties,
            }
            for e in result.entities
        ],
    }, default=str)  # default=str handles any non-JSON-serialisable edge cases


def _kg_result_from_json(raw) -> KGResult:
    """Reconstruct a KGResult from a JSON string or pass through an existing KGResult."""
    if isinstance(raw, KGResult):
        return raw
    data = json.loads(raw) if isinstance(raw, str) else {}
    return KGResult(
        triples=[
            KGTriple(
                subject=t["subject"],
                predicate=t["predicate"],
                obj=t["obj"],
                subject_type=t.get("subject_type", ""),
                obj_type=t.get("obj_type", ""),
                relation_properties=t.get("relation_properties", {}),
            )
            for t in data.get("triples", [])
        ],
        entities=[
            KGEntity(
                label=e["label"],
                entity_type=e.get("entity_type", ""),
                properties=e.get("properties", {}),
            )
            for e in data.get("entities", [])
        ],
    )


if _COCO_AVAILABLE:
    @coco.fn(memo=True)  # type: ignore[misc]
    async def extract_kg_llamaindex(
        chunk_text: str,
        schema_json: str = "{}",
        llm_provider: str = "",
        llm_config_json: str = "{}",
        extractor_config_json: str = "{}",
    ) -> str:
        """Extract KG triples with LlamaIndex.  Ontology-guided when schema_json is set.

        Returns a JSON string (not ``KGResult``) so CocoIndex can safely
        memoize the result in LMDB — ``KGResult`` contains ``Dict[str, Any]``
        which CocoIndex's type introspection cannot serialise.  Use
        ``_kg_result_from_json()`` to reconstruct the object on the caller side.

        Parameters
        ----------
        chunk_text:
            The document chunk to extract from.
        schema_json:
            **Primary ontology lever.**  JSON from ``load_ontology_schema_json()``.
            When non-empty, extraction is guided by entity types, relation types,
            and datatype properties defined in your ``.ttl`` ontology files.
            ``"{}"`` = no ontology; extractor uses its built-in behaviour.
        llm_provider:
            Provider name (openai, ollama, gemini, bedrock, …).
            Falls back to ``LLM_PROVIDER`` env var when empty.
        llm_config_json:
            JSON of extra LLM kwargs (model name, temperature, …).
        extractor_config_json:
            JSON from ``load_extractor_config_json()``.  Controls
            ``KG_EXTRACTOR_TYPE``, ``DISABLE_PROPERTIES``, etc.
            All values are read from env by default — only pass this when
            you need CocoIndex to fingerprint config changes for cache
            invalidation.
        """
        try:
            from cocoindex_integration.functions.llm import get_llama_index_llm
            provider = llm_provider or os.getenv("LLM_PROVIDER", "openai")
            llm_cfg = _parse_json(llm_config_json)
            llm = get_llama_index_llm(provider, llm_cfg)
            if llm is None:
                logger.warning("extract_kg_llamaindex: LLM is None for provider=%s", provider)
                return _kg_result_to_json(KGResult())
            result = await _extract_li_async(
                chunk_text,
                _parse_json(schema_json),
                _parse_json(extractor_config_json),
                llm, provider,
            )
            return _kg_result_to_json(result)
        except Exception as _exc:
            logger.error("extract_kg_llamaindex failed: %s", _exc, exc_info=True)
            return _kg_result_to_json(KGResult())

else:
    async def extract_kg_llamaindex(  # type: ignore[misc]
        chunk_text: str,
        schema_json: str = "{}",
        llm_provider: str = "",
        llm_config_json: str = "{}",
        extractor_config_json: str = "{}",
    ) -> KGResult:
        from cocoindex_integration.functions.llm import get_llama_index_llm
        provider = llm_provider or os.getenv("LLM_PROVIDER", "openai")
        llm = get_llama_index_llm(provider, _parse_json(llm_config_json))
        if llm is None:
            return KGResult()
        return await _extract_li_async(
            chunk_text,
            _parse_json(schema_json),
            _parse_json(extractor_config_json),
            llm, provider,
        )


if _COCO_AVAILABLE:
    @coco.fn(memo=True)  # type: ignore[misc]
    async def extract_kg_langchain(
        chunk_text: str,
        schema_json: str = "{}",
        llm_provider: str = "",
        llm_config_json: str = "{}",
        extractor_config_json: str = "{}",
    ) -> str:
        """Extract KG triples with LangChain LLMGraphTransformer.

        Returns a JSON string for the same CocoIndex serialisation reason as
        ``extract_kg_llamaindex``.  Use ``_kg_result_from_json()`` to rebuild.

        Parameters mirror ``extract_kg_llamaindex`` — see that docstring.
        ``extractor_config_json`` controls ``STRICT_SCHEMA_VALIDATION`` only
        (LLMGraphTransformer does not have simple/dynamic/schema variants).
        """
        try:
            from cocoindex_integration.functions.llm import get_langchain_llm
            provider = llm_provider or os.getenv("LLM_PROVIDER", "openai")
            lc_llm = get_langchain_llm(provider, _parse_json(llm_config_json))
            if lc_llm is None:
                logger.warning("extract_kg_langchain: LLM is None for provider=%s", provider)
                return _kg_result_to_json(KGResult())
            result = await _extract_lc_async(
                chunk_text,
                _parse_json(schema_json),
                _parse_json(extractor_config_json),
                lc_llm,
            )
            return _kg_result_to_json(result)
        except Exception as _exc:
            logger.error("extract_kg_langchain failed: %s", _exc, exc_info=True)
            return _kg_result_to_json(KGResult())

else:
    async def extract_kg_langchain(  # type: ignore[misc]
        chunk_text: str,
        schema_json: str = "{}",
        llm_provider: str = "",
        llm_config_json: str = "{}",
        extractor_config_json: str = "{}",
    ) -> KGResult:
        from cocoindex_integration.functions.llm import get_langchain_llm
        provider = llm_provider or os.getenv("LLM_PROVIDER", "openai")
        lc_llm = get_langchain_llm(provider, _parse_json(llm_config_json))
        if lc_llm is None:
            return KGResult()
        return await _extract_lc_async(
            chunk_text,
            _parse_json(schema_json),
            _parse_json(extractor_config_json),
            lc_llm,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Custom extractors — one dispatcher for every registered KGExtractor
# ─────────────────────────────────────────────────────────────────────────────

# Extractors are documented as reusable across chunks (see KGExtractor), so keep
# one instance per class rather than rebuilding — an __init__ may be expensive.
_CUSTOM_INSTANCES: Dict[type, Any] = {}


async def _extract_custom_async(
    chunk_text: str,
    extractor_spec: str,
    schema_json: str,
    llm_provider: str,
    llm_config_json: str,
    extractor_config_json: str,
) -> KGResult:
    """Resolve *extractor_spec*, build its context, and run it over one chunk."""
    # Imported lazily: kg_extractors imports KGResult from this module, so a
    # module-level import here would be circular.
    from cocoindex_integration.functions.kg_extractors import (  # noqa: PLC0415
        KGExtractionContext,
        resolve_kg_extractor,
    )

    cls = resolve_kg_extractor(extractor_spec)
    instance = _CUSTOM_INSTANCES.get(cls)
    if instance is None:
        instance = _CUSTOM_INSTANCES.setdefault(cls, cls())

    ctx = KGExtractionContext(
        schema=_parse_json(schema_json),
        extractor_config=_parse_json(extractor_config_json),
        llm_provider=llm_provider or os.getenv("LLM_PROVIDER", "openai"),
        llm_config=_parse_json(llm_config_json),
    )
    result = await instance.extract(chunk_text, ctx)
    if not isinstance(result, KGResult):
        raise TypeError(
            f"{cls.__name__}.extract returned {type(result).__name__}, "
            "expected KGResult"
        )
    return result


if _COCO_AVAILABLE:
    @coco.fn(memo=True)  # type: ignore[misc]
    async def extract_kg_custom(
        chunk_text: str,
        extractor_spec: str = "",
        extractor_version: str = "",
        schema_json: str = "{}",
        llm_provider: str = "",
        llm_config_json: str = "{}",
        extractor_config_json: str = "{}",
    ) -> str:
        """Run a custom :class:`KGExtractor` over one chunk.

        Unlike the two built-ins — which are separate ``@coco.fn`` objects and so
        memoise into separate keyspaces — every custom extractor shares this one
        function.  ``extractor_spec`` and ``extractor_version`` are therefore
        arguments rather than lookups: they enter the memo key, so switching
        extractors or bumping ``version`` re-extracts instead of serving another
        implementation's cached triples.

        ``extractor_version`` is intentionally **unused in the body** — its only
        job is to participate in that key.  Removing it as "dead" would silently
        make edited extractors return stale results.

        Returns a JSON string for the same serialisation reason as
        ``extract_kg_llamaindex``; use ``_kg_result_from_json()`` to rebuild.
        """
        try:
            result = await _extract_custom_async(
                chunk_text, extractor_spec, schema_json,
                llm_provider, llm_config_json, extractor_config_json,
            )
            return _kg_result_to_json(result)
        except Exception as _exc:
            logger.error(
                "extract_kg_custom(%s) failed: %s", extractor_spec, _exc, exc_info=True
            )
            return _kg_result_to_json(KGResult())

else:
    async def extract_kg_custom(  # type: ignore[misc]
        chunk_text: str,
        extractor_spec: str = "",
        extractor_version: str = "",
        schema_json: str = "{}",
        llm_provider: str = "",
        llm_config_json: str = "{}",
        extractor_config_json: str = "{}",
    ) -> KGResult:
        return await _extract_custom_async(
            chunk_text, extractor_spec, schema_json,
            llm_provider, llm_config_json, extractor_config_json,
        )
