# Exclusion Feature for MarkItDown

## Overview

The exclusion feature allows users to exclude specific sections from the table of contents when converting documents to Markdown. This feature works seamlessly with the preview functionality to help users identify which sections to exclude.

## How It Works

### 1. Preview Your Document

First, use the `--sitemap` flag to preview the document structure and see available sections:

```bash
markitdown --sitemap example.txt --sitemap-format text
```

**Output:**
```
============================================================
  SITEMAP PREVIEW
============================================================

  File type:              .txt
  Subject:                Introduction
  Total page count:       1
  Total token count:      56
  Conversion confidence:  100%

------------------------------------------------------------
  TABLE OF CONTENTS
------------------------------------------------------------
    1. [   --]  Introduction
               Section with no body text.
               To exclude: --exclude "Introduction"
    2. [   --]  Background
               Section with no body text.
               To exclude: --exclude "Background"
    3. [   --]  Chapter 1
               Section with no body text.
               To exclude: --exclude "Chapter 1"
    4. [   --]  Conclusion
               Section with no body text.
               To exclude: --exclude "Conclusion"
```

### 2. Convert with Exclusions

Use the preview information to exclude specific sections:

```bash
markitdown example.txt -o output.md --exclude "Chapter 1" --exclude "Conclusion"
```

This command will:
- Convert the document to Markdown
- Exclude "Chapter 1" and all its subsections
- Exclude "Conclusion" and all its subsections
- Save the filtered result to `output.md`

### 3. JSON Preview Format

You can also get the exclusion commands in JSON format:

```bash
markitdown --sitemap example.txt
```

**Output:**
```json
{
  "file_type": ".txt",
  "subject": "Introduction",
  "sections": [
    {
      "title": "Introduction",
      "page": null,
      "summary": "Section with no body text.",
      "exclusion_command": "--exclude \"Introduction\""
    },
    {
      "title": "Chapter 1",
      "page": null,
      "summary": "Section with no body text.",
      "exclusion_command": "--exclude \"Chapter 1\""
    }
  ]
}
```

## Command Syntax

### Preview Commands
```bash
# Text format preview
markitdown --sitemap <file> --sitemap-format text

# JSON format preview (default)
markitdown --sitemap <file>

# Save preview to file
markitdown --sitemap <file> -o preview.json
```

### Conversion with Exclusions
```bash
# Single exclusion
markitdown <file> -o output.md --exclude "Section Name"

# Multiple exclusions
markitdown <file> -o output.md --exclude "Section 1" --exclude "Section 2"

# Output to stdout
markitdown <file> --exclude "Section Name"
```

## Features

### 1. Section Hierarchy Support
When you exclude a section, all its subsections are automatically excluded:

```bash
markitdown document.md --exclude "Chapter 1"
```

This will exclude:
- Chapter 1
- All subsections under Chapter 1 (e.g., Section 1.1, Section 1.2)

### 2. Multiple Exclusions
You can exclude multiple sections in a single command:

```bash
markitdown document.md --exclude "Introduction" --exclude "Conclusion" --exclude "Appendix"
```

### 3. Format Support
The exclusion feature works with all supported document formats:
- PDF (`.pdf`)
- DOCX (`.docx`)
- PPTX (`.pptx`)
- XLSX (`.xlsx`)
- XLS (`.xls`)
- EPUB (`.epub`)
- HTML (`.html`)
- Markdown (`.md`)
- Text files (`.txt`)
- Jupyter Notebooks (`.ipynb`)
- CSV (`.csv`)
- iCalendar (`.ics`)
- And more...

### 4. Shell-Safe Quoting
Section titles with special characters are automatically escaped:

```bash
--exclude "Chapter: \"Introduction\""
```

### 5. Subject/Section Name Separation
The document subject is formatted distinctly from section titles to prevent conflicts:

- **Subject Format**: `[Document] <title>` - Document-level metadata
- **Section Format**: `<title>` - Exact heading from document content
- **No Conflicts**: These different formats make conflicts impossible

