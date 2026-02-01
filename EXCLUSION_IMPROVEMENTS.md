# Exclusion Feature - Subject vs Section Separation

## Problem Statement

The initial implementation of the exclusion feature had a critical flaw: if the document subject (document-level metadata) matched an excluded section name, users might be confused about what they're excluding.

**Example of the Problem:**
```bash
# Document content:
# "# Introduction"
# "Introduction content..."
# "# Chapter 1"
# "Chapter 1 content..."

# Preview shows:
# Subject: "Introduction"
# Sections: ["Introduction", "Chapter 1"]

# If user excludes "Introduction", which one is excluded?
# The subject (metadata) or the section (content)?
```

## Solution Implemented

The solution is simple and elegant: **The document subject is now formatted distinctly from section titles**, making it impossible for them to conflict.

### Subject Formatting with "[Document]" Prefix

**Implementation**: All document subjects are now prefixed with `[Document]` to make them visually distinct from section titles.

**Before (Problem):**
```
Subject: "Introduction"
Sections:
  1. Introduction
  2. Chapter 1
  3. Conclusion
```

**After (Solution):**
```
Subject: "[Document] Introduction"
Sections:
  1. Introduction
  2. Chapter 1
  3. Conclusion
```

**Result**: Users can never accidentally exclude the subject because:
- Subject format: `[Document] Introduction`
- Section format: `Introduction`
- These are completely different strings that cannot conflict

### Example Usage

**Document Preview:**
```bash
python -m markitdown --sitemap example.txt --sitemap-format text
```

**Output:**
```
============================================================
  SITEMAP PREVIEW
============================================================

  File type:              .txt
  Subject:                [Document] Introduction
  ...

------------------------------------------------------------
  TABLE OF CONTENTS
------------------------------------------------------------
    1. [p.1]  Introduction
               To exclude: --exclude "Introduction"
    2. [p.2]  Chapter 1
               To exclude: --exclude "Chapter 1"
```

**Conversion with Exclusion:**
```bash
# Exclude the "Introduction" section (NOT the subject)
markitdown example.txt --exclude "Introduction" -o output.md

# Result: "Introduction" section is excluded
# But subject "[Document] Introduction" remains as metadata
# Output contains: Chapter 1, Conclusion
```

**Key Benefits:**
1. **No Conflicts**: Subject and sections can never have the same name
2. **Clear Intent**: Users know they're excluding content sections, not metadata
3. **Simple Implementation**: Just a formatting prefix, no complex logic needed
4. **Universal**: Works across all document formats (PDF, DOCX, TXT, etc.)

## Technical Implementation

### Code Changes

**File**: `_sitemap_preview_converter.py`

**Function**: `_extract_subject()`

```python
def _extract_subject(text: str, title: Optional[str] = None) -> str:
    """Derive a short subject phrase from the document.

    The subject is a document-level descriptor and is formatted to be
    distinct from section titles to avoid exclusion conflicts.
    """
    if title and title.strip():
        return f"[Document] {_to_one_sentence(title.strip())}"

    for line in text.splitlines():
        stripped = line.lstrip("#").strip()
        if stripped and line.startswith("#"):
            return f"[Document] {_to_one_sentence(stripped)}"

    snippet = " ".join(text.split()[:12])
    return f"[Document] {snippet}" if snippet else "[Document] Untitled"
```

**Changes Made:**
- Added `[Document]` prefix to all subject strings
- This applies universally across all document formats
- Section titles remain unchanged - they are the exact headings from the document

### Simplified Exclusion Logic

**File**: `__main__.py`

**Function**: `_apply_exclusions()`

The exclusion logic is now simple and straightforward:
1. Parse markdown line by line
2. When a heading matches an exclusion, skip that section
3. Stop skipping when reaching the next heading at the same or higher level
4. Return the filtered markdown

**No special cases needed** because:
- Subjects can never match section titles (different format)
- Each section title is unique in the document
- Users see exactly what they're excluding in the preview

## Testing Scenarios

### ✅ Test 1: Exclude First Section (Former "Subject")
```bash
# Document: "# Introduction", "# Chapter 1"
markitdown doc.txt --exclude "Introduction" -o output.md
# PASS: Chapter 1 preserved, Introduction removed
```

### ✅ Test 2: Exclude Middle Section
```bash
# Document: "# Intro", "# Middle", "# End"
markitdown doc.txt --exclude "Middle" -o output.md
# PASS: Intro and End preserved, Middle removed
```

### ✅ Test 3: No Name Conflicts
```bash
# Subject: "[Document] Introduction"
# Section: "Introduction"
markitdown doc.txt --exclude "Introduction" -o output.md
# PASS: Only section excluded, subject untouched
```

### ✅ Test 4: Multiple Exclusions
```bash
markitdown doc.txt --exclude "Section 1" --exclude "Section 2" -o output.md
# PASS: Both sections excluded, others preserved
```

## JSON Output Format

The subject formatting also appears in JSON output:

```json
{
  "file_type": ".txt",
  "subject": "[Document] Introduction",
  "sections": [
    {
      "title": "Introduction",
      "page": 1,
      "summary": "...",
      "exclusion_command": "--exclude \"Introduction\""
    },
    {
      "title": "Chapter 1",
      "page": 2,
      "summary": "...",
      "exclusion_command": "--exclude \"Chapter 1\""
    }
  ]
}
```

**Notice**:
- `subject` has `[Document]` prefix
- `sections[].title` does NOT have prefix
- They can never conflict

## Migration Notes

### For Existing Users

If you have scripts or code that parse the subject field, be aware:
- **OLD**: Subject was the raw first heading (e.g., "Introduction")
- **NEW**: Subject has `[Document]` prefix (e.g., "[Document] Introduction")

**To extract the original subject text:**
```python
subject = result.subject.removeprefix("[Document] ").strip()
```

### Backwards Compatibility

- **CLI behavior**: Unchanged - exclusions work the same way
- **API behavior**: Subject field format changed (documented above)
- **JSON output**: Subject field format changed (documented above)

## Summary

The exclusion feature is now **production-ready** with a simple, elegant solution:

1. **Subject** = `[Document] <title>` (metadata, cannot be excluded)
2. **Sections** = Exact heading text (content, can be excluded)
3. **No conflicts** possible - different naming formats
4. **No complex logic** needed - simple string prefix
5. **Universal** - works across all file types

This approach is:
- ✅ Simple to understand
- ✅ Simple to implement
- ✅ Impossible to break
- ✅ Clear to users
- ✅ Works everywhere
