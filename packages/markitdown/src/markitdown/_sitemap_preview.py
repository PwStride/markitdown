from dataclasses import dataclass, field
from typing import List, Optional
import json


@dataclass
class MediaItem:
    """A single image or table found inside the document."""
    type: str
    page: Optional[int]
    description: str


@dataclass
class SectionPreview:
    """A single section (heading) discovered in the document."""
    title: str
    page: Optional[int]
    summary: str


@dataclass
class SitemapPreviewResult:
    """Top-level JSON-serialisable sitemap preview for a document."""
    file_type: str
    subject: str
    total_token_count: int
    conversion_confidence: int
    total_page_count: Optional[int] = None
    sections: List[SectionPreview] = field(default_factory=list)
    media: List[MediaItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file_type": self.file_type,
            "subject": self.subject,
            "total_token_count": self.total_token_count,
            "total_page_count": self.total_page_count,
            "conversion_confidence": self.conversion_confidence,
            "sections": [{"title": s.title, "page": s.page, "summary": s.summary} for s in self.sections],
            "media": [{"type": m.type, "page": m.page, "description": m.description} for m in self.media],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
