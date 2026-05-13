"""langchain.process.chunker_adapter — LangChain chunker implementation.

The ABC and factory live in :mod:`adapters.process.chunker_adapter`.
The LlamaIndex implementation lives in :mod:`llamaindex.process.chunker_adapter`.

Supported splitter types (set via LC_SPLITTER_TYPE):
  recursive           — RecursiveCharacterTextSplitter (default)
  character           — CharacterTextSplitter
  token               — TokenTextSplitter (tiktoken-based)
  markdown            — MarkdownTextSplitter
  python              — PythonCodeTextSplitter
  sentence_transformers — SentenceTransformersTokenTextSplitter
"""
from __future__ import annotations

from typing import Any, List
import logging
import uuid

from adapters.process.chunker_adapter import ChunkerAdapter

logger = logging.getLogger(__name__)

# All splitter types this adapter supports.
SUPPORTED_SPLITTER_TYPES = (
    "recursive",
    "character",
    "token",
    "markdown",
    "python",
    "sentence_transformers",
)


class LangChainChunkerAdapter(ChunkerAdapter):
    """Wraps a LangChain text splitter.

    Accepts LlamaIndex ``Document`` objects in :meth:`split_documents` and
    returns LlamaIndex ``TextNode`` objects so the output is compatible with
    the rest of the LlamaIndex ingest pipeline (embedding, KG extraction,
    vector indexing).
    """

    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 128,
        splitter_type: str = "recursive",
    ):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._splitter_type = splitter_type
        self._splitter = self._build_splitter(splitter_type, chunk_size, chunk_overlap)
        logger.info(
            "LangChainChunkerAdapter: splitter=%s, chunk_size=%d, overlap=%d",
            splitter_type, chunk_size, chunk_overlap,
        )

    @staticmethod
    def _build_splitter(splitter_type: str, chunk_size: int, chunk_overlap: int):
        """Instantiate the requested LangChain text splitter."""
        st = splitter_type.lower()

        if st == "sentence_transformers":
            try:
                from langchain_text_splitters import SentenceTransformersTokenTextSplitter
                return SentenceTransformersTokenTextSplitter(
                    chunk_overlap=chunk_overlap,
                    tokens_per_chunk=chunk_size,
                )
            except ImportError:
                logger.warning(
                    "SentenceTransformersTokenTextSplitter not available; "
                    "falling back to RecursiveCharacterTextSplitter"
                )
                st = "recursive"

        if st == "character":
            from langchain_text_splitters import CharacterTextSplitter
            return CharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

        if st == "token":
            try:
                from langchain_text_splitters import TokenTextSplitter
                return TokenTextSplitter(
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            except ImportError:
                logger.warning(
                    "TokenTextSplitter requires tiktoken; "
                    "falling back to RecursiveCharacterTextSplitter"
                )
                st = "recursive"

        if st == "markdown":
            from langchain_text_splitters import MarkdownTextSplitter
            return MarkdownTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

        if st == "python":
            from langchain_text_splitters import PythonCodeTextSplitter
            return PythonCodeTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

        # default: recursive
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    @property
    def backend(self) -> str:
        return "langchain"

    def split_text(self, text: str) -> List[str]:
        """Split *text* into a list of chunk strings."""
        return self._splitter.split_text(text)

    def split_documents(self, documents: List[Any]) -> List[Any]:
        """Split documents and return LangChain ``Document`` objects.

        Accepts either LangChain ``Document`` or LlamaIndex ``Document``
        objects.  For LlamaIndex documents the text and metadata are extracted
        before splitting so the LangChain splitter can work with them.
        Returns a list of LangChain ``Document`` objects (one per chunk).
        """
        from langchain_core.documents import Document as LCDocument

        lc_docs: List[LCDocument] = []
        for doc in documents:
            # Support both LlamaIndex Document and LangChain Document
            if hasattr(doc, "get_content"):
                # LlamaIndex Document / BaseNode
                text = doc.get_content()
                meta = dict(doc.metadata or {})
                meta.setdefault("doc_id", str(doc.id_))
            elif hasattr(doc, "page_content"):
                # LangChain Document
                text = doc.page_content
                meta = dict(doc.metadata or {})
            else:
                text = str(doc)
                meta = {}
            lc_docs.append(LCDocument(page_content=text, metadata=meta))

        return self._splitter.split_documents(lc_docs)

    def split_to_llama_nodes(self, documents: List[Any]) -> List[Any]:
        """Split documents and return LlamaIndex ``TextNode`` objects.

        This is the primary method used by ``run_chunk_pipeline`` when
        ``CHUNKER_BACKEND=langchain``.  Each output node carries:

        * ``text``      — the chunk text
        * ``metadata``  — inherited from the parent document
        * ``id_``       — stable UUID (deterministic from parent id + chunk index)
        * ``ref_doc_id``— parent document ``id_`` for incremental-update deletion
        """
        from llama_index.core.schema import TextNode

        nodes: List[TextNode] = []
        for doc in documents:
            if hasattr(doc, "get_content"):
                text = doc.get_content()
                meta = dict(doc.metadata or {})
                parent_id = str(doc.id_)
            elif hasattr(doc, "page_content"):
                text = doc.page_content
                meta = dict(doc.metadata or {})
                parent_id = meta.get("doc_id", str(uuid.uuid4()))
            else:
                text = str(doc)
                meta = {}
                parent_id = str(uuid.uuid4())

            chunks = self._splitter.split_text(text)
            for i, chunk in enumerate(chunks):
                # Deterministic node ID: namespace v5 from (parent_id + chunk_index)
                node_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{parent_id}:{i}"))
                node = TextNode(
                    text=chunk,
                    id_=node_id,
                    metadata=dict(meta),  # copy so nodes don't share dict
                )
                node.relationships = {}  # avoid reference issues
                # Record which source document this node came from
                try:
                    from llama_index.core.schema import NodeRelationship, RelatedNodeInfo
                    node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(
                        node_id=parent_id,
                        metadata={"doc_id": parent_id},
                    )
                except Exception:
                    pass
                nodes.append(node)

        logger.info(
            "LangChainChunkerAdapter: split %d docs -> %d nodes (splitter=%s)",
            len(documents), len(nodes), self._splitter_type,
        )
        return nodes

    def get_splitter(self):
        return self._splitter
