"""Keyword index feature.

Scans a directory (non-recursively), converts each supported file to Markdown
via the standard MarkItDown pipeline, extracts keywords using a three-tier
heuristic, and renders an alphabetical keyword index as a Markdown document.

Keyword extraction tiers (in priority order):

1. **Heading words** — every significant word found in ATX headings (# ... ######).
   These are the highest-signal terms because the document author explicitly
   chose them.  The heading text itself is used as the keyword context.

2. **Proper nouns** — capitalised words that do not appear at sentence-start
   positions, and ALL-CAPS acronyms (3–8 characters).  Context is derived
   from the nearest preceding heading.

3. **High-frequency body words** — words that appear at least three times in
   the body text after stop-word filtering.  Used to capture domain-specific
   vocabulary that does not happen to be capitalised or in headings.

Pipeline overview::

    _index.py
        IndexFileRef        -- single file reference under a keyword
        IndexEntry          -- one keyword + all files where it appears
        IndexResult         -- full index for a directory
        DirectoryIndexBuilder -- scans directory, builds IndexResult
        IndexWriter         -- renders IndexResult as Markdown or JSON

Usage::

    CLI::

        markitdown --index ~/Documents
        markitdown --index ~/Documents -o index.md
        markitdown --index ~/Documents --index-format json -o index.json

    Python API::

        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.generate_index("~/Documents")
        md.write_index("~/Documents")
        md.write_index("~/Documents", "index.md")
        md.write_index("~/Documents", "index.json", fmt="json")
"""

import json
import os
import re
import string
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TextIO, Tuple, Union

from ._dir_preview import CONVERTIBLE_EXTENSIONS
from ._mono_format import COBALT, TEAL, CORAL, GOLD, ASH, RESET


# ---------------------------------------------------------------------------
# Stop-word list (~150 common English words plus markdown / document noise)
# ---------------------------------------------------------------------------

_STOP_WORDS: frozenset = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "also", "am",
    "an", "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "could", "did",
    "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "get", "got", "had", "has", "have", "having", "he", "her",
    "here", "hers", "herself", "him", "himself", "his", "how", "i", "if",
    "in", "into", "is", "it", "its", "itself", "just", "let", "like", "make",
    "may", "me", "more", "most", "my", "myself", "new", "no", "nor", "not",
    "now", "of", "off", "on", "once", "only", "or", "other", "our", "ours",
    "out", "over", "own", "s", "same", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "theirs", "them", "themselves", "then",
    "there", "these", "they", "this", "those", "through", "to", "too", "under",
    "until", "up", "us", "use", "used", "using", "very", "was", "we", "were",
    "what", "when", "where", "which", "while", "who", "whom", "why", "will",
    "with", "would", "you", "your", "yours", "yourself",
    # Common markdown / document noise
    "see", "note", "example", "page", "chapter", "section", "table",
    "figure", "list", "item", "type", "name", "value", "data", "file",
    "text", "line", "number", "time", "date", "code", "true", "false",
    "null", "none", "yes",
})

# Minimum character length for any keyword
_MIN_KEYWORD_LEN = 4

# Minimum body frequency for Tier-3 promotion
_MIN_BODY_FREQ = 3

# Maximum distinct keywords to extract per file (caps memory growth on large docs)
_MAX_KEYWORDS_PER_FILE = 150

# Match word tokens: letter-start, then letters/digits/hyphens, length >= 3
_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9\-]{2,}\b")

# ATX heading line
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)

# Sentence-start detection: capital letter immediately after start-of-string
# or after sentence-ending punctuation + whitespace
_SENTENCE_START_RE = re.compile(r"(?:(?:^)|(?:[.!?]\s+))([A-Z][a-z]+)")

# Inline markdown to strip before tokenising
_INLINE_MARKUP_RE = re.compile(r"[*_`\[\]()]")
_URL_RE = re.compile(r"https?://\S+")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class IndexFileRef:
    """A single file reference under a keyword entry."""
    filename: str         # basename of the file
    file_path: str        # absolute path to the file
    context: Optional[str] = None  # nearest heading above where keyword appears


