# Index Feature Implementation Plan

## Overview

Generate a printable alphabetical keyword index from a directory of documents.
Users can look up any keyword and find which files contain it, with section context.
CLI: `markitdown --index <directory>` → stdout or `-o index.txt`

---

## Architecture

Follows the **3-part pipeline pattern** used by every existing feature:

| File | Role |
|---|---|
| `_index.py` *(new)* | Data models: `IndexFileRef`, `IndexEntry`, `IndexResult` |
| `_index_extractor.py` *(new)* | Scanner + 3-tier keyword extraction: `DirectoryIndexBuilder` |
| `_index_writer.py` *(new)* | Text and JSON output: `IndexWriter` |
| `_markitdown.py` *(modify)* | Add `generate_index()` + `write_index()` methods |
| `__main__.py` *(modify)* | Add `--index` + `--index-format` args and dispatch handler |
| `__init__.py` *(modify)* | Export new public symbols |

---

## 1. `_index.py` — Data Models

```python
@dataclass
class IndexFileRef:
    filename: str        # basename
    file_path: str       # absolute path
    context: Optional[str] = None  # nearest heading where keyword found

@dataclass
class IndexEntry:
    keyword: str          # lowercase canonical form
    display_keyword: str  # original casing for display
    refs: List[IndexFileRef] = field(default_factory=list)

    def add_ref(self, filename, file_path, context=None): ...  # deduplicates by file_path
    def to_dict(self) -> dict: ...

@dataclass
class IndexResult:
    directory: str
    total_files_scanned: int
    total_files_indexed: int
    total_keywords: int
    entries: Dict[str, IndexEntry] = field(default_factory=dict)
    errors: List[Tuple[str, str]] = field(default_factory=list)  # (filename, error_msg)

    def sorted_entries(self) -> List[IndexEntry]: ...
    def entries_for_letter(self, letter: str) -> List[IndexEntry]: ...
    def entries_for_non_alpha(self) -> List[IndexEntry]: ...  # '#' bucket
    def to_dict(self) -> dict: ...
    def to_json(self, *, indent=2) -> str: ...
```

---

## 2. `_index_extractor.py` — Scanner + Keyword Extraction

### Constants
```python
STOP_WORDS: frozenset  # ~150 common English words + markdown noise words
_MIN_KEYWORD_LEN = 4
_MIN_BODY_FREQ = 3
_MAX_KEYWORDS_PER_FILE = 150

_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9\-]{2,}\b")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_SENTENCE_START_RE = re.compile(r"(?:^|[.!?]\s+)([A-Z][a-z]+)")
```

### `DirectoryIndexBuilder`

```python
class DirectoryIndexBuilder:
    def __init__(self, markitdown_instance): ...

    def build(self, directory: str) -> IndexResult:
        # 1. os.listdir + filter by CONVERTIBLE_EXTENSIONS (imported from _dir_preview)
        # 2. For each file: md.convert(path) -> result.markdown
        # 3. _extract_keywords(markdown) -> list of (canonical, display, context)
        # 4. Add to shared index dict, deduplicating via IndexEntry.add_ref()
        # 5. Track per-file errors without failing the whole batch
        ...
```

### 3-Tier Keyword Extraction

**Tier 1 — Heading words** (highest priority, most reliable):
- Match `_HEADING_RE`, strip inline markdown (`[*_\`\[\]()]`)
- Tokenize with `_WORD_RE`, skip `STOP_WORDS` and `len < 4`
- Context = the heading text itself

**Tier 2 — Proper nouns from body** (medium priority):
- Build `heading_context_map: {line_idx -> nearest_preceding_heading}`
- For each non-heading line: find `\b[A-Z][a-zA-Z0-9\-]{2,}\b` matches
- Reject words at sentence-start positions (`_SENTENCE_START_RE`)
- Also collect `\b[A-Z]{3,8}\b` ALL-CAPS acronyms
- Skip `STOP_WORDS`, `len < 4`

**Tier 3 — High-frequency body words** (lowest priority, fills gaps):
- Strip headings, code blocks, inline code, URLs, image/link markup
- `Counter` all `_WORD_RE` tokens (lowercased), skip STOP_WORDS, len < 4
- Keep only words with count ≥ 3
- Display form = most common casing variant

