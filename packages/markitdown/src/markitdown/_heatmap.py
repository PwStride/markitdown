# SPDX-FileCopyrightText: 2024-present Adam Fourney <adamfo@microsoft.com>
#
# SPDX-License-Identifier: MIT
"""Directory heatmap — visualise file-size distribution as proportional square tiles.

Pipeline
--------
HeatmapScanner  →  HeatmapResult  →  HeatmapWriter  →  terminal output

Usage (Python API)::

    from markitdown import MarkItDown
    md = MarkItDown()
    md.write_heatmap("~/Documents")

Usage (CLI)::

    markitdown --heatmap ~/Documents
    markitdown --heatmap ~/Documents --heatmap-width 120
"""

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, TextIO, Tuple, Union

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

TILE_GAP: int = 2        # spaces between adjacent tiles
MAX_TILE_SIDE: int = 36  # maximum tile width in columns

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

def _rgb_str(r: int, g: int, b: int) -> str:
    """Return a 24-bit ANSI foreground escape sequence."""
    return f"\033[38;2;{r};{g};{b}m"


def _rgb_bg(r: int, g: int, b: int) -> str:
    """Return a 24-bit ANSI background escape sequence."""
    return f"\033[48;2;{r};{g};{b}m"


_RESET = "\033[0m"
_WHITE_FG = "\033[38;2;255;255;255m"
_DARK_FG = "\033[38;2;30;30;30m"

# Heat colour anchors: cool (small) → warm (medium) → hot (large)
_COOL: Tuple[int, int, int] = (30, 144, 255)   # Dodger Blue
_WARM: Tuple[int, int, int] = (255, 140, 0)    # Dark Orange
_HOT: Tuple[int, int, int] = (220, 20, 60)     # Crimson

# Header accent (distinct from all existing palette colours)
_HEADER: Tuple[int, int, int] = (160, 210, 235)  # Pale Steel Blue

# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def _text_fg(r: int, g: int, b: int) -> str:
    """Return a foreground colour that contrasts with the given background.

    Uses the W3C relative luminance formula to decide between white and
    dark text for maximum readability on the heat-coloured background.
    """
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return _WHITE_FG if luminance < 160 else _DARK_FG


def _lerp(a: int, b: int, t: float) -> int:
    """Integer linear interpolation."""
    return int(a + (b - a) * t)


def _heat_color(t: float) -> Tuple[int, int, int]:
    """Map *t* in [0, 1] to an (r, g, b) heat colour.

    t=0.0 → cool blue; t=0.5 → warm orange; t=1.0 → hot crimson.
    The colour space is split at t=0.5.
    """
    if t <= 0.5:
        s = t / 0.5
        return (
            _lerp(_COOL[0], _WARM[0], s),
            _lerp(_COOL[1], _WARM[1], s),
            _lerp(_COOL[2], _WARM[2], s),
        )
    else:
        s = (t - 0.5) / 0.5
        return (
            _lerp(_WARM[0], _HOT[0], s),
            _lerp(_WARM[1], _HOT[1], s),
            _lerp(_WARM[2], _HOT[2], s),
        )


def _size_to_t(size_bytes: int, max_bytes: int) -> float:
    """Map a file size to a [0, 1] heat value using a square-root scale.

    The sqrt scale ensures that colour advances at the same rate as tile
    side length (which is also sqrt-proportional to file size), so the
    two visual cues always agree.
    """
    if max_bytes == 0:
        return 0.0
    return math.sqrt(size_bytes / max_bytes)


def _format_size(n: int) -> str:
    """Format a byte count as a compact human-readable string.

    Examples: ``0 B``, ``512 B``, ``1.5 KB``, ``4.2 MB``, ``1.3 GB``.
    """
    if n < 1_024:
        return f"{n} B"
    elif n < 1_024 ** 2:
        kb = n / 1_024
        return f"{kb:.1f} KB" if kb < 100 else f"{int(kb)} KB"
    elif n < 1_024 ** 3:
        mb = n / (1_024 ** 2)
        return f"{mb:.1f} MB" if mb < 100 else f"{int(mb)} MB"
    else:
        gb = n / (1_024 ** 3)
        return f"{gb:.1f} GB"


