# SPDX-FileCopyrightText: 2024-present Adam Fourney <adamfo@microsoft.com>
#
# SPDX-License-Identifier: MIT

from .__about__ import __version__
from ._markitdown import (
    MarkItDown,
    PRIORITY_SPECIFIC_FILE_FORMAT,
    PRIORITY_GENERIC_FILE_FORMAT,
)
from ._base_converter import DocumentConverterResult, DocumentConverter
from ._stream_info import StreamInfo
from ._exceptions import (
    MarkItDownException,
    MissingDependencyException,
    FailedConversionAttempt,
    FileConversionException,
    UnsupportedFormatException,
)
from ._sitemap_preview import SitemapPreviewResult, SectionPreview, MediaItem
from ._sitemap_preview_converter import SitemapPreviewConverter
from ._sitemap_preview_writer import SitemapPreviewWriter
from ._docx_tree_mapper import DocumentMap, TreeNode, TreeMediaItem
from ._docx_tree_mapper_converter import DocxTreeMapConverter
from ._docx_tree_mapper_writer import DocxTreeMapWriter
from ._preview_style import STYLE_CLASSIC, STYLE_MONO, STYLE_TREE, DEFAULT_STYLE, DEFAULT_MAP_STYLE, STYLES, resolve_style
from ._dir_preview import DirectoryPreviewResult, FilePreviewEntry, DirectoryPreviewScanner, DirectoryPreviewWriter, CONVERTIBLE_EXTENSIONS
from ._search import SearchResult, DocumentSearcher, SearchResultWriter

__all__ = [
    "__version__",
    "MarkItDown",
    "DocumentConverter",
    "DocumentConverterResult",
    "MarkItDownException",
    "MissingDependencyException",
    "FailedConversionAttempt",
    "FileConversionException",
    "UnsupportedFormatException",
    "StreamInfo",
    "PRIORITY_SPECIFIC_FILE_FORMAT",
    "PRIORITY_GENERIC_FILE_FORMAT",
    "SitemapPreviewResult",
    "SectionPreview",
    "MediaItem",
    "SitemapPreviewConverter",
    "SitemapPreviewWriter",
    "DocumentMap",
    "TreeNode",
    "TreeMediaItem",
    "DocxTreeMapConverter",
    "DocxTreeMapWriter",
    "STYLE_CLASSIC",
    "STYLE_MONO",
    "STYLE_TREE",
    "DEFAULT_STYLE",
    "DEFAULT_MAP_STYLE",
    "STYLES",
    "resolve_style",
    "DirectoryPreviewResult",
    "FilePreviewEntry",
    "DirectoryPreviewScanner",
    "CONVERTIBLE_EXTENSIONS",
    "DirectoryPreviewWriter",
    "SearchResult",
    "DocumentSearcher",
    "SearchResultWriter",
]
