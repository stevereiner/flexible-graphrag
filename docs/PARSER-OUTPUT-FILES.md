# Parser Output Files Documentation

## Overview

When `SAVE_PARSING_OUTPUT=true` is configured, the document processor saves intermediate parsing results to `./parsing_output/` for inspection.

## Output Files

### LlamaParse
- `<filename>_llamaparse_output.md` - Markdown output (multiple chunks automatically combined)
- `<filename>_llamaparse_output.txt` - Plaintext version (markdown formatting stripped)
- `<filename>_llamaparse_metadata.json` - Processing metadata

### Docling
- `<filename>_docling_markdown.md` - Markdown format (preserves tables)
- `<filename>_docling_plaintext.txt` - Plain text format (better for entity extraction)
- `<filename>_docling_metadata.json` - Processing metadata

## Configuration

```bash
# Enable saving both formats to disk
SAVE_PARSING_OUTPUT=true

# Control what format gets sent for knowledge graph extraction (optional)
PARSER_FORMAT_FOR_EXTRACTION=auto  # Default: markdown if tables, else plaintext
#PARSER_FORMAT_FOR_EXTRACTION=markdown  # Always use markdown
#PARSER_FORMAT_FOR_EXTRACTION=plaintext  # Always use plaintext
```

## Automatic Behavior

The system automatically:
- **Saves both formats** (markdown + plaintext) to disk for inspection
- **Combines** LlamaParse chunks from the same PDF into one file
- **Detects and logs** parser errors
- **Detects** LaTeX/math expressions that may cause preview issues

**For Knowledge Graph Extraction:**
- `auto` (default): Documents **with tables** → markdown format, **without tables** → plaintext format
- `markdown`: Always sends markdown (preserves structure, better for tables)
- `plaintext`: Always sends plaintext (better for entity extraction in text-heavy docs)

## KaTeX Preview Errors

If you see errors like `ParseError: KaTeX parse error` in the VS Code/Cursor markdown preview, these are **rendering errors**, not parsing errors. The actual `.md` file content is correct - it's just the preview renderer having trouble with table syntax or math expressions. You can ignore these or use a different markdown viewer.
