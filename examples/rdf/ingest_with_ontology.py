# flexible-graphrag/ingest_with_ontology.py

from llama_index.core import PropertyGraphIndex, Document, Settings
from llama_index.core.indices.property_graph import (
    SchemaLLMPathExtractor,
    SimpleLLMPathExtractor,
    ImplicitPathExtractor,
    DynamicLLMPathExtractor
)
from .ontology_manager import OntologyManager
from typing import List, Optional, Dict, Any
import logging

class OntologyAwarePropertyGraphBuilder:
    """Build PropertyGraphIndex with optional ontology guidance"""
    
    def __init__(self, graph_store, llm, embed_model, ontology_path: Optional[str] = None):
        """
        Args:
            graph_store: LlamaIndex graph store (Neo4j, Ladybug, etc.)
            llm: Language model
            embed_model: Embedding model
            ontology_path: Path to RDF ontology file (optional)
        """
        self.graph_store = graph_store
        self.llm = llm
        self.embed_model = embed_model
        self.ontology_manager: Optional[OntologyManager] = None
        
        if ontology_path:
            self.ontology_manager = OntologyManager()
            self.ontology_manager.load_ontology(ontology_path)
        
        self.logger = logging.getLogger(__name__)
    
    def build_index(
        self,
        documents: List[Document],
        use_ontology: bool = True,
        use_implicit: bool = True,
        use_simple: bool = False,
        show_progress: bool = True
    ) -> PropertyGraphIndex:
        """
        Build PropertyGraphIndex with multiple extractors
        
        Args:
            documents: List of documents to process
            use_ontology: Use ontology-guided extraction (if ontology loaded)
            use_implicit: Use implicit path extraction (structural relationships)
            use_simple: Use simple LLM extraction for any missed relationships
            show_progress: Show progress bar
        
        Returns:
            PropertyGraphIndex with extracted knowledge graph
        """
        kg_extractors = []
        
        # Primary: Ontology-guided extraction if available
        if use_ontology and self.ontology_manager:
            self.logger.info("Using ontology-guided extraction with SchemaLLMPathExtractor")
            
            entities = list(self.ontology_manager.entities.keys())
            relations = list(self.ontology_manager.relations.keys())
            
            # Extract entity properties from ontology
            # Format: [(property_name, property_type), ...] - properties are global, not entity-specific
            entity_props = []
            seen_props = set()  # Track unique properties
            for entity_name, entity in self.ontology_manager.entities.items():
                if entity.properties:
                    for prop_name, prop_type in entity.properties.items():
                        prop_key = (prop_name, prop_type)
                        if prop_key not in seen_props:
                            entity_props.append(prop_key)
                            seen_props.add(prop_key)
            
            self.logger.info(f"Ontology provides {len(entities)} entity types, {len(relations)} relation types")
            if entity_props:
                self.logger.info(f"Ontology defines {len(entity_props)} unique properties")
            
            extractor_kwargs = {
                "llm": self.llm,
                "possible_entities": entities,
                "possible_relations": relations,
                "strict": False,  # Use False for better compatibility
                "max_triplets_per_chunk": 10
            }
            
            # Add entity properties if available
            if entity_props:
                extractor_kwargs["possible_entity_props"] = entity_props
            
            ontology_extractor = SchemaLLMPathExtractor(**extractor_kwargs)
            kg_extractors.append(ontology_extractor)
        
        # Secondary: Implicit path extraction (always useful for document structure)
        if use_implicit:
            self.logger.info("Adding implicit path extraction")
            kg_extractors.append(ImplicitPathExtractor())
        
        # Tertiary: Simple LLM extraction for any missed relationships
        if use_simple:
            self.logger.info("Adding simple LLM extraction")
            kg_extractors.append(SimpleLLMPathExtractor(llm=self.llm))
        
        # Build index
        index = PropertyGraphIndex.from_documents(
            documents,
            kg_extractors=kg_extractors,
            property_graph_store=self.graph_store,
            llm=self.llm,
            embed_model=self.embed_model,
            show_progress=show_progress
        )
        
        self.logger.info(f"Built PropertyGraphIndex with {len(kg_extractors)} extractors")
        return index
    
    def get_ontology_info(self) -> Optional[Dict[str, Any]]:
        """Get information about loaded ontology"""
        if not self.ontology_manager:
            return None
        
        # Get all entity properties
        entity_properties = {}
        for entity_name, entity in self.ontology_manager.entities.items():
            if entity.properties:
                entity_properties[entity_name] = entity.properties
        
        return {
            "entities_count": len(self.ontology_manager.entities),
            "relations_count": len(self.ontology_manager.relations),
            "entities": list(self.ontology_manager.entities.keys()),
            "relations": list(self.ontology_manager.relations.keys()),
            "properties": entity_properties,
            "validation_schema": self.ontology_manager.get_validation_schema()
        }
