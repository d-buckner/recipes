"""Ingredient parsing and scaling utilities.

Shared module used by the grocery list backend and any other server-side
ingredient processing.  The core fraction/scaling logic was originally in
openwebui/recipe_tool.py; this is now the canonical location.
"""

import re
from dataclasses import dataclass
from fractions import Fraction


# ---------------------------------------------------------------------------
# Unicode fraction tables
# ---------------------------------------------------------------------------

UNICODE_FRACTIONS: dict[str, Fraction] = {
    "½": Fraction(1, 2),
    "⅓": Fraction(1, 3),
    "⅔": Fraction(2, 3),
    "¼": Fraction(1, 4),
    "¾": Fraction(3, 4),
    "⅕": Fraction(1, 5),
    "⅖": Fraction(2, 5),
    "⅗": Fraction(3, 5),
    "⅘": Fraction(4, 5),
    "⅙": Fraction(1, 6),
    "⅚": Fraction(5, 6),
    "⅛": Fraction(1, 8),
    "⅜": Fraction(3, 8),
    "⅝": Fraction(5, 8),
    "⅞": Fraction(7, 8),
}

REVERSE_UNICODE: dict[Fraction, str] = {v: k for k, v in UNICODE_FRACTIONS.items()}


# ---------------------------------------------------------------------------
# Unit normalization
# ---------------------------------------------------------------------------

UNIT_ALIASES: dict[str, str] = {
    # tablespoon
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tbsp": "tbsp",
    "Tbsp": "tbsp",
    # teaspoon
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tsp": "tsp",
    # cup
    "cup": "cup",
    "cups": "cup",
    # ounce
    "ounce": "oz",
    "ounces": "oz",
    "oz": "oz",
    # pound
    "pound": "lb",
    "pounds": "lb",
    "lb": "lb",
    "lbs": "lb",
    # gram
    "gram": "g",
    "grams": "g",
    "g": "g",
    # kilogram
    "kilogram": "kg",
    "kilograms": "kg",
    "kg": "kg",
    # milliliter
    "milliliter": "ml",
    "milliliters": "ml",
    "ml": "ml",
    "mL": "ml",
    # liter
    "liter": "l",
    "liters": "l",
    # pint
    "pint": "pt",
    "pints": "pt",
    "pt": "pt",
    # quart
    "quart": "qt",
    "quarts": "qt",
    "qt": "qt",
    # gallon
    "gallon": "gal",
    "gallons": "gal",
    "gal": "gal",
}


# ---------------------------------------------------------------------------
# Trailing notes patterns (stripped from ingredient names)
# ---------------------------------------------------------------------------

_TRAILING_PAREN_NOTES_RE = re.compile(
    r"\s*\((divided|optional|for\s+serving|or\s+to\s+taste|to\s+taste|for\s+garnish|to\s+garnish)\)\s*$",
    re.IGNORECASE,
)

