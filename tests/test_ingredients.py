"""Tests for src/recipes/ingredients.py — ingredient parsing and scaling."""

from fractions import Fraction

import pytest

from recipes.ingredients import (
    format_fraction,
    normalize_name,
    parse_ingredient,
    parse_qty_token,
    scale_ingredient,
)


# ---------------------------------------------------------------------------
# parse_qty_token
# ---------------------------------------------------------------------------


class TestParseQtyToken:
    def test_integer(self):
        assert parse_qty_token("3") == Fraction(3)

    def test_large_integer(self):
        assert parse_qty_token("15") == Fraction(15)

    def test_decimal(self):
        assert parse_qty_token("1.5") == Fraction(3, 2)

    def test_ascii_fraction(self):
        assert parse_qty_token("1/2") == Fraction(1, 2)
        assert parse_qty_token("3/4") == Fraction(3, 4)
        assert parse_qty_token("1/3") == Fraction(1, 3)

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
        assert parse_qty_token(char) == expected

    def test_word_returns_none(self):
        assert parse_qty_token("cups") is None
        assert parse_qty_token("tsp") is None
        assert parse_qty_token("black") is None

    def test_empty_string_returns_none(self):
        assert parse_qty_token("") is None

    def test_division_by_zero_returns_none(self):
        assert parse_qty_token("1/0") is None

    def test_malformed_fraction_returns_none(self):
        assert parse_qty_token("1/2/3") is None


# ---------------------------------------------------------------------------
# format_fraction
# ---------------------------------------------------------------------------


class TestFormatFraction:
    def test_whole_numbers(self):
        assert format_fraction(Fraction(1)) == "1"
        assert format_fraction(Fraction(6)) == "6"
        assert format_fraction(Fraction(24)) == "24"

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
        assert format_fraction(frac) == expected

    def test_mixed_number(self):
        assert format_fraction(Fraction(3, 2)) == "1½"
        assert format_fraction(Fraction(5, 4)) == "1¼"
        assert format_fraction(Fraction(7, 4)) == "1¾"
        assert format_fraction(Fraction(9, 4)) == "2¼"

    def test_uncommon_fraction_falls_back_to_ascii(self):
        assert format_fraction(Fraction(1, 7)) == "1/7"
        assert format_fraction(Fraction(5, 7)) == "5/7"

    def test_uncommon_mixed_number_falls_back_to_ascii(self):
        assert format_fraction(Fraction(8, 7)) == "11/7"


# ---------------------------------------------------------------------------
# scale_ingredient
# ---------------------------------------------------------------------------


