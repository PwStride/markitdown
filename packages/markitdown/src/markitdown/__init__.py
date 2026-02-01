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
from ._preview_style import STYLE_CLASSIC, STYLE_MONO, DEFAULT_STYLE, STYLES, resolve_style

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
    "STYLE_CLASSIC",
    "STYLE_MONO",
    "DEFAULT_STYLE",
    "STYLES",
    "resolve_style",
]