def _compute_tile_sides(
    sizes: List[int],
    min_sides: List[int],
    terminal_width: int = 80,
) -> List[int]:
    """Compute tile side lengths (columns) for a list of file sizes.

    Each side is proportional to ``sqrt(size)`` so that tile *area* is
    proportional to file size.  The largest tile is scaled to at most
    half the terminal width, capped by ``MAX_TILE_SIDE``.  Each tile is
    then clamped to the per-entry *min_sides* value so that the full
    filename and size label always fit without truncation.  Even values
    are incremented by one so that there is always an exact centre row.
    """
    if not sizes:
        return []

    max_size = max(sizes)
    if max_size == 0:
        return [m if m % 2 != 0 else m + 1 for m in min_sides]

    raw = [math.sqrt(s) for s in sizes]
    max_raw = max(raw)
    target_max = min(MAX_TILE_SIDE, terminal_width // 2)
    scale = target_max / max_raw

    sides: List[int] = []
    for i, r in enumerate(raw):
        side = int(r * scale)
        side = max(side, min_sides[i])
        if side % 2 == 0:
            side += 1
        sides.append(side)

    return sides


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class HeatmapEntry:
    """Metadata for one file tile in the heatmap."""

    filename: str                       # basename, e.g. ``"report.pdf"``
    file_path: str                      # absolute path
    size_bytes: int                     # raw byte count
    size_label: str                     # human-readable, e.g. ``"1.2 MB"``
    tile_side: int                      # character width of the square tile
    heat_rgb: Tuple[int, int, int]      # ``(r, g, b)`` derived from relative size


@dataclass
class HeatmapResult:
    """Aggregated heatmap data for a directory scan."""

    directory: str                          # resolved absolute path
    total_files: int                        # count of files found
    total_bytes: int                        # sum of all file sizes in bytes
    total_label: str                        # human-readable total
    entries: List[HeatmapEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return {
            "directory": self.directory,
            "total_files": self.total_files,
            "total_bytes": self.total_bytes,
            "total_label": self.total_label,
            "entries": [
                {
                    "filename": e.filename,
                    "file_path": e.file_path,
                    "size_bytes": e.size_bytes,
                    "size_label": e.size_label,
                    "tile_side": e.tile_side,
                    "heat_rgb": list(e.heat_rgb),
                }
                for e in self.entries
            ],
        }


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class HeatmapScanner:
    """Scans a directory and produces a :class:`HeatmapResult`.

    Only ``os.stat()`` is used — no file content is read or converted.
    All files are included regardless of extension because the heatmap
    represents physical disk volume, not just convertible document types.
    The scan is non-recursive: only files directly inside *directory* are
    included.

    Usage::

        scanner = HeatmapScanner()
        result = scanner.scan("/path/to/documents")
        result = scanner.scan("/path/to/documents", terminal_width=120)
    """

    def scan(
        self,
        directory: str,
        *,
        terminal_width: int = 80,
    ) -> HeatmapResult:
        """Scan *directory* and return a :class:`HeatmapResult`.

        Args:
            directory: Path to the directory to scan.
            terminal_width: Target character width used to scale tile sizes.

        Returns:
            A populated :class:`HeatmapResult`.

        Raises:
            FileNotFoundError: If *directory* does not exist.
            NotADirectoryError: If *directory* is not a directory.
        """
        directory = str(Path(directory).expanduser().resolve())

        if not os.path.exists(directory):
            raise FileNotFoundError(f"Directory not found: {directory}")
        if not os.path.isdir(directory):
            raise NotADirectoryError(f"Not a directory: {directory}")

        names: List[str] = sorted(
            name
            for name in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, name))
        )

        raw_entries: List[Tuple[str, int]] = []
        for name in names:
            full_path = os.path.join(directory, name)
            try:
                size = os.path.getsize(full_path)
            except OSError:
                size = 0
            raw_entries.append((name, size))

        total_bytes = sum(s for _, s in raw_entries)
        max_bytes = max((s for _, s in raw_entries), default=0)

        sizes = [s for _, s in raw_entries]

        # Each tile must be wide enough to display the full filename and size
        # label without truncation.  inner_w = tile_side - 2 (borders), so
        # tile_side >= max(len(name), len(size_label)) + 2.
        min_sides: List[int] = []
        for name, size_bytes in raw_entries:
            size_label = _format_size(size_bytes)
            needed = max(len(name), len(size_label)) + 2  # +2 for │ borders
            min_sides.append(needed)

        tile_sides = _compute_tile_sides(sizes, min_sides, terminal_width)

        entries: List[HeatmapEntry] = []
        for i, (name, size_bytes) in enumerate(raw_entries):
            t = _size_to_t(size_bytes, max_bytes)
            entries.append(
                HeatmapEntry(
                    filename=name,
                    file_path=os.path.join(directory, name),
                    size_bytes=size_bytes,
                    size_label=_format_size(size_bytes),
                    tile_side=tile_sides[i],
                    heat_rgb=_heat_color(t),
                )
            )

        return HeatmapResult(
            directory=directory,
            total_files=len(entries),
            total_bytes=total_bytes,
            total_label=_format_size(total_bytes),
            entries=entries,
        )


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

