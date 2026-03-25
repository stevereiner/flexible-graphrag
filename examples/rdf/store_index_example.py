ontology = OntologyManager()
ontology.load_ontology("schemas/company_ontology.ttl")

pg_store = Neo4jPropertyGraphStore(
    uri="bolt://localhost:7687",
    username="neo4j",
    password="password",
)

builder = OntologyAwarePropertyGraphBuilder(
    graph_store=pg_store,
    llm=llm,
    embed_model=embed_model,
    ontology_path="schemas/company_ontology.ttl",
)

index = builder.build_index(documents, use_ontology=True)
