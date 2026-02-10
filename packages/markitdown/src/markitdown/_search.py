"""Full-text search across a directory of convertible documents.

Converts each supported file to Markdown, then searches the resulting text
for one or more query terms.  Results are aggregated per file and rendered
as a compact table.

Usage
-----
CLI::

    markitdown --search ~/Documents "API" "error"
    markitdown --search ~/Documents "TODO" -o results.md

Python API::

    from markitdown import MarkItDown

    md = MarkItDown()
    md.write_search("~/Documents", ["API", "error"])           # prints to stdout
    md.write_search("~/Documents", ["TODO"], "results.md")     # writes to file

    # Or get the raw result object for programmatic access:
    result = md.generate_search("~/Documents", ["API", "error"])
    for entry in result.entries:
        print(entry["filename"], entry["matches"])

Example
-------
Given a directory ``~/docs`` containing three files:

* ``readme.md``  — contains "API" 5 times and "error" 2 times
* ``notes.txt``  — contains "API" 1 time
* ``report.pdf`` — contains neither term

Running::

    markitdown --search ~/docs "API" "error"

Produces output::

    # Search Results

    **Directory:** `/home/user/docs`

    **Queries:** "API", "error"

    **Files scanned:** 3  **Files with matches:** 2

    | Query      | Occurrences | Path            | File       |
    |------------|-------------|-----------------|------------|
    | API, error | 5, 2        | /home/user/docs | readme.md  |
    | API        | 1           | /home/user/docs | notes.txt  |

Table columns
-------------
``Query``
    The search term(s) that matched.  Multiple terms are comma-separated.
``Occurrences``
    How many times each corresponding term appears (case-insensitive by default).
``Path``
    The directory containing the file.
``File``
    The file's base name.

Multiple query terms that match the same file are condensed into a single
row.  The order of queries and occurrences is preserved so the counts
align with their respective terms.

Pipeline overview::

    _search.py
        SearchResult      -- data container for search results
        DocumentSearcher  -- scans directory and counts query hits
        SearchResultWriter -- formats results as Markdown table
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union, TextIO

from ._dir_preview import CONVERTIBLE_EXTENSIONS


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """Container for search results across a directory.

    Attributes:
        directory: The scanned directory path.
        queries: The search terms used.
        total_files_scanned: Number of convertible files found.
        entries: List of file results, each a dict with keys:
            - filename: str (basename)
            - file_path: str (full path)
            - matches: List[tuple[str, int]] — (query, count) pairs
            - error: Optional[str] — set when conversion failed
    """
    directory: str
    queries: List[str]
    total_files_scanned: int
    entries: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "directory": self.directory,
            "queries": self.queries,
            "total_files_scanned": self.total_files_scanned,
            "entries": self.entries,
        }


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class DocumentSearcher:
    """Scan a directory and search converted documents for query terms.

    Args:
        markitdown: A MarkItDown instance used for file conversion.
        case_sensitive: If True, queries are matched case-sensitively.
            Defaults to False (case-insensitive).

    Usage::

        from markitdown import MarkItDown

        md = MarkItDown()
        searcher = DocumentSearcher(md)
        result = searcher.search("/path/to/docs", ["hello", "world"])

        # Case-sensitive search:
        searcher = DocumentSearcher(md, case_sensitive=True)
        result = searcher.search("/path/to/docs", ["Hello"])
    """

    def __init__(self, markitdown, *, case_sensitive: bool = False) -> None:
        self._md = markitdown
        self._case_sensitive = case_sensitive

    def search(self, directory: str, queries: List[str]) -> SearchResult:
        """Search *directory* for all *queries*.

        Only files whose extension is in ``CONVERTIBLE_EXTENSIONS`` are
        processed.  Files that fail conversion are included with an
        ``error`` field.  Files with zero hits are omitted.

        Args:
            directory: Path to scan (non-recursive).
            queries: One or more search terms.

        Returns:
            A ``SearchResult`` instance.

        Raises:
            FileNotFoundError: If *directory* does not exist.
            NotADirectoryError: If *directory* is not a directory.
        """
        directory = str(Path(directory).resolve())

        if not os.path.exists(directory):
            raise FileNotFoundError(f"Directory not found: {directory}")
        if not os.path.isdir(directory):
            raise NotADirectoryError(f"Not a directory: {directory}")

        queries = [q.strip() for q in queries if q.strip()]

        candidates: List[str] = sorted(
            name for name in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, name))
            and os.path.splitext(name)[1].lower() in CONVERTIBLE_EXTENSIONS
        )

        entries: List[Dict] = []
        for name in candidates:
            full_path = os.path.join(directory, name)
            entry = self._process_file(full_path, name, queries)
            if entry is not None:
                entries.append(entry)

        return SearchResult(
            directory=directory,
            queries=queries,
            total_files_scanned=len(candidates),
            entries=entries,
        )

    def _process_file(
        self, full_path: str, name: str, queries: List[str]
    ) -> Optional[Dict]:
        """Convert file and count query hits. Returns None if no matches."""
        try:
            result = self._md.convert(full_path)
            text = result.markdown or ""
        except Exception as exc:
            return {
                "filename": name,
                "file_path": full_path,
                "matches": [],
                "error": str(exc),
            }

        matches = self._count_queries(text, queries)
        if not matches:
            return None

        return {
            "filename": name,
            "file_path": full_path,
            "matches": matches,
            "error": None,
        }

    def _count_queries(self, text: str, queries: List[str]) -> List[tuple]:
        """Return (query, count) tuples for queries with at least one hit."""
        flags = 0 if self._case_sensitive else re.IGNORECASE
        hits: List[tuple] = []
        for q in queries:
            count = len(re.findall(re.escape(q), text, flags=flags))
            if count > 0:
                hits.append((q, count))
        return hits


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class SearchResultWriter:
    """Render a SearchResult as a Markdown table.

    Usage::

        writer = SearchResultWriter()
        text = writer.format(result)      # get as string
        writer.write(result)              # print to stdout
        writer.write(result, "out.md")    # write to file
    """

    def format(self, result: SearchResult) -> str:
        """Return a Markdown string containing the search-results table."""
        lines: List[str] = []
        lines.append(self._render_header(result))

        if not result.entries:
            lines.append("*No matches found.*")
            lines.append("")
            return "\n".join(lines)

        lines.append(self._render_table(result.entries))
        return "\n".join(lines)

    def write(
        self,
        result: SearchResult,
        destination: Union[str, TextIO, None] = None,
    ) -> str:
        """Format and write a SearchResult.

        Args:
            result: The search result to render.
            destination:
                - A file path (str) -- writes to that file.
                - A text stream -- writes to the stream.
                - ``None`` -- writes to stdout.

        Returns:
            The formatted string (same content that was written).
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

    @staticmethod
    def _render_header(result: SearchResult) -> str:
        quoted = ", ".join(f'"{q}"' for q in result.queries)
        lines = [
            "# Search Results",
            "",
            f"**Directory:** `{result.directory}`",
            "",
            f"**Queries:** {quoted}",
            "",
            f"**Files scanned:** {result.total_files_scanned}  "
            f"**Files with matches:** {len(result.entries)}",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _render_table(entries: List[Dict]) -> str:
        """Build a Markdown table from the result entries."""
        col_query = "Query"
        col_occ = "Occurrences"
        col_path = "Path"
        col_file = "File"

        rows: List[Dict[str, str]] = []
        for entry in entries:
            if entry.get("error"):
                rows.append({
                    col_query: "*(conversion error)*",
                    col_occ: "-",
                    col_path: os.path.dirname(entry["file_path"]),
                    col_file: entry["filename"],
                })
            else:
                query_cell = ", ".join(m[0] for m in entry["matches"])
                occ_cell = ", ".join(str(m[1]) for m in entry["matches"])
                rows.append({
                    col_query: query_cell,
                    col_occ: occ_cell,
                    col_path: os.path.dirname(entry["file_path"]),
                    col_file: entry["filename"],
                })

        cols = [col_query, col_occ, col_path, col_file]
        widths = {c: len(c) for c in cols}
        for row in rows:
            for c in cols:
                widths[c] = max(widths[c], len(row[c]))

        def _row_str(cells: Dict[str, str]) -> str:
            parts = [cells[c].ljust(widths[c]) for c in cols]
            return "| " + " | ".join(parts) + " |"

        def _sep_str() -> str:
            parts = ["-" * widths[c] for c in cols]
            return "| " + " | ".join(parts) + " |"

        header_cells = {c: c for c in cols}
        lines = [
            _row_str(header_cells),
            _sep_str(),
        ]
        for row in rows:
            lines.append(_row_str(row))

        lines.append("")
        return "\n".join(lines)
