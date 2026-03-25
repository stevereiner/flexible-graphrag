# flexible-graphrag/rdf/api_enhancements.py

from fastapi import APIRouter, UploadFile, HTTPException, Query, Depends
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import logging
import json

router = APIRouter(prefix="/api/rdf", tags=["ontology_rdf"])
logger = logging.getLogger(__name__)

# Global references (will be set during app initialization)
ontology_manager = None
rdf_stores = {}
unified_query_engine = None

class OntologyUploadRequest(BaseModel):
    format: str = "turtle"  # turtle, rdfxml, ntriples

class SPARQLQueryRequest(BaseModel):
    query: str
    target_backend: Optional[str] = None  # "neo4j", "fuseki", "graphdb", etc.

class CypherQueryRequest(BaseModel):
    query: str

class RDFExportRequest(BaseModel):
    format: str = "turtle"  # turtle, rdfxml, ntriples, nquads
    include_implicit: bool = True

class RDFStoreConnectRequest(BaseModel):
    name: str
    store_type: str  # fuseki, graphdb, oxigraph
    config: Dict[str, Any]

class NaturalLanguageQueryRequest(BaseModel):
    query: str
    target_backend: Optional[str] = None
    routing_mode: Optional[str] = "hybrid"  # property_graph, sparql, hybrid

@router.post("/ontology/upload")
async def upload_ontology(file: UploadFile):
    """Upload and load RDF ontology file"""
    global ontology_manager
    
    try:
        from .ontology_manager import OntologyManager
        
        if ontology_manager is None:
            ontology_manager = OntologyManager()
        
        # Read file content
        content = await file.read()
        
        # Determine format from file extension
        format_map = {
            '.ttl': 'turtle',
            '.rdf': 'rdfxml',
            '.nt': 'ntriples',
            '.nq': 'nquads',
            '.jsonld': 'jsonld'
        }
        
        file_ext = '.' + file.filename.split('.')[-1].lower() if '.' in file.filename else ''
        format = format_map.get(file_ext, 'turtle')
        
        # Load ontology
        ontology_manager.load_ontology_from_content(content, format=format)
        
        return {
            "status": "success",
            "message": f"Loaded ontology from {file.filename}",
            "entities": list(ontology_manager.entities.keys()),
            "relations": list(ontology_manager.relations.keys()),
            "entity_count": len(ontology_manager.entities),
            "relation_count": len(ontology_manager.relations)
        }
    except Exception as e:
        logger.error(f"Failed to upload ontology: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ontology/info")
async def get_ontology_info():
    """Get information about loaded ontology"""
    global ontology_manager
    
    if ontology_manager is None:
        return {
            "status": "no_ontology",
            "message": "No ontology loaded"
        }
    
    return {
        "status": "loaded",
        "entities": {
            name: {
                "uri": str(entity.uri),
                "description": entity.description
            }
            for name, entity in ontology_manager.entities.items()
        },
        "relations": {
            name: {
                "uri": str(relation.uri),
                "domain": relation.domain.name if relation.domain else None,
                "range": relation.range.name if relation.range else None
            }
            for name, relation in ontology_manager.relations.items()
        },
        "validation_schema": ontology_manager.validation_schema
    }

@router.post("/query/sparql")
async def execute_sparql_query(request: SPARQLQueryRequest):
    """Execute SPARQL query against RDF store or property graph"""
    global unified_query_engine
    
    if unified_query_engine is None:
        raise HTTPException(status_code=503, detail="Query engine not initialized")
    
    try:
        from .unified_query_engine import QueryType
        
        result = unified_query_engine.query(
            query_text=request.query,
            query_type=QueryType.SPARQL,
            target_backend=request.target_backend
        )
        
        return {
            "status": "success",
            "backend": result.backend,
            "query_type": result.query_type.value,
            "results": result.formatted_results
        }
    except Exception as e:
        logger.error(f"SPARQL query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/query/cypher")
async def execute_cypher_query(request: CypherQueryRequest):
    """Execute Cypher query against property graph"""
    global unified_query_engine
    
    if unified_query_engine is None:
        raise HTTPException(status_code=503, detail="Query engine not initialized")
    
    try:
        from .unified_query_engine import QueryType
        
        result = unified_query_engine.query(
            query_text=request.query,
            query_type=QueryType.CYPHER
        )
        
        return {
            "status": "success",
            "backend": result.backend,
            "query_type": result.query_type.value,
            "results": result.formatted_results
        }
    except Exception as e:
        logger.error(f"Cypher query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/query/natural-language")
async def execute_natural_language_query(request: NaturalLanguageQueryRequest):
    """Execute natural language query using LLM-based routing"""
    global unified_query_engine
    
    if unified_query_engine is None:
        raise HTTPException(status_code=503, detail="Query engine not initialized")
    
    try:
        from .unified_query_engine import QueryType
        
        result = unified_query_engine.query(
            query_text=request.query,
            query_type=QueryType.NATURAL_LANGUAGE,
            target_backend=request.target_backend
        )
        
        return {
            "status": "success",
            "backend": result.backend,
            "query_type": result.query_type.value,
            "results": result.formatted_results
        }
    except Exception as e:
        logger.error(f"Natural language query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/export/rdf")
