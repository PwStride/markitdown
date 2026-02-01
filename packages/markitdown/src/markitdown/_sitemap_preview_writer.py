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

Text style selection
--------------------
The ``preview_style`` parameter on :py:meth:`format` / :py:meth:`write`
controls which visual layout is used when *fmt* is ``"text"``.

``"classic"`` (default)
    The original plain-ASCII layout.  ``=`` and ``-`` rule lines, two-space
    indented labels.  No colour codes are emitted, so the output is safe
    for any consumer.

``"mono"``
    A modern minimalist layout.  Thin box-drawing rules, generous vertical
    spacing, and a single bold-violet accent colour that highlights
    headings and key labels.  Confidence scores are colour-coded with
    three distinct badge colours (emerald / amber / rose).  All colour
    information is carried by standard 24-bit ANSI escape sequences.

    Configuration details
    ~~~~~~~~~~~~~~~~~~~~~
    * **Accent colour** -- deep violet (``#8A2BE2`` / ``rgb(138,43,226)``)
      applied to panel headers, section numbers, and metadata labels.
    * **Muted text** -- slate grey (``#708090`` / ``rgb(112,128,144)``)
      used for section summaries and exclusion hints.
    * **Confidence badges** -- three-tier colour coding:

      ========  =========  ================================
      Tier      Colour     Condition
      ========  =========  ================================
      High      Emerald    score >= 70
      Mid       Amber      40 <= score < 70
      Low       Rose       score < 40
      ========  =========  ================================

    * **Rule characters** -- U+2500 (BOX DRAWINGS LIGHT HORIZONTAL, ``─``)
      at a width of 64 columns; replaces the ``=`` / ``-`` ASCII rules.
    * **Layout spacing** -- one blank line between every logical block
      (metadata, TOC, media) for readability.
    * **Number alignment** -- section indices are right-aligned in a
      3-column field, prefixed by the accent colour.

See ``_preview_style.py`` for the full style registry and instructions on
registering custom styles.
"""

import sys
from typing import TextIO, Union

from ._sitemap_preview import SitemapPreviewResult
from ._preview_style import resolve_style, DEFAULT_STYLE


class SitemapPreviewWriter:
    """Writes a SitemapPreviewResult to a file, stream, or stdout.

    Usage::

        from markitdown import SitemapPreviewWriter, SitemapPreviewResult

        writer = SitemapPreviewWriter()

        # Write JSON to a file
        writer.write(result, "preview.json")

        # Write human-readable text to a file  (classic layout)
        writer.write(result, "preview.txt", fmt="text")

        # Write human-readable text using the new minimalist layout
        writer.write(result, "preview.txt", fmt="text", preview_style="mono")

        # Write to stdout
        writer.write(result)

        # Get formatted string without writing
        json_str = writer.format(result, fmt="json")
        text_str = writer.format(result, fmt="text", preview_style="mono")
    """

    def format(
        self,
        result: SitemapPreviewResult,
        *,
        fmt: str = "json",
        indent: int = 2,
        preview_style: str = DEFAULT_STYLE,
    ) -> str:
        """Format a SitemapPreviewResult as a string.

        Args:
            result: The preview result to format.
            fmt: Output format -- ``"json"`` (default) or ``"text"``.
            indent: JSON indentation level (only used when *fmt* is ``"json"``).
            preview_style: Visual style for text output.  ``"mono"``
                (default) uses the minimalist layout with bold accent
                colours.  Pass ``"classic"`` to revert to the original
                plain-ASCII layout.  Ignored when *fmt* is ``"json"``.

        Returns:
            The formatted string.
        """
        if fmt == "json":
            return result.to_json(indent=indent)
        elif fmt == "text":
            style = resolve_style(preview_style)
            return self._format_text(result, style)
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
        preview_style: str = DEFAULT_STYLE,
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
            preview_style: Visual style for text output.  ``"mono"``
                (default) uses the minimalist layout with bold accent
                colours.  Pass ``"classic"`` to revert to the original
                plain-ASCII layout.  Ignored when *fmt* is ``"json"``.

        Returns:
            The formatted output string (same content that was written).
        """
        output = self.format(result, fmt=fmt, indent=indent, preview_style=preview_style)

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

    def _format_text(self, result: SitemapPreviewResult, style: dict) -> str:
        """Route to the renderer selected by *style*."""
        # "mono" uses its own layout; everything else falls back to classic.
        if style.get("accent"):
            return self._render_mono(result, style)
        return self._render_classic(result, style)

    # ------------------------------------------------------------------
    # Classic renderer  (original layout, preserved verbatim in logic)
    # ------------------------------------------------------------------

    def _render_classic(self, result: SitemapPreviewResult, style: dict) -> str:
        """Render a SitemapPreviewResult as a human-readable text summary
        using the original classic layout."""
        W = style["rule_width"]
        TOP = style["rule_top"] * W
        MID = style["rule_mid"] * W
        lines = []

        lines.append(TOP)
        lines.append("  SITEMAP PREVIEW")
        lines.append(TOP)
        lines.append("")
        lines.append(f"  File type:              {result.file_type}")
        lines.append(f"  Subject:                {result.subject}")
        page_display = str(result.total_page_count) if result.total_page_count is not None else "N/A"
        lines.append(f"  Total page count:       {page_display}")
        lines.append(f"  Total token count:      {result.total_token_count}")
        lines.append(f"  Conversion confidence:  {result.conversion_confidence}%")
        lines.append("")

        # Table of contents
        lines.append(MID)
        lines.append("  TABLE OF CONTENTS")
        lines.append(MID)
        if result.sections:
            for i, section in enumerate(result.sections, start=1):
                page_str = f"p.{section.page}" if section.page is not None else "  --"
                lines.append(f"  {i:>3}. [{page_str:>5}]  {section.title}")
                lines.append(f"               {section.summary}")
                if section.exclusion_command:
                    lines.append(f"               To exclude: {section.exclusion_command}")
        else:
            lines.append("  (no sections detected)")
        lines.append("")

        # Media listing
        lines.append(MID)
        lines.append("  IMAGES & TABLES")
        lines.append(MID)
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

        lines.append(TOP)
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Mono renderer  (new minimalist layout with bold accent colours)
    # ------------------------------------------------------------------

    def _render_mono(self, result: SitemapPreviewResult, style: dict) -> str:
        """Render using the minimalist mono layout.

        Design principles applied here:
        * Thin single-character rules (box-drawing ─) for clean horizontal
          separation.
        * A single accent colour on headings and labels; everything else
          stays at the terminal default.
        * Muted slate for secondary / annotation text.
        * Confidence score rendered as a colour-coded badge.
        * Generous blank lines between logical blocks.
        """
        A = style["accent"]       # violet accent on
        M = style["mute"]         # slate mute on
        R = style["reset"]        # reset colours
        W = style["rule_width"]
        RULE = style["rule_top"] * W

        lines = []

        # ── top panel header ──────────────────────────────────────────
        lines.append(f"{A}{RULE}{R}")
        lines.append(f"  {A}{style['header_label']}{R}")
        lines.append(f"{A}{RULE}{R}")
        lines.append("")

        # ── compact metadata block ────────────────────────────────────
        page_display = str(result.total_page_count) if result.total_page_count is not None else "N/A"
        confidence_badge = self._confidence_badge(result.conversion_confidence, style)

        lines.append(f"  {A}file type{R}          {result.file_type}")
        lines.append(f"  {A}subject{R}            {result.subject}")
        lines.append(f"  {A}pages{R}              {page_display}")
        lines.append(f"  {A}tokens{R}             {result.total_token_count}")
        lines.append(f"  {A}confidence{R}         {confidence_badge}")
        lines.append("")

        # ── table of contents ─────────────────────────────────────────
        lines.append(f"  {A}{style['toc_label']}{R}")
        lines.append(f"  {style['rule_mid'] * (W - 2)}")
        lines.append("")
        if result.sections:
            for i, section in enumerate(result.sections, start=1):
                page_str = f"p.{section.page}" if section.page is not None else "--"
                lines.append(f"  {A}{i:>3}{R}  [{page_str}]  {section.title}")
                lines.append(f"       {M}{section.summary}{R}")
                if section.exclusion_command:
                    lines.append(f"       {M}exclude: {section.exclusion_command}{R}")
                lines.append("")
        else:
            lines.append(f"  {M}(no sections detected){R}")
            lines.append("")

        # ── media listing ─────────────────────────────────────────────
        lines.append(f"  {A}{style['media_label']}{R}")
        lines.append(f"  {style['rule_mid'] * (W - 2)}")
        lines.append("")
        if result.media:
            images = [m for m in result.media if m.type == "image"]
            tables = [m for m in result.media if m.type == "table"]

            if images:
                lines.append(f"  {A}Images ({len(images)}){R}")
                for img in images:
                    page_str = f"p.{img.page}" if img.page is not None else "--"
                    lines.append(f"    [{page_str}]  {img.description}")
                lines.append("")

            if tables:
                lines.append(f"  {A}Tables ({len(tables)}){R}")
                for tbl in tables:
                    page_str = f"p.{tbl.page}" if tbl.page is not None else "--"
                    lines.append(f"    [{page_str}]  {tbl.description}")
                lines.append("")
        else:
            lines.append(f"  {M}(no images or tables detected){R}")
            lines.append("")

        # ── bottom rule ───────────────────────────────────────────────
        lines.append(f"{A}{RULE}{R}")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _confidence_badge(score: int, style: dict) -> str:
        """Return a colour-coded confidence string like ``87%``."""
        if style.get("badge_hi"):
            # Colour badges are available -- pick tier
            if score >= 70:
                colour = style["badge_hi"]
            elif score >= 40:
                colour = style["badge_mid"]
            else:
                colour = style["badge_lo"]
            return f"{colour}{score}%{style['reset']}"
        # Classic / no-colour fallback
        return f"{score}%"
