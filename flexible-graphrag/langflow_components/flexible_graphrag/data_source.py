"""Flexible GraphRAG Data Source Component for Langflow.

Ingestion entry point. Builds the shared flexible-graphrag system (from the backend .env,
with optional per-run overrides) and loads the chosen source, threading the result
downstream. Delegates loading/parsing to the real source layer (IngestionManager /
DataSourceFactory). Filesystem (incl. the file picker) produces file paths for the
Document Processor; the other 12 sources are loaded+parsed by the source layer into
documents directly. In app/flow mode the backend passes the per-source config as JSON via
the `source_config` field (tweaks), so no manual field entry is needed.
"""

import json
import os

from langflow_components.flexible_graphrag._fg_shared import build_settings, build_system, start_run, make_payload

from langflow.custom import Component
from langflow.io import MessageTextInput, StrInput, DropdownInput, FileInput, HandleInput, Output
from langflow.schema import Data

_DEFAULT = "(.env default)"
_DOC_EXTS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".txt",
             ".md", ".html", ".htm", ".csv", ".json", ".rtf", ".odt"}
_SOURCE_TYPES = ["filesystem", "alfresco", "nuxeo", "cmis", "web", "wikipedia", "youtube",
                 "s3", "gcs", "azure_blob", "onedrive", "sharepoint", "box", "google_drive"]


