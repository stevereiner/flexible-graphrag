"""
flexible-graphrag LangChain Integration Module

Provides LangChain-based graph retrieval and QA chains integrated into
the LlamaIndex QueryFusionRetriever pipeline.

Subpackages:
  graph/  — property graph and RDF retrieval components
              TextToGraphQueryRetriever       — natural language -> Cypher/SPARQL QA chain
              GraphEntityVectorRetriever  — entity embedding similarity search (Neo4j vector index)
              GraphNeighborhoodRetriever  — k-hop graph expansion from seed entity nodes
              SynonymExpander             — LLM query rewriter (adds synonyms to embedding strs)
              SynonymExpanderRetriever    — wraps any retriever with SynonymExpander pre-processing

              langchain_adapters/         — per-store adapters supplying the chain backends above
                RDF stores (SPARQL QA):
                  GraphDBLangChainAdapter   — Ontotext GraphDB (RDF4J)
                  FusekiLangChainAdapter    — Apache Jena Fuseki
                  OxigraphLangChainAdapter  — Oxigraph
                  NeptuneRDFAdapter         — Amazon Neptune RDF
                Property graph stores (Cypher QA):
                  property_graph_adapters   — Neo4j (+ extensible to other PG stores)

              logging_retriever.py        — LoggingRetriever / wrap_with_logging()
              synonym_fusion.py           — SynonymFusion.from_config() / .wrap() / .wrap_all()

  llm/    — provider-aware LangChain chat model factory
              get_langchain_llm()         — returns ChatModel matching the active LLM_PROVIDER
"""
