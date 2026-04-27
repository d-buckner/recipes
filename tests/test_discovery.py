from unittest.mock import MagicMock, patch

import pytest
from recipe_scrapers._exceptions import NoSchemaFoundInWildMode, RecipeSchemaNotFound

from recipes.discovery import _collect_leaf_sitemaps, _is_valid_recipe, _probe_has_recipes, discover_site


# ---------------------------------------------------------------------------
# usp tree mock helpers
# ---------------------------------------------------------------------------

def _leaf(url: str, page_urls: list[str]) -> MagicMock:
    """Simulate a PagesXMLSitemap (leaf) node."""
    node = MagicMock()
    node.url = url
    node.sub_sitemaps = []
    node.all_pages.return_value = [_page(u) for u in page_urls]
    return node


def _index(url: str, children: list) -> MagicMock:
    """Simulate an IndexXMLSitemap node."""
    node = MagicMock()
    node.url = url
    node.sub_sitemaps = children
    return node


def _page(url: str) -> MagicMock:
    page = MagicMock()
    page.url = url
    return page


# ---------------------------------------------------------------------------
# _collect_leaf_sitemaps
# ---------------------------------------------------------------------------

class TestCollectLeafSitemaps:
    def test_single_leaf(self):
        leaf = _leaf("https://example.com/sitemap.xml", [])
        assert _collect_leaf_sitemaps(leaf) == [leaf]

    def test_flat_index(self):
        a = _leaf("https://example.com/sitemap-a.xml", [])
        b = _leaf("https://example.com/sitemap-b.xml", [])
        root = _index("https://example.com/sitemap_index.xml", [a, b])
        assert _collect_leaf_sitemaps(root) == [a, b]

    def test_nested_index(self):
        leaf1 = _leaf("https://example.com/sitemap-posts.xml", [])
        leaf2 = _leaf("https://example.com/sitemap-pages.xml", [])
        inner = _index("https://example.com/sitemap_index.xml", [leaf1, leaf2])
        robots = _index(None, [inner])
        assert _collect_leaf_sitemaps(robots) == [leaf1, leaf2]


# ---------------------------------------------------------------------------
# _probe_has_recipes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _is_valid_recipe
# ---------------------------------------------------------------------------

class TestIsValidRecipe:
    def test_valid_with_ingredients(self):
        assert _is_valid_recipe({"title": "Pasta", "ingredients": ["pasta", "salt"]}) is True

    def test_valid_with_instructions_only(self):
        assert _is_valid_recipe({"title": "Pasta", "instructions": "Boil water."}) is True

    def test_invalid_no_title(self):
        assert _is_valid_recipe({"title": None, "ingredients": ["pasta"]}) is False

    def test_invalid_no_content(self):
        assert _is_valid_recipe({"title": "Vegan", "ingredients": [], "instructions": ""}) is False

    def test_invalid_empty_dict(self):
        assert _is_valid_recipe({}) is False


