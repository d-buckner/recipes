from unittest.mock import MagicMock, patch

import pytest
from recipe_scrapers._exceptions import NoSchemaFoundInWildMode, RecipeSchemaNotFound

from recipes.discovery import (
    _collect_leaf_sitemaps,
    _is_valid_recipe,
    _log_sample_size,
    _probe_sitemap,
    discover_site,
)


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


# ---------------------------------------------------------------------------
# _log_sample_size
# ---------------------------------------------------------------------------

class TestLogSampleSize:
    def test_small_returns_all(self):
        assert _log_sample_size(3) == 3

    def test_min_n_boundary(self):
        assert _log_sample_size(5) == 5

    def test_grows_with_size(self):
        s100 = _log_sample_size(100)
        s1000 = _log_sample_size(1000)
        assert s100 < s1000

    def test_capped_at_max(self):
        assert _log_sample_size(1_000_000) == 20


# ---------------------------------------------------------------------------
# _probe_sitemap
# ---------------------------------------------------------------------------

class TestProbeSitemap:
    def test_empty_sitemap_returns_zeros(self):
        sitemap = _leaf("https://example.com/sitemap.xml", [])
        assert _probe_sitemap(sitemap) == (0, 0)

    def test_all_hits(self):
        sitemap = _leaf("https://example.com/sitemap.xml", [
            "https://example.com/recipes/pasta",
            "https://example.com/recipes/soup",
        ])
        full_recipe = {"title": "Pasta", "ingredients": ["pasta"], "instructions": "Boil."}
        with patch("recipes.discovery.fetch_html", return_value="<html>"), \
             patch("recipes.discovery.parse_recipe", return_value=full_recipe):
            n_sampled, n_hits = _probe_sitemap(sitemap)
        assert n_sampled == 2
        assert n_hits == 2

    def test_no_hits_no_schema(self):
        sitemap = _leaf("https://example.com/sitemap.xml", [
            "https://example.com/tag/vegan",
            "https://example.com/tag/quick",
        ])
        with patch("recipes.discovery.fetch_html", return_value="<html>"), \
             patch("recipes.discovery.parse_recipe", side_effect=RecipeSchemaNotFound("no schema")):
            n_sampled, n_hits = _probe_sitemap(sitemap)
        assert n_sampled == 2
        assert n_hits == 0

    def test_no_hits_empty_fields(self):
        sitemap = _leaf("https://example.com/sitemap.xml", [
            "https://example.com/recipes/collections/vegan/",
        ])
        empty = {"title": None, "ingredients": [], "instructions": ""}
        with patch("recipes.discovery.fetch_html", return_value="<html>"), \
             patch("recipes.discovery.parse_recipe", return_value=empty):
            n_sampled, n_hits = _probe_sitemap(sitemap)
        assert n_sampled == 1
        assert n_hits == 0

    def test_network_errors_counted_as_sampled_not_hit(self):
        import requests as req
        sitemap = _leaf("https://example.com/sitemap.xml", [
            "https://example.com/broken",
            "https://example.com/also-broken",
        ])
        with patch("recipes.discovery.fetch_html", side_effect=req.ConnectionError("timeout")):
            n_sampled, n_hits = _probe_sitemap(sitemap)
        assert n_sampled == 2
        assert n_hits == 0

    def test_partial_hits(self):
        sitemap = _leaf("https://example.com/sitemap.xml", [
            "https://example.com/tag/vegan",
            "https://example.com/recipes/pasta",
        ])
        full_recipe = {"title": "Pasta", "ingredients": ["pasta"], "instructions": "Boil."}
        with patch("recipes.discovery.fetch_html", return_value="<html>"), \
             patch("recipes.discovery.parse_recipe", side_effect=[
                 NoSchemaFoundInWildMode("no schema"),
                 full_recipe,
             ]):
            n_sampled, n_hits = _probe_sitemap(sitemap)
        assert n_sampled == 2
        assert n_hits == 1


# ---------------------------------------------------------------------------
# discover_site
# ---------------------------------------------------------------------------

