"""llamaindex.process.chunker_adapter — LlamaIndexChunkerAdapter."""
from __future__ import annotations

from typing import Any, List
import logging

from adapters.process.chunker_adapter import ChunkerAdapter

logger = logging.getLogger(__name__)


class LlamaIndexChunkerAdapter(ChunkerAdapter):
    """Wraps ``llama_index.core.node_parser.SentenceSplitter``."""

    def __init__(self, chunk_size: int = 1024, chunk_overlap: int = 20):
        from llama_index.core.node_parser import SentenceSplitter
        # tokenizer=list → chunk_size/overlap counted in characters, not tokens.
        self._splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, tokenizer=list)

    @property
    def backend(self) -> str:
        return "llamaindex"

    def split_text(self, text: str) -> List[str]:
        from llama_index.core.schema import Document as LIDocument
        nodes = self._splitter.get_nodes_from_documents([LIDocument(text=text)])
        return [n.get_content() for n in nodes]

    def split_documents(self, documents: List[Any]) -> List[Any]:
        """Split LlamaIndex ``Document`` objects and return ``TextNode`` list."""
        return self._splitter.get_nodes_from_documents(documents)

    def get_splitter(self):
        return self._splitter
