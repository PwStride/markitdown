"""Preview-style registry for sitemap and document-map text output.

Three built-in styles are shipped.  The active style is selected at render
time via the ``preview_style`` parameter that flows through
``write_sitemap_preview`` / ``SitemapPreviewWriter.format`` and
``write_document_map`` / ``DocxTreeMapWriter.format``.

Built-in styles
---------------
``"classic"`` (default for sitemap)
    The original plain-ASCII layout that ships with MarkItDown.  No colour,
    ``=`` / ``-`` rule lines, indented labels.

``"mono"``
    A modern, minimalist layout built on three design principles:

    * **Clean lines** -- rules are thin single-character lines; sections
      breathe with generous vertical spacing.
    * **Bold accent colour** -- a single vibrant accent (deep violet
      ``\\033[38;2;138;43;226m``) pulls the eye to headings and key labels.
      All other text remains the terminal's default colour.
    * **Tight information hierarchy** -- metadata is rendered in a compact
      two-column block at the top; the table of contents uses flush-left
      numbering with an indented annotation line beneath each entry.

    Accent colours used (none of these appear anywhere else in the
    codebase):

    ========  ===========  =================================================
    Name      Hex          Purpose
    ========  ===========  =================================================
    violet    ``#8A2BE2``  Section numbers, panel headers, field labels
    slate     ``#708090``  Muted annotation / summary text
    emerald   ``#2ECC71``  Confidence-score badge when score >= 70
    amber     ``#F39C12``  Confidence-score badge when 40 <= score < 70
    rose      ``#E74C3C``  Confidence-score badge when score < 40
    ========  ===========  =================================================

``"tree"`` (default for document maps)
    A layout optimised for the hierarchical document-map view.  Uses an
    indigo accent (``#5B5FC7``) that is visually distinct from the violet
    used by "mono", making it easy to tell sitemap previews and document
    maps apart at a glance.

    ========  ===========  =================================================
    Name      Hex          Purpose
    ========  ===========  =================================================
    indigo    ``#5B5FC7``  Tree connectors, panel headers, field labels
    slate     ``#708090``  Muted summaries and media annotations
    emerald   ``#2ECC71``  Confidence-score badge when score >= 70
    amber     ``#F39C12``  Confidence-score badge when 40 <= score < 70
    rose      ``#E74C3C``  Confidence-score badge when score < 40
    ========  ===========  =================================================

Style objects
-------------
Each style is a plain ``dict`` consumed only by ``SitemapPreviewWriter``.
Keys are intentionally terse; their meaning is documented in the table
below.

============================  ===============================================
Key                           Meaning
============================  ===============================================
``accent``                    ANSI escape prefix for the accent colour.
``mute``                      ANSI escape prefix for muted / secondary text.
``badge_hi``                  ANSI escape for high-confidence badge.
``badge_mid``                 ANSI escape for mid-confidence badge.
``badge_lo``                  ANSI escape for low-confidence badge.
``reset``                     ANSI reset sequence (``\\033[0m``).
``rule_top`` / ``rule_mid``   Characters repeated to form top / mid rules.
``rule_width``                Integer width of rules in columns.
``header_label``              Label string shown in the top panel
                              (e.g. ``"SITEMAP PREVIEW"``).
``toc_label``                 Label for the table-of-contents panel.
``media_label``               Label for the images-and-tables panel.
============================  ===============================================

Adding a custom style
---------------------
Register a new style by inserting a ``dict`` into ``STYLES``::

    from markitdown._preview_style import STYLES

    STYLES["my_style"] = {
        "accent":       "",   # no colour
        "mute":         "",
        "badge_hi":     "",
        "badge_mid":    "",
        "badge_lo":     "",
        "reset":        "",
        "rule_top":     "=",
        "rule_mid":     "-",
        "rule_width":   60,
        "header_label": "MY PREVIEW",
        "toc_label":    "TABLE OF CONTENTS",
        "media_label":  "IMAGES & TABLES",
    }

Then pass ``preview_style="my_style"`` to any write / format call.
"""

