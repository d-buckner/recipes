"""Tests for openwebui/recipe_tool.py — fraction parsing and scaling helpers."""

from fractions import Fraction
from unittest.mock import MagicMock, patch

import pytest

from openwebui.recipe_tool import (
    Tools,
    _format_fraction,
    _parse_qty_token,
    _scale_ingredient,
)


# ---------------------------------------------------------------------------
# _parse_qty_token
# ---------------------------------------------------------------------------


class TestParseQtyToken:
    def test_integer(self):
        assert _parse_qty_token("3") == Fraction(3)

    def test_large_integer(self):
        assert _parse_qty_token("15") == Fraction(15)

    def test_decimal(self):
        assert _parse_qty_token("1.5") == Fraction(3, 2)

    def test_ascii_fraction(self):
        assert _parse_qty_token("1/2") == Fraction(1, 2)
        assert _parse_qty_token("3/4") == Fraction(3, 4)
        assert _parse_qty_token("1/3") == Fraction(1, 3)

    @pytest.mark.parametrize(
        "char, expected",
        [
            ("½", Fraction(1, 2)),
            ("⅓", Fraction(1, 3)),
            ("⅔", Fraction(2, 3)),
            ("¼", Fraction(1, 4)),
            ("¾", Fraction(3, 4)),
            ("⅛", Fraction(1, 8)),
            ("⅜", Fraction(3, 8)),
            ("⅝", Fraction(5, 8)),
            ("⅞", Fraction(7, 8)),
        ],
    )
    def test_unicode_fractions(self, char, expected):
        assert _parse_qty_token(char) == expected

    def test_word_returns_none(self):
        assert _parse_qty_token("cups") is None
        assert _parse_qty_token("tsp") is None
        assert _parse_qty_token("black") is None

    def test_empty_string_returns_none(self):
        assert _parse_qty_token("") is None

    def test_division_by_zero_returns_none(self):
        assert _parse_qty_token("1/0") is None

    def test_malformed_fraction_returns_none(self):
        assert _parse_qty_token("1/2/3") is None


# ---------------------------------------------------------------------------
# _format_fraction
# ---------------------------------------------------------------------------


class TestFormatFraction:
    def test_whole_numbers(self):
        assert _format_fraction(Fraction(1)) == "1"
        assert _format_fraction(Fraction(6)) == "6"
        assert _format_fraction(Fraction(24)) == "24"

    @pytest.mark.parametrize(
        "frac, expected",
        [
            (Fraction(1, 2), "½"),
            (Fraction(1, 4), "¼"),
            (Fraction(3, 4), "¾"),
            (Fraction(1, 3), "⅓"),
            (Fraction(2, 3), "⅔"),
            (Fraction(1, 8), "⅛"),
            (Fraction(3, 8), "⅜"),
        ],
    )
    def test_common_fractions_use_unicode(self, frac, expected):
        assert _format_fraction(frac) == expected

    def test_mixed_number(self):
        assert _format_fraction(Fraction(3, 2)) == "1½"
        assert _format_fraction(Fraction(5, 4)) == "1¼"
        assert _format_fraction(Fraction(7, 4)) == "1¾"
        assert _format_fraction(Fraction(9, 4)) == "2¼"

    def test_uncommon_fraction_falls_back_to_ascii(self):
        # 1/7 has no unicode glyph
        assert _format_fraction(Fraction(1, 7)) == "1/7"
        assert _format_fraction(Fraction(5, 7)) == "5/7"

    def test_uncommon_mixed_number_falls_back_to_ascii(self):
        # 1 + 1/7 has no unicode glyph for the fractional part
        assert _format_fraction(Fraction(8, 7)) == "11/7"


# ---------------------------------------------------------------------------
# _scale_ingredient
# ---------------------------------------------------------------------------