@dataclass
class IndexEntry:
    """One keyword and all the files in which it appears."""
    keyword: str           # lowercase canonical form
    display_keyword: str   # original casing for display
    refs: List[IndexFileRef] = field(default_factory=list)

    def add_ref(
        self,
        filename: str,
        file_path: str,
        context: Optional[str] = None,
    ) -> None:
        """Add a file reference, deduplicating by file_path."""
        for existing in self.refs:
            if existing.file_path == file_path:
                if context and not existing.context:
                    existing.context = context
                return
        self.refs.append(IndexFileRef(filename=filename, file_path=file_path, context=context))

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "display_keyword": self.display_keyword,
            "refs": [
                {
                    "filename": r.filename,
                    "file_path": r.file_path,
                    "context": r.context,
                }
                for r in self.refs
            ],
        }


@dataclass
class IndexResult:
    """Aggregated keyword index for a directory of documents."""
    directory: str
    total_files_scanned: int
    total_files_indexed: int    # files that yielded at least one keyword
    total_keywords: int         # distinct keywords across all files
    entries: Dict[str, IndexEntry] = field(default_factory=dict)
    errors: List[Tuple[str, str]] = field(default_factory=list)  # (filename, error_msg)

    def sorted_entries(self) -> List[IndexEntry]:
        """Return all IndexEntry objects sorted case-insensitively by keyword."""
        return sorted(self.entries.values(), key=lambda e: e.keyword.lower())

    def entries_for_letter(self, letter: str) -> List[IndexEntry]:
        """Return entries whose display_keyword starts with letter (case-insensitive)."""
        letter = letter.upper()
        return [
            e for e in self.sorted_entries()
            if e.display_keyword and e.display_keyword[0].upper() == letter
        ]

    def entries_for_non_alpha(self) -> List[IndexEntry]:
        """Return entries that start with a digit or symbol (the '#' bucket)."""
        return [
            e for e in self.sorted_entries()
            if e.display_keyword and not e.display_keyword[0].isalpha()
        ]

    def to_dict(self) -> dict:
        return {
            "directory": self.directory,
            "total_files_scanned": self.total_files_scanned,
            "total_files_indexed": self.total_files_indexed,
            "total_keywords": self.total_keywords,
            "errors": [{"filename": f, "error": e} for f, e in self.errors],
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Scanner / builder
# ---------------------------------------------------------------------------


class DirectoryIndexBuilder:
    """Scan a directory, convert files to Markdown, extract keywords,
    and assemble an IndexResult.

    Usage::

        from markitdown import MarkItDown
        from markitdown._index import DirectoryIndexBuilder

        md = MarkItDown()
        builder = DirectoryIndexBuilder(md)
        result = builder.build("/path/to/documents")
    """

    def __init__(self, markitdown_instance: Any) -> None:
        self._md = markitdown_instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, directory: str) -> IndexResult:
        """Scan *directory* (non-recursive) and build a keyword index.

        Only files whose extension is in ``CONVERTIBLE_EXTENSIONS`` are
        processed.  Files that fail conversion are tracked in
        ``IndexResult.errors`` and do not abort the scan.

        Args:
            directory: Path to the directory to index.

        Returns:
            An ``IndexResult`` instance.

        Raises:
            FileNotFoundError: If *directory* does not exist.
            NotADirectoryError: If *directory* is not a directory.
        """
        directory = str(Path(directory).resolve())

        if not os.path.exists(directory):
            raise FileNotFoundError(f"Directory not found: {directory}")
        if not os.path.isdir(directory):
            raise NotADirectoryError(f"Not a directory: {directory}")

        candidates: List[str] = sorted(
            name for name in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, name))
            and os.path.splitext(name)[1].lower() in CONVERTIBLE_EXTENSIONS
        )

        index: Dict[str, IndexEntry] = {}
        errors: List[Tuple[str, str]] = []
        files_indexed = 0

        for name in candidates:
            full_path = os.path.join(directory, name)
            try:
                result = self._md.convert(full_path)
                markdown = result.markdown or ""
            except Exception as exc:
                errors.append((name, str(exc)))
                continue

            keywords = self._extract_keywords(markdown)
            if keywords:
                files_indexed += 1

            for canonical, display, context in keywords:
                if canonical not in index:
                    index[canonical] = IndexEntry(
                        keyword=canonical,
                        display_keyword=display,
                    )
                index[canonical].add_ref(
                    filename=name,
                    file_path=full_path,
                    context=context,
                )

        return IndexResult(
            directory=directory,
            total_files_scanned=len(candidates),
            total_files_indexed=files_indexed,
            total_keywords=len(index),
            entries=index,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------

    def _extract_keywords(
        self, markdown: str
    ) -> List[Tuple[str, str, Optional[str]]]:
        """Extract keywords from *markdown* text.

        Returns a list of ``(canonical_lowercase, display_form, context)``
        tuples capped at ``_MAX_KEYWORDS_PER_FILE``.
        """
        keywords: Dict[str, Tuple[str, Optional[str]]] = {}

        for canonical, display, context in self._extract_heading_keywords(markdown):
            if canonical not in keywords:
                keywords[canonical] = (display, context)

        for canonical, display, context in self._extract_proper_nouns(markdown):
            if canonical not in keywords:
                keywords[canonical] = (display, context)

        for canonical, display in self._extract_frequent_words(markdown):
            if canonical not in keywords:
                keywords[canonical] = (display, None)

        result = [
            (canonical, display, ctx)
            for canonical, (display, ctx) in keywords.items()
        ]
        return result[:_MAX_KEYWORDS_PER_FILE]

    def _extract_heading_keywords(
        self, markdown: str
    ) -> List[Tuple[str, str, Optional[str]]]:
        """Yield significant words from all ATX headings."""
        results: List[Tuple[str, str, Optional[str]]] = []

        for m in _HEADING_RE.finditer(markdown):
            heading_text = m.group(1).strip()
            clean = _INLINE_MARKUP_RE.sub("", heading_text)
            clean = _URL_RE.sub("", clean)

            for wm in _WORD_RE.finditer(clean):
                word = wm.group(0)
                canonical = word.lower()
                if canonical in _STOP_WORDS:
                    continue
                if len(canonical) < _MIN_KEYWORD_LEN:
                    continue
                results.append((canonical, word, heading_text))

        return results

    def _extract_proper_nouns(
        self, markdown: str
    ) -> List[Tuple[str, str, Optional[str]]]:
        """Yield proper noun candidates and ALL-CAPS acronyms from body text."""
        heading_map = self._build_heading_context_map(markdown)
        results: List[Tuple[str, str, Optional[str]]] = []

        lines = markdown.split("\n")
        for line_idx, line in enumerate(lines):
            if line.strip().startswith("#"):
                continue

            context = heading_map.get(line_idx)
            clean = _INLINE_MARKUP_RE.sub("", line)
            clean = _URL_RE.sub("", clean)

            sentence_starts: Set[int] = set()
            for sm in _SENTENCE_START_RE.finditer(clean):
                sentence_starts.add(sm.start(1))

            for wm in re.finditer(r"\b[A-Z][a-zA-Z0-9\-]{2,}\b", clean):
                if wm.start() in sentence_starts:
                    continue
                word = wm.group(0)
                canonical = word.lower()
                if canonical in _STOP_WORDS:
                    continue
                if len(canonical) < _MIN_KEYWORD_LEN:
                    continue
                results.append((canonical, word, context))

            for wm in re.finditer(r"\b[A-Z]{3,8}\b", clean):
                word = wm.group(0)
                canonical = word.lower()
                if canonical in _STOP_WORDS:
                    continue
                results.append((canonical, word, context))

        return results

    def _extract_frequent_words(
        self, markdown: str
    ) -> List[Tuple[str, str]]:
        """Yield body words that appear >= _MIN_BODY_FREQ times."""
        body = _HEADING_RE.sub("", markdown)
        body = re.sub(r"```[\s\S]*?```", "", body)
        body = re.sub(r"`[^`]+`", "", body)
        body = _URL_RE.sub("", body)
        body = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", body)
        body = re.sub(r"\[[^\]]*\]\([^)]+\)", "", body)
        body = re.sub(r"[*_#>\|\-]", " ", body)

        canonical_counter: Counter = Counter()
        display_counter: Dict[str, Counter] = {}

        for wm in _WORD_RE.finditer(body):
            raw = wm.group(0)
            canonical = raw.lower()
            if canonical in _STOP_WORDS:
                continue
            if len(canonical) < _MIN_KEYWORD_LEN:
                continue
            canonical_counter[canonical] += 1
            if canonical not in display_counter:
                display_counter[canonical] = Counter()
            display_counter[canonical][raw] += 1

        results: List[Tuple[str, str]] = []
        for canonical, count in canonical_counter.most_common():
            if count < _MIN_BODY_FREQ:
                break
            display = display_counter[canonical].most_common(1)[0][0]
            results.append((canonical, display))

        return results

    def _build_heading_context_map(self, markdown: str) -> Dict[int, str]:
        """Map each line index to the nearest preceding heading text."""
        lines = markdown.split("\n")
        heading_map: Dict[int, str] = {}
        current_heading: Optional[str] = None

        for i, line in enumerate(lines):
            m = re.match(r"^#{1,6}\s+(.+)$", line.strip())
            if m:
                current_heading = m.group(1).strip()
            elif current_heading is not None:
                heading_map[i] = current_heading

        return heading_map


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class IndexWriter:
    """Render and write an ``IndexResult`` to a file, stream, or stdout.

    Supported output formats:

    * ``"text"`` (default) -- visually rendered index with coloured letter
      headings, bold keywords, and indented file reference lists.  Uses the
      same ``_mono_format`` helpers as the rest of the converter output, so
      the result reads like rendered markdown rather than raw source.
    * ``"json"``           -- machine-readable JSON dump.

    Usage::

        writer = IndexWriter()

        # Print to stdout
        writer.write(result)

        # Save to file
        writer.write(result, "index.txt")

        # JSON format
        writer.write(result, "index.json", fmt="json")
    """

    def format(
        self,
        result: IndexResult,
        *,
        fmt: str = "text",
        indent: int = 2,
    ) -> str:
        """Format an ``IndexResult`` as a string.

        Args:
            result: The index result to format.
            fmt: Output format -- ``"text"`` (default) or ``"json"``.
            indent: JSON indentation level (only when fmt is ``"json"``).

        Returns:
            The formatted string.
        """
        if fmt == "json":
            return result.to_json(indent=indent)
        if fmt == "text":
            return self._format_text(result)
        raise ValueError(
            f"Unsupported format: {fmt!r}. Supported formats: 'text', 'json'."
        )

    def write(
        self,
        result: IndexResult,
        destination: Union[str, TextIO, None] = None,
        *,
        fmt: str = "text",
        indent: int = 2,
    ) -> str:
        """Format and write an ``IndexResult``.

        Args:
            result: The index result to write.
            destination:
                - A file path (str) -- writes to that file.
                - A text stream -- writes to the stream.
                - ``None`` -- writes to stdout.
            fmt: Output format -- ``"text"`` or ``"json"``.
            indent: JSON indentation level.

        Returns:
            The formatted string (same content that was written).
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
    # Text formatter
    # ------------------------------------------------------------------

    def _format_text(self, result: IndexResult) -> str:
        _RULE  = "\u2500" * 64   # ────  full-width rule (cobalt)
        _DIVIDER = "\u2500" * 3   # ───  letter-section divider (teal)
        _BULLET  = "\u25c6"       # ◆   gold file-reference marker

        out = []

        # ── Title block ────────────────────────────────────────────────
        out.append(f"{COBALT}{_RULE}{RESET}\n")
        out.append(f"{COBALT}  Keyword Index{RESET}\n")
        out.append(f"{COBALT}{_RULE}{RESET}\n\n")

        # ── Summary metadata (key in ash, value in plain) ─────────────
        out.append(f"  {ASH}Directory{RESET}      {result.directory}\n")
        out.append(f"  {ASH}Files scanned{RESET}  {result.total_files_scanned}\n")
        out.append(f"  {ASH}Files indexed{RESET}  {result.total_files_indexed}\n")
        out.append(f"  {ASH}Keywords{RESET}       {result.total_keywords}\n")
        out.append("\n")

        if result.errors:
            out.append(f"  {ASH}Conversion errors{RESET}  {len(result.errors)}\n")
            for fname, err in result.errors:
                out.append(f"    {ASH}{fname}{RESET}  {err[:120]}\n")
            out.append("\n")

        # ── Alphabetical sections ──────────────────────────────────────
        for letter in list(string.ascii_uppercase) + ["#"]:
            if letter == "#":
                entries = result.entries_for_non_alpha()
            else:
                entries = result.entries_for_letter(letter)

            if not entries:
                continue

            # Letter label with short rule (teal)
            out.append(f"{TEAL}{_DIVIDER}  {letter}{RESET}\n\n")

            for entry in entries:
                # Keyword name (coral — prominent, no markup characters)
                out.append(f"  {CORAL}{entry.display_keyword}{RESET}\n")

                # File references bulleted under the keyword (gold ◆, ash context)
                for ref in entry.refs:
                    if ref.context:
                        out.append(
                            f"    {GOLD}{_BULLET}{RESET}  "
                            f"{ref.filename}   {ASH}{ref.context}{RESET}\n"
                        )
                    else:
                        out.append(
                            f"    {GOLD}{_BULLET}{RESET}  {ref.filename}\n"
                        )

                out.append("\n")

        out.append(f"{COBALT}{_RULE}{RESET}\n")
        return "".join(out)