_TRAILING_NOTES_RE = re.compile(
    r"[,\s]*\b(divided|optional|for\s+serving|or\s+to\s+taste|to\s+taste|for\s+garnish|to\s+garnish)\b\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Core data type
# ---------------------------------------------------------------------------

@dataclass
class ParsedIngredient:
    qty: Fraction | None   # parsed quantity; None if no numeric quantity found
    unit: str | None       # normalized unit (e.g. "tbsp", "cup"); None if absent
    name: str              # ingredient name with trailing notes stripped
    raw: str               # original unmodified string


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def parse_qty_token(token: str) -> Fraction | None:
    """Parse a single token as a quantity.  Returns None if it is not numeric."""
    if token in UNICODE_FRACTIONS:
        return UNICODE_FRACTIONS[token]
    if "/" in token:
        parts = token.split("/")
        if len(parts) == 2:
            try:
                return Fraction(int(parts[0]), int(parts[1]))
            except (ValueError, ZeroDivisionError):
                pass
        return None
    try:
        return Fraction(token).limit_denominator(1000)
    except (ValueError, ZeroDivisionError):
        return None


def format_fraction(f: Fraction) -> str:
    """Format a Fraction as a human-readable string, preferring unicode glyphs."""
    whole = int(f)
    remainder = f - whole
    if remainder == 0:
        return str(whole)
    frac_str = REVERSE_UNICODE.get(remainder) or f"{remainder.numerator}/{remainder.denominator}"
    return frac_str if whole == 0 else f"{whole}{frac_str}"


def scale_ingredient(ingredient: str, factor: Fraction) -> str:
    """Return *ingredient* with its leading quantity multiplied by *factor*.

    Handles unicode fractions, mixed numbers (both "1 ½" and "1½" forms), and
    ASCII fractions ("1/2").  If no numeric quantity is found, returns the
    string unchanged.
    """
    # Insert space between a digit and a unicode fraction glyph: "1½" → "1 ½"
    normalized = ingredient
    for uf in UNICODE_FRACTIONS:
        normalized = re.sub(rf"(\d)({re.escape(uf)})", r"\1 \2", normalized)

    tokens = normalized.split()
    if not tokens:
        return ingredient

    qty: Fraction | None = None
    qty_tokens = 0

    # Try mixed number: whole integer + proper fraction ("1 ½", "1 1/2")
    if len(tokens) >= 2:
        first = parse_qty_token(tokens[0])
        second = parse_qty_token(tokens[1])
        if (
            first is not None
            and second is not None
            and first == int(first)
            and 0 < second < 1
        ):
            qty = first + second
            qty_tokens = 2

    if qty is None:
        first = parse_qty_token(tokens[0])
        if first is not None:
            qty = first
            qty_tokens = 1

    if qty is None:
        return ingredient

    scaled_str = format_fraction(qty * factor)
    rest = " ".join(tokens[qty_tokens:])
    return f"{scaled_str} {rest}".strip()


def parse_ingredient(raw: str) -> ParsedIngredient:
    """Parse a raw ingredient string into its components.

    Extracts quantity, normalized unit, and ingredient name (with trailing
    "meta-notes" like ", divided" or "(optional)" removed).  Returns the
    original string in ``raw`` regardless of whether parsing succeeded.
    """
    # Normalise unicode mixed numbers: "1½" → "1 ½"
    normalized = raw
    for uf in UNICODE_FRACTIONS:
        normalized = re.sub(rf"(\d)({re.escape(uf)})", r"\1 \2", normalized)

    tokens = normalized.split()
    if not tokens:
        return ParsedIngredient(qty=None, unit=None, name=raw, raw=raw)

    # --- parse quantity ---
    qty: Fraction | None = None
    qty_tokens = 0

    if len(tokens) >= 2:
        first = parse_qty_token(tokens[0])
        second = parse_qty_token(tokens[1])
        if (
            first is not None
            and second is not None
            and first == int(first)
            and 0 < second < 1
        ):
            qty = first + second
            qty_tokens = 2

    if qty is None:
        first = parse_qty_token(tokens[0])
        if first is not None:
            qty = first
            qty_tokens = 1

    if qty_tokens == 0:
        # No leading quantity — whole string is the name (notes stripped)
        return ParsedIngredient(qty=None, unit=None, name=_strip_notes(raw), raw=raw)

    # --- parse unit ---
    remaining = tokens[qty_tokens:]
    unit: str | None = None
    name_start = 0

    if remaining and remaining[0] in UNIT_ALIASES:
        unit = UNIT_ALIASES[remaining[0]]
        name_start = 1

    name_raw = " ".join(remaining[name_start:])
    name = _strip_notes(name_raw)

    return ParsedIngredient(qty=qty, unit=unit, name=name, raw=raw)


def normalize_name(name: str) -> str:
    """Return a normalized form of *name* suitable for ingredient matching.

    Lowercases, strips parenthetical content, replaces punctuation with spaces,
    and collapses whitespace.  Preserves hyphens.
    """
    name = name.lower()
    name = re.sub(r"\([^)]*\)", "", name)          # remove (parenthetical content)
    name = re.sub(r"[^\w\s-]", " ", name)          # punctuation → space, keep hyphen
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _strip_notes(text: str) -> str:
    """Remove trailing meta-notes like ', divided' or '(optional)' from a name."""
    text = _TRAILING_PAREN_NOTES_RE.sub("", text)
    text = _TRAILING_NOTES_RE.sub("", text)
    return text.strip(" ,")
