engine = UnifiedQueryEngine(
    property_graph_index=index,
    rdf_stores={"fuseki": fuseki_adapter}
)

# SPARQL
engine.query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }", QueryType.SPARQL)

# Cypher
engine.query("MATCH (e:EMPLOYEE)-[:WORKS_FOR]->(c:COMPANY) RETURN e, c", QueryType.CYPHER)

# Natural language
engine.query("Who works at which companies?", QueryType.NATURAL_LANGUAGE)
