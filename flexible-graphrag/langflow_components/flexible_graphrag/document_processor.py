"""Flexible GraphRAG Document Processor Component for Langflow.

Parses the source files into documents using the real backend DocumentProcessor
(Docling / LlamaParse per .env), reusing the shared system. Threads documents downstream.
"""

from langflow_components.flexible_graphrag._fg_shared import get_run, make_payload

from langflow.custom import Component
from langflow.io import HandleInput, Output
from langflow.schema import Data


class FlexibleDocProcessorComponent(Component):
    """Process documents (PDF, DOCX, XLSX, …) with Docling or LlamaParse."""

    display_name = "Flexible: Document Processor"
    description = "Parse source files into documents using the backend DocumentProcessor (Docling/LlamaParse per .env)"
    icon = "FileText"
    name = "FlexibleDocProcessor"

    inputs = [
        HandleInput(name="source", display_name="Source", input_types=["Data"],
                    info="From Data Source: shared system + file paths."),
    ]

    outputs = [
        Output(display_name="Documents", name="documents", method="process_documents"),
    ]

    @staticmethod
    def _assign_stable_ids(run, documents) -> None:
        """For incremental sync (app mode), give documents stable {config_id}:{identity}
        doc_ids before chunking — same as the backend's ingest_source_documents path — so a
        re-sync can locate and replace them. No-op when no config_id on the run."""
        config_id = run.get("config_id")
        if not config_id or not documents:
            return
        from ingest.ingest_from_source import _assign_stable_doc_ids
        _assign_stable_doc_ids(documents, config_id)

    @classmethod
    async def _assign_ids_and_replace(cls, run, documents) -> None:
        """Stable ids, then delete the stored copy of any document an earlier ingest of this
        source already put in the stores (the backend sends those ids as replace_doc_ids), so
        a repeat ingest refreshes instead of adding duplicate chunks/entities/triples."""
        cls._assign_stable_ids(run, documents)
        if run.get("config_id") and run.get("replace_doc_ids") and documents:
            from ingest.replace_existing import delete_previous_versions
            await delete_previous_versions(run["system"], documents, run["replace_doc_ids"])

    @staticmethod
    def _doc_states(run, documents):
        """Compact per-doc {id_, text, metadata} list so the backend can create document_state
        rows for incremental sync (the docs live in this langflow process; the backend needs
        their stable doc_id + text for the content_hash + metadata). Only emitted when config_id
        is set (sync enabled). text is needed because the sync engine's content_hash =
        SHA-256(doc.text); an empty hash breaks change detection AND the NOT NULL column."""
        if not run.get("config_id") or not documents:
            return None
        return [{"id_": getattr(d, "id_", "") or "",
                 "text": getattr(d, "text", "") or "",
                 "metadata": dict(getattr(d, "metadata", {}) or {})} for d in documents]

    async def process_documents(self) -> Data:
        run = get_run(self.source)
        system = run["system"]

        # Non-filesystem sources already produced parsed documents in the Data Source node
        # (the source layer runs the DocumentProcessor internally) — pass through.
        existing = run.get("documents")
        if existing:
            await self._assign_ids_and_replace(run, existing)
            self.status = f"Documents already parsed by source ({len(existing)}); passing through."
            return make_payload(run["_key"], "documents", num_documents=len(existing),
                                doc_states=self._doc_states(run, existing))

        file_paths = run.get("file_paths")
        if not file_paths:
            raise ValueError("No file paths or documents in the ingestion run")

        documents = await system.document_processor.process_documents(file_paths)
        if not documents:
            raise ValueError("No documents were successfully processed")

        # Mirror the backend: track ingested documents on the system
        if not getattr(system, "_last_ingested_documents", None):
            system._last_ingested_documents = []
        system._last_ingested_documents.extend(documents)

        await self._assign_ids_and_replace(run, documents)
        run["documents"] = documents
        self.status = f"Processed {len(documents)} document(s) from {len(file_paths)} file(s)."
        return make_payload(run["_key"], "documents", num_documents=len(documents),
                            doc_states=self._doc_states(run, documents))