async def export_property_graph_as_rdf(request: RDFExportRequest):
    """Export property graph as RDF"""
    try:
        from .sparql_property_graph_wrapper import PropertyGraphSPARQLWrapper
        
        # This would need access to the property graph store
        # Implementation requires backend instance
        raise HTTPException(status_code=501, detail="RDF export not yet implemented - requires backend integration")
    except Exception as e:
        logger.error(f"RDF export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/rdf-store/connect")
async def connect_rdf_store(request: RDFStoreConnectRequest):
    """Connect to an RDF store"""
    global rdf_stores
    
    try:
        from .store.rdf_store_factory import RDFStoreFactory
        
        # Create adapter
        adapter = RDFStoreFactory.create(request.store_type, request.config)
        adapter.connect()
        
        # Store in global dict
        rdf_stores[request.name] = adapter
        
        return {
            "status": "success",
            "message": f"Connected to RDF store '{request.name}' (type: {request.store_type})",
            "store_name": request.name,
            "store_type": request.store_type
        }
    except Exception as e:
        logger.error(f"Failed to connect to RDF store: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rdf-store/list")
async def list_rdf_stores():
    """List connected RDF stores"""
    global rdf_stores
    
    return {
        "stores": [
            {
                "name": name,
                "type": type(adapter).__name__
            }
            for name, adapter in rdf_stores.items()
        ],
        "count": len(rdf_stores)
    }

@router.delete("/rdf-store/{store_name}")
async def disconnect_rdf_store(store_name: str):
    """Disconnect from an RDF store"""
    global rdf_stores
    
    if store_name not in rdf_stores:
        raise HTTPException(status_code=404, detail=f"RDF store '{store_name}' not found")
    
    del rdf_stores[store_name]
    
    return {
        "status": "success",
        "message": f"Disconnected from RDF store '{store_name}'"
    }

def initialize_rdf_system(settings, property_graph_index=None):
    """Initialize RDF system with configuration from settings"""
    global ontology_manager, rdf_stores, unified_query_engine
    
    logger.info("Initializing RDF system...")
    
    # Initialize ontology manager if enabled
    if settings.use_ontology:
        try:
            from .ontology_manager import OntologyManager

            ontology_dir   = getattr(settings, "ontology_dir",   None)
            ontology_paths = getattr(settings, "ontology_paths", None)
            ontology_path  = getattr(settings, "ontology_path",  None)
            fmt            = getattr(settings, "ontology_format", "turtle")

            if ontology_dir or ontology_paths or ontology_path:
                ontology_manager = OntologyManager()

                if ontology_dir:
                    # Directory of ontology files — highest precedence
                    ontology_manager.load_ontology_dir(ontology_dir, format=fmt)
                elif ontology_paths:
                    # Comma-separated list of files — second precedence
                    paths = [p.strip() for p in ontology_paths.split(",") if p.strip()]
                    ontology_manager.load_ontology_files(paths, format=fmt)
                else:
                    # Single file — fallback
                    ontology_manager.load_ontology(ontology_path, format=fmt)
                    logger.info(
                        "Loaded ontology from %s: %d entities, %d relations",
                        ontology_path,
                        len(ontology_manager.entities),
                        len(ontology_manager.relations),
                    )
            else:
                logger.warning(
                    "USE_ONTOLOGY=true but no ontology source configured. "
                    "Set ONTOLOGY_DIR, ONTOLOGY_PATHS, or ONTOLOGY_PATH."
                )
        except Exception as e:
            logger.error(f"Failed to load ontology: {e}")
    
    # Initialize RDF stores using get_rdf_store_configs() method
    # This automatically handles standalone env vars overriding JSON config
    rdf_store_configs = settings.get_rdf_store_configs()
    
    if rdf_store_configs:
        from .store.rdf_store_factory import RDFStoreFactory
        
        for store_config in rdf_store_configs:
            store_name = store_config.get("name")
            try:
                store_type = store_config.get("type")
                config = store_config.get("config", {})
                
                adapter = RDFStoreFactory.create(store_type, config)
                adapter.connect()
                rdf_stores[store_name] = adapter
                
                logger.info(f"Connected to RDF store '{store_name}' (type: {store_type})")
            except Exception as e:
                logger.error(f"Failed to connect to RDF store '{store_name}': {e}")
    
    # Initialize unified query engine
    if property_graph_index or rdf_stores:
        from .unified_query_engine import UnifiedQueryEngine
        
        unified_query_engine = UnifiedQueryEngine(
            property_graph_index=property_graph_index,
            rdf_stores=rdf_stores
        )
        logger.info("Initialized unified query engine")
    
    logger.info("RDF system initialization complete")

