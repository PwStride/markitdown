"""Mono-style formatting primitives for converter output.

Every converter that emits structured markdown imports from here.  The module
exposes pre-built ANSI escape strings and thin helper functions; no logic
lives inside the individual converters.

Colour palette
--------------
All colours below are *distinct* from the five used in ``_preview_style.py``
(violet #8A2BE2, slate #708090, emerald #2ECC71, amber #F39C12, rose #E74C3C).

==========  ===========  =============================================
Name        Hex          Role in converter output
==========  ===========  =============================================
Cobalt      #4169E1      H1 headings (top-level document / feed title)
Teal        #20B2AA      H2 headings (sections, sheet names, entries)
Coral       #FF6F61      H3 headings (sub-sections, notes, metadata)
Gold        #DAA520      Bullet / list-item markers
Ash         #A9A9A9      Metadata key labels (muted but readable)
==========  ===========  =============================================
"""


def _rgb(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"


_RESET = "\033[0m"

# Cobalt   #4169E1  rgb(65, 105, 225)
# Teal     #20B2AA  rgb(32, 178, 170)
# Coral    #FF6F61  rgb(255, 111, 97)
# Gold     #DAA520  rgb(218, 165, 32)
# Ash      #A9A9A9  rgb(169, 169, 169)

COBALT = _rgb(65, 105, 225)
TEAL = _rgb(32, 178, 170)
CORAL = _rgb(255, 111, 97)
GOLD = _rgb(218, 165, 32)
ASH = _rgb(169, 169, 169)
RESET = _RESET


# ---------------------------------------------------------------------------
# Heading helpers  –  return a coloured ATX heading with a trailing newline
# ---------------------------------------------------------------------------


def h1(text: str) -> str:
    """Coloured H1 heading (cobalt)."""
    return f"{COBALT}# {text}{RESET}\n"


def h2(text: str) -> str:
    """Coloured H2 heading (teal)."""
    return f"{TEAL}## {text}{RESET}\n"


def h3(text: str) -> str:
    """Coloured H3 heading (coral)."""
    return f"{CORAL}### {text}{RESET}\n"


# ---------------------------------------------------------------------------
# Bullet helper  –  gold diamond marker
# ---------------------------------------------------------------------------


def bullet(text: str) -> str:
    """A single bullet line with a gold diamond marker."""
    return f"{GOLD}\u25c6{RESET} {text}\n"


# ---------------------------------------------------------------------------
# Metadata-label helper
# ---------------------------------------------------------------------------


def meta(key: str, value: str) -> str:
    """A key/value metadata line.  Key is ash-coloured and bold."""
    return f"{ASH}**{key}:**{RESET} {value}\n"
