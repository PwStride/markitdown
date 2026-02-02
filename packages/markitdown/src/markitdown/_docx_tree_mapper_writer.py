"""Document-map output writer.

Handles formatting and writing ``DocumentMap`` instances to various output
destinations (files, streams, stdout).  This module completes the document
mapping pipeline:

    _docx_tree_mapper.py            -- data model (TreeNode, DocumentMap)
    _docx_tree_mapper_converter.py  -- analysis engine (reads files)
    _docx_tree_mapper_writer.py     -- output writer (writes maps)

Supported output formats:

* **json** (default) -- compact or pretty-printed JSON
* **text** -- human-readable tree-drawing layout

Text style selection
--------------------
The ``preview_style`` parameter on :py:meth:`format` / :py:meth:`write`
controls which visual layout is used when *fmt* is ``"text"``.

``"classic"``
    A plain-ASCII tree using ``|``, ``+--``, and ``\\--`` connectors.
    No colour codes are emitted.

``"mono"``
    A modern tree using Unicode box-drawing characters (``├──``, ``└──``,
    ``│``) with ANSI colour accents.  Headings use the violet accent from
    the preview-style palette; summaries use muted slate.  Confidence
    scores are colour-coded with three badge tiers.

``"tree"``
    The default style for document maps.  Similar to ``"mono"`` but uses
    a distinctive indigo accent colour and a specialised header label.
"""

import sys
from typing import TextIO, Union

from ._docx_tree_mapper import DocumentMap, TreeNode
from ._preview_style import resolve_style, STYLES


# ---------------------------------------------------------------------------
# Fallback style name -- use "tree" if registered, else "mono"
# ---------------------------------------------------------------------------

_DEFAULT_MAP_STYLE = "tree" if "tree" in STYLES else "mono"


