# flexible_graphrag/rdf_store_factory.py

from typing import Dict, Any
from .rdf_store_adapter import RDFStoreAdapter
from .fuseki_rdf_store_adapter import FusekiAdapter
from .ontotext_graphdb_rdf_store_adapter import OntotextGraphDBAdapter
from .oxigraph_rdf_store_adapter import OxigraphAdapter


class RDFStoreFactory:
    """Factory for creating RDF store adapters."""

    ADAPTERS = {
        "fuseki": FusekiAdapter,
        "graphdb": OntotextGraphDBAdapter,
        "ontotext": OntotextGraphDBAdapter,
        "oxigraph": OxigraphAdapter,
    }

    @staticmethod
    def create(store_type: str, config: Dict[str, Any]) -> RDFStoreAdapter:
        """
        Create RDF store adapter.

        store_type:
          - "fuseki"
          - "graphdb" / "ontotext"
          - "oxigraph"
        """
        key = store_type.lower()
        if key not in RDFStoreFactory.ADAPTERS:
            raise ValueError(f"Unknown RDF store type: {store_type}")
        adapter_cls = RDFStoreFactory.ADAPTERS[key]
        return adapter_cls(config)