class TestDiscoverSite:
    def test_uses_high_rate_sitemap_only(self, mem_db):
        """A sitemap with 100% hit rate (≥ HIGH) causes only that sitemap to be selected."""
        posts = _leaf(
            "https://example.com/sitemap-posts.xml",
            ["https://example.com/recipes/pasta", "https://example.com/recipes/soup"],
        )
        pages = _leaf(
            "https://example.com/sitemap-pages.xml",
            ["https://example.com/about", "https://example.com/contact"],
        )
        root = _index(None, [_index("https://example.com/sitemap.xml", [posts, pages])])

        def fake_probe(sitemap):
            return (10, 10) if sitemap is posts else (10, 0)

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_sitemap", side_effect=fake_probe), \
             patch("recipes.discovery._check_reachable", return_value=True):
            count = discover_site("https://example.com")

        assert count == 2  # only posts sitemap selected

    def test_falls_back_to_all_when_no_hits(self, mem_db):
        """When all probes return 0 hits, all sitemaps are used as fallback."""
        leaf = _leaf(
            "https://example.com/sitemap.xml",
            ["https://example.com/recipes/pasta"],
        )
        root = _index(None, [leaf])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_sitemap", return_value=(10, 0)), \
             patch("recipes.discovery._check_reachable", return_value=True):
            count = discover_site("https://example.com")

        assert count == 1  # fallback: all URLs used

    def test_all_urls_included_no_filter(self, mem_db):
        """Probe-selected sitemaps include all their URLs with no URL filtering."""
        posts = _leaf(
            "https://example.com/sitemap-posts.xml",
            [
                "https://example.com/recipes/pasta",
                "https://example.com/newsletters/issue-1",  # no /recipe/ segment
            ],
        )
        root = _index(None, [posts])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_sitemap", return_value=(10, 10)), \
             patch("recipes.discovery._check_reachable", return_value=True):
            count = discover_site("https://example.com")

        assert count == 2  # both URLs included; no URL filtering applied

    def test_deduplicates_across_sitemaps(self, mem_db):
        url = "https://example.com/recipes/pasta"
        a = _leaf("https://example.com/sitemap-a.xml", [url])
        b = _leaf("https://example.com/sitemap-b.xml", [url])
        root = _index(None, [a, b])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_sitemap", return_value=(10, 10)), \
             patch("recipes.discovery._check_reachable", return_value=True):
            count = discover_site("https://example.com")

        assert count == 1  # same URL in both sitemaps deduplicated

    def test_unreachable_site_returns_zero(self, mem_db):
        with patch("recipes.discovery._check_reachable", return_value=False):
            count = discover_site("https://unreachable.example.com")
        assert count == 0

    def test_medium_rate_sitemaps_included_when_high_rate_present(self, mem_db):
        """When best rate ≥ HIGH, sitemaps with rate ≥ MEDIUM are also included."""
        posts = _leaf(
            "https://example.com/sitemap-posts.xml",
            ["https://example.com/recipes/pasta", "https://example.com/recipes/soup"],
        )
        mixed = _leaf(
            "https://example.com/sitemap-mixed.xml",
            ["https://example.com/recipes/cake"],  # 2/10 = 20% — above MEDIUM
        )
        noise = _leaf(
            "https://example.com/sitemap-pages.xml",
            ["https://example.com/about"],  # 0/10 = 0% — below MEDIUM
        )
        root = _index(None, [posts, mixed, noise])

        def fake_probe(sitemap):
            if sitemap is posts:
                return (10, 10)   # 100% → HIGH
            if sitemap is mixed:
                return (10, 2)    # 20% → above MEDIUM
            return (10, 0)        # 0% → below MEDIUM

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_sitemap", side_effect=fake_probe), \
             patch("recipes.discovery._check_reachable", return_value=True):
            count = discover_site("https://example.com")

        assert count == 3  # posts (2) + mixed (1) selected; noise excluded


# ---------------------------------------------------------------------------
# Flat-URL sites (e.g. justinesnacks.com)
# ---------------------------------------------------------------------------

class TestFlatUrlSites:
    """
    Sites like justinesnacks.com (Yoast SEO / WordPress) publish recipe posts at
    flat top-level slugs: https://justinesnacks.com/vanilla-latte-cake/

    There is no /recipe/ path segment. The hit-rate approach handles this
    correctly: the post-sitemap will have a high hit rate and all its URLs
    (including flat-slug ones) are included without any URL filtering.
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
             patch("recipes.discovery._probe_sitemap", return_value=(10, 10)), \
             patch("recipes.discovery._check_reachable", return_value=True):
            count = discover_site("https://justinesnacks.com")

        assert count == 3

    def test_non_post_sitemaps_excluded_by_probe(self, mem_db):
        """Category sitemaps with 0% hit rate are excluded when post sitemap is ≥ HIGH."""
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

        def fake_probe(sitemap):
            return (10, 10) if sitemap is posts else (10, 0)

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root), \
             patch("recipes.discovery._probe_sitemap", side_effect=fake_probe), \
             patch("recipes.discovery._check_reachable", return_value=True):
            count = discover_site("https://justinesnacks.com")

        assert count == 2  # only the 2 post URLs; category sitemap excluded
