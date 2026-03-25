"""
Example: Complete Ontology-Guided Ingestion Pipeline

This example demonstrates how to use the flexible-graphrag RDF/Ontology module
to perform ontology-driven knowledge graph extraction from documents.

Usage:
    cd flexible-graphrag
    python -m rdf.ontology_guided_ingestion_example
"""

import sys
import os
# Add parent directory to path to allow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from llama_index.core import Document
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore

# Import RDF module components
from rdf.ontology_manager import OntologyManager
from rdf.ingest_with_ontology import OntologyAwarePropertyGraphBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Load environment variables from .env file
    from dotenv import load_dotenv
    load_dotenv()
    
    # Step 1: Initialize LLM and embeddings
    logger.info("Initializing LLM and embeddings...")
    llm = OpenAI(model="gpt-4o-mini", temperature=0)
    embed_model = OpenAIEmbedding()
    
    # Step 2: Load ontology
    logger.info("Loading ontology...")
    ontology_path = "rdf/schemas/company_ontology.ttl"
    
    ontology = OntologyManager()
    ontology.load_ontology(ontology_path, format="turtle")
    
    logger.info(f"Ontology loaded: {len(ontology.entities)} entities, {len(ontology.relations)} relations")
    logger.info(f"Entities: {list(ontology.entities.keys())}")
    logger.info(f"Relations: {list(ontology.relations.keys())}")
    
    # Show entity properties
    entity_properties = ontology.get_entity_properties()
    if entity_properties:
        logger.info(f"Properties: {sum(len(props) for props in entity_properties.values())} properties across {len(entity_properties)} entities")
        for entity_name, props in entity_properties.items():
            logger.info(f"  {entity_name}: {list(props.keys())}")
    
    # Step 3: Initialize property graph store (Neo4j example)
    logger.info("Connecting to Neo4j...")
    pg_store = Neo4jPropertyGraphStore(
        url=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "password"),
    )
    
    # Step 4: Create ontology-aware builder
    logger.info("Creating ontology-aware builder...")
    builder = OntologyAwarePropertyGraphBuilder(
        graph_store=pg_store,
        llm=llm,
        embed_model=embed_model,
        ontology_path=ontology_path,
    )
    
    # Step 5: Prepare documents
    logger.info("Preparing sample documents...")
    documents = [
        Document(text="""
        Alice Johnson works at TechCorp as a Senior Software Engineer.
        She is working on the AI Platform project alongside Bob Smith.
        TechCorp is located in San Francisco and specializes in artificial intelligence.
        The AI Platform uses Python, TensorFlow, and Kubernetes.
        """),
        Document(text="""
        Bob Smith is the Project Manager for the AI Platform at TechCorp.
        He collaborates with Alice Johnson and manages a team of 10 engineers.
        The project aims to build a scalable machine learning infrastructure.
        TechCorp has partnerships with Google Cloud and AWS.
        """),
        Document(text="""
        TechCorp was founded in 2015 and has offices in San Francisco and New York.
        The company develops enterprise AI solutions using cutting-edge technologies.
        Their main projects include the AI Platform and Data Analytics Suite.
        """)
    ]
    
    # Step 6: Build index with ontology-guided extraction
    logger.info("Building PropertyGraphIndex with ontology-guided extraction...")
    index = builder.build_index(
        documents,
        use_ontology=True,      # Use ontology schema
        use_implicit=True,      # Also extract implicit document relationships
        use_simple=False,       # Don't use free-form LLM extraction
        show_progress=True
    )
    
    logger.info("Index built successfully!")
    
    # Step 7: Query the knowledge graph
    logger.info("Querying knowledge graph...")
    
    query_engine = index.as_query_engine(
        include_text=True,
        response_mode="tree_summarize"
    )
    
    # Example queries
    queries = [
        "Who works at TechCorp?",
        "What projects is Alice Johnson working on?",
        "What technologies does TechCorp use?",
        "Where is TechCorp located?"
    ]
    
    for query in queries:
        logger.info(f"\nQuery: {query}")
        response = query_engine.query(query)
        logger.info(f"Response: {response}")
    
    # Step 8: Get ontology info
    ontology_info = builder.get_ontology_info()
    logger.info(f"\nOntology Info: {ontology_info}")

if __name__ == "__main__":
    main()