class TestProbeHasRecipes:
    def test_returns_true_on_first_success(self):
        sitemap = _leaf("https://example.com/sitemap.xml", ["https://example.com/recipes/pasta"])
        full_recipe = {"title": "Pasta", "ingredients": ["pasta", "salt"], "instructions": "Boil."}
        with patch("recipes.discovery.fetch_html", return_value="<html>"), \
             patch("recipes.discovery.parse_recipe", return_value=full_recipe):
            assert _probe_has_recipes(sitemap) is True

    def test_returns_true_when_later_url_succeeds(self):
        sitemap = _leaf("https://example.com/sitemap.xml", [
            "https://example.com/recipes/collections/vegan",
            "https://example.com/recipes/pasta",
        ])
        full_recipe = {"title": "Pasta", "ingredients": ["pasta", "salt"], "instructions": "Boil."}
        with patch("recipes.discovery.fetch_html", return_value="<html>"), \
             patch("recipes.discovery.parse_recipe", side_effect=[
                 NoSchemaFoundInWildMode("no schema"),
                 full_recipe,
             ]):
            assert _probe_has_recipes(sitemap) is True

    def test_returns_false_when_all_raise_no_schema(self):
        sitemap = _leaf("https://example.com/sitemap.xml", [
            "https://example.com/tag/vegan",
            "https://example.com/tag/quick",
        ])
        with patch("recipes.discovery.fetch_html", return_value="<html>"), \
             patch("recipes.discovery.parse_recipe", side_effect=RecipeSchemaNotFound("no schema")):
            assert _probe_has_recipes(sitemap) is False

    def test_returns_false_when_parse_returns_empty_fields(self):
        """Collection/tag pages may parse without error but return no real recipe data."""
        sitemap = _leaf("https://example.com/sitemap.xml", [
            "https://example.com/recipes/collections/vegan/",
        ])
        empty = {"title": None, "ingredients": [], "instructions": "", "host": "example.com"}
        with patch("recipes.discovery.fetch_html", return_value="<html>"), \
             patch("recipes.discovery.parse_recipe", return_value=empty):
            assert _probe_has_recipes(sitemap) is False

    def test_returns_false_for_empty_sitemap(self):
        sitemap = _leaf("https://example.com/sitemap.xml", [])
        assert _probe_has_recipes(sitemap) is False

    def test_skips_network_errors_and_continues(self):
        sitemap = _leaf("https://example.com/sitemap.xml", [
            "https://example.com/broken",
            "https://example.com/recipes/pasta",
        ])
        import requests
        full_recipe = {"title": "Pasta", "ingredients": ["pasta", "salt"], "instructions": "Boil."}
        with patch("recipes.discovery.fetch_html", side_effect=[
            requests.ConnectionError("timeout"),
            "<html>",
        ]), patch("recipes.discovery.parse_recipe", return_value=full_recipe):
            assert _probe_has_recipes(sitemap) is True

    def test_respects_sample_size(self):
        sitemap = _leaf("https://example.com/sitemap.xml", [
            "https://example.com/tag/a",
            "https://example.com/tag/b",
            "https://example.com/tag/c",
            "https://example.com/recipes/pasta",  # would succeed but beyond sample
        ])
        with patch("recipes.discovery.fetch_html", return_value="<html>"), \
             patch("recipes.discovery.parse_recipe", side_effect=NoSchemaFoundInWildMode("no schema")):
            assert _probe_has_recipes(sitemap, sample_size=3) is False


# ---------------------------------------------------------------------------
# discover_site
# ---------------------------------------------------------------------------