# ---------------------------------------------------------------------------
# ANSI colour helpers  (kept private; only the assembled escape strings are
# stored in the style dicts)
# ---------------------------------------------------------------------------


def _rgb(r: int, g: int, b: int) -> str:  # 24-bit foreground
    return f"\033[38;2;{r};{g};{b}m"


_RESET = "\033[0m"

# ---------------------------------------------------------------------------
# Colour palette for "mono"  (none used elsewhere in the project)
# ---------------------------------------------------------------------------
# Violet   #8A2BE2  ->  rgb(138, 43, 226)
# Slate    #708090  ->  rgb(112, 128, 144)
# Emerald  #2ECC71  ->  rgb(46, 204, 113)
# Amber    #F39C12  ->  rgb(243, 156, 18)
# Rose     #E74C3C  ->  rgb(231, 76, 60)
# ---------------------------------------------------------------------------

_VIOLET = _rgb(138, 43, 226)
_SLATE = _rgb(112, 128, 144)
_EMERALD = _rgb(46, 204, 113)
_AMBER = _rgb(243, 156, 18)
_ROSE = _rgb(231, 76, 60)

# ---------------------------------------------------------------------------
# Colour palette for "tree"  (distinct from "mono")
# ---------------------------------------------------------------------------
# Indigo   #5B5FC7  ->  rgb(91, 95, 199)
# ---------------------------------------------------------------------------

_INDIGO = _rgb(91, 95, 199)

# ---------------------------------------------------------------------------
# Style definitions
# ---------------------------------------------------------------------------

STYLE_CLASSIC = "classic"
STYLE_MONO = "mono"
STYLE_TREE = "tree"
DEFAULT_STYLE = STYLE_MONO  # mono is the active default; pass "classic" to revert
DEFAULT_MAP_STYLE = STYLE_TREE  # tree is the default for document maps

STYLES: dict = {
    # ------------------------------------------------------------------
    # classic  -- original plain-ASCII layout, no colour
    # ------------------------------------------------------------------
    STYLE_CLASSIC: {
        "accent": "",
        "mute": "",
        "badge_hi": "",
        "badge_mid": "",
        "badge_lo": "",
        "reset": "",
        "rule_top": "=",
        "rule_mid": "-",
        "rule_width": 60,
        "header_label": "SITEMAP PREVIEW",
        "toc_label": "TABLE OF CONTENTS",
        "media_label": "IMAGES & TABLES",
    },
    # ------------------------------------------------------------------
    # mono  -- minimalist, bold violet accent
    # ------------------------------------------------------------------
    STYLE_MONO: {
        "accent": _VIOLET,
        "mute": _SLATE,
        "badge_hi": _EMERALD,
        "badge_mid": _AMBER,
        "badge_lo": _ROSE,
        "reset": _RESET,
        "rule_top": "\u2500",  # ─  box-drawing horizontal
        "rule_mid": "\u2500",  # ─  same thin line for consistency
        "rule_width": 64,
        "header_label": "SITEMAP PREVIEW",
        "toc_label": "TABLE OF CONTENTS",
        "media_label": "IMAGES & TABLES",
    },
    # ------------------------------------------------------------------
    # tree  -- indigo accent, optimised for hierarchical document maps
    # ------------------------------------------------------------------
    STYLE_TREE: {
        "accent": _INDIGO,
        "mute": _SLATE,
        "badge_hi": _EMERALD,
        "badge_mid": _AMBER,
        "badge_lo": _ROSE,
        "reset": _RESET,
        "rule_top": "\u2500",  # ─  box-drawing horizontal
        "rule_mid": "\u2500",  # ─  thin line
        "rule_width": 64,
        "header_label": "DOCUMENT MAP",
        "toc_label": "CONTENT TREE",
        "media_label": "IMAGES & TABLES",
    },
}

# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------


def resolve_style(name: str) -> dict:
    """Return the style dict for *name*, raising ``ValueError`` on unknown."""
    try:
        return STYLES[name]
    except KeyError:
        available = ", ".join(repr(k) for k in STYLES)
        raise ValueError(
            f"Unknown preview style: {name!r}. Available styles: {available}"
        )
