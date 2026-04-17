# Data Sources

Flexible GraphRAG supports **13 data sources** for ingesting documents into your knowledge base.

[![Data Sources](https://raw.githubusercontent.com/stevereiner/flexible-graphrag/main/screen-shots/react/data-sources-1.jpeg)](https://raw.githubusercontent.com/stevereiner/flexible-graphrag/main/screen-shots/react/data-sources-1.jpeg)

## Overview

| Category | Sources |
|---|---|
| **File & Upload** | File Upload |
| **Cloud Storage** | Amazon S3, Google Cloud Storage, Azure Blob Storage, Google Drive, Microsoft OneDrive |
| **Enterprise Repositories** | Alfresco, Microsoft SharePoint, Box, CMIS |
| **Web Sources** | Web Pages, Wikipedia, YouTube |

All data sources support:

- **Docling** (default) or **LlamaParse** document parser
- **Skip Graph** — ingest to vector + search only, skip KG extraction
- **Incremental Auto-Sync** — keep databases synchronized when files change (most sources)

Each data source includes:

- **Configuration Forms**: Easy-to-use interfaces for credentials and settings
- **Progress Tracking**: Real-time per-file progress indicators
- **Flexible Authentication**: Support for various auth methods (API keys, OAuth, service accounts)

## File Upload

No credentials required. Supports drag & drop or file dialog.

- **UI**: Sources tab → "File Upload" → drag files or click to select
- **API**: `POST /api/upload` with multipart form data
- **MCP**: `ingest_documents()` with `source_type: "filesystem"` and `paths`

## Cloud Storage Sources

### Amazon S3

```bash
# .env configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name
S3_PREFIX=optional/prefix/      # optional
```

Incremental updates supported via **SQS event notifications**.
See [S3 Setup Guide](S3-SETUP.md) for full setup.

### Google Cloud Storage

```bash
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
GCS_BUCKET_NAME=your-bucket-name
GCS_PREFIX=optional/prefix/     # optional
```

Incremental updates supported via **Pub/Sub notifications**.
See [GCS Setup Guide](GCS-SETUP.md) for full setup.

### Azure Blob Storage

```bash
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
AZURE_CONTAINER_NAME=your-container-name
```

Incremental updates supported via **Change Feed**.
See [Azure Blob Setup Guide](AZURE-BLOB-SETUP.md) for full setup.

### Google Drive

Requires OAuth credentials or service account.
See [Data Source Configuration](DATA-SOURCE-CONFIGURATION.md) for setup.

Incremental updates supported via **Changes API** (polling).

### Microsoft OneDrive

Requires Microsoft Entra app registration (OneDrive for Business only).

!!! note
    Personal OneDrive is not supported. OneDrive for Business can be accessed with a M365 Developer Program sandbox.

Incremental updates supported via **polling**.

## Enterprise Repository Sources

### Alfresco

Two integration modes:

1. **KG Spaces ACA Extension** — multi-select documents/folders directly from the Alfresco Content Application using nodeIds
2. **Direct Integration** — use Alfresco paths (e.g., `/Shared/GraphRAG/cmispress.txt`)

```bash
ALFRESCO_BASE_URL=http://localhost:8080/alfresco
ALFRESCO_USERNAME=admin
ALFRESCO_PASSWORD=admin
```

Incremental updates supported via **ActiveMQ events** (real-time).

### Microsoft SharePoint

Requires Microsoft Entra app registration.
Incremental updates supported via polling.

### Box

Requires Box Business account (minimum 3 users).
Incremental updates supported via **Events API** (polling).

### CMIS

Any CMIS-compliant repository (Alfresco, Nuxeo, etc.).

```bash
CMIS_URL=http://localhost:8080/alfresco/api/-default-/public/cmis/versions/1.1/atom
CMIS_USERNAME=admin
CMIS_PASSWORD=admin
```

See [CMIS Setup Guide](README-cmis.md) and [Source Path Examples](SOURCE-PATH-EXAMPLES.md).

## Web Sources

### Web Pages

Provide a URL — the page content is fetched and processed.

- **MCP**: `ingest_documents()` with `source_type: "web"` and `urls: [...]`

### Wikipedia

Provide article titles or Wikipedia URLs.

- **MCP**: `ingest_documents()` with `source_type: "wikipedia"` and `titles: [...]`

### YouTube

Provide YouTube video URLs — transcripts are extracted and processed.

- **MCP**: `ingest_documents()` with `source_type: "youtube"` and `urls: [...]`

## Incremental Auto-Sync Summary

| Source | Auto-Sync | Detection Method |
|---|---|---|
| Alfresco | Real-time | Community ActiveMQ |
| Amazon S3 | Real-time | SQS event notifications |
| Azure Blob Storage | Real-time | Change feed |
| Google Cloud Storage | Real-time | Pub/Sub notifications |
| Google Drive | Near real-time | Changes API (polling) |
| OneDrive | Near real-time | Polling |
| SharePoint | Near real-time | Polling |
| Box | Near real-time | Events API (polling) |
| Local Filesystem | Real-time | OS watchdog events |
| File Upload, CMIS, Web, Wikipedia, YouTube | Not supported | — |

See [Incremental Auto-Sync](INCREMENTAL-UPDATE-AUTO-SYNC/README.md) for full setup.

---

## Supported File Formats

### Document Formats

- **PDF**: `.pdf`
  - **Docling**: Advanced layout analysis, table extraction, formula recognition, configurable OCR (EasyOCR, Tesseract, RapidOCR)
  - **LlamaParse**: Automatic OCR within parsing pipeline, multimodal vision processing
- **Microsoft Office**: `.docx`, `.xlsx`, `.pptx` and legacy formats (`.doc`, `.xls`, `.ppt`)
  - **Docling**: DOCX, XLSX, PPTX structure preservation and content extraction
  - **LlamaParse**: Full Office suite support including legacy formats and hundreds of variants
- **Web Formats**: `.html`, `.htm`, `.xhtml`
  - **Docling**: HTML/XHTML markup structure analysis
  - **LlamaParse**: HTML/XHTML content extraction and formatting
- **Data Formats**: `.csv`, `.tsv`, `.json`, `.xml`
  - **Docling**: CSV structured data processing
  - **LlamaParse**: CSV, TSV, JSON, XML with enhanced table understanding
- **Documentation**: `.md`, `.markdown`, `.asciidoc`, `.adoc`, `.rtf`, `.txt`, `.epub`
  - **Docling**: Markdown, AsciiDoc technical documentation with markup preservation
  - **LlamaParse**: Extended format support including RTF, EPUB, and hundreds of text format variants

### Image Formats

- **Standard Images**: `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.webp`, `.tiff`, `.tif`
  - **Docling**: OCR text extraction with configurable OCR backends (EasyOCR, Tesseract, RapidOCR)
  - **LlamaParse**: Automatic OCR with multimodal vision processing and context understanding

### Audio Formats

- **Audio Files**: `.wav`, `.mp3`, `.mp4`, `.m4a`
  - **Docling**: Automatic speech recognition (ASR) support
  - **LlamaParse**: Transcription and content extraction for MP3, MP4, MPEG, MPGA, M4A, WAV, WEBM

### Processing Intelligence

- **Parser Selection**:
  - **Docling** (default, free): Local processing with specialized CV models (DocLayNet layout analysis, TableFormer for tables), configurable OCR backends (EasyOCR/Tesseract/RapidOCR), optional local VLM support (Granite-Docling, SmolDocling, Qwen2.5-VL, Pixtral)
  - **LlamaParse** (cloud API, 3 credits/page): Automatic OCR in parsing pipeline, supports hundreds of file formats, fast mode (OCR-only), default mode (proprietary LlamaCloud model), premium mode (proprietary VLM mixture), multimodal mode (bring your own API keys: OpenAI GPT-4o, Anthropic Claude 3.5/4.5 Sonnet, Google Gemini 1.5/2.0, Azure OpenAI)
- **Output Formats**:
  - **Flexible GraphRAG** saves both markdown and plaintext, then automatically selects which to use for processing (knowledge graph extraction, vector embeddings, and search indexing) — defaults to markdown for tables, plaintext for text-heavy docs — override with `PARSER_FORMAT_FOR_EXTRACTION`
  - **Docling** supports: Markdown, JSON (lossless with bounding boxes and provenance), HTML, plain text, and DocTags (specialized markup preserving multi-column layouts, mathematical formulas, and code blocks)
  - **LlamaParse** supports: Markdown, plain text, raw JSON, XLSX (extracted tables), PDF, images (extracted separately), and structured output (beta — enforces custom JSON schema for strict data model extraction)
- **Format Detection**: Automatic routing based on file extension and content analysis

See [Document Processing](DOC-PROCESSING/SUPPORTED-FILE-FORMATS.md) for full details.