class TestScaleIngredient:
    def test_integer_quantity(self):
        assert scale_ingredient("6 radishes (thinly sliced)", Fraction(4)) == "24 radishes (thinly sliced)"

    def test_integer_quantity_half(self):
        assert scale_ingredient("6 cups flour", Fraction(1, 2)) == "3 cups flour"

    def test_standalone_unicode_fraction(self):
        assert scale_ingredient("¼ cup Lemon Garlic Dressing", Fraction(4)) == "1 cup Lemon Garlic Dressing"

    def test_standalone_unicode_fraction_half(self):
        assert scale_ingredient("½ tsp salt", Fraction(4)) == "2 tsp salt"

    def test_unicode_fraction_times_three(self):
        assert scale_ingredient("⅓ cup sugar", Fraction(3)) == "1 cup sugar"

    def test_unicode_mixed_number(self):
        assert scale_ingredient("1½ cups pearl couscous", Fraction(4)) == "6 cups pearl couscous"

    def test_unicode_mixed_number_with_parens(self):
        assert scale_ingredient("1½ cups broth (low sodium)", Fraction(2)) == "3 cups broth (low sodium)"

    def test_ascii_mixed_number_space_separated(self):
        assert scale_ingredient("1 ½ cups milk", Fraction(4)) == "6 cups milk"

    def test_ascii_mixed_number_slash(self):
        assert scale_ingredient("1 1/2 cups broth", Fraction(3)) == "4½ cups broth"

    def test_ascii_fraction_alone(self):
        assert scale_ingredient("1/2 cup cream", Fraction(2)) == "1 cup cream"

    def test_scale_down_to_fraction(self):
        assert scale_ingredient("1 cup flour", Fraction(1, 2)) == "½ cup flour"

    def test_scale_produces_large_integer(self):
        assert scale_ingredient("3 tbsp avocado oil", Fraction(4)) == "12 tbsp avocado oil"

    def test_no_quantity_passes_through(self):
        assert scale_ingredient("black pepper (to taste)", Fraction(4)) == "black pepper (to taste)"

    def test_word_only_ingredient_passes_through(self):
        assert scale_ingredient("salt to taste", Fraction(4)) == "salt to taste"

    def test_decimal_quantity(self):
        assert scale_ingredient("1.5 cups oats", Fraction(2)) == "3 cups oats"

    def test_scale_by_one_unchanged(self):
        ingredient = "2 cups rice"
        assert scale_ingredient(ingredient, Fraction(1)) == ingredient

    def test_multi_word_description_preserved(self):
        result = scale_ingredient("15 oz white beans (canned, drained and rinsed)", Fraction(4))
        assert result == "60 oz white beans (canned, drained and rinsed)"

    def test_single_word_no_unit(self):
        assert scale_ingredient("4 eggs", Fraction(3)) == "12 eggs"


# ---------------------------------------------------------------------------
# parse_ingredient
# ---------------------------------------------------------------------------


