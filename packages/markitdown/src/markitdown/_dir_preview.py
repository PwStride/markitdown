"""Directory-preview feature.

Scans a directory (non-recursively), identifies every file whose extension
is supported by the sitemap-preview pipeline, runs
``SitemapPreviewConverter.generate()`` on each one, and renders the
aggregated results as a self-contained Markdown document.

Each file gets its own H2 section containing the file type and a
one-sentence subject summary derived from the document content.

Supported extensions are derived from the same set that
``SitemapPreviewConverter`` handles natively, plus the plain-text
catch-all that covers ``.txt``, ``.md``, ``.rst``, ``.json``, ``.xml``.

Pipeline overview::

    _dir_preview.py
        Data models   -- FilePreviewEntry, DirectoryPreviewResult
        Scanner       -- DirectoryPreviewScanner  (reads files)
        Writer        -- DirectoryPreviewWriter   (writes markdown)
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Union, TextIO
from pathlib import Path

from ._stream_info import StreamInfo
from ._sitemap_preview import SitemapPreviewResult
from ._sitemap_preview_converter import SitemapPreviewConverter


# ---------------------------------------------------------------------------
# Recognised extensions (superset of what SitemapPreviewConverter dispatches)
# ---------------------------------------------------------------------------

CONVERTIBLE_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".epub", ".csv", ".html", ".htm", ".ipynb",
    ".ics", ".txt", ".md", ".rst", ".json", ".xml",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FilePreviewEntry:
    """Preview data for a single file inside the directory."""
    filename: str                          # basename only
    file_path: str                         # full path as provided to the scanner
    preview: SitemapPreviewResult          # the per-file sitemap preview
    error: Optional[str] = None            # non-None when preview generation failed


@dataclass
class DirectoryPreviewResult:
    """Aggregated preview for every convertible file in a directory."""
    directory: str                                          # the directory that was scanned
    total_files_found: int                                  # number of convertible files discovered
    entries: List[FilePreviewEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "directory": self.directory,
            "total_files_found": self.total_files_found,
            "entries": [
                {
                    "filename": e.filename,
                    "file_path": e.file_path,
                    "error": e.error,
                    "preview": e.preview.to_dict() if e.preview else None,
                }
                for e in self.entries
            ],
        }


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class DirectoryPreviewScanner:
    """Scans a directory and produces a DirectoryPreviewResult.

    Usage::

        scanner = DirectoryPreviewScanner()
        result  = scanner.scan("/path/to/documents")
    """

    def __init__(self) -> None:
        self._converter = SitemapPreviewConverter()

    def scan(self, directory: str) -> DirectoryPreviewResult:
        """Scan *directory* (non-recursive) and preview every convertible file.

        Files are returned sorted alphabetically by filename.  Files whose
        extension is not in ``CONVERTIBLE_EXTENSIONS`` are silently skipped.
        If preview generation raises an exception for a particular file the
        entry is still included but with a populated ``error`` field and a
        ``None`` preview.

        Args:
            directory: Path to the directory to scan.  Must exist and be a
                directory.

        Returns:
            A ``DirectoryPreviewResult`` instance.

        Raises:
            FileNotFoundError: If *directory* does not exist.
            NotADirectoryError: If *directory* is not a directory.
        """
        directory = str(Path(directory).resolve())

        if not os.path.exists(directory):
            raise FileNotFoundError(f"Directory not found: {directory}")
        if not os.path.isdir(directory):
            raise NotADirectoryError(f"Not a directory: {directory}")

        # Collect convertible files, sorted by name
        candidates: List[str] = sorted(
            name for name in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, name))
            and os.path.splitext(name)[1].lower() in CONVERTIBLE_EXTENSIONS
        )

        entries: List[FilePreviewEntry] = []
        for name in candidates:
            full_path = os.path.join(directory, name)
            ext = os.path.splitext(name)[1].lower()
            stream_info = StreamInfo(
                local_path=full_path,
                extension=ext,
                filename=name,
            )

            try:
                with open(full_path, "rb") as fh:
                    preview = self._converter.generate(fh, stream_info)
                entries.append(FilePreviewEntry(
                    filename=name,
                    file_path=full_path,
                    preview=preview,
                ))
            except Exception as exc:
                entries.append(FilePreviewEntry(
                    filename=name,
                    file_path=full_path,
                    preview=None,
                    error=str(exc),
                ))

        return DirectoryPreviewResult(
            directory=directory,
            total_files_found=len(candidates),
            entries=entries,
        )


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class DirectoryPreviewWriter:
    """Renders and writes a DirectoryPreviewResult as Markdown.

    Usage::

        writer = DirectoryPreviewWriter()

        # Get the markdown string
        md = writer.format(result)

        # Write directly to a file
        writer.write(result, "directory_preview.md")

        # Write to stdout
        writer.write(result)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format(self, result: DirectoryPreviewResult) -> str:
        """Format a DirectoryPreviewResult as a Markdown string."""
        sections: list[str] = []

        # ── document header ───────────────────────────────────────────
        sections.append(self._render_header(result))

        # ── one section per file ──────────────────────────────────────
        for entry in result.entries:
            sections.append(self._render_entry(entry))

        return "\n".join(sections)

    def write(
        self,
        result: DirectoryPreviewResult,
        destination: Union[str, TextIO, None] = None,
    ) -> str:
        """Format and write a DirectoryPreviewResult.

        Args:
            result: The directory preview to write.
            destination:
                - A file path (str) -- writes to that file.
                - A text stream -- writes to the stream.
                - ``None`` -- writes to stdout.

        Returns:
            The formatted Markdown string (same content that was written).
        """
        output = self.format(result)

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
    # Internal renderers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_header(result: DirectoryPreviewResult) -> str:
        """Top-of-document header with directory path and file count."""
        lines = [
            "# Directory Preview",
            "",
            f"**Scanned directory:** `{result.directory}`",
            "",
            f"**Convertible documents found:** {result.total_files_found}",
            "",
            "---",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _render_entry(entry: FilePreviewEntry) -> str:
        """Render a single file's preview as a Markdown sub-section."""
        lines: list[str] = []

        # ── H2: filename ──────────────────────────────────────────────
        lines.append(f"## {entry.filename}")
        lines.append("")

        # ── error fallback ────────────────────────────────────────────
        if entry.preview is None:
            lines.append(f"> **Preview unavailable:** {entry.error or 'unknown error'}")
            lines.append("")
            lines.append("---")
            lines.append("")
            return "\n".join(lines)

        # ── file type + one-sentence subject ─────────────────────────
        p = entry.preview
        lines.append(f"`{p.file_type}` — {p.subject}")
        lines.append("")

        # ── separator ─────────────────────────────────────────────────
        lines.append("---")
        lines.append("")

        return "\n".join(lines)
