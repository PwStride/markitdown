"""Sitemap-preview analyser.

Given a file stream and its StreamInfo the analyser produces a
SitemapPreviewResult -- a JSON-serialisable table-of-contents preview that
includes per-section summaries, media listings (images / tables), an
approximate token count, and a conversion-confidence score (0-100).

Confidence scoring rubric
-------------------------
The score is assembled from three orthogonal factors:

* Format support (base score)
  - Fully supported formats start at 80+.
  - Unknown formats receive 30.

* Structural richness penalty (-0 to -15)
  Formats with heavy styling or complex nested containers lose points.

* Content-complexity bonus / penalty (-5 to +5)
  - Images without alt-text: -5.
  - Mostly text with clear headings: +5.

The final score is clamped to [0, 100].
"""

import io
import re
import sys
import csv
import json
import zipfile
from typing import BinaryIO, Any, List, Optional, Tuple

from ._stream_info import StreamInfo
from ._sitemap_preview import SitemapPreviewResult, SectionPreview, MediaItem


# ---------------------------------------------------------------------------
# Optional-dependency guards  (same pattern used throughout markitdown)
# ---------------------------------------------------------------------------

_pdf_exc: Any = None
try:
    import pdfminer.high_level
    import pdfminer.layout
    import pdfminer.pdfpage
except ImportError:
    _pdf_exc = sys.exc_info()

_docx_exc: Any = None
try:
    import mammoth
except ImportError:
    _docx_exc = sys.exc_info()

_pptx_exc: Any = None
try:
    import pptx as _pptx_mod
except ImportError:
    _pptx_exc = sys.exc_info()

_xlsx_exc: Any = None
try:
    import openpyxl
except ImportError:
    _xlsx_exc = sys.exc_info()

_xlrd_exc: Any = None
try:
    import xlrd
except ImportError:
    _xlrd_exc = sys.exc_info()

_epub_exc: Any = None
try:
    from defusedxml import minidom as _safe_minidom
    from bs4 import BeautifulSoup as _BS4
except ImportError:
    _epub_exc = sys.exc_info()

_ics_exc: Any = None
try:
    import icalendar
except ImportError:
    _ics_exc = sys.exc_info()


# ---------------------------------------------------------------------------
# Token-count helper
# ---------------------------------------------------------------------------


def _approx_token_count(text: str) -> int:
    """Lightweight token-count proxy: split on whitespace, count words."""
    return len(text.split())


# ---------------------------------------------------------------------------
# Sentence-truncation helper
# ---------------------------------------------------------------------------


def _to_one_sentence(text: str) -> str:
    """Collapse text into a single sentence (<= 150 chars).

    Takes the first sentence boundary (`.`, `!`, `?`) within 150 chars.
    If none is found, hard-truncates at 150 chars with an ellipsis.
    """
    text = " ".join(text.split())  # normalise whitespace
    if len(text) <= 150:
        return text.rstrip()

    for i, ch in enumerate(text[:150]):
        if ch in ".!?":
            return text[: i + 1].strip()

    return text[:150].rsplit(" ", 1)[0] + "..."


# ---------------------------------------------------------------------------
# Subject extraction helper
# ---------------------------------------------------------------------------


def _extract_subject(text: str, title: Optional[str] = None) -> str:
    """Derive a short subject phrase from the document."""
    if title and title.strip():
        return _to_one_sentence(title.strip())

    for line in text.splitlines():
        stripped = line.lstrip("#").strip()
        if stripped and line.startswith("#"):
            return _to_one_sentence(stripped)

    snippet = " ".join(text.split()[:12])
    return snippet if snippet else "Untitled document"


# ---------------------------------------------------------------------------
# Confidence scorer
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


def _compute_confidence(
    extension: str, media: List[MediaItem], sections: List[SectionPreview]
) -> int:
    ext = extension.lower() if extension else ""
    base = _BASE_SCORES.get(ext, 30)
    penalty = _STRUCTURAL_PENALTY.get(ext, 0)

    images = [m for m in media if m.type == "image"]

    adjustment = 0
    if images and all("no description available" in img.description.lower() for img in images):
        adjustment = -5
    elif sections and not images:
        adjustment = 5

    score = base - penalty + adjustment
    return max(0, min(100, score))