**Deduplication**: All three tiers write into `Dict[canonical, (display, context)]`. Tier 1 inserts first and wins. `IndexEntry.add_ref()` deduplicates by `file_path`.

---

## 3. `_index_writer.py` — Output Writer

### Colours (new, distinct from existing palette)
```python
_SAGE  = rgb(95, 138, 107)   # #5F8A6B — letter section headers A, B, C ...
_DUSK  = rgb(139, 126, 184)  # #8B7EB8 — keyword lines
_STONE = rgb(158, 158, 158)  # #9E9E9E — file reference lines (muted)
```

### `IndexWriter`
```python
class IndexWriter:
    def format(self, result, *, fmt="text", indent=2, use_color=True) -> str: ...
    def write(self, result, destination=None, *, fmt="text", indent=2, use_color=True) -> str: ...
    def _format_text(self, result, *, use_color) -> str: ...
```

**Text output structure:**
```
────────────────────────────────────────────────────────────────
  KEYWORD INDEX
────────────────────────────────────────────────────────────────

  directory      /path/to/dir
  files scanned  5
  files indexed  5
  keywords       63

────────────────
  A

  API
      api_guide.md  [in: Authentication]
      report.pdf

  authentication
      api_guide.md  [in: Getting Started]

────────────────
  B

  backend
      report.pdf    [in: Architecture]

────────────────────────────────────────────────────────────────
```

**Key formatting rules:**
- Horizontal rule `─` (U+2500) 64 chars — consistent with mono/tree styles
- Letter section dividers: 16-char rule
- Keywords: 2-space indent, dusk colour
- File refs: 6-space indent, stone colour
- Context `[in: <heading>]` inline on file ref line when available
- When writing to file (`destination` is a path str): `use_color=False` for clean printable output
- JSON format: delegates to `result.to_json(indent=indent)`

---

## 4. `_markitdown.py` Modifications

**New imports** after line 53 (`from ._search import ...`):
```python
from ._index import IndexResult
from ._index_extractor import DirectoryIndexBuilder
from ._index_writer import IndexWriter
```

**Two new methods** after `write_search()` (~line 1131):
```python
def generate_index(self, directory: Union[str, Path]) -> IndexResult:
    builder = DirectoryIndexBuilder(self)
    return builder.build(str(directory))

def write_index(self, directory, output=None, *, fmt="text") -> str:
    result = self.generate_index(directory)
    writer = IndexWriter()
    use_color = (output is None)
    return writer.write(result, output, fmt=fmt, use_color=use_color)
```

---

## 5. `__main__.py` Modifications

**New arguments** after the `--search` block (before line 224 `parser.add_argument("filename")`):
```python
parser.add_argument(
    "-I", "--index",
    metavar="DIRECTORY",
    help="Scan a directory and generate a printable alphabetical keyword index...",
)
parser.add_argument(
    "--index-format",
    choices=["text", "json"],
    default="text",
    help="Output format for --index: 'text' (default) or 'json'.",
)
```

**New dispatch handler** after `if args.search:` block (before line 346):
```python
if args.index:
    markitdown.write_index(args.index, output=args.output, fmt=args.index_format)
    sys.exit(0)
```

---

## 6. `__init__.py` Modifications

After line 28 (`from ._search import ...`):
```python
from ._index import IndexResult, IndexEntry, IndexFileRef
from ._index_extractor import DirectoryIndexBuilder
from ._index_writer import IndexWriter
```

Add to `__all__`: `"IndexResult"`, `"IndexEntry"`, `"IndexFileRef"`, `"DirectoryIndexBuilder"`, `"IndexWriter"`

---

## Implementation Order

1. `_index.py` — pure dataclasses, no dependencies
2. `_index_extractor.py` — depends on `_index.py` + `_dir_preview.CONVERTIBLE_EXTENSIONS`
3. `_index_writer.py` — depends on `_index.py` only
4. `_markitdown.py` — 3 imports + 2 methods (purely additive)
5. `__main__.py` — 2 args + 1 dispatch block (purely additive)
6. `__init__.py` — 5 new symbols exported
