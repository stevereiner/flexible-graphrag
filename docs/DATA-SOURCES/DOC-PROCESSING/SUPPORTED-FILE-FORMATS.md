# Supported File Formats

Flexible GraphRAG supports a wide range of document, image, and audio formats through its two parser options: **Docling** (local, default) and **LlamaParse** (cloud API).

## Document Formats

| Format | Extensions | Docling | LlamaParse |
|---|---|---|---|
| **PDF** | `.pdf` | Advanced layout analysis, table extraction, formula recognition, configurable OCR (EasyOCR, Tesseract, RapidOCR) | Automatic OCR, multimodal vision processing |
| **Microsoft Office** | `.docx`, `.xlsx`, `.pptx`, `.doc`, `.xls`, `.ppt` | DOCX, XLSX, PPTX structure preservation | Full Office suite including legacy formats and hundreds of variants |
| **Web** | `.html`, `.htm`, `.xhtml` | HTML/XHTML markup structure analysis | HTML/XHTML content extraction and formatting |
| **Data** | `.csv`, `.tsv`, `.json`, `.xml` | CSV structured data processing | CSV, TSV, JSON, XML with enhanced table understanding |
| **Documentation** | `.md`, `.markdown`, `.asciidoc`, `.adoc`, `.rtf`, `.txt`, `.epub` | Markdown, AsciiDoc with markup preservation | Extended format support including RTF, EPUB, and hundreds of text format variants |

## Image Formats

| Format | Extensions | Docling | LlamaParse |
|---|---|---|---|
| **Standard Images** | `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.webp`, `.tiff`, `.tif` | OCR text extraction with configurable backends (EasyOCR, Tesseract, RapidOCR) | Automatic OCR with multimodal vision processing |

## Audio Formats

| Format | Extensions | Docling | LlamaParse |
|---|---|---|---|
| **Audio** | `.wav`, `.mp3`, `.mp4`, `.m4a` | Automatic speech recognition (ASR) | Transcription for MP3, MP4, MPEG, MPGA, M4A, WAV, WEBM |

## Parser Comparison

### Docling (default, free, local)

- Local processing — no API costs, no data sent to third parties
- Specialized CV models: DocLayNet layout analysis, TableFormer for tables
- Configurable OCR backends: EasyOCR, Tesseract, RapidOCR
- Optional local VLM support: Granite-Docling, SmolDocling, Qwen2.5-VL, Pixtral
- GPU acceleration supported (CUDA / Apple Silicon) — see [Docling GPU Configuration](DOCLING-GPU-CONFIGURATION.md)
- Output formats: Markdown, JSON (lossless with bounding boxes), HTML, plain text, DocTags

### LlamaParse (cloud API, 3 credits/page by default)

- Cloud-based with advanced AI, multimodal parsing with Claude Sonnet 3.5
- Supports hundreds of file format variants
- Three modes: `parse_page_without_llm` (1 credit), `parse_page_with_llm` (3 credits, default), `parse_page_with_agent` (10–90 credits)
- Multimodal mode: bring your own API keys (OpenAI GPT-4o, Anthropic Claude, Google Gemini, Azure OpenAI)
- Output formats: Markdown, plain text, raw JSON, XLSX (extracted tables), PDF, images, structured output (beta)
- Get your API key at [LlamaCloud](https://cloud.llamaindex.ai/)

## Output Format Selection

Flexible GraphRAG saves **both** markdown and plaintext from the parser, then automatically selects which to use for knowledge graph extraction, vector embeddings, and search indexing:

- **Markdown** — preferred for documents with tables
- **Plaintext** — preferred for text-heavy documents

Override with `PARSER_FORMAT_FOR_EXTRACTION=auto|markdown|plaintext` in `.env`.

Save intermediate parsed output for inspection with `SAVE_PARSING_OUTPUT=true`.

See [Parser Output Files](PARSER-OUTPUT-FILES.md) for details on the saved files.