**Example:**
```bash
# Preview shows:
# Subject: "[Document] Introduction"
# Sections: ["Introduction", "Chapter 1"]

markitdown doc.txt --exclude "Introduction" -o output.md
# Result: "Introduction" section excluded, other sections kept
# Subject "[Document] Introduction" is metadata, not excludable
```

## Use Cases

### 1. Remove Confidential Sections
```bash
markitdown report.pdf --exclude "Financial Data" --exclude "Internal Notes" -o public_report.md
```

### 2. Extract Specific Content
```bash
markitdown book.epub --exclude "Copyright" --exclude "Acknowledgments" --exclude "Index" -o main_content.md
```

### 3. Focus on Specific Chapters
```bash
markitdown thesis.docx --exclude "Abstract" --exclude "References" --exclude "Appendix" -o chapters_only.md
```

### 4. Remove Boilerplate
```bash
markitdown presentation.pptx --exclude "Title Slide" --exclude "Thank You" -o slides_content.md
```

## Technical Details

### Implementation
The exclusion feature consists of three main components:

1. **Preview Enhancement**: Each section in the preview includes an `exclusion_command` field showing the exact command to exclude that section.

2. **Command-Line Argument**: The `--exclude` flag can be used multiple times to specify sections to exclude.

3. **Section Filtering**: The markdown output is filtered using regex-based heading detection to remove excluded sections and their content.

### Section Matching
- **Exact Matching**: Sections are matched by exact title (case-sensitive)
- **Hierarchical Removal**: When a section is excluded, all content up to the next section at the same or higher level is removed
- **Subject Protection**: Document subjects use `[Document]` prefix and cannot match section titles

## Examples

### Example 1: Text Document
```bash
# Preview
markitdown --sitemap document.txt --sitemap-format text

# Convert excluding specific sections
markitdown document.txt -o output.md --exclude "Introduction" --exclude "Conclusion"
```

### Example 2: PDF Document
```bash
# Preview with JSON
markitdown --sitemap report.pdf -o preview.json

# Convert excluding chapters
markitdown report.pdf -o report.md --exclude "Chapter 1" --exclude "Chapter 5"
```

### Example 3: XLSX Spreadsheet
```bash
# Preview sheets
markitdown --sitemap data.xlsx --sitemap-format text

# Convert excluding specific sheets
markitdown data.xlsx -o data.md --exclude "Sheet2" --exclude "Sheet3"
```

## Workflow

1. **Discover** → Use `--sitemap` to see all available sections
2. **Identify** → Note the exclusion commands for unwanted sections
3. **Exclude** → Run the conversion with `--exclude` flags
4. **Verify** → Check the output file to ensure correct sections were removed

## Subject vs Section Names

### No Naming Conflicts

The exclusion feature is designed to prevent confusion between the document subject (metadata) and section titles (content):

**Document Subject**: Always formatted as `[Document] <title>`
- Example: `[Document] Introduction`
- This is metadata showing what the document is about
- **Cannot be excluded** (it's not a content section)

**Section Titles**: Exact heading text from the document
- Example: `Introduction` (from `# Introduction`)
- These are content sections in the table of contents
- **Can be excluded** using their exact title

### Example

**Preview Output:**
```
Subject: [Document] Introduction
TABLE OF CONTENTS:
  1. Introduction    --exclude "Introduction"
  2. Chapter 1       --exclude "Chapter 1"
  3. Conclusion      --exclude "Conclusion"
```

**Result**: The subject `[Document] Introduction` and section `Introduction` are different strings that cannot conflict.

## Notes

- Exclusion only applies to the markdown conversion output, not to the preview
- The preview always shows all sections to help you decide what to exclude
- Empty lines and spacing are preserved around excluded sections
- If no sections match the exclusion criteria, the full document is output
- Document subjects are prefixed with `[Document]` to avoid naming conflicts with sections
- Section titles in the table of contents match exactly what appears in the document
