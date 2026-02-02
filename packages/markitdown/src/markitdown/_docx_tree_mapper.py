"""Hierarchical document-map data model.

Represents the structure of a Word document (or any supported format) as a
tree of ``TreeNode`` objects.  Each node corresponds to a heading-delimited
section and carries:

* **title** -- the heading text (or a synthetic label for the root)
* **level** -- the heading depth (0 for root, 1 for H1, 2 for H2, ...)
* **summary** -- a one-sentence digest of the body text beneath the heading
* **children** -- ordered list of sub-section nodes
* **media** -- images / tables discovered inside the section body
* **page** -- optional page or slide number

The top-level container is ``DocumentMap``, which wraps the root node together
with file-level metadata (type, token count, confidence score).

Serialisation
-------------
Both ``TreeNode`` and ``DocumentMap`` expose ``to_dict()`` and ``to_json()``
for JSON-friendly output.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import json


@dataclass
class TreeMediaItem:
    """An image or table discovered inside a section."""
    type: str           # "image" or "table"
    description: str
    page: Optional[int] = None


@dataclass
class TreeNode:
    """A single node in the document hierarchy.

    Leaf nodes have an empty ``children`` list.  The root node uses
    ``level=0`` and its *title* is the document subject.
    """
    title: str
    level: int
    summary: str
    page: Optional[int] = None
    children: List["TreeNode"] = field(default_factory=list)
    media: List[TreeMediaItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "level": self.level,
            "summary": self.summary,
            "page": self.page,
            "media": [
                {"type": m.type, "description": m.description, "page": m.page}
                for m in self.media
            ],
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class DocumentMap:
    """Top-level container for the hierarchical document map."""
    file_type: str
    subject: str
    total_token_count: int
    conversion_confidence: int
    total_page_count: Optional[int] = None
    root: TreeNode = field(default_factory=lambda: TreeNode(
        title="(root)", level=0, summary=""
    ))

    def to_dict(self) -> dict:
        return {
            "file_type": self.file_type,
            "subject": self.subject,
            "total_token_count": self.total_token_count,
            "total_page_count": self.total_page_count,
            "conversion_confidence": self.conversion_confidence,
            "root": self.root.to_dict(),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
