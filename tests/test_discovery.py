import re
from unittest.mock import MagicMock, patch

import pytest

from recipes.discovery import _collect_leaf_sitemaps, discover_site


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
# discover_site — recipe sub-sitemap preference
# ---------------------------------------------------------------------------

class TestDiscoverSite:
    def test_prefers_recipe_named_sitemaps(self, mem_db):
        recipe_leaf = _leaf(
            "https://example.com/sitemap-recipes.xml",
            ["https://example.com/recipes/pasta", "https://example.com/recipes/soup"],
        )
        pages_leaf = _leaf(
            "https://example.com/sitemap-pages.xml",
            ["https://example.com/about"],
        )
        root = _index(None, [
            _index("https://example.com/sitemap.xml", [recipe_leaf, pages_leaf])
        ])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root):
            count = discover_site("https://example.com")

        assert count == 2

    def test_falls_back_to_all_sitemaps_when_no_recipe_hint(self, mem_db):
        posts_leaf = _leaf(
            "https://example.com/sitemap-posts.xml",
            [
                "https://example.com/recipes/pasta",
                "https://example.com/newsletters/issue-1",
            ],
        )
        pages_leaf = _leaf(
            "https://example.com/sitemap-pages.xml",
            [
                "https://example.com/recipes/collections/vegan",
                "https://example.com/about",
            ],
        )
        root = _index(None, [
            _index("https://example.com/sitemap.xml", [posts_leaf, pages_leaf])
        ])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root):
            count = discover_site("https://example.com")

        # Both recipe-matching URLs are collected across both sitemaps
        assert count == 2

    def test_url_filter_excludes_non_recipe_urls(self, mem_db):
        leaf = _leaf(
            "https://example.com/sitemap.xml",
            [
                "https://example.com/recipes/chicken-soup",
                "https://example.com/about",
                "https://example.com/contact",
            ],
        )
        root = _index(None, [leaf])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root):
            count = discover_site("https://example.com")

        assert count == 1

    def test_custom_url_filter(self, mem_db):
        leaf = _leaf(
            "https://example.com/sitemap.xml",
            [
                "https://example.com/food/chicken",
                "https://example.com/recipes/pasta",
                "https://example.com/about",
            ],
        )
        root = _index(None, [leaf])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root):
            count = discover_site("https://example.com", url_filter=r"/food|/recipe")

        assert count == 2

    def test_returns_zero_when_no_matches(self, mem_db):
        leaf = _leaf(
            "https://example.com/sitemap.xml",
            ["https://example.com/about", "https://example.com/contact"],
        )
        root = _index(None, [leaf])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root):
            count = discover_site("https://example.com")

        assert count == 0

    def test_deduplicates_urls(self, mem_db):
        # Same URL appears in two sitemaps
        url = "https://example.com/recipes/pasta"
        a = _leaf("https://example.com/sitemap-a.xml", [url])
        b = _leaf("https://example.com/sitemap-b.xml", [url])
        root = _index(None, [a, b])

        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=root):
            count = discover_site("https://example.com")

        assert count == 1