class TestScaleIngredient:
    # --- basic integer quantities ---

    def test_integer_quantity(self):
        assert _scale_ingredient("6 radishes (thinly sliced)", Fraction(4)) == "24 radishes (thinly sliced)"

    def test_integer_quantity_half(self):
        assert _scale_ingredient("6 cups flour", Fraction(1, 2)) == "3 cups flour"

    # --- unicode fractions ---

    def test_standalone_unicode_fraction(self):
        assert _scale_ingredient("¼ cup Lemon Garlic Dressing", Fraction(4)) == "1 cup Lemon Garlic Dressing"

    def test_standalone_unicode_fraction_half(self):
        assert _scale_ingredient("½ tsp salt", Fraction(4)) == "2 tsp salt"

    def test_unicode_fraction_times_three(self):
        assert _scale_ingredient("⅓ cup sugar", Fraction(3)) == "1 cup sugar"

    # --- unicode mixed numbers (digit immediately followed by glyph) ---

    def test_unicode_mixed_number(self):
        assert _scale_ingredient("1½ cups pearl couscous", Fraction(4)) == "6 cups pearl couscous"

    def test_unicode_mixed_number_with_parens(self):
        assert _scale_ingredient("1½ cups broth (low sodium)", Fraction(2)) == "3 cups broth (low sodium)"

    # --- ASCII mixed numbers ---

    def test_ascii_mixed_number_space_separated(self):
        assert _scale_ingredient("1 ½ cups milk", Fraction(4)) == "6 cups milk"

    def test_ascii_mixed_number_slash(self):
        assert _scale_ingredient("1 1/2 cups broth", Fraction(3)) == "4½ cups broth"

    def test_ascii_fraction_alone(self):
        assert _scale_ingredient("1/2 cup cream", Fraction(2)) == "1 cup cream"

    # --- scaling produces a fraction ---

    def test_scale_down_to_fraction(self):
        assert _scale_ingredient("1 cup flour", Fraction(1, 2)) == "½ cup flour"

    def test_scale_produces_mixed_number(self):
        assert _scale_ingredient("3 tbsp avocado oil", Fraction(4)) == "12 tbsp avocado oil"

    # --- no quantity: pass through unchanged ---

    def test_no_quantity_passes_through(self):
        assert _scale_ingredient("black pepper (to taste)", Fraction(4)) == "black pepper (to taste)"

    def test_word_only_ingredient_passes_through(self):
        assert _scale_ingredient("salt to taste", Fraction(4)) == "salt to taste"

    # --- decimal quantities ---

    def test_decimal_quantity(self):
        assert _scale_ingredient("1.5 cups oats", Fraction(2)) == "3 cups oats"

    # --- scale factor of 1 is a no-op ---

    def test_scale_by_one_unchanged(self):
        ingredient = "2 cups rice"
        assert _scale_ingredient(ingredient, Fraction(1)) == ingredient

    # --- multi-word rest is fully preserved ---

    def test_multi_word_description_preserved(self):
        result = _scale_ingredient("15 oz white beans (canned, drained and rinsed)", Fraction(4))
        assert result == "60 oz white beans (canned, drained and rinsed)"

    def test_single_word_no_unit(self):
        assert _scale_ingredient("4 eggs", Fraction(3)) == "12 eggs"


# ---------------------------------------------------------------------------
# Tools.scale_recipe (integration — mocked HTTP)
# ---------------------------------------------------------------------------


def _make_mock_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    if json_data is not None:
        mock.json.return_value = json_data
    if status_code >= 400:
        mock.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    else:
        mock.raise_for_status.return_value = None
    return mock


_SAMPLE_RECIPE_JSON = {
    "title": "Kale White Bean Salad",
    "yields": "4 servings",
    "ingredients": [
        "1½ cups pearl couscous",
        "¼ cup lemon dressing",
        "½ tsp salt",
        "black pepper (to taste)",
    ],
}


class TestScaleRecipeTool:
    def setup_method(self):
        self.tools = Tools()

    @patch("openwebui.recipe_tool.requests.get")
    def test_happy_path_4x(self, mock_get):
        mock_get.return_value = _make_mock_response(
            200,
            {"recipe_json": _SAMPLE_RECIPE_JSON, "url": "https://example.com/salad", "status": "complete"},
        )
        result = self.tools.scale_recipe(1, 4)

        assert "Kale White Bean Salad × 4" in result
        assert "6 cups pearl couscous" in result
        assert "1 cup lemon dressing" in result
        assert "2 tsp salt" in result
        assert "black pepper (to taste)" in result

    @patch("openwebui.recipe_tool.requests.get")
    def test_yields_line_included(self, mock_get):
        mock_get.return_value = _make_mock_response(
            200,
            {"recipe_json": _SAMPLE_RECIPE_JSON, "url": "https://example.com/salad", "status": "complete"},
        )
        result = self.tools.scale_recipe(1, 2)
        assert "4 servings" in result

    @patch("openwebui.recipe_tool.requests.get")
    def test_recipe_not_found(self, mock_get):
        mock_get.return_value = _make_mock_response(404)
        result = self.tools.scale_recipe(999, 4)
        assert "not found" in result.lower()

    @patch("openwebui.recipe_tool.requests.get")
    def test_recipe_not_scraped(self, mock_get):
        mock_get.return_value = _make_mock_response(
            200, {"recipe_json": None, "status": "discovered"}
        )
        result = self.tools.scale_recipe(1, 4)
        assert "not been scraped" in result.lower()

    @patch("openwebui.recipe_tool.requests.get")
    def test_connection_error(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.exceptions.ConnectionError()
        result = self.tools.scale_recipe(1, 4)
        assert "could not connect" in result.lower()

    @patch("openwebui.recipe_tool.requests.get")
    def test_scale_factor_half(self, mock_get):
        mock_get.return_value = _make_mock_response(
            200,
            {"recipe_json": _SAMPLE_RECIPE_JSON, "url": "https://example.com/salad", "status": "complete"},
        )
        result = self.tools.scale_recipe(1, 0.5)
        assert "× 1/2" in result
        assert "¾ cups pearl couscous" in result

    @patch("openwebui.recipe_tool.requests.get")
    def test_does_not_expose_recipe_id(self, mock_get):
        mock_get.return_value = _make_mock_response(
            200,
            {"recipe_json": _SAMPLE_RECIPE_JSON, "url": "https://example.com/salad", "status": "complete"},
        )
        result = self.tools.scale_recipe(523, 4)
        # The numeric ID must not appear in the output shown to the user
        assert "523" not in result
