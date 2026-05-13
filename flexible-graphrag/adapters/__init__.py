"""
adapters — framework-neutral ABCs and factories for all subsystems.

Each sub-package defines one or more ABCs (the contract) and a factory
function that selects the right concrete implementation based on AppSettings.

Concrete implementations live in:
  llamaindex/   — LlamaIndex-backed adapters
  langchain/    — LangChain-backed adapters

Sub-packages
------------
adapters.graph   — PropertyGraphStoreAdapter, RdfGraphStoreAdapter
adapters.vector  — VectorStoreAdapter
adapters.search  — SearchStoreAdapter
adapters.process — ChunkerAdapter, KGExtractorAdapter
adapters.llm     — LLMAdapter, EmbeddingAdapter
"""
