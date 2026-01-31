#!/usr/bin/env python3 -m pytest
"""Tests for the sitemap-preview feature."""

import io
import os
import json
import pytest

from markitdown import MarkItDown, StreamInfo, SitemapPreviewWriter
from markitdown._sitemap_preview import SitemapPreviewResult, SectionPreview, MediaItem
from markitdown._sitemap_preview_converter import SitemapPreviewConverter, _approx_token_count, _to_one_sentence

TEST_FILES_DIR = os.path.join(os.path.dirname(__file__), "test_files")


def _valid_result(result):
    assert isinstance(result, SitemapPreviewResult)
    assert isinstance(result.file_type, str) and result.file_type
    assert isinstance(result.subject, str) and result.subject
    assert isinstance(result.total_token_count, int) and result.total_token_count >= 0
    assert result.total_page_count is None or (isinstance(result.total_page_count, int) and result.total_page_count >= 0)
    assert 0 <= result.conversion_confidence <= 100
    d = result.to_dict()
    j = result.to_json()
    assert json.loads(j) == d
    assert "total_page_count" in d
    for s in result.sections:
        assert isinstance(s, SectionPreview)
        assert isinstance(s.title, str) and s.title
        assert isinstance(s.summary, str) and s.summary
    for m in result.media:
        assert isinstance(m, MediaItem)
        assert m.type in ("image", "table")
        assert isinstance(m.description, str) and m.description


class TestSitemapPreviewResult:
    def test_to_dict_keys(self):
        result = SitemapPreviewResult(
            file_type=".pdf", subject="Test subject", total_token_count=42,
            conversion_confidence=75, total_page_count=5,
            sections=[SectionPreview(title="Intro", page=1, summary="An introduction.")],
            media=[MediaItem(type="image", page=1, description="A photo.")],
        )
        d = result.to_dict()
        assert set(d.keys()) == {"file_type", "subject", "total_token_count", "total_page_count", "conversion_confidence", "sections", "media"}
        assert d["total_page_count"] == 5
        assert d["sections"][0] == {"title": "Intro", "page": 1, "summary": "An introduction."}
        assert d["media"][0] == {"type": "image", "page": 1, "description": "A photo."}

    def test_to_json_is_valid_json(self):
        result = SitemapPreviewResult(file_type=".docx", subject="Hello", total_token_count=10, conversion_confidence=80, total_page_count=3)
        parsed = json.loads(result.to_json())
        assert parsed["file_type"] == ".docx"
        assert parsed["total_page_count"] == 3
        assert parsed["sections"] == []
        assert parsed["media"] == []

    def test_to_json_indent(self):
        result = SitemapPreviewResult(file_type=".txt", subject="s", total_token_count=1, conversion_confidence=95, total_page_count=1)
        assert "\n" in result.to_json()


class TestHelpers:
    def test_approx_token_count_empty(self):
        assert _approx_token_count("") == 0

    def test_approx_token_count_words(self):
        assert _approx_token_count("hello world foo") == 3

    def test_approx_token_count_extra_whitespace(self):
        assert _approx_token_count("  hello   world  ") == 2

    def test_to_one_sentence_short(self):
        assert _to_one_sentence("This is short.") == "This is short."

    def test_to_one_sentence_truncates_at_period(self):
        text = "First sentence. " + "Second sentence that is much longer and goes on and on and on and on and on and on and on and on and on and on and on and on and on and on."
        assert len(text) > 150
        assert _to_one_sentence(text) == "First sentence."

    def test_to_one_sentence_hard_truncate(self):
        text = "a" * 200
        result = _to_one_sentence(text)
        assert result.endswith("...")
        assert len(result) <= 154