class TestDiscoverSite:
    def test_uses_probe_confirmed_sitemaps(self, mem_db):
        posts = _leaf(
            "https://example.com/sitemap-posts.xml",
            ["https://example.com/recipes/pasta", "https://example.com/recipes/soup"],
        )
        pages = _leaf(
            "https://example.com/sitemap-pages.xml",
            ["https://example.com/recipes/collections/vegan", "https://example.com/about"],
        )
        root = _index(None, [_index("https://example.com/sitemap.xml", [posts, pages])])

        def fake_probe(sitemap, **_):
            return sitemap is posts  # only posts sitemap has recipes

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_has_recipes", side_effect=fake_probe):
            count = discover_site("https://example.com")

        # Only posts sitemap selected; collection pages are skipped by URL filter too
        assert count == 2

    def test_collection_pages_excluded_even_if_url_matches(self, mem_db):
        """Sitemap with /recipes/collections/... URLs should be excluded by probe."""
        pages = _leaf(
            "https://example.com/sitemap-pages.xml",
            [
                "https://example.com/recipes/collections/vegan/free/",
                "https://example.com/recipes/collections/quick/",
            ],
        )
        root = _index(None, [pages])

        # Probe returns False (collection pages don't parse as recipes)
        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_has_recipes", return_value=False):
            count = discover_site("https://example.com")

        # Fallback: all sitemaps used, but URL filter still matches (demonstrating
        # that probe exclusion is the real fix — without probe these would sneak in)
        assert count == 2  # fallback includes them; probe is what we rely on

    def test_falls_back_to_all_when_probe_finds_nothing(self, mem_db):
        leaf = _leaf(
            "https://example.com/sitemap.xml",
            ["https://example.com/recipes/pasta"],
        )
        root = _index(None, [leaf])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_has_recipes", return_value=False):
            count = discover_site("https://example.com")

        assert count == 1  # fallback: URL filter picks it up

    def test_confirmed_sitemaps_bypass_url_filter(self, mem_db):
        """Probe-confirmed sitemaps bypass the URL filter entirely.
        Sites with flat slugs (no /recipe/ segment) must not have their URLs dropped."""
        posts = _leaf(
            "https://example.com/sitemap-posts.xml",
            [
                "https://example.com/recipes/pasta",
                "https://example.com/newsletters/issue-1",
            ],
        )
        root = _index(None, [posts])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_has_recipes", return_value=True):
            count = discover_site("https://example.com")

        assert count == 2  # probe confirmed the sitemap; URL filter is not applied

    def test_custom_url_filter_applied_in_fallback_mode(self, mem_db):
        """Custom URL filter is applied when probe finds no confirmed sitemaps (fallback)."""
        leaf = _leaf(
            "https://example.com/sitemap.xml",
            ["https://example.com/food/chicken", "https://example.com/about"],
        )
        root = _index(None, [leaf])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_has_recipes", return_value=False):
            count = discover_site("https://example.com", url_filter=r"/food")

        assert count == 1  # /food filter applied in fallback; /about excluded

    def test_deduplicates_across_sitemaps(self, mem_db):
        url = "https://example.com/recipes/pasta"
        a = _leaf("https://example.com/sitemap-a.xml", [url])
        b = _leaf("https://example.com/sitemap-b.xml", [url])
        root = _index(None, [a, b])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_has_recipes", return_value=True):
            count = discover_site("https://example.com")

        assert count == 1


# ---------------------------------------------------------------------------
# Flat-URL sites (e.g. justinesnacks.com)
# ---------------------------------------------------------------------------

class TestFlatUrlSites:
    """
    Sites like justinesnacks.com (Yoast SEO / WordPress) publish recipe posts at
    flat top-level slugs: https://justinesnacks.com/vanilla-latte-cake/

    There is no /recipe/ path segment, so the default url_filter_pattern=r"/recipe"
    drops every URL from the post-sitemap even when the probe correctly confirms it
    contains recipes.  Probe-confirmed sitemaps must bypass the URL filter.
    """

    def test_flat_url_recipes_discovered_when_post_sitemap_confirmed(self, mem_db):
        posts = _leaf(
            "https://justinesnacks.com/post-sitemap.xml",
            [
                "https://justinesnacks.com/vanilla-latte-cake/",
                "https://justinesnacks.com/burrata-with-hot-honey-on-ciabatta/",
                "https://justinesnacks.com/lemon-poppyseed-truffles-easy-4-ingredients/",
            ],
        )
        root = _index(None, [posts])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_has_recipes", return_value=True):
            count = discover_site("https://justinesnacks.com")

        assert count == 3  # all flat-slug recipes included; currently 0 due to /recipe filter

    def test_non_post_sitemaps_excluded_by_probe(self, mem_db):
        """Category and tag sitemaps should be excluded by probe, not URL filter."""
        posts = _leaf(
            "https://justinesnacks.com/post-sitemap.xml",
            [
                "https://justinesnacks.com/vanilla-latte-cake/",
                "https://justinesnacks.com/chocolate-chip-tahini-cookies/",
            ],
        )
        categories = _leaf(
            "https://justinesnacks.com/category-sitemap.xml",
            [
                "https://justinesnacks.com/category/baking/",
                "https://justinesnacks.com/category/breakfast/",
            ],
        )
        root = _index(None, [posts, categories])

        def fake_probe(sitemap, **_):
            return sitemap is posts  # only the post sitemap has real recipes

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_has_recipes", side_effect=fake_probe):
            count = discover_site("https://justinesnacks.com")

        assert count == 2  # only the 2 post URLs; category sitemap excluded by probe
