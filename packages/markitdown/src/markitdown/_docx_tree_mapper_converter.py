"""Document-map converter -- builds a hierarchical tree from converted markdown.

Instead of re-implementing format-specific parsing (which duplicates logic and
misses the pre-processing steps each converter relies on), this module
delegates to the existing ``MarkItDown.convert()`` pipeline to obtain the
markdown output, then parses the heading structure from that markdown to
build a ``DocumentMap``.

This guarantees that:
* Every format the main pipeline supports is automatically mapped.
* Pre-processing steps (DOCX ZIP re-packaging, OMML→LaTeX, etc.) are honoured.
* Fallback chains (e.g. .docx detected as plain text) work correctly.

Tree construction
-----------------
Section titles (markdown headings ``# ... ######``) become **primary branches**.
The body text beneath each heading is condensed into a **detailed summary**
that appears as the branch annotation.  Heading levels drive parent/child
nesting::

    # Chapter 1              →  depth-1 branch of root
    ## Section 1.1           →  depth-2 child of Chapter 1
    ### Subsection 1.1.1     →  depth-3 child of Section 1.1
    ## Section 1.2           →  depth-2 child of Chapter 1
    # Chapter 2              →  depth-1 branch of root
"""

import re
from typing import Any, List, Optional

from ._docx_tree_mapper import DocumentMap, TreeNode, TreeMediaItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approx_token_count(text: str) -> int:
    return len(text.split())


def _to_detailed_summary(text: str, max_len: int = 300) -> str:
    """Produce a multi-sentence summary (up to *max_len* chars)."""
    text = " ".join(text.split())
    if not text:
        return "No content."
    if len(text) <= max_len:
        return text.rstrip()
    end = 0
    for i, ch in enumerate(text[:max_len]):
        if ch in ".!?":
            end = i + 1
    if end > 0:
        return text[:end].strip()
    return text[:max_len].rsplit(" ", 1)[0] + "..."