class HeatmapWriter:
    """Renders a :class:`HeatmapResult` as a terminal heatmap diagram.

    Each file is drawn as a square tile whose side length (in columns) is
    proportional to ``sqrt(file_size)``, so tile *area* is proportional to
    file size.  Tiles are coloured on a cool-blue → orange → crimson heat
    scale.  Multiple tiles are packed into rows that fit within the target
    terminal width.

    Usage::

        writer = HeatmapWriter()
        text = writer.format(result)
        writer.write(result)                   # stdout
        writer.write(result, "heatmap.txt")    # file
    """

    DEFAULT_TERMINAL_WIDTH: int = 80

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format(
        self,
        result: HeatmapResult,
        *,
        terminal_width: int = DEFAULT_TERMINAL_WIDTH,
    ) -> str:
        """Format a :class:`HeatmapResult` as a terminal-ready string.

        Args:
            result: The heatmap result to render.
            terminal_width: Target output width in columns.

        Returns:
            A multi-line string ready to print to a terminal.
        """
        lines: List[str] = []

        lines.append(self._render_header(result, terminal_width))
        lines.append("")

        if not result.entries:
            pad = " " * ((terminal_width - 30) // 2)
            lines.append(f"{pad}(no files found in directory)")
        else:
            rows = self._pack_into_rows(result.entries, terminal_width)
            for row_tiles in rows:
                lines.extend(self._render_tile_row(row_tiles))
                lines.append("")

        return "\n".join(lines)

    def write(
        self,
        result: HeatmapResult,
        destination: Union[str, TextIO, None] = None,
        *,
        terminal_width: int = DEFAULT_TERMINAL_WIDTH,
    ) -> str:
        """Format and write a :class:`HeatmapResult`.

        Args:
            result: The heatmap result to render.
            destination:
                - ``None`` — write to stdout.
                - A file path (str) — write to that file.
                - A writable file-like object — write to it.
            terminal_width: Target output width in columns.

        Returns:
            The rendered string.

        Raises:
            TypeError: If *destination* is not a recognised type.
        """
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

    # ------------------------------------------------------------------
    # Header and legend
    # ------------------------------------------------------------------

    def _render_header(self, result: HeatmapResult, width: int) -> str:
        """Render the double-box banner at the top of the heatmap."""
        inner = width - 2
        accent = _rgb_str(*_HEADER)
        rst = _RESET

        dir_line = f"DIRECTORY HEATMAP  \u00b7  {result.directory}"
        stat_line = f"{result.total_files} file{'s' if result.total_files != 1 else ''}  \u00b7  {result.total_label} total"

        # Truncate directory path if it overflows the inner width
        max_dir_len = inner - 20  # leave room for "DIRECTORY HEATMAP  ·  "
        if len(result.directory) > max_dir_len:
            truncated = "\u2026" + result.directory[-(max_dir_len - 1):]
            dir_line = f"DIRECTORY HEATMAP  \u00b7  {truncated}"

        top    = f"{accent}\u2554{'=' * inner}\u2557{rst}"
        mid1   = f"{accent}\u2551{rst}{dir_line.center(inner)}{accent}\u2551{rst}"
        mid2   = f"{accent}\u2551{rst}{stat_line.center(inner)}{accent}\u2551{rst}"
        bottom = f"{accent}\u255a{'=' * inner}\u255d{rst}"

        return "\n".join([top, mid1, mid2, bottom])

    # ------------------------------------------------------------------
    # Row packing
    # ------------------------------------------------------------------

    def _pack_into_rows(
        self,
        entries: List[HeatmapEntry],
        terminal_width: int,
    ) -> List[List[HeatmapEntry]]:
        """Group entries into rows that fit within *terminal_width* columns."""
        rows: List[List[HeatmapEntry]] = []
        current_row: List[HeatmapEntry] = []
        current_width = 0

        for entry in entries:
            needed = entry.tile_side + (TILE_GAP if current_row else 0)
            if current_row and current_width + needed > terminal_width:
                rows.append(current_row)
                current_row = [entry]
                current_width = entry.tile_side
            else:
                current_row.append(entry)
                current_width += needed

        if current_row:
            rows.append(current_row)

        return rows

    # ------------------------------------------------------------------
    # Tile rendering
    # ------------------------------------------------------------------

    def _render_tile_row(self, tiles: List[HeatmapEntry]) -> List[str]:
        """Render one horizontal band of tiles, returning a list of output lines.

        All tiles in the row are padded vertically to the height of the
        tallest tile so they bottom-align cleanly.
        """
        if not tiles:
            return []

        max_height = max(max(3, t.tile_side // 2) for t in tiles)

        columns: List[List[str]] = [
            self._build_tile_lines(tile, max_height) for tile in tiles
        ]

        gap = " " * TILE_GAP
        output_lines: List[str] = []
        for row_idx in range(max_height):
            parts: List[str] = []
            for col_idx, col_lines in enumerate(columns):
                if col_idx > 0:
                    parts.append(gap)
                parts.append(col_lines[row_idx])
            output_lines.append("".join(parts))

        return output_lines

    def _build_tile_lines(
        self,
        entry: HeatmapEntry,
        total_rows: int,
    ) -> List[str]:
        """Return *total_rows* strings, each exactly ``entry.tile_side`` visible columns wide.

        Every interior row is filled with the heat background colour so
        that the tile reads as a solid coloured block.  The filename and
        size label are rendered in a contrasting foreground (white on dark
        backgrounds, dark on light backgrounds).

        Structure::

            ┌────────────────┐   ← border in heat foreground colour
            │████████████████│   ← filled padding
            │██ filename ████│   ← filled, contrasting text
            │████ 42 KB █████│   ← filled, contrasting text
            │████████████████│   ← filled padding
            └────────────────┘   ← border in heat foreground colour
        """
        W = entry.tile_side
        H = total_rows
        R, G, B = entry.heat_rgb
        heat = _rgb_str(R, G, B)
        bg = _rgb_bg(R, G, B)
        fg = _text_fg(R, G, B)
        rst = _RESET

        inner_w = W - 2  # visible columns inside the │ borders

        # Tile width is guaranteed by the scanner to fit the full filename
        # and size label — no truncation needed.
        name = entry.filename
        size = entry.size_label

        top_border  = f"{heat}\u250c{'\u2500' * inner_w}\u2510{rst}"
        bot_border  = f"{heat}\u2514{'\u2500' * inner_w}\u2518{rst}"
        blank_line  = f"{heat}\u2502{bg}{' ' * inner_w}{rst}{heat}\u2502{rst}"
        name_line   = f"{heat}\u2502{bg}{fg}{name.center(inner_w)}{rst}{heat}\u2502{rst}"
        size_line   = f"{heat}\u2502{bg}{fg}{size.center(inner_w)}{rst}{heat}\u2502{rst}"

        # Distribute blank padding above and below the content (name + size)
        content_rows = H - 2          # rows between top and bottom borders
        content_height = 2            # name row + size row
        padding_total = max(0, content_rows - content_height)
        pad_top = padding_total // 2
        pad_bot = padding_total - pad_top

        lines: List[str] = [top_border]
        lines.extend([blank_line] * pad_top)
        lines.append(name_line)
        lines.append(size_line)
        lines.extend([blank_line] * pad_bot)
        lines.append(bot_border)

        return lines
