

# Example code for exporting and importing RDF data using rdflib


# Export property graph as RDF
rdf_graph = wrapper.get_rdf_representation()
rdf_graph.serialize("output/graph.ttl", format="turtle")

# Importing RDF data from an external Turtle file
rdf_graph = Graph()
rdf_graph.parse("external_data.ttl")