def _to_one_sentence(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= 150:
        return text.rstrip()
    for i, ch in enumerate(text[:150]):
        if ch in ".!?":
            return text[: i + 1].strip()
    return text[:150].rsplit(" ", 1)[0] + "..."


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

_BASE_SCORES = {
    ".pdf": 80, ".docx": 85, ".pptx": 75, ".xlsx": 80, ".xls": 75,
    ".epub": 82, ".csv": 90, ".html": 88, ".htm": 88, ".ipynb": 88,
    ".ics": 85, ".txt": 95, ".json": 88, ".xml": 80, ".md": 98,
    ".rst": 90, ".msg": 55, ".zip": 50,
}

_STRUCTURAL_PENALTY = {
    ".msg": 15, ".zip": 15, ".pptx": 10, ".pdf": 8,
    ".epub": 5, ".xlsx": 5, ".xls": 8,
}


def _compute_confidence(extension: str, has_sections: bool, has_images_without_alt: bool) -> int:
    ext = extension.lower() if extension else ""
    base = _BASE_SCORES.get(ext, 30)
    penalty = _STRUCTURAL_PENALTY.get(ext, 0)
    adjustment = -5 if has_images_without_alt else (5 if has_sections else 0)
    return max(0, min(100, base - penalty + adjustment))


# ---------------------------------------------------------------------------
# Markdown parser → flat section list
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _parse_markdown_to_flat(markdown: str) -> List[dict]:
    """Extract a flat list of section dicts from markdown text.

    Each dict has keys: title, level, summary, media.
    """
    lines = markdown.split("\n")
    flat: List[dict] = []

    # Find all heading line indices and their levels
    heading_indices: List[tuple] = []  # (line_idx, level, title)
    for idx, line in enumerate(lines):
        m = _HEADING_RE.match(line.strip())
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if title:
                heading_indices.append((idx, level, title))

    for pos, (line_idx, level, title) in enumerate(heading_indices):
        # Collect body text from after this heading to before the next heading
        if pos + 1 < len(heading_indices):
            end_idx = heading_indices[pos + 1][0]
        else:
            end_idx = len(lines)

        body_lines: List[str] = []
        section_media: List[TreeMediaItem] = []

        for j in range(line_idx + 1, end_idx):
            stripped = lines[j].strip()
            if not stripped:
                continue
            body_lines.append(stripped)

            # Detect inline images
            for img_match in _IMAGE_RE.finditer(stripped):
                alt = img_match.group(1)
                src = img_match.group(2)
                desc = (
                    f"Image '{src}': {alt}" if alt
                    else f"Image '{src}' with no description available."
                )
                section_media.append(TreeMediaItem(type="image", description=desc))

        body = " ".join(body_lines)
        summary = _to_detailed_summary(body) if body else "Section with no body text."

        flat.append({
            "title": title,
            "level": level,
            "summary": summary,
            "media": section_media,
        })

    return flat


def _infer_sections_from_text(text: str) -> List[dict]:
    """Fallback: when no markdown headings are found, infer structure from
    paragraph breaks, capitalised lines, or bold markers."""
    flat: List[dict] = []
    lines = text.split("\n")

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        is_heading = False
        heading_level = 1

        # Bold-text headings: **Title** at start of line
        bold_match = re.match(r"^\*\*(.+?)\*\*\s*$", stripped)
        if bold_match:
            is_heading = True
            heading_level = 1
            stripped = bold_match.group(1)

        # ALL-CAPS short lines
        elif (
            len(stripped) <= 80
            and stripped == stripped.upper()
            and stripped != stripped.lower()
            and any(c.isalpha() for c in stripped)
        ):
            is_heading = True
            heading_level = 1

        # Title-case short lines followed by text
        elif (
            len(stripped) <= 80
            and stripped[0].isupper()
            and stripped != stripped.lower()
            and idx + 1 < len(lines)
            and lines[idx + 1].strip()
            and not any(c in stripped for c in ".!?;,:")
        ):
            is_heading = True
            heading_level = 2

        if is_heading:
            title = stripped
            body_parts: List[str] = []
            for j in range(idx + 1, min(idx + 15, len(lines))):
                next_line = lines[j].strip()
                if not next_line:
                    if body_parts:
                        break
                    continue
                # Stop if we hit what looks like another heading
                if re.match(r"^\*\*(.+?)\*\*\s*$", next_line):
                    break
                if next_line == next_line.upper() and len(next_line) <= 80 and any(c.isalpha() for c in next_line):
                    break
                body_parts.append(next_line)
                if len(" ".join(body_parts)) > 300:
                    break

            body = " ".join(body_parts)
            summary = _to_detailed_summary(body) if body else "Section with no body text."
            flat.append({
                "title": title,
                "level": heading_level,
                "summary": summary,
                "media": [],
            })

    return flat


# ---------------------------------------------------------------------------
# Tree-building
# ---------------------------------------------------------------------------


def _build_tree(flat_sections: List[dict]) -> TreeNode:
    """Convert a flat list into a nested TreeNode tree using a stack."""
    root = TreeNode(title="(root)", level=0, summary="")
    stack: List[TreeNode] = [root]

    for sec in flat_sections:
        node = TreeNode(
            title=sec["title"],
            level=sec["level"],
            summary=sec["summary"],
            page=sec.get("page"),
            media=sec.get("media", []),
        )
        # Walk stack back to the nearest ancestor with a strictly lower level.
        while len(stack) > 1 and stack[-1].level >= node.level:
            stack.pop()

        stack[-1].children.append(node)
        stack.append(node)

    return root


# ---------------------------------------------------------------------------
# Public converter class
# ---------------------------------------------------------------------------


class DocxTreeMapConverter:
    """Builds a ``DocumentMap`` by delegating to the MarkItDown conversion
    pipeline, then parsing the resulting markdown into a hierarchical tree.

    Usage::

        from markitdown import MarkItDown

        md = MarkItDown()
        converter = DocxTreeMapConverter(md)
        doc_map = converter.generate("document.docx")
        print(doc_map.to_json())
    """

    def __init__(self, markitdown_instance: Any) -> None:
        self._md = markitdown_instance

    def generate(self, source: Any, **kwargs: Any) -> DocumentMap:
        """Generate a DocumentMap for *source*.

        Args:
            source: Anything accepted by ``MarkItDown.convert()`` -- a file
                path string, a ``pathlib.Path``, or a ``BinaryIO`` stream.
            **kwargs: Forwarded to ``MarkItDown.convert()`` (e.g.
                ``stream_info``, ``keep_data_uris``).

        Returns:
            A fully populated ``DocumentMap``.
        """
        # --- Step 1: Run the real conversion pipeline ----------------------
        result = self._md.convert(source, **kwargs)
        markdown = result.markdown or ""
        title = result.title

        # --- Step 2: Detect the file extension for metadata ----------------
        import os
        if isinstance(source, str):
            ext = os.path.splitext(source)[1].lower()
        elif hasattr(source, "name"):
            ext = os.path.splitext(source.name)[1].lower()
        else:
            ext = kwargs.get("stream_info", None)
            if ext and hasattr(ext, "extension"):
                ext = (ext.extension or "").lower()
            else:
                ext = ""

        # --- Step 3: Parse headings from the markdown ----------------------
        flat = _parse_markdown_to_flat(markdown)

        # If no markdown headings were found, try inferring from text patterns
        if not flat:
            flat = _infer_sections_from_text(markdown)

        # --- Step 4: Build the tree ----------------------------------------
        root = _build_tree(flat)

        # --- Step 5: Derive subject ----------------------------------------
        subject = title if title else ""
        if not subject:
            # First heading
            if flat:
                subject = flat[0]["title"]
            else:
                snippet = " ".join(markdown.split()[:12])
                subject = snippet if snippet else "Untitled"

        # --- Step 6: Compute metadata --------------------------------------
        has_images_without_alt = any(
            "no description available" in m.description.lower()
            for sec in flat for m in sec.get("media", [])
            if m.type == "image"
        )
        confidence = _compute_confidence(ext, bool(flat), has_images_without_alt)
        token_count = _approx_token_count(markdown)

        return DocumentMap(
            file_type=ext if ext else ".txt",
            subject=subject,
            total_token_count=token_count,
            conversion_confidence=confidence,
            root=root,
        )
