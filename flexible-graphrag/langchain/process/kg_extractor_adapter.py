"""langchain.process.kg_extractor_adapter — LangChain KG extractor implementation.

The ABC and factory live in :mod:`adapters.process.kg_extractor_adapter`.
The LlamaIndex implementation lives in :mod:`llamaindex.process.kg_extractor_adapter`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

from adapters.process.kg_extractor_adapter import KGExtractorAdapter

logger = logging.getLogger(__name__)


class LangChainKGExtractorAdapter(KGExtractorAdapter):
    """Wraps ``LLMGraphTransformer`` with optional ontology guidance.

    Ontology awareness
    ------------------
    When an ``OntologyManager`` is provided (via ``ontology_manager`` kwarg or
    from ``rdf.api_rdf_enhancements.ontology_manager``), the adapter reads:

    * ``om.get_entities_literal()`` → ``allowed_nodes``
    * ``om.get_relations_literal()`` → ``allowed_relationships``
    """

    def __init__(
        self,
        lc_llm,
        ontology_manager=None,
        use_ontology: bool = True,
        node_properties: Optional[List[str]] = None,
        relationship_properties: Optional[List[str]] = None,
        strict_mode: bool = False,
    ):
        self._lc_llm = lc_llm
        self._use_ontology = use_ontology
        self._node_properties = node_properties or []
        self._relationship_properties = relationship_properties or []
        self._strict_mode = strict_mode
        self._transformer = None

        self._om = ontology_manager
        if self._om is None and use_ontology:
            try:
                from rdf.api_rdf_enhancements import ontology_manager as _global_om
                self._om = _global_om
            except (ImportError, AttributeError):
                pass

        self._build_transformer()

    def _build_transformer(self) -> None:
        try:
            from langchain_experimental.graph_transformers import LLMGraphTransformer
        except ImportError as exc:
            raise ImportError(
                "langchain-experimental is required for LangChainKGExtractorAdapter. "
                "Install: pip install langchain-experimental"
            ) from exc

        allowed_nodes: Optional[List[str]] = None
        allowed_relationships: Optional[List[str]] = None

        if self._use_ontology and self._om is not None:
            try:
                entity_labels = self._om.get_entities_literal()
                relation_labels = self._om.get_relations_literal()
                if entity_labels:
                    allowed_nodes = list(entity_labels)
                    logger.info(f"LangChain KG extractor: ontology allowed_nodes={len(allowed_nodes)} types")
                if relation_labels:
                    allowed_relationships = list(relation_labels)
                    logger.info(f"LangChain KG extractor: ontology allowed_relationships={len(allowed_relationships)} types")
            except Exception as exc:
                logger.warning(f"Could not read ontology for LangChain KG extractor: {exc}")

        kwargs: Dict[str, Any] = {"llm": self._lc_llm, "strict_mode": self._strict_mode}
        if allowed_nodes:
            kwargs["allowed_nodes"] = allowed_nodes
        if allowed_relationships:
            kwargs["allowed_relationships"] = allowed_relationships
        if self._node_properties:
            kwargs["node_properties"] = self._node_properties
        if self._relationship_properties:
            kwargs["relationship_properties"] = self._relationship_properties

        self._transformer = LLMGraphTransformer(**kwargs)
        logger.info(
            f"LangChainKGExtractorAdapter: LLMGraphTransformer built "
            f"(ontology={self._use_ontology and self._om is not None}, "
            f"strict={self._strict_mode})"
        )

    @property
    def backend(self) -> str:
        return "langchain"

    def get_extractors(self) -> List[Any]:
        return []

    async def aextract(self, documents: List[Any]) -> List[Any]:
        """Extract graph data and return LangChain ``GraphDocument`` list."""
        from langchain_core.documents import Document as LCDocument

        lc_docs: List[LCDocument] = []
        for doc in documents:
            if isinstance(doc, LCDocument):
                lc_docs.append(doc)
            elif hasattr(doc, "text") and hasattr(doc, "metadata"):
                lc_docs.append(LCDocument(page_content=doc.text or "", metadata=doc.metadata or {}))
            elif hasattr(doc, "page_content"):
                lc_docs.append(doc)
            else:
                logger.warning(f"Unknown document type {type(doc).__name__}, skipping")

        if not lc_docs:
            return []

        try:
            graph_docs = await self._transformer.aconvert_to_graph_documents(lc_docs)
            total_nodes = sum(len(gd.nodes) for gd in graph_docs)
            total_rels = sum(len(gd.relationships) for gd in graph_docs)
            logger.info(f"LangChain KG extraction: {len(graph_docs)} graph docs, {total_nodes} nodes, {total_rels} relationships")
            return graph_docs
        except Exception as exc:
            logger.error(f"LangChainKGExtractorAdapter.aextract failed: {exc}")
            raise
