


from sparql_property_graph_wrapper import PropertyGraphSPARQLWrapper

#Query Property Graphs with SPARQL
wrapper = PropertyGraphSPARQLWrapper(index.property_graph_store)
results = wrapper.query_sparql("""
    SELECT ?person ?org WHERE {
        ?person rdf:type :PERSON .
        ?person :WORKS_FOR ?org .
    }
""")

# Query RDF Stores with SPARQL
store = RDFStoreFactory.create("fuseki", config)
results = store.query_sparql("""
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>
    SELECT ?name WHERE { ?x foaf:name ?name }
""")

# Route Queries Automatically
engine = UnifiedQueryEngine(
    property_graph_index=index,
    rdf_stores={"fuseki": fuseki_adapter}
)

# Query any backend, engine routes automatically
result = engine.query("Find all employees at Acme", QueryType.NATURAL_LANGUAGE)