class FlexibleDataSourceComponent(Component):
    """Load documents from a data source and start the shared ingestion system."""

    display_name = "Flexible: Data Source"
    description = "Entry point: builds the shared GraphRAG system (.env + overrides) and resolves a source to file paths"
    icon = "FolderOpen"
    name = "FlexibleDataSource"

    inputs = [
        HandleInput(
            name="trigger", display_name="Trigger", input_types=["Message"], required=False,
            info="Optional: connect a ChatInput here so the flow runs end-to-end from the "
                 "Playground or the API (the value is ignored). Not needed for the file picker.",
        ),
        DropdownInput(
            name="source_type",
            display_name="Source Type",
            options=_SOURCE_TYPES,
            value="filesystem",
            info="Data source. Filesystem uses the file picker/paths below; the other 12 are "
                 "configured via Source Config (JSON) — the app provides it automatically in flow mode.",
        ),
        FileInput(
            name="files",
            display_name="Files (drag & drop / pick)",
            file_types=["pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "txt",
                        "md", "html", "htm", "csv", "json", "rtf", "odt"],
            info="Filesystem only: drag & drop or pick one or more files to ingest.",
        ),
        StrInput(
            name="source_config",
            display_name="Source Config (JSON)",
            value="",
            info="JSON config for the selected source (e.g. {\"bucket_name\": \"...\"} for s3, "
                 "{\"url\": \"...\"} for web). The app/backend sets this via tweaks in flow mode. "
                 "Must be a plain parameter (StrInput) — a Message input would not receive API tweaks.",
        ),
        MessageTextInput(
            name="source_path",
            display_name="Path(s) (file or folder)",
            info="Alternative to the file picker: one or more files/folders, one per line or comma-separated. Folders are ingested recursively.",
        ),
        StrInput(
            name="config_path",
            display_name="Config (.env) path",
            value="",
            info="Path to the flexible-graphrag .env. Blank = backend default. "
                 "StrInput so the backend can set it via API tweaks.",
        ),
        DropdownInput(
            name="vector_db", display_name="Vector DB (override)",
            options=[_DEFAULT, "none", "qdrant", "neo4j", "elasticsearch", "opensearch",
                     "chroma", "milvus", "weaviate", "lancedb", "pinecone", "postgres"],
            value=_DEFAULT, advanced=True, info="Override VECTOR_DB for this run.",
        ),
        DropdownInput(
            name="pg_graph_db", display_name="Property Graph DB (override)",
            options=[_DEFAULT, "none", "neo4j", "ladybug", "falkordb", "arcadedb", "memgraph", "neptune"],
            value=_DEFAULT, advanced=True, info="Override PG_GRAPH_DB (property graph / KG).",
        ),
        DropdownInput(
            name="search_db", display_name="Fulltext Search DB (override)",
            options=[_DEFAULT, "none", "bm25", "elasticsearch", "opensearch"],
            value=_DEFAULT, advanced=True, info="Override SEARCH_DB.",
        ),
        DropdownInput(
            name="rdf_graph_db", display_name="RDF Graph DB (override)",
            options=[_DEFAULT, "none", "fuseki", "oxigraph", "graphdb", "neptune_rdf"],
            value=_DEFAULT, advanced=True, info="Override RDF_GRAPH_DB.",
        ),
        DropdownInput(
            name="enable_knowledge_graph", display_name="KG Extraction (override)",
            options=[_DEFAULT, "true", "false"], value=_DEFAULT, advanced=True,
            info="Override ENABLE_KNOWLEDGE_GRAPH.",
        ),
    ]

    outputs = [
        Output(display_name="Source", name="source", method="load_source"),
    ]

    def _overrides(self) -> dict:
        ov = {}
        def put(env_key, val):
            if val and val != _DEFAULT:
                ov[env_key] = val
        put("VECTOR_DB", self.vector_db)
        put("PG_GRAPH_DB", self.pg_graph_db)
        put("SEARCH_DB", self.search_db)
        put("RDF_GRAPH_DB", self.rdf_graph_db)
        put("ENABLE_KNOWLEDGE_GRAPH", self.enable_knowledge_graph)
        return ov

    def _walk(self, path: str) -> list:
        if os.path.isfile(path):
            return [path]
        found = []
        for root, _dirs, files in os.walk(path):
            for fn in files:
                if os.path.splitext(fn)[1].lower() in _DOC_EXTS:
                    found.append(os.path.join(root, fn))
        return found

    def _parse_source_config(self) -> dict:
        raw = self.source_config
        # langflow may coerce a JSON-looking StrInput value into a dict at the param
        # level, or pass it through as a string — handle both.
        if isinstance(raw, dict):
            return raw
        raw = (raw or "").strip()
        if not raw:
            return {}
        try:
            cfg = json.loads(raw)
        except Exception as e:
            raise ValueError(f"Source Config must be a JSON object: {e}")
        return cfg if isinstance(cfg, dict) else {}

    def _resolve_paths(self, cfg: dict = None) -> list:
        # 1) Uploaded files (drag & drop / dialog) take precedence
        uploaded = self.files if isinstance(self.files, list) else ([self.files] if self.files else [])
        entries = [str(u).strip() for u in uploaded if u]

        # 2) Typed paths/folders (newline or comma separated)
        raw = (self.source_path or "").replace(",", "\n")
        entries += [ln.strip().strip('"') for ln in raw.splitlines() if ln.strip()]

        # 3) Paths from Source Config JSON (app-provided in flow mode)
        for key in ("paths", "input_paths"):
            for p in ((cfg or {}).get(key) or []):
                if p:
                    entries.append(str(p).strip())

        if not entries:
            raise ValueError("Provide files (picker/drag-drop), one or more paths, or Source Config paths")

        paths = []
        for entry in entries:
            # Normalize Windows backslash separators to forward slashes so a path produced by a
            # Windows host backend (e.g. "uploads\\file.txt") resolves when the flow runs in a Linux
            # container. Safe cross-platform: Windows accepts "/", and Linux never uses "\\" as a sep.
            entry = str(entry).replace("\\", "/")
            if not os.path.exists(entry):
                raise ValueError(f"Path does not exist: {entry}")
            paths.extend(self._walk(entry))
        if not paths:
            raise ValueError("No supported documents found in the given files/folders")
        # de-dupe, keep order
        seen, out = set(), []
        for p in paths:
            ap = os.path.abspath(p)
            if ap not in seen:
                seen.add(ap)
                out.append(p)
        return out

    def _config_from_trigger(self) -> dict:
        """In app/flow mode the backend sends the per-run config as a JSON object via the
        ChatInput message connected to `trigger` (the normal langflow data path — no tweaks).
        Returns {} for manual/Playground use (plain text or no trigger).
        """
        trig = self.trigger
        if trig is None:
            return {}
        text = getattr(trig, "text", None)
        if text is None:
            text = trig if isinstance(trig, str) else str(trig)
        text = (text or "").strip()
        if not text.startswith("{"):
            return {}
        try:
            d = json.loads(text)
        except Exception:
            return {}
        return d if isinstance(d, dict) else {}

    async def load_source(self) -> Data:
        # Run config arrives as DATA on the trigger edge (input_value), falling back to the
        # node's own fields for manual/Playground use.
        rc = self._config_from_trigger()
        source_type = rc.get("source_type") or self.source_type or "filesystem"
        config_path = rc.get("config_path") or self.config_path
        skip_graph = bool(rc.get("skip_graph"))
        config_id = rc.get("config_id")  # stable doc_id prefix for incremental sync (app mode)
        # doc_ids an earlier ingest of this source stored; replaced, not duplicated (app mode)
        replace_doc_ids = rc.get("replace_doc_ids") or []

        cfg = rc.get("source_config")
        if cfg is None:
            cfg = self._parse_source_config()
        elif isinstance(cfg, str):
            cfg = json.loads(cfg) if cfg.strip() else {}
        elif not isinstance(cfg, dict):
            cfg = {}

        settings = build_settings(config_path=config_path, overrides=self._overrides())
        system = build_system(settings)

        if source_type == "filesystem":
            # Filesystem: produce file paths; the Document Processor node parses them.
            file_paths = self._resolve_paths(cfg)
            run_key = start_run(system, file_paths=file_paths, skip_graph=skip_graph, config_id=config_id,
                            replace_doc_ids=replace_doc_ids)
            self.status = f"Source ready (filesystem): {len(file_paths)} file(s)."
            return make_payload(run_key, "source", num_files=len(file_paths))

        # Other 12 sources: the real source layer loads AND parses into documents
        # (get_documents_with_progress runs the DocumentProcessor internally).
        from ingest.manager import IngestionManager
        documents = await IngestionManager().ingest_from_source(source_type, cfg)
        if not documents:
            raise ValueError(f"No documents loaded from source '{source_type}'")

        if not getattr(system, "_last_ingested_documents", None):
            system._last_ingested_documents = []
        system._last_ingested_documents.extend(documents)

        run_key = start_run(system, documents=documents, skip_graph=skip_graph, config_id=config_id,
                            replace_doc_ids=replace_doc_ids)
        self.status = f"Source ready ({source_type}): {len(documents)} document(s)."
        return make_payload(run_key, "source", num_documents=len(documents))