class DocxTreeMapWriter:
    """Writes a DocumentMap to a file, stream, or stdout.

    Usage::

        from markitdown import DocxTreeMapWriter, DocumentMap

        writer = DocxTreeMapWriter()

        # Write JSON to a file
        writer.write(doc_map, "map.json")

        # Write tree-drawing text to stdout
        writer.write(doc_map, fmt="text")

        # Write tree-drawing text with the classic ASCII layout
        writer.write(doc_map, fmt="text", preview_style="classic")

        # Get formatted string without writing
        text = writer.format(doc_map, fmt="text")
    """

    def format(
        self,
        doc_map: DocumentMap,
        *,
        fmt: str = "json",
        indent: int = 2,
        preview_style: str = _DEFAULT_MAP_STYLE,
    ) -> str:
        """Format a DocumentMap as a string.

        Args:
            doc_map: The document map to format.
            fmt: Output format -- ``"json"`` (default) or ``"text"``.
            indent: JSON indentation level (only used when *fmt* is ``"json"``).
            preview_style: Visual style for text output.

        Returns:
            The formatted string.
        """
        if fmt == "json":
            return doc_map.to_json(indent=indent)
        elif fmt == "text":
            style = resolve_style(preview_style)
            return self._format_text(doc_map, style)
        else:
            raise ValueError(
                f"Unsupported format: {fmt!r}. Supported formats: 'json', 'text'."
            )

    def write(
        self,
        doc_map: DocumentMap,
        destination: Union[str, TextIO, None] = None,
        *,
        fmt: str = "json",
        indent: int = 2,
        preview_style: str = _DEFAULT_MAP_STYLE,
    ) -> str:
        """Format and write a DocumentMap.

        Args:
            doc_map: The document map to write.
            destination: Where to write (file path, stream, or None for stdout).
            fmt: Output format -- ``"json"`` (default) or ``"text"``.
            indent: JSON indentation level (only used when *fmt* is ``"json"``).
            preview_style: Visual style for text output.

        Returns:
            The formatted output string.
        """
        output = self.format(doc_map, fmt=fmt, indent=indent, preview_style=preview_style)

        if destination is None:
            print(output)
        elif isinstance(destination, str):
            with open(destination, "w", encoding="utf-8") as f:
                f.write(output)
        elif hasattr(destination, "write") and callable(destination.write):
            destination.write(output)
        else:
            raise TypeError(
                f"Invalid destination type: {type(destination)}. "
                "Expected a file path (str), a text stream, or None for stdout."
            )

        return output

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    def _format_text(self, doc_map: DocumentMap, style: dict) -> str:
        if style.get("accent"):
            return self._render_tree_colour(doc_map, style)
        return self._render_tree_plain(doc_map, style)

    # ------------------------------------------------------------------
    # Plain-ASCII tree renderer  (classic style)
    # ------------------------------------------------------------------

    def _render_tree_plain(self, doc_map: DocumentMap, style: dict) -> str:
        W = style["rule_width"]
        TOP = style["rule_top"] * W
        lines: list = []

        lines.append(TOP)
        lines.append("  DOCUMENT MAP")
        lines.append(TOP)
        lines.append("")

        # Metadata
        lines.append(f"  File type:              {doc_map.file_type}")
        lines.append(f"  Subject:                {doc_map.subject}")
        page_display = str(doc_map.total_page_count) if doc_map.total_page_count is not None else "N/A"
        lines.append(f"  Total page count:       {page_display}")
        lines.append(f"  Total token count:      {doc_map.total_token_count}")
        lines.append(f"  Conversion confidence:  {doc_map.conversion_confidence}%")
        lines.append("")

        # Section tree
        lines.append(style["rule_mid"] * W)
        lines.append("  CONTENT TREE")
        lines.append(style["rule_mid"] * W)
        lines.append("")

        root = doc_map.root
        if root.children:
            self._draw_plain_children(root.children, lines, prefix="  ")
        else:
            lines.append("  (no sections detected)")
        lines.append("")

        lines.append(TOP)
        return "\n".join(lines) + "\n"

    def _draw_plain_children(
        self, children: list, lines: list, prefix: str
    ) -> None:
        for i, child in enumerate(children):
            is_last = i == len(children) - 1
            connector = "\\-- " if is_last else "+-- "
            page_tag = f" [p.{child.page}]" if child.page is not None else ""

            lines.append(f"{prefix}{connector}{child.title}{page_tag}")
            lines.append(f"{prefix}{'    ' if is_last else '|   '}  {child.summary}")

            # Media items within this section
            for media in child.media:
                marker = "[img]" if media.type == "image" else "[tbl]"
                lines.append(f"{prefix}{'    ' if is_last else '|   '}  {marker} {media.description}")

            if child.children:
                child_prefix = prefix + ("    " if is_last else "|   ")
                self._draw_plain_children(child.children, lines, child_prefix)

    # ------------------------------------------------------------------
    # Colour tree renderer  (mono / tree style)
    # ------------------------------------------------------------------

    def _render_tree_colour(self, doc_map: DocumentMap, style: dict) -> str:
        A = style["accent"]
        M = style["mute"]
        R = style["reset"]
        W = style["rule_width"]
        RULE = style["rule_top"] * W

        lines: list = []

        # Header
        header_label = style.get("header_label", "DOCUMENT MAP")
        lines.append(f"{A}{RULE}{R}")
        lines.append(f"  {A}{header_label}{R}")
        lines.append(f"{A}{RULE}{R}")
        lines.append("")

        # Metadata
        page_display = str(doc_map.total_page_count) if doc_map.total_page_count is not None else "N/A"
        confidence_badge = self._confidence_badge(doc_map.conversion_confidence, style)

        lines.append(f"  {A}file type{R}          {doc_map.file_type}")
        lines.append(f"  {A}subject{R}            {doc_map.subject}")
        lines.append(f"  {A}pages{R}              {page_display}")
        lines.append(f"  {A}tokens{R}             {doc_map.total_token_count}")
        lines.append(f"  {A}confidence{R}         {confidence_badge}")
        lines.append("")

        # Section tree
        toc_label = style.get("toc_label", "CONTENT TREE")
        lines.append(f"  {A}{toc_label}{R}")
        lines.append(f"  {style['rule_mid'] * (W - 2)}")
        lines.append("")

        root = doc_map.root
        if root.children:
            self._draw_colour_children(root.children, lines, prefix="  ", style=style)
        else:
            lines.append(f"  {M}(no sections detected){R}")
        lines.append("")

        # Bottom rule
        lines.append(f"{A}{RULE}{R}")
        return "\n".join(lines) + "\n"

    def _draw_colour_children(
        self, children: list, lines: list, prefix: str, style: dict
    ) -> None:
        A = style["accent"]
        M = style["mute"]
        R = style["reset"]

        # Box-drawing connectors
        TEE = "\u251c\u2500\u2500"    # ├──
        ELL = "\u2514\u2500\u2500"    # └──
        BAR = "\u2502"                # │
        SPC = " "

        for i, child in enumerate(children):
            is_last = i == len(children) - 1
            connector = ELL if is_last else TEE
            page_tag = f" {M}[p.{child.page}]{R}" if child.page is not None else ""

            # Title line with connector
            lines.append(f"{prefix}{A}{connector}{R} {child.title}{page_tag}")

            # Summary line
            cont = f"{SPC}   " if is_last else f"{BAR}   "
            lines.append(f"{prefix}{cont} {M}{child.summary}{R}")

            # Media items
            for media in child.media:
                marker = f"{A}[img]{R}" if media.type == "image" else f"{A}[tbl]{R}"
                lines.append(f"{prefix}{cont} {marker} {M}{media.description}{R}")

            # Recurse into children
            if child.children:
                child_prefix = prefix + (f"{SPC}   " if is_last else f"{BAR}   ")
                lines.append(f"{prefix}{cont}")  # blank connector line before children
                self._draw_colour_children(child.children, lines, child_prefix, style)

            # Separator between siblings (except after last)
            if not is_last:
                lines.append(f"{prefix}{BAR}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _confidence_badge(score: int, style: dict) -> str:
        if style.get("badge_hi"):
            if score >= 70:
                colour = style["badge_hi"]
            elif score >= 40:
                colour = style["badge_mid"]
            else:
                colour = style["badge_lo"]
            return f"{colour}{score}%{style['reset']}"
        return f"{score}%"
