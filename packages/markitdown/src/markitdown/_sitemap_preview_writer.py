"""Sitemap-preview output writer.

Handles formatting and writing SitemapPreviewResult instances to various
output destinations (files, streams, stdout).  This module completes the
sitemap-preview pipeline:

    _sitemap_preview.py           -- data model (dataclasses)
    _sitemap_preview_converter.py -- analysis engine (reads files)
    _sitemap_preview_writer.py    -- output writer (writes previews)

Supported output formats:

* **json** (default) -- compact or pretty-printed JSON
* **text** -- human-readable plain-text summary
"""

import io
import sys
from typing import BinaryIO, Optional, TextIO, Union


from ._sitemap_preview import SitemapPreviewResult


class SitemapPreviewWriter:
    """Writes a SitemapPreviewResult to a file, stream, or stdout.

    Usage::

        from markitdown import SitemapPreviewWriter, SitemapPreviewResult

        writer = SitemapPreviewWriter()

        # Write JSON to a file
        writer.write(result, "preview.json")

        # Write human-readable text to a file
        writer.write(result, "preview.txt", fmt="text")

        # Write to stdout
        writer.write(result)

        # Get formatted string without writing
        json_str = writer.format(result, fmt="json")
        text_str = writer.format(result, fmt="text")
    """

    def format(
        self,
        result: SitemapPreviewResult,
        *,
        fmt: str = "json",
        indent: int = 2,
    ) -> str:
        """Format a SitemapPreviewResult as a string.

        Args:
            result: The preview result to format.
            fmt: Output format -- ``"json"`` (default) or ``"text"``.
            indent: JSON indentation level (only used when *fmt* is ``"json"``).

        Returns:
            The formatted string.
        """
        if fmt == "json":
            return result.to_json(indent=indent)
        elif fmt == "text":
            return self._format_text(result)
        else:
            raise ValueError(
                f"Unsupported format: {fmt!r}. Supported formats: 'json', 'text'."
            )

    def write(
        self,
        result: SitemapPreviewResult,
        destination: Union[str, TextIO, None] = None,
        *,
        fmt: str = "json",
        indent: int = 2,
    ) -> str:
        """Format and write a SitemapPreviewResult.

        Args:
            result: The preview result to write.
            destination: Where to write. Accepts:
                - A file path (str) -- writes to that file.
                - A text stream (e.g. ``sys.stdout``) -- writes to the stream.
                - ``None`` -- writes to ``sys.stdout``.
            fmt: Output format -- ``"json"`` (default) or ``"text"``.
            indent: JSON indentation level (only used when *fmt* is ``"json"``).

        Returns:
            The formatted output string (same content that was written).
        """
        output = self.format(result, fmt=fmt, indent=indent)

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
    # Human-readable text formatter
    # ------------------------------------------------------------------

    def _format_text(self, result: SitemapPreviewResult) -> str:
        """Render a SitemapPreviewResult as a human-readable text summary."""
        lines = []

        lines.append("=" * 60)
        lines.append("  SITEMAP PREVIEW")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"  File type:              {result.file_type}")
        lines.append(f"  Subject:                {result.subject}")
        page_display = str(result.total_page_count) if result.total_page_count is not None else "N/A"
        lines.append(f"  Total page count:       {page_display}")
        lines.append(f"  Total token count:      {result.total_token_count}")
        lines.append(f"  Conversion confidence:  {result.conversion_confidence}%")
        lines.append("")

        # Table of contents
        lines.append("-" * 60)
        lines.append("  TABLE OF CONTENTS")
        lines.append("-" * 60)
        if result.sections:
            for i, section in enumerate(result.sections, start=1):
                page_str = f"p.{section.page}" if section.page is not None else "  --"
                lines.append(f"  {i:>3}. [{page_str:>5}]  {section.title}")
                lines.append(f"               {section.summary}")
        else:
            lines.append("  (no sections detected)")
        lines.append("")

        # Media listing
        lines.append("-" * 60)
        lines.append("  IMAGES & TABLES")
        lines.append("-" * 60)
        if result.media:
            images = [m for m in result.media if m.type == "image"]
            tables = [m for m in result.media if m.type == "table"]

            if images:
                lines.append(f"  Images ({len(images)}):")
                for img in images:
                    page_str = f"p.{img.page}" if img.page is not None else "--"
                    lines.append(f"    [{page_str}]  {img.description}")

            if tables:
                lines.append(f"  Tables ({len(tables)}):")
                for tbl in tables:
                    page_str = f"p.{tbl.page}" if tbl.page is not None else "--"
                    lines.append(f"    [{page_str}]  {tbl.description}")
        else:
            lines.append("  (no images or tables detected)")
        lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines) + "\n"
