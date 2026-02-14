"""Directory overview — consolidated view of summaries, tree maps, keywords, and volume tiles.

Combines the tree map, directory preview, keyword index, and heatmap
features into a single document for every file in a directory.

CLI::

    markitdown --overview ~/Documents
    markitdown --overview ~/Documents -o overview.txt
    markitdown --overview ~/Documents --overview-width 80
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, TextIO, Union

from ._dir_preview import (
    DirectoryPreviewResult,
    DirectoryPreviewScanner,
)
from ._docx_tree_mapper import DocumentMap
from ._docx_tree_mapper_converter import DocxTreeMapConverter
from ._heatmap import HeatmapResult, HeatmapScanner, HeatmapWriter
from ._index import IndexResult, DirectoryIndexBuilder, IndexWriter
from ._mono_format import COBALT, TEAL, CORAL, ASH, RESET


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class OverviewFileEntry:
    """Per-file subject summary and document map."""

    filename: str
    file_path: str
    subject: Optional[str] = None
    file_type: Optional[str] = None
    doc_map: Optional[DocumentMap] = None
    error: Optional[str] = None


@dataclass
class OverviewResult:
    """Aggregated overview for a directory."""

    directory: str
    total_files: int
    file_entries: List[OverviewFileEntry] = field(default_factory=list)
    dir_preview: Optional[DirectoryPreviewResult] = None
    index: Optional[IndexResult] = None
    heatmap: Optional[HeatmapResult] = None


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class OverviewScanner:
    """Orchestrates the four feature scanners and assembles an OverviewResult."""

    def __init__(self, markitdown_instance: Any) -> None:
        self._md = markitdown_instance

    def scan(
        self,
        directory: str,
        *,
        terminal_width: int = 80,
    ) -> OverviewResult:
        """Scan *directory* and produce a combined overview."""
        directory = str(Path(directory).expanduser().resolve())

        if not os.path.exists(directory):
            raise FileNotFoundError(f"Directory not found: {directory}")
        if not os.path.isdir(directory):
            raise NotADirectoryError(f"Not a directory: {directory}")

        # 1. Directory preview (one-sentence summaries)
        dir_scanner = DirectoryPreviewScanner()
        dir_preview = dir_scanner.scan(directory)

        # 2. Document maps (tree structure per file)
        map_converter = DocxTreeMapConverter(self._md)
        file_entries: List[OverviewFileEntry] = []

        for entry in dir_preview.entries:
            subject = None
            file_type = None
            if entry.preview is not None:
                subject = entry.preview.subject
                file_type = entry.preview.file_type

            doc_map = None
            error = entry.error
            try:
                doc_map = map_converter.generate(entry.file_path)
            except Exception as exc:
                if error is None:
                    error = str(exc)

            file_entries.append(
                OverviewFileEntry(
                    filename=entry.filename,
                    file_path=entry.file_path,
                    subject=subject,
                    file_type=file_type,
                    doc_map=doc_map,
                    error=error,
                )
            )

        # 3. Keyword index
        index_builder = DirectoryIndexBuilder(self._md)
        index = index_builder.build(directory)

        # 4. Heatmap
        heatmap_scanner = HeatmapScanner()
        heatmap = heatmap_scanner.scan(directory, terminal_width=terminal_width)

        return OverviewResult(
            directory=directory,
            total_files=dir_preview.total_files_found,
            file_entries=file_entries,
            dir_preview=dir_preview,
            index=index,
            heatmap=heatmap,
        )


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class OverviewWriter:
    """Renders an OverviewResult as a consolidated text document."""

    DEFAULT_TERMINAL_WIDTH: int = 80

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format(
        self,
        result: OverviewResult,
        *,
        terminal_width: int = DEFAULT_TERMINAL_WIDTH,
    ) -> str:
        """Format an OverviewResult as a single text document."""
        _RULE = "\u2500" * 64
        _THIN = "\u2500" * 40

        parts: List[str] = []

        # ── Master header ─────────────────────────────────────────────
        parts.append(f"{COBALT}{_RULE}{RESET}")
        parts.append(f"  {COBALT}DIRECTORY OVERVIEW{RESET}")
        parts.append(f"{COBALT}{_RULE}{RESET}")
        parts.append("")
        parts.append(f"  {ASH}Directory{RESET}   {result.directory}")
        parts.append(f"  {ASH}Files{RESET}       {result.total_files}")
        parts.append("")

        # ── Section 1: Volume Heatmap ─────────────────────────────────
        parts.append(f"{TEAL}{_RULE}{RESET}")
        parts.append(f"  {TEAL}VOLUME HEATMAP{RESET}")
        parts.append(f"  {TEAL}{_THIN}{RESET}")
        parts.append("")

        if result.heatmap and result.heatmap.entries:
            heatmap_writer = HeatmapWriter()
            effective_width = max(40, terminal_width - 2)
            heatmap_text = heatmap_writer.format(
                result.heatmap, terminal_width=effective_width
            )
            for line in heatmap_text.splitlines():
                parts.append(f"  {line}")
            parts.append("")
        else:
            parts.append(f"  {ASH}(no files found for heatmap){RESET}")
            parts.append("")

        # ── Section 2: Tree Maps ──────────────────────────────────────
        parts.append(f"{TEAL}{_RULE}{RESET}")
        parts.append(f"  {TEAL}TREE MAPS{RESET}")
        parts.append(f"  {TEAL}{_THIN}{RESET}")
        parts.append("")

        has_any_map = False

        for entry in result.file_entries:
            if entry.doc_map is None:
                continue
            has_any_map = True
            parts.append(f"  {CORAL}{entry.filename}{RESET}")
            self._render_tree_nodes(
                entry.doc_map.root.children, parts, prefix="  "
            )
            parts.append("")

        if not has_any_map:
            parts.append(f"  {ASH}(no document maps generated){RESET}")
            parts.append("")

        # ── Section 3: Document Summaries ─────────────────────────────
        parts.append(f"{TEAL}{_RULE}{RESET}")
        parts.append(f"  {TEAL}DOCUMENT SUMMARIES{RESET}")
        parts.append(f"  {TEAL}{_THIN}{RESET}")
        parts.append("")

        if not result.file_entries:
            parts.append(f"  {ASH}(no convertible files found){RESET}")
            parts.append("")
        else:
            for entry in result.file_entries:
                type_label = f" {ASH}{entry.file_type}{RESET}" if entry.file_type else ""
                parts.append(f"  {CORAL}{entry.filename}{RESET}{type_label}")
                if entry.subject:
                    parts.append(f"    {entry.subject}")
                elif entry.error:
                    parts.append(f"    {ASH}(preview unavailable: {entry.error}){RESET}")
                parts.append("")

        # ── Section 4: Keyword Index ──────────────────────────────────
        parts.append(f"{TEAL}{_RULE}{RESET}")
        parts.append(f"  {TEAL}KEYWORD INDEX{RESET}")
        parts.append(f"  {TEAL}{_THIN}{RESET}")
        parts.append("")

        if result.index and result.index.total_keywords > 0:
            index_writer = IndexWriter()
            index_text = index_writer.format(result.index, fmt="text")
            for line in index_text.splitlines():
                parts.append(f"  {line}")
            parts.append("")
        else:
            parts.append(f"  {ASH}(no keywords extracted){RESET}")
            parts.append("")

        # ── Footer ────────────────────────────────────────────────────
        parts.append(f"{COBALT}{_RULE}{RESET}")

        return "\n".join(parts)

    def _render_tree_nodes(
        self,
        children: list,
        parts: List[str],
        prefix: str,
    ) -> None:
        """Render nested tree-node summaries using box-drawing connectors."""
        TEE = "\u251c\u2500\u2500"   # ├──
        ELL = "\u2514\u2500\u2500"   # └──
        BAR = "\u2502"               # │

        for i, child in enumerate(children):
            is_last = i == len(children) - 1
            connector = ELL if is_last else TEE
            parts.append(f"{prefix}{TEAL}{connector}{RESET} {child.title}")
            cont = "    " if is_last else f"{BAR}   "
            parts.append(f"{prefix}{cont} {ASH}{child.summary}{RESET}")
            if child.children:
                child_prefix = prefix + ("    " if is_last else f"{BAR}   ")
                self._render_tree_nodes(child.children, parts, child_prefix)

    def write(
        self,
        result: OverviewResult,
        destination: Union[str, TextIO, None] = None,
        *,
        terminal_width: int = DEFAULT_TERMINAL_WIDTH,
    ) -> str:
        """Write an OverviewResult to a file, stream, or stdout."""
        output = self.format(result, terminal_width=terminal_width)

        if destination is None:
            print(output)
        elif isinstance(destination, str):
            with open(destination, "w", encoding="utf-8") as fh:
                fh.write(output)
        elif hasattr(destination, "write") and callable(destination.write):
            destination.write(output)
        else:
            raise TypeError(
                f"destination must be a file path, file-like object, or None; "
                f"got {type(destination)!r}"
            )
        return output