class TestParseIngredient:
    # --- qty + unit + name ---

    def test_basic_qty_unit_name(self):
        p = parse_ingredient("2 cups flour")
        assert p.qty == Fraction(2)
        assert p.unit == "cup"
        assert p.name == "flour"

    def test_raw_preserved(self):
        raw = "2 cups flour"
        assert parse_ingredient(raw).raw == raw

    # --- unit normalization ---

    def test_tablespoon_normalized(self):
        assert parse_ingredient("1 tablespoon olive oil").unit == "tbsp"

    def test_tablespoons_normalized(self):
        assert parse_ingredient("2 tablespoons oil").unit == "tbsp"

    def test_tbsp_normalized(self):
        assert parse_ingredient("2 tbsp butter").unit == "tbsp"

    def test_teaspoon_normalized(self):
        assert parse_ingredient("½ teaspoon salt").unit == "tsp"

    def test_teaspoons_normalized(self):
        assert parse_ingredient("2 teaspoons vanilla").unit == "tsp"

    def test_cups_normalized(self):
        assert parse_ingredient("3 cups water").unit == "cup"

    def test_ounce_normalized(self):
        assert parse_ingredient("15 ounces chickpeas").unit == "oz"

    def test_ounces_normalized(self):
        assert parse_ingredient("2 ounces cheese").unit == "oz"

    def test_oz_normalized(self):
        assert parse_ingredient("15 oz white beans").unit == "oz"

    def test_pound_normalized(self):
        assert parse_ingredient("1 pound chicken").unit == "lb"

    def test_pounds_normalized(self):
        assert parse_ingredient("2 pounds beef").unit == "lb"

    def test_lbs_normalized(self):
        assert parse_ingredient("2 lbs ground beef").unit == "lb"

    def test_grams_normalized(self):
        assert parse_ingredient("200 grams pasta").unit == "g"

    def test_kg_preserved(self):
        assert parse_ingredient("1 kg potatoes").unit == "kg"

    def test_ml_preserved(self):
        assert parse_ingredient("250 ml milk").unit == "ml"

    def test_liter_normalized(self):
        assert parse_ingredient("1 liter water").unit == "l"

    # --- no unit ---

    def test_no_unit_integer(self):
        p = parse_ingredient("3 eggs")
        assert p.qty == Fraction(3)
        assert p.unit is None
        assert p.name == "eggs"

    def test_no_unit_multi_word_name(self):
        p = parse_ingredient("2 cloves garlic, minced")
        assert p.qty == Fraction(2)
        assert p.unit is None
        assert p.name == "cloves garlic, minced"

    # --- no qty ---

    def test_no_qty_plain(self):
        p = parse_ingredient("garlic")
        assert p.qty is None
        assert p.unit is None
        assert p.name == "garlic"

    def test_no_qty_multi_word(self):
        p = parse_ingredient("kosher salt")
        assert p.qty is None
        assert p.unit is None
        assert p.name == "kosher salt"

    # --- mixed numbers ---

    def test_unicode_mixed_number(self):
        p = parse_ingredient("1½ cups broth")
        assert p.qty == Fraction(3, 2)
        assert p.unit == "cup"
        assert p.name == "broth"

    def test_ascii_mixed_number(self):
        p = parse_ingredient("1 1/2 cups broth")
        assert p.qty == Fraction(3, 2)
        assert p.unit == "cup"
        assert p.name == "broth"

    def test_unicode_fraction_only(self):
        p = parse_ingredient("¼ cup butter")
        assert p.qty == Fraction(1, 4)
        assert p.unit == "cup"
        assert p.name == "butter"

    # --- trailing notes stripped ---

    def test_strip_divided_with_comma(self):
        p = parse_ingredient("1 cup butter, divided")
        assert p.name == "butter"

    def test_strip_divided_without_comma(self):
        p = parse_ingredient("2 cups flour divided")
        assert p.name == "flour"

    def test_strip_optional_in_parens(self):
        p = parse_ingredient("1 tsp vanilla (optional)")
        assert p.name == "vanilla"

    def test_strip_optional_with_comma(self):
        p = parse_ingredient("2 tbsp capers, optional")
        assert p.name == "capers"

    def test_strip_or_to_taste(self):
        p = parse_ingredient("½ tsp salt, or to taste")
        assert p.name == "salt"

    def test_strip_to_taste_no_qty(self):
        p = parse_ingredient("black pepper to taste")
        assert p.name == "black pepper"

    def test_strip_to_taste_in_parens_no_qty(self):
        p = parse_ingredient("black pepper (to taste)")
        assert p.name == "black pepper"

    def test_strip_for_serving(self):
        p = parse_ingredient("2 tbsp olive oil, for serving")
        assert p.name == "olive oil"

    # --- preserve useful parenthetical content ---

    def test_preserve_description_parens(self):
        p = parse_ingredient("15 oz white beans (canned, drained)")
        assert "canned" in p.name
        assert "white beans" in p.name

    def test_preserve_qualifier_parens(self):
        p = parse_ingredient("1 cup broth (low sodium)")
        assert p.name == "broth (low sodium)"

    # --- multi-word and hyphenated names ---

    def test_hyphenated_name(self):
        p = parse_ingredient("1 cup all-purpose flour")
        assert p.name == "all-purpose flour"

    def test_multi_word_with_number_in_name(self):
        p = parse_ingredient("1 can (14 oz) diced tomatoes")
        assert p.qty == Fraction(1)
        assert p.unit is None  # "can" is not a known unit


# ---------------------------------------------------------------------------
# normalize_name
# ---------------------------------------------------------------------------


class TestNormalizeName:
    def test_lowercases(self):
        assert normalize_name("All-Purpose Flour") == "all-purpose flour"

    def test_removes_parenthetical(self):
        assert normalize_name("white beans (canned)") == "white beans"

    def test_replaces_comma_with_space(self):
        assert normalize_name("garlic, minced") == "garlic minced"

    def test_collapses_whitespace(self):
        assert normalize_name("  kosher   salt  ") == "kosher salt"

    def test_preserves_hyphen(self):
        assert normalize_name("all-purpose flour") == "all-purpose flour"

    def test_removes_nested_parens_content(self):
        assert normalize_name("white beans (canned, drained and rinsed)") == "white beans"

    def test_plain_word_unchanged(self):
        assert normalize_name("butter") == "butter"