class TestPdfPreview:
    def test_pdf_preview(self):
        path = os.path.join(TEST_FILES_DIR, "test.pdf")
        if not os.path.exists(path):
            pytest.skip("test.pdf not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=".pdf"))
        _valid_result(result)
        assert result.file_type == ".pdf"
        assert result.total_token_count > 0
        assert result.total_page_count is not None and result.total_page_count >= 1


class TestDocxPreview:
    def test_docx_preview(self):
        path = os.path.join(TEST_FILES_DIR, "test.docx")
        if not os.path.exists(path):
            pytest.skip("test.docx not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=".docx"))
        _valid_result(result)
        assert result.file_type == ".docx"
        assert result.total_token_count > 0

    def test_docx_with_comments(self):
        path = os.path.join(TEST_FILES_DIR, "test_with_comment.docx")
        if not os.path.exists(path):
            pytest.skip("test_with_comment.docx not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=".docx"))
        _valid_result(result)
        assert result.total_token_count > 0


class TestPptxPreview:
    def test_pptx_preview(self):
        path = os.path.join(TEST_FILES_DIR, "test.pptx")
        if not os.path.exists(path):
            pytest.skip("test.pptx not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=".pptx"))
        _valid_result(result)
        assert result.file_type == ".pptx"
        assert result.total_page_count is not None and result.total_page_count >= 1
        assert len(result.sections) > 0
        for s in result.sections:
            assert s.page is not None and 1 <= s.page <= result.total_page_count
        assert len(result.media) > 0
        for m in result.media:
            assert m.page is not None and 1 <= m.page <= result.total_page_count


class TestXlsxPreview:
    def test_xlsx_preview(self):
        path = os.path.join(TEST_FILES_DIR, "test.xlsx")
        if not os.path.exists(path):
            pytest.skip("test.xlsx not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=".xlsx"))
        _valid_result(result)
        assert result.file_type == ".xlsx"
        assert result.total_page_count is not None and result.total_page_count >= 1
        assert len(result.sections) > 0
        assert len(result.media) > 0
        assert all(m.type == "table" for m in result.media)


class TestXlsPreview:
    def test_xls_preview(self):
        path = os.path.join(TEST_FILES_DIR, "test.xls")
        if not os.path.exists(path):
            pytest.skip("test.xls not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=".xls"))
        _valid_result(result)
        assert result.file_type == ".xls"
        assert result.total_page_count is not None and result.total_page_count >= 1
        assert len(result.sections) > 0
        assert all(m.type == "table" for m in result.media)


class TestEpubPreview:
    def test_epub_preview(self):
        path = os.path.join(TEST_FILES_DIR, "test.epub")
        if not os.path.exists(path):
            pytest.skip("test.epub not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=".epub"))
        _valid_result(result)
        assert result.file_type == ".epub"
        assert result.total_page_count is not None and result.total_page_count >= 1
        assert len(result.sections) > 0
        pages = [s.page for s in result.sections]
        assert pages == sorted(pages)


class TestCsvPreview:
    def test_csv_preview(self):
        path = os.path.join(TEST_FILES_DIR, "test_mskanji.csv")
        if not os.path.exists(path):
            pytest.skip("test_mskanji.csv not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=".csv"))
        _valid_result(result)
        assert result.file_type == ".csv"
        assert len(result.sections) == 1
        assert result.sections[0].title == "Data Table"
        assert len(result.media) == 1
        assert result.media[0].type == "table"

    def test_csv_from_string(self):
        csv_data = "name,age,city\nAlice,30,NYC\nBob,25,LA\n"
        converter = SitemapPreviewConverter()
        stream = io.BytesIO(csv_data.encode("utf-8"))
        result = converter.generate(stream, StreamInfo(extension=".csv", charset="utf-8"))
        _valid_result(result)
        assert result.total_token_count > 0
        assert result.total_page_count == 1
        assert "name" in result.media[0].description
        assert "age" in result.media[0].description
        assert "city" in result.media[0].description


class TestHtmlPreview:
    def test_html_preview(self):
        path = os.path.join(TEST_FILES_DIR, "test_blog.html")
        if not os.path.exists(path):
            pytest.skip("test_blog.html not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=".html"))
        _valid_result(result)
        assert result.file_type == ".html"
        assert result.total_token_count > 0

    def test_html_from_string_with_headings_and_image(self):
        html = (
            '<html><head><title>Test Page</title></head><body>'
            '<h1>Main Title</h1><p>Some introductory text here.</p>'
            '<h2>Section A</h2><p>Details about section A.</p>'
            '<img src="photo.png" alt="A landscape photo">'
            '<h2>Section B</h2><p>Details about section B.</p>'
            '</body></html>'
        )
        converter = SitemapPreviewConverter()
        stream = io.BytesIO(html.encode("utf-8"))
        result = converter.generate(stream, StreamInfo(extension=".html", charset="utf-8"))
        _valid_result(result)
        assert result.subject == "Test Page"
        titles = [s.title for s in result.sections]
        assert "Main Title" in titles
        assert "Section A" in titles
        assert "Section B" in titles
        image_items = [m for m in result.media if m.type == "image"]
        assert len(image_items) == 1
        assert "landscape" in image_items[0].description

    def test_html_table_detection(self):
        html = (
            '<html><body><h1>Data</h1>'
            '<table><tr><th>Name</th><th>Score</th></tr>'
            '<tr><td>Alice</td><td>95</td></tr></table></body></html>'
        )
        converter = SitemapPreviewConverter()
        stream = io.BytesIO(html.encode("utf-8"))
        result = converter.generate(stream, StreamInfo(extension=".html", charset="utf-8"))
        tables = [m for m in result.media if m.type == "table"]
        assert len(tables) == 1
        assert "Name" in tables[0].description
        assert "Score" in tables[0].description


class TestIpynbPreview:
    def test_ipynb_preview(self):
        path = os.path.join(TEST_FILES_DIR, "test_notebook.ipynb")
        if not os.path.exists(path):
            pytest.skip("test_notebook.ipynb not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=".ipynb"))
        _valid_result(result)
        assert result.file_type == ".ipynb"
        assert result.total_token_count > 0

    def test_ipynb_synthetic(self):
        notebook = {
            "nbformat": 4, "nbformat_minor": 2,
            "metadata": {"title": "My Notebook"},
            "cells": [
                {"cell_type": "markdown", "source": ["# Introduction\n", "This notebook explores data analysis.\n"], "metadata": {}},
                {"cell_type": "code", "source": ["import pandas as pd\n"], "metadata": {},
                 "outputs": [{"output_type": "display_data", "data": {"image/png": "base64data...", "text/plain": "<Figure>"}}], "execution_count": 1},
                {"cell_type": "markdown", "source": ["## Results\n", "Here are the results of the analysis.\n"], "metadata": {}},
                {"cell_type": "code", "source": ["df.head()\n"], "metadata": {},
                 "outputs": [{"output_type": "execute_result", "data": {"text/html": ["<table><tr><th>A</th></tr><tr><td>1</td></tr></table>"], "text/plain": ["   A\n0  1"]}}], "execution_count": 2},
            ],
        }
        converter = SitemapPreviewConverter()
        stream = io.BytesIO(json.dumps(notebook).encode("utf-8"))
        result = converter.generate(stream, StreamInfo(extension=".ipynb", charset="utf-8"))
        _valid_result(result)
        assert result.subject == "My Notebook"
        titles = [s.title for s in result.sections]
        assert "Introduction" in titles
        assert "Results" in titles
        assert result.total_page_count == 4
        images = [m for m in result.media if m.type == "image"]
        tables = [m for m in result.media if m.type == "table"]
        assert len(images) == 1
        assert len(tables) == 1


class TestIcsPreview:
    def test_ics_preview(self):
        path = os.path.join(TEST_FILES_DIR, "test.ics")
        if not os.path.exists(path):
            pytest.skip("test.ics not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=".ics"))
        _valid_result(result)
        assert result.file_type == ".ics"
        assert len(result.media) == 0
        assert len(result.sections) > 0

    def test_ics_synthetic(self):
        ics_text = (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-WR-CALNAME:Work Calendar\r\n"
            "BEGIN:VEVENT\r\nSUMMARY:Team Standup\r\nDTSTART:20250115T090000Z\r\n"
            "DTEND:20250115T093000Z\r\nLOCATION:Conference Room B\r\n"
            "DESCRIPTION:Daily sync meeting.\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nSUMMARY:Sprint Review\r\nDTSTART:20250120T140000Z\r\n"
            "DTEND:20250120T160000Z\r\nLOCATION:Main Hall\r\n"
            "DESCRIPTION:End-of-sprint review session.\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        converter = SitemapPreviewConverter()
        stream = io.BytesIO(ics_text.encode("utf-8"))
        result = converter.generate(stream, StreamInfo(extension=".ics", charset="utf-8"))
        _valid_result(result)
        assert result.subject == "Work Calendar"
        titles = [s.title for s in result.sections]
        assert "Team Standup" in titles
        assert "Sprint Review" in titles
        assert result.total_page_count == 2
        assert len(result.media) == 0


class TestPlainTextPreview:
    def test_plain_text_with_headings(self):
        text = "# Welcome\n\nThis document covers basic setup.\n\n## Installation\n\nRun the install command to get started.\n\n## Usage\n\nImport the module and call the main function.\n"
        converter = SitemapPreviewConverter()
        stream = io.BytesIO(text.encode("utf-8"))
        result = converter.generate(stream, StreamInfo(extension=".txt", charset="utf-8"))
        _valid_result(result)
        assert result.file_type == ".txt"
        assert result.total_page_count == 1
        titles = [s.title for s in result.sections]
        assert "Welcome" in titles
        assert "Installation" in titles
        assert "Usage" in titles

    def test_markdown_file(self):
        text = "# Project README\n\nA short description of the project.\n\n## Features\n\n- Feature one\n- Feature two\n\n![Logo](logo.png)\n"
        converter = SitemapPreviewConverter()
        stream = io.BytesIO(text.encode("utf-8"))
        result = converter.generate(stream, StreamInfo(extension=".md", charset="utf-8"))
        _valid_result(result)
        assert result.file_type == ".md"
        images = [m for m in result.media if m.type == "image"]
        assert len(images) == 1
        assert "Logo" in images[0].description
        assert result.conversion_confidence >= 93


class TestConfidenceScores:
    def _get_confidence(self, path, ext):
        if not os.path.exists(path):
            pytest.skip(f"{path} not available")
        converter = SitemapPreviewConverter()
        with open(path, "rb") as fh:
            result = converter.generate(fh, StreamInfo(extension=ext))
        return result.conversion_confidence

    def test_pdf_confidence_range(self):
        assert 60 <= self._get_confidence(os.path.join(TEST_FILES_DIR, "test.pdf"), ".pdf") <= 90

    def test_docx_confidence_range(self):
        assert 75 <= self._get_confidence(os.path.join(TEST_FILES_DIR, "test.docx"), ".docx") <= 95

    def test_pptx_confidence_range(self):
        assert 55 <= self._get_confidence(os.path.join(TEST_FILES_DIR, "test.pptx"), ".pptx") <= 80

    def test_xlsx_confidence_range(self):
        assert 65 <= self._get_confidence(os.path.join(TEST_FILES_DIR, "test.xlsx"), ".xlsx") <= 85

    def test_csv_confidence_range(self):
        converter = SitemapPreviewConverter()
        stream = io.BytesIO(b"a,b\n1,2\n")
        result = converter.generate(stream, StreamInfo(extension=".csv", charset="utf-8"))
        assert 85 <= result.conversion_confidence <= 100

    def test_unknown_extension_confidence(self):
        converter = SitemapPreviewConverter()
        stream = io.BytesIO(b"some random bytes here")
        result = converter.generate(stream, StreamInfo(extension=".xyz", charset="utf-8"))
        assert 0 <= result.conversion_confidence <= 40


class TestMarkItDownIntegration:
    def test_from_local_path(self):
        path = os.path.join(TEST_FILES_DIR, "test.docx")
        if not os.path.exists(path):
            pytest.skip("test.docx not available")
        md = MarkItDown()
        result = md.generate_sitemap_preview(path)
        _valid_result(result)
        assert result.file_type == ".docx"

    def test_from_stream(self):
        html = "<html><body><h1>Title</h1><p>Body text here.</p></body></html>"
        md = MarkItDown()
        stream = io.BytesIO(html.encode("utf-8"))
        result = md.generate_sitemap_preview(stream, stream_info=StreamInfo(extension=".html", charset="utf-8"))
        _valid_result(result)
        assert result.file_type == ".html"

    def test_invalid_source_type_raises(self):
        md = MarkItDown()
        with pytest.raises(TypeError):
            md.generate_sitemap_preview(12345)

    def test_pptx_integration(self):
        path = os.path.join(TEST_FILES_DIR, "test.pptx")
        if not os.path.exists(path):
            pytest.skip("test.pptx not available")
        md = MarkItDown()
        result = md.generate_sitemap_preview(path)
        _valid_result(result)
        assert result.file_type == ".pptx"
        parsed = json.loads(result.to_json())
        assert "sections" in parsed
        assert "media" in parsed
        assert "conversion_confidence" in parsed

    def test_epub_integration(self):
        path = os.path.join(TEST_FILES_DIR, "test.epub")
        if not os.path.exists(path):
            pytest.skip("test.epub not available")
        md = MarkItDown()
        result = md.generate_sitemap_preview(path)
        _valid_result(result)
        assert result.file_type == ".epub"

    def test_xlsx_integration(self):
        path = os.path.join(TEST_FILES_DIR, "test.xlsx")
        if not os.path.exists(path):
            pytest.skip("test.xlsx not available")
        md = MarkItDown()
        result = md.generate_sitemap_preview(path)
        _valid_result(result)
        assert all(m.type == "table" for m in result.media)

    def test_ics_integration(self):
        path = os.path.join(TEST_FILES_DIR, "test.ics")
        if not os.path.exists(path):
            pytest.skip("test.ics not available")
        md = MarkItDown()
        result = md.generate_sitemap_preview(path)
        _valid_result(result)
        assert result.file_type == ".ics"

    def test_non_seekable_stream(self):
        html = "<html><body><h1>Non-Seekable</h1><p>Content.</p></body></html>"

        class NonSeekableStream:
            def __init__(self, data):
                self._buf = io.BytesIO(data)
            def read(self, n=-1):
                return self._buf.read(n)
            def seekable(self):
                return False

        md = MarkItDown()
        stream = NonSeekableStream(html.encode("utf-8"))
        result = md.generate_sitemap_preview(stream, stream_info=StreamInfo(extension=".html", charset="utf-8"))
        _valid_result(result)


class TestSitemapPreviewWriter:
    """Tests for the SitemapPreviewWriter output module."""

    def _sample_result(self):
        return SitemapPreviewResult(
            file_type=".pdf",
            subject="Test Document",
            total_token_count=500,
            conversion_confidence=82,
            total_page_count=5,
            sections=[
                SectionPreview(title="Introduction", page=1, summary="Covers the background of the study."),
                SectionPreview(title="Methods", page=3, summary="Describes the experimental setup."),
            ],
            media=[
                MediaItem(type="image", page=2, description="Figure showing data distribution."),
                MediaItem(type="table", page=3, description="Table of results with 10 rows."),
            ],
        )

    def test_format_json(self):
        writer = SitemapPreviewWriter()
        result = self._sample_result()
        output = writer.format(result, fmt="json")
        parsed = json.loads(output)
        assert parsed["file_type"] == ".pdf"
        assert parsed["subject"] == "Test Document"
        assert parsed["total_token_count"] == 500
        assert parsed["total_page_count"] == 5
        assert parsed["conversion_confidence"] == 82
        assert len(parsed["sections"]) == 2
        assert len(parsed["media"]) == 2

    def test_format_text(self):
        writer = SitemapPreviewWriter()
        result = self._sample_result()
        output = writer.format(result, fmt="text")
        assert "SITEMAP PREVIEW" in output
        assert "TABLE OF CONTENTS" in output
        assert "IMAGES & TABLES" in output
        assert ".pdf" in output
        assert "Test Document" in output
        assert "Total page count:" in output
        assert "5" in output
        assert "82%" in output
        assert "Introduction" in output
        assert "Methods" in output
        assert "Figure showing data distribution" in output
        assert "Table of results" in output

    def test_format_text_no_sections(self):
        writer = SitemapPreviewWriter()
        result = SitemapPreviewResult(
            file_type=".bin", subject="Empty", total_token_count=0,
            conversion_confidence=10,
        )
        output = writer.format(result, fmt="text")
        assert "no sections detected" in output
        assert "no images or tables detected" in output
        assert "N/A" in output  # total_page_count is None

    def test_format_invalid_raises(self):
        writer = SitemapPreviewWriter()
        result = self._sample_result()
        with pytest.raises(ValueError, match="Unsupported format"):
            writer.format(result, fmt="xml")

    def test_write_to_file(self, tmp_path):
        writer = SitemapPreviewWriter()
        result = self._sample_result()
        out_file = str(tmp_path / "preview.json")
        returned = writer.write(result, out_file, fmt="json")
        assert os.path.exists(out_file)
        with open(out_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert json.loads(content) == json.loads(returned)

    def test_write_to_text_file(self, tmp_path):
        writer = SitemapPreviewWriter()
        result = self._sample_result()
        out_file = str(tmp_path / "preview.txt")
        returned = writer.write(result, out_file, fmt="text")
        assert os.path.exists(out_file)
        with open(out_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == returned
        assert "SITEMAP PREVIEW" in content

    def test_write_to_stream(self):
        writer = SitemapPreviewWriter()
        result = self._sample_result()
        buf = io.StringIO()
        returned = writer.write(result, buf, fmt="json")
        buf.seek(0)
        assert buf.read() == returned

    def test_write_to_stdout(self, capsys):
        writer = SitemapPreviewWriter()
        result = self._sample_result()
        returned = writer.write(result, None, fmt="json")
        captured = capsys.readouterr()
        assert returned in captured.out

    def test_write_invalid_destination_raises(self):
        writer = SitemapPreviewWriter()
        result = self._sample_result()
        with pytest.raises(TypeError, match="Invalid destination"):
            writer.write(result, 12345)


class TestWriteSitemapPreviewMethod:
    """Tests for MarkItDown.write_sitemap_preview() convenience method."""

    def test_write_json_to_file(self, tmp_path):
        path = os.path.join(TEST_FILES_DIR, "test.docx")
        if not os.path.exists(path):
            pytest.skip("test.docx not available")
        md = MarkItDown()
        out_file = str(tmp_path / "preview.json")
        returned = md.write_sitemap_preview(path, out_file)
        assert os.path.exists(out_file)
        with open(out_file, "r", encoding="utf-8") as f:
            parsed = json.loads(f.read())
        assert parsed["file_type"] == ".docx"
        assert "subject" in parsed
        assert "total_token_count" in parsed
        assert "total_page_count" in parsed
        assert parsed["total_page_count"] is not None
        assert "conversion_confidence" in parsed
        assert "sections" in parsed
        assert "media" in parsed
        assert json.loads(returned) == parsed

    def test_write_text_to_file(self, tmp_path):
        path = os.path.join(TEST_FILES_DIR, "test.pptx")
        if not os.path.exists(path):
            pytest.skip("test.pptx not available")
        md = MarkItDown()
        out_file = str(tmp_path / "preview.txt")
        returned = md.write_sitemap_preview(path, out_file, fmt="text")
        assert os.path.exists(out_file)
        with open(out_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert "SITEMAP PREVIEW" in content
        assert ".pptx" in content
        assert content == returned

    def test_write_to_stdout(self, capsys):
        path = os.path.join(TEST_FILES_DIR, "test.pdf")
        if not os.path.exists(path):
            pytest.skip("test.pdf not available")
        md = MarkItDown()
        md.write_sitemap_preview(path)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["file_type"] == ".pdf"

    def test_write_from_stream(self, tmp_path):
        html = "<html><body><h1>Stream Test</h1><p>Content here.</p></body></html>"
        md = MarkItDown()
        out_file = str(tmp_path / "stream_preview.json")
        stream = io.BytesIO(html.encode("utf-8"))
        md.write_sitemap_preview(
            stream, out_file,
            stream_info=StreamInfo(extension=".html", charset="utf-8"),
        )
        assert os.path.exists(out_file)
        with open(out_file, "r", encoding="utf-8") as f:
            parsed = json.loads(f.read())
        assert parsed["file_type"] == ".html"


class TestCLISitemap:
    def test_sitemap_flag_produces_json(self):
        """markitdown --sitemap <file> should produce valid JSON."""
        import subprocess
        import sys

        test_file = os.path.join(TEST_FILES_DIR, "test.pdf")
        if not os.path.exists(test_file):
            pytest.skip("test.pdf not available")
        result = subprocess.run(
            [sys.executable, "-m", "markitdown", "--sitemap", test_file],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        parsed = json.loads(result.stdout)
        assert "file_type" in parsed
        assert "subject" in parsed
        assert "total_token_count" in parsed
        assert "total_page_count" in parsed
        assert parsed["total_page_count"] is not None
        assert "conversion_confidence" in parsed
        assert "sections" in parsed
        assert "media" in parsed

    def test_sitemap_flag_requires_filename(self):
        """markitdown --sitemap without a filename should error."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "markitdown", "--sitemap"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

    def test_sitemap_output_to_file(self, tmp_path):
        """markitdown --sitemap <file> -o <output> writes to a file."""
        import subprocess
        import sys

        test_file = os.path.join(TEST_FILES_DIR, "test.pdf")
        if not os.path.exists(test_file):
            pytest.skip("test.pdf not available")
        out_file = str(tmp_path / "preview_output.json")
        result = subprocess.run(
            [sys.executable, "-m", "markitdown", "--sitemap", test_file, "-o", out_file],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert os.path.exists(out_file)
        with open(out_file, "r", encoding="utf-8") as f:
            parsed = json.loads(f.read())
        assert "file_type" in parsed
        assert "sections" in parsed

    def test_sitemap_text_format(self):
        """markitdown --sitemap --sitemap-format text produces human-readable output."""
        import subprocess
        import sys

        test_file = os.path.join(TEST_FILES_DIR, "test.docx")
        if not os.path.exists(test_file):
            pytest.skip("test.docx not available")
        result = subprocess.run(
            [sys.executable, "-m", "markitdown", "--sitemap", "--sitemap-format", "text", test_file],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "SITEMAP PREVIEW" in result.stdout
        assert "TABLE OF CONTENTS" in result.stdout
        assert "IMAGES & TABLES" in result.stdout

    def test_sitemap_text_format_to_file(self, tmp_path):
        """markitdown --sitemap --sitemap-format text -o <output> writes text to a file."""
        import subprocess
        import sys

        test_file = os.path.join(TEST_FILES_DIR, "test.pptx")
        if not os.path.exists(test_file):
            pytest.skip("test.pptx not available")
        out_file = str(tmp_path / "preview.txt")
        result = subprocess.run(
            [sys.executable, "-m", "markitdown", "--sitemap", "--sitemap-format", "text", test_file, "-o", out_file],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert os.path.exists(out_file)
        with open(out_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert "SITEMAP PREVIEW" in content
        assert ".pptx" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