# ---------------------------------------------------------------------------
# Main converter class
# ---------------------------------------------------------------------------


class SitemapPreviewConverter:
    """Produces a SitemapPreviewResult for a given file stream.

    Usage::

        converter = SitemapPreviewConverter()
        result = converter.generate(file_stream, stream_info)
        print(result.to_json())
    """

    def generate(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> SitemapPreviewResult:
        """Entry point: dispatch to the appropriate format handler."""
        ext = (stream_info.extension or "").lower()
        cur_pos = file_stream.tell()

        try:
            if ext == ".pdf":
                return self._handle_pdf(file_stream, stream_info)
            elif ext == ".docx":
                return self._handle_docx(file_stream, stream_info)
            elif ext == ".pptx":
                return self._handle_pptx(file_stream, stream_info)
            elif ext == ".xlsx":
                return self._handle_xlsx(file_stream, stream_info)
            elif ext == ".xls":
                return self._handle_xls(file_stream, stream_info)
            elif ext == ".epub":
                return self._handle_epub(file_stream, stream_info)
            elif ext == ".csv":
                return self._handle_csv(file_stream, stream_info)
            elif ext in (".html", ".htm"):
                return self._handle_html(file_stream, stream_info)
            elif ext == ".ipynb":
                return self._handle_ipynb(file_stream, stream_info)
            elif ext == ".ics":
                return self._handle_ics(file_stream, stream_info)
            else:
                return self._handle_plain_text(file_stream, stream_info)
        finally:
            file_stream.seek(cur_pos)

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    def _handle_pdf(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        if _pdf_exc is not None:
            return self._fallback_preview(file_stream, stream_info)

        pages: List[str] = []
        for page in pdfminer.pdfpage.PDFPage.get_pages(file_stream):
            from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
            from pdfminer.converter import TextConverter

            rsrcmgr = PDFResourceManager()
            buf = io.StringIO()
            interpreter = PDFPageInterpreter(
                rsrcmgr, TextConverter(rsrcmgr, buf, laparams=pdfminer.layout.LAParams())
            )
            interpreter.process_page(page)
            pages.append(buf.getvalue())

        full_text = "\n".join(pages)
        sections = self._sections_from_text(full_text, pages)
        media = self._media_from_text_pages(full_text, pages)
        confidence = _compute_confidence(".pdf", media, sections)

        return SitemapPreviewResult(
            file_type=".pdf",
            subject=_extract_subject(full_text),
            total_token_count=_approx_token_count(full_text),
            conversion_confidence=confidence,
            total_page_count=len(pages),
            sections=sections,
            media=media,
        )

    # ------------------------------------------------------------------
    # DOCX
    # ------------------------------------------------------------------

    def _handle_docx(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        if _docx_exc is not None:
            return self._fallback_preview(file_stream, stream_info)

        html_text = mammoth.convert_to_html(file_stream).value
        sections, media, plain_text = self._parse_html(html_text, page=None)
        confidence = _compute_confidence(".docx", media, sections)

        return SitemapPreviewResult(
            file_type=".docx",
            subject=_extract_subject(plain_text),
            total_token_count=_approx_token_count(plain_text),
            conversion_confidence=confidence,
            total_page_count=1,
            sections=sections,
            media=media,
        )

    # ------------------------------------------------------------------
    # PPTX
    # ------------------------------------------------------------------

    def _handle_pptx(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        if _pptx_exc is not None:
            return self._fallback_preview(file_stream, stream_info)

        presentation = _pptx_mod.Presentation(file_stream)
        sections: List[SectionPreview] = []
        media: List[MediaItem] = []
        all_text_parts: List[str] = []

        for slide_num, slide in enumerate(presentation.slides, start=1):
            slide_texts: List[str] = []
            title_text: Optional[str] = None

            for shape in slide.shapes:
                if shape.has_text_frame:
                    text = shape.text_frame.text.strip()
                    if text:
                        slide_texts.append(text)
                        if shape == slide.shapes.title and text:
                            title_text = text

                if shape.shape_type == _pptx_mod.enum.shapes.MSO_SHAPE_TYPE.PICTURE:
                    alt = ""
                    try:
                        alt = shape._element._nvXxPr.cNvPr.attrib.get("descr", "")
                    except Exception:
                        pass
                    desc = (
                        f"Image on slide {slide_num}: {alt}"
                        if alt
                        else f"Image on slide {slide_num} with no description available."
                    )
                    media.append(MediaItem(type="image", page=slide_num, description=desc))

                if shape.has_table:
                    table = shape.table
                    header_cells = [cell.text.strip() for cell in table.rows[0].cells] if table.rows else []
                    header_str = ", ".join(header_cells) if header_cells else "unknown columns"
                    media.append(
                        MediaItem(
                            type="table",
                            page=slide_num,
                            description=f"Table on slide {slide_num} with columns: {header_str}.",
                        )
                    )

            slide_body = " ".join(slide_texts)
            all_text_parts.append(slide_body)

            if title_text:
                summary = _to_one_sentence(slide_body) if slide_body else "Slide with no body text."
                sections.append(SectionPreview(title=title_text, page=slide_num, summary=summary))

        total_slides = len(presentation.slides)
        full_text = " ".join(all_text_parts)
        confidence = _compute_confidence(".pptx", media, sections)

        return SitemapPreviewResult(
            file_type=".pptx",
            subject=_extract_subject(full_text),
            total_token_count=_approx_token_count(full_text),
            conversion_confidence=confidence,
            total_page_count=total_slides,
            sections=sections,
            media=media,
        )

    # ------------------------------------------------------------------
    # XLSX
    # ------------------------------------------------------------------

    def _handle_xlsx(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        if _xlsx_exc is not None:
            return self._fallback_preview(file_stream, stream_info)

        wb = openpyxl.load_workbook(file_stream, read_only=True, data_only=True)
        sections: List[SectionPreview] = []
        media: List[MediaItem] = []
        all_text: List[str] = []

        for sheet_idx, sheet_name in enumerate(wb.sheetnames, start=1):
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))

            if not rows:
                sections.append(
                    SectionPreview(
                        title=sheet_name, page=sheet_idx,
                        summary=f"Sheet '{sheet_name}' contains no data.",
                    )
                )
                continue

            header = [str(c) if c is not None else "" for c in rows[0]]
            data_row_count = max(0, len(rows) - 1)
            summary = _to_one_sentence(
                f"Sheet '{sheet_name}' contains {data_row_count} row(s) "
                f"with columns: {', '.join(header)}."
            )

            sections.append(SectionPreview(title=sheet_name, page=sheet_idx, summary=summary))
            media.append(
                MediaItem(
                    type="table", page=sheet_idx,
                    description=f"Spreadsheet table in sheet '{sheet_name}' with {data_row_count} data row(s) and {len(header)} column(s).",
                )
            )

            for row in rows:
                all_text.append(" ".join(str(c) for c in row if c is not None))

        total_sheets = len(wb.sheetnames)
        wb.close()
        full_text = "\n".join(all_text)
        confidence = _compute_confidence(".xlsx", media, sections)

        return SitemapPreviewResult(
            file_type=".xlsx",
            subject=_extract_subject(full_text, title=wb.sheetnames[0] if wb.sheetnames else None),
            total_token_count=_approx_token_count(full_text),
            conversion_confidence=confidence,
            total_page_count=total_sheets,
            sections=sections,
            media=media,
        )

    # ------------------------------------------------------------------
    # XLS
    # ------------------------------------------------------------------

    def _handle_xls(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        if _xlrd_exc is not None:
            return self._fallback_preview(file_stream, stream_info)

        data = file_stream.read()
        wb = xlrd.open_workbook(file_contents=data)
        sections: List[SectionPreview] = []
        media: List[MediaItem] = []
        all_text: List[str] = []

        for sheet_idx, sheet_name in enumerate(wb.sheet_names(), start=1):
            ws = wb.sheet_by_name(sheet_name)
            nrows = ws.nrows

            if nrows == 0:
                sections.append(
                    SectionPreview(
                        title=sheet_name, page=sheet_idx,
                        summary=f"Sheet '{sheet_name}' contains no data.",
                    )
                )
                continue

            header = [str(ws.cell_value(0, c)) for c in range(ws.ncols)]
            data_row_count = nrows - 1
            summary = _to_one_sentence(
                f"Sheet '{sheet_name}' contains {data_row_count} row(s) "
                f"with columns: {', '.join(header)}."
            )

            sections.append(SectionPreview(title=sheet_name, page=sheet_idx, summary=summary))
            media.append(
                MediaItem(
                    type="table", page=sheet_idx,
                    description=f"Spreadsheet table in sheet '{sheet_name}' with {data_row_count} data row(s) and {len(header)} column(s).",
                )
            )

            for r in range(nrows):
                all_text.append(" ".join(str(ws.cell_value(r, c)) for c in range(ws.ncols)))

        total_sheets = len(wb.sheet_names())
        full_text = "\n".join(all_text)
        confidence = _compute_confidence(".xls", media, sections)

        return SitemapPreviewResult(
            file_type=".xls",
            subject=_extract_subject(full_text, title=wb.sheet_names()[0] if wb.sheet_names() else None),
            total_token_count=_approx_token_count(full_text),
            conversion_confidence=confidence,
            total_page_count=total_sheets,
            sections=sections,
            media=media,
        )

    # ------------------------------------------------------------------
    # EPUB
    # ------------------------------------------------------------------

    def _handle_epub(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        if _epub_exc is not None:
            return self._fallback_preview(file_stream, stream_info)

        with zipfile.ZipFile(file_stream, "r") as z:
            container_dom = _safe_minidom.parse(z.open("META-INF/container.xml"))
            opf_path = container_dom.getElementsByTagName("rootfile")[0].getAttribute("full-path")
            opf_dom = _safe_minidom.parse(z.open(opf_path))

            title_nodes = opf_dom.getElementsByTagName("dc:title")
            epub_title: Optional[str] = None
            if title_nodes and title_nodes[0].firstChild:
                epub_title = title_nodes[0].firstChild.nodeValue.strip()

            manifest = {
                item.getAttribute("id"): item.getAttribute("href")
                for item in opf_dom.getElementsByTagName("item")
            }
            spine_order = [
                item.getAttribute("idref")
                for item in opf_dom.getElementsByTagName("itemref")
            ]
            base_path = "/".join(opf_path.split("/")[:-1])
            spine = [
                f"{base_path}/{manifest[iid]}" if base_path else manifest[iid]
                for iid in spine_order if iid in manifest
            ]

            sections: List[SectionPreview] = []
            media: List[MediaItem] = []
            all_text: List[str] = []

            for chapter_num, filepath in enumerate(spine, start=1):
                if filepath not in z.namelist():
                    continue
                with z.open(filepath) as f:
                    soup = _BS4(f.read(), "html.parser")
                    chapter_text = soup.get_text(separator=" ", strip=True)
                    all_text.append(chapter_text)

                    chapter_title: Optional[str] = None
                    for tag in ("h1", "h2", "h3"):
                        heading = soup.find(tag)
                        if heading and heading.get_text(strip=True):
                            chapter_title = heading.get_text(strip=True)
                            break
                    if not chapter_title:
                        chapter_title = filepath.split("/")[-1]

                    summary = _to_one_sentence(chapter_text) if chapter_text else "Empty chapter."
                    sections.append(SectionPreview(title=chapter_title, page=chapter_num, summary=summary))

                    for img in soup.find_all("img"):
                        alt = (img.get("alt") or "").strip()
                        src = img.get("src", "unknown")
                        desc = (
                            f"Image '{src}': {alt}" if alt
                            else f"Image '{src}' with no description available."
                        )
                        media.append(MediaItem(type="image", page=chapter_num, description=desc))

                    for tbl in soup.find_all("table"):
                        first_row = tbl.find("tr")
                        if first_row:
                            headers = [th.get_text(strip=True) for th in first_row.find_all(["th", "td"])]
                            header_str = ", ".join(headers) if headers else "unknown columns"
                        else:
                            header_str = "unknown columns"
                        media.append(
                            MediaItem(
                                type="table", page=chapter_num,
                                description=f"Table in chapter {chapter_num} with columns: {header_str}.",
                            )
                        )

        full_text = " ".join(all_text)
        confidence = _compute_confidence(".epub", media, sections)

        return SitemapPreviewResult(
            file_type=".epub",
            subject=_extract_subject(full_text, title=epub_title),
            total_token_count=_approx_token_count(full_text),
            conversion_confidence=confidence,
            total_page_count=len(spine),
            sections=sections,
            media=media,
        )

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    def _handle_csv(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        from charset_normalizer import from_bytes as _detect_charset

        raw = file_stream.read()
        if stream_info.charset:
            text = raw.decode(stream_info.charset)
        else:
            result = _detect_charset(raw)
            text = str(result.best()) if result.best() else raw.decode("utf-8", errors="replace")

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

        sections: List[SectionPreview] = []
        media: List[MediaItem] = []

        if rows:
            header = rows[0]
            data_count = max(0, len(rows) - 1)
            header_str = ", ".join(header)
            summary = _to_one_sentence(f"CSV with {data_count} row(s) and columns: {header_str}.")

            sections.append(SectionPreview(title="Data Table", page=1, summary=summary))
            media.append(
                MediaItem(
                    type="table", page=1,
                    description=f"Tabular data with {data_count} row(s) and {len(header)} column(s): {header_str}.",
                )
            )

        confidence = _compute_confidence(".csv", media, sections)

        return SitemapPreviewResult(
            file_type=".csv",
            subject=_extract_subject(text),
            total_token_count=_approx_token_count(text),
            conversion_confidence=confidence,
            total_page_count=1,
            sections=sections,
            media=media,
        )

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def _handle_html(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        if _epub_exc is not None:
            return self._fallback_preview(file_stream, stream_info)

        encoding = stream_info.charset or "utf-8"
        html_text = file_stream.read().decode(encoding, errors="replace")
        sections, media, plain_text = self._parse_html(html_text, page=None)

        ext = (stream_info.extension or ".html").lower()
        confidence = _compute_confidence(ext, media, sections)

        title: Optional[str] = None
        soup = _BS4(html_text, "html.parser")
        if soup.title:
            title = soup.title.string

        return SitemapPreviewResult(
            file_type=ext,
            subject=_extract_subject(plain_text, title=title),
            total_token_count=_approx_token_count(plain_text),
            conversion_confidence=confidence,
            total_page_count=1,
            sections=sections,
            media=media,
        )

    # ------------------------------------------------------------------
    # Jupyter Notebook (.ipynb)
    # ------------------------------------------------------------------

    def _handle_ipynb(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        encoding = stream_info.charset or "utf-8"
        raw = file_stream.read().decode(encoding)
        notebook = json.loads(raw)

        sections: List[SectionPreview] = []
        media: List[MediaItem] = []
        all_text: List[str] = []
        cell_num = 0

        title: Optional[str] = notebook.get("metadata", {}).get("title")

        for cell in notebook.get("cells", []):
            cell_num += 1
            cell_type = cell.get("cell_type", "")
            source = "".join(cell.get("source", []))
            all_text.append(source)

            if cell_type == "markdown":
                for line in source.splitlines():
                    if line.startswith("#"):
                        heading_text = line.lstrip("#").strip()
                        if heading_text:
                            remaining = source[source.index(line) + len(line):].strip()
                            summary = _to_one_sentence(remaining) if remaining else "Section with no body text."
                            sections.append(SectionPreview(title=heading_text, page=cell_num, summary=summary))
                            break

                for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", source):
                    alt, src = m.group(1), m.group(2)
                    desc = (
                        f"Image '{src}': {alt}" if alt
                        else f"Image '{src}' with no description available."
                    )
                    media.append(MediaItem(type="image", page=cell_num, description=desc))

            elif cell_type == "code":
                for output in cell.get("outputs", []):
                    if "image/png" in output.get("data", {}):
                        media.append(
                            MediaItem(type="image", page=cell_num,
                                      description=f"Output image in code cell {cell_num}.")
                        )
                    if "text/html" in output.get("data", {}):
                        html_out = "".join(output["data"]["text/html"])
                        if "<table" in html_out.lower():
                            media.append(
                                MediaItem(type="table", page=cell_num,
                                          description=f"HTML table output in code cell {cell_num}.")
                            )

        full_text = "\n".join(all_text)
        confidence = _compute_confidence(".ipynb", media, sections)

        return SitemapPreviewResult(
            file_type=".ipynb",
            subject=_extract_subject(full_text, title=title),
            total_token_count=_approx_token_count(full_text),
            conversion_confidence=confidence,
            total_page_count=cell_num,
            sections=sections,
            media=media,
        )

    # ------------------------------------------------------------------
    # ICS (iCalendar)
    # ------------------------------------------------------------------

    def _handle_ics(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        if _ics_exc is not None:
            return self._fallback_preview(file_stream, stream_info)

        raw = file_stream.read()
        cal = icalendar.Calendar.from_ical(raw)

        cal_title: Optional[str] = None
        cal_name = cal.get("X-WR-CALNAME")
        if cal_name:
            cal_title = str(cal_name).strip()

        sections: List[SectionPreview] = []
        all_text: List[str] = []

        events = [c for c in cal.walk() if c.name == "VEVENT"]

        for idx, event in enumerate(events, start=1):
            summary_val = event.get("SUMMARY")
            event_title = str(summary_val).strip() if summary_val else f"Event {idx}"

            desc_val = event.get("DESCRIPTION")
            location_val = event.get("LOCATION")

            parts: List[str] = []
            if location_val:
                parts.append(f"Location: {location_val}")
            if desc_val:
                parts.append(str(desc_val).strip())

            body = "; ".join(parts) if parts else "No additional details."
            all_text.append(f"{event_title} -- {body}")

            summary = _to_one_sentence(body)
            sections.append(SectionPreview(title=event_title, page=idx, summary=summary))

        full_text = "\n".join(all_text)
        confidence = _compute_confidence(".ics", [], sections)

        return SitemapPreviewResult(
            file_type=".ics",
            subject=_extract_subject(full_text, title=cal_title),
            total_token_count=_approx_token_count(full_text),
            conversion_confidence=confidence,
            total_page_count=len(events),
            sections=sections,
            media=[],
        )

    # ------------------------------------------------------------------
    # Plain text (fallback for .txt, .md, .rst, unknown)
    # ------------------------------------------------------------------

    def _handle_plain_text(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        encoding = stream_info.charset or "utf-8"
        text = file_stream.read().decode(encoding, errors="replace")

        ext = (stream_info.extension or ".txt").lower()
        sections = self._sections_from_text(text)
        media = self._media_from_text(text)
        confidence = _compute_confidence(ext, media, sections)

        return SitemapPreviewResult(
            file_type=ext,
            subject=_extract_subject(text),
            total_token_count=_approx_token_count(text),
            conversion_confidence=confidence,
            total_page_count=1,
            sections=sections,
            media=media,
        )

    # ------------------------------------------------------------------
    # Fallback: used when the needed library is not installed
    # ------------------------------------------------------------------

    def _fallback_preview(
        self, file_stream: BinaryIO, stream_info: StreamInfo
    ) -> SitemapPreviewResult:
        ext = (stream_info.extension or "").lower()
        raw = file_stream.read()
        try:
            text = raw.decode(stream_info.charset or "utf-8", errors="replace")
        except Exception:
            text = ""

        return SitemapPreviewResult(
            file_type=ext or ".unknown",
            subject="Preview unavailable (missing dependency).",
            total_token_count=_approx_token_count(text),
            conversion_confidence=30,
            sections=[],
            media=[],
        )

    # ------------------------------------------------------------------
    # Shared HTML parser (used by DOCX and HTML handlers)
    # ------------------------------------------------------------------

    def _parse_html(
        self, html_text: str, *, page: Optional[int]
    ) -> Tuple[List[SectionPreview], List[MediaItem], str]:
        """Extract sections, media, and plain text from an HTML string."""
        soup = _BS4(html_text, "html.parser")
        sections: List[SectionPreview] = []
        media: List[MediaItem] = []

        for tag in soup.find_all(re.compile(r"^h[1-6]$")):
            heading_text = tag.get_text(strip=True)
            if not heading_text:
                continue
            sibling_texts: List[str] = []
            for sib in tag.next_siblings:
                if sib.name and re.match(r"^h[1-6]$", sib.name):
                    break
                if hasattr(sib, "get_text"):
                    sibling_texts.append(sib.get_text(strip=True))
            body = " ".join(sibling_texts)
            summary = _to_one_sentence(body) if body else "Section with no body text."
            sections.append(SectionPreview(title=heading_text, page=page, summary=summary))

        for img in soup.find_all("img"):
            alt = (img.get("alt") or "").strip()
            src = img.get("src", "unknown")
            desc = (
                f"Image '{src}': {alt}" if alt
                else f"Image '{src}' with no description available."
            )
            media.append(MediaItem(type="image", page=page, description=desc))

        for tbl in soup.find_all("table"):
            first_row = tbl.find("tr")
            if first_row:
                headers = [th.get_text(strip=True) for th in first_row.find_all(["th", "td"])]
                header_str = ", ".join(headers) if headers else "unknown columns"
            else:
                header_str = "unknown columns"
            media.append(
                MediaItem(type="table", page=page, description=f"Table with columns: {header_str}.")
            )

        plain_text = soup.get_text(separator=" ", strip=True)
        return sections, media, plain_text

    # ------------------------------------------------------------------
    # Text-based section / media helpers (for PDF and plain-text)
    # ------------------------------------------------------------------

    def _sections_from_text(
        self, full_text: str, pages: Optional[List[str]] = None
    ) -> List[SectionPreview]:
        """Extract sections from plain text using heuristic heading detection."""
        sections: List[SectionPreview] = []
        lines = full_text.splitlines()

        page_boundaries: List[int] = []
        if pages:
            offset = 0
            for p in pages:
                offset += len(p) + 1
                page_boundaries.append(offset)

        def _page_for_offset(offset: int) -> Optional[int]:
            if not page_boundaries:
                return None
            for i, boundary in enumerate(page_boundaries):
                if offset < boundary:
                    return i + 1
            return len(page_boundaries)

        char_offset = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                char_offset += len(line) + 1
                continue

            is_heading = False
            if stripped.startswith("#"):
                is_heading = True
            elif (
                len(stripped) <= 80
                and stripped != stripped.lower()
                and i + 1 < len(lines)
                and lines[i + 1].strip()
            ):
                if stripped == stripped.upper() or stripped[0].isupper():
                    is_heading = True

            if is_heading:
                title = stripped.lstrip("#").strip()
                body_parts: List[str] = []
                for j in range(i + 1, min(i + 6, len(lines))):
                    next_line = lines[j].strip()
                    if next_line.startswith("#") or (next_line == next_line.upper() and len(next_line) <= 80):
                        break
                    if next_line:
                        body_parts.append(next_line)
                        if len(" ".join(body_parts)) > 150:
                            break

                body = " ".join(body_parts)
                summary = _to_one_sentence(body) if body else "Section with no body text."
                page = _page_for_offset(char_offset)
                sections.append(SectionPreview(title=title, page=page, summary=summary))

            char_offset += len(line) + 1

        return sections

    def _media_from_text_pages(
        self, full_text: str, pages: List[str]
    ) -> List[MediaItem]:
        """Detect markdown image references in page-separated text."""
        media: List[MediaItem] = []
        for page_num, page_text in enumerate(pages, start=1):
            for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", page_text):
                alt, src = m.group(1), m.group(2)
                desc = (
                    f"Image '{src}': {alt}" if alt
                    else f"Image '{src}' with no description available."
                )
                media.append(MediaItem(type="image", page=page_num, description=desc))
        return media

    def _media_from_text(self, text: str) -> List[MediaItem]:
        """Detect markdown image references in plain text (no page info)."""
        media: List[MediaItem] = []
        for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", text):
            alt, src = m.group(1), m.group(2)
            desc = (
                f"Image '{src}': {alt}" if alt
                else f"Image '{src}' with no description available."
            )
            media.append(MediaItem(type="image", page=None, description=desc))
        return media
