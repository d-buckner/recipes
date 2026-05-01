import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import responses as responses_lib
from recipe_scrapers._exceptions import NoSchemaFoundInWildMode, RecipeSchemaNotFound

from recipes.discovery import (
    _collect_leaf_sitemaps,
    _is_valid_recipe,
    _log_sample_size,
    _probe_sitemap,
    discover_site,
)

_FIXTURES = Path(__file__).parent / "fixtures"
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


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


# ---------------------------------------------------------------------------
# mollybaz.com — fixture-based integration tests
# ---------------------------------------------------------------------------

def _urls_from_fixture(name: str) -> list[str]:
    """Parse a mollybaz fixture XML and return all <loc> URLs."""
    path = _FIXTURES / "mollybaz" / name
    root = ET.parse(path).getroot()
    return [loc.text.strip() for loc in root.iter(f"{{{_SITEMAP_NS}}}loc")]


def _mollybaz_leaf(fixture_name: str) -> MagicMock:
    """Build a mock usp leaf node from a real mollybaz fixture file."""
    urls = _urls_from_fixture(fixture_name)
    url = f"https://mollybaz.com/{fixture_name}"
    return _leaf(url, urls)


# Probe results that mirror what live mollybaz.com returns:
#   post-sitemap  → 100% recipe hits (all flat-slug posts are recipes)
#   wf-sitemap    → 100% recipe hits (all /wf/ posts are recipes)
#   everything else → 0% (page, more, update_posts, category, tag, secondary_category)
_MOLLYBAZ_HIT_RATES = {
    "post-sitemap.xml": (20, 20),
    "wf-sitemap.xml": (5, 5),
    "page-sitemap.xml": (14, 0),
    "more-sitemap.xml": (13, 0),
    "update_posts-sitemap.xml": (10, 0),
    "category-sitemap.xml": (9, 0),
    "post_tag-sitemap.xml": (17, 0),
    "secondary_category-sitemap.xml": (7, 0),
}


def _mollybaz_probe(sitemap) -> tuple[int, int]:
    for name, result in _MOLLYBAZ_HIT_RATES.items():
        if sitemap.url and sitemap.url.endswith(name):
            return result
    return (0, 0)


def _mollybaz_tree() -> MagicMock:
    """Build a full mock usp tree for mollybaz.com using fixture data."""
    leaves = [
        _mollybaz_leaf("post-sitemap.xml"),
        _mollybaz_leaf("page-sitemap.xml"),
        _mollybaz_leaf("more-sitemap.xml"),
        _mollybaz_leaf("update_posts-sitemap.xml"),
        _mollybaz_leaf("wf-sitemap.xml"),
        _mollybaz_leaf("category-sitemap.xml"),
        _mollybaz_leaf("post_tag-sitemap.xml"),
        _mollybaz_leaf("secondary_category-sitemap.xml"),
    ]
    return _index(None, [_index("https://mollybaz.com/sitemap_index.xml", leaves)])


class TestMollybazDiscovery:
    """
    Fixture-based tests for mollybaz.com discovery.

    mollybaz.com (Yoast SEO / WordPress) has:
      - post-sitemap.xml  — 312 flat-slug recipe posts (e.g. /leaf-peepin-ragu/)
      - wf-sitemap.xml    — 5 /wf/ recipe posts
      - 6 non-recipe sitemaps (page, more, update_posts, category, tag, secondary_category)

    Expected: post-sitemap and wf-sitemap are selected; all others excluded.
    """

    def test_sitemap_index_has_eight_leaf_sitemaps(self):
        """The sitemap index declares exactly 8 child sitemaps."""
        locs = _urls_from_fixture("sitemap_index.xml")
        assert len(locs) == 8

    def test_post_sitemap_fixture_contains_flat_slug_urls(self):
        """Fixture post-sitemap URLs have no /recipe/ prefix — just flat slugs."""
        urls = _urls_from_fixture("post-sitemap.xml")
        assert len(urls) == 20
        assert all(u.startswith("https://mollybaz.com/") for u in urls)
        # No URL contains a /recipe/ segment — they are flat slugs
        assert all("/recipe/" not in u for u in urls)
        assert "https://mollybaz.com/leaf-peepin-ragu/" in urls

    def test_wf_sitemap_fixture_contains_wf_path_urls(self):
        """Fixture wf-sitemap URLs are all under /wf/."""
        urls = _urls_from_fixture("wf-sitemap.xml")
        assert len(urls) == 5
        assert all("/wf/" in u for u in urls)
        assert "https://mollybaz.com/wf/salami-and-iceberg-antipasto-pasta-salad/" in urls

    def test_post_sitemap_selected_when_probe_high_hit_rate(self, mem_db):
        """post-sitemap.xml wins the probe; all its 20 fixture URLs are discovered."""
        tree = _mollybaz_tree()
        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=tree), \
             patch("recipes.discovery._probe_sitemap", side_effect=_mollybaz_probe), \
             patch("recipes.discovery._check_reachable", return_value=True):
            count = discover_site("https://mollybaz.com")

        # 20 from post-sitemap + 5 from wf-sitemap = 25 total
        assert count == 25

    def test_flat_slug_urls_included_in_discovered_set(self, mem_db):
        """Flat-slug recipe URLs (no /recipe/ segment) must be discovered."""
        tree = _mollybaz_tree()
        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=tree), \
             patch("recipes.discovery._probe_sitemap", side_effect=_mollybaz_probe), \
             patch("recipes.discovery._check_reachable", return_value=True):
            discover_site("https://mollybaz.com")

        from recipes import db
        with db.get_conn() as conn:
            urls = {row[0] for row in conn.execute("SELECT url FROM recipes").fetchall()}

        assert "https://mollybaz.com/leaf-peepin-ragu/" in urls
        assert "https://mollybaz.com/toona-melt/" in urls
        assert "https://mollybaz.com/farro-and-crunchy-thangs-salad-with-herby-feta-dressing/" in urls

    def test_wf_path_urls_included_in_discovered_set(self, mem_db):
        """/wf/ recipe URLs must be discovered alongside post-sitemap URLs."""
        tree = _mollybaz_tree()
        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=tree), \
             patch("recipes.discovery._probe_sitemap", side_effect=_mollybaz_probe), \
             patch("recipes.discovery._check_reachable", return_value=True):
            discover_site("https://mollybaz.com")

        from recipes import db
        with db.get_conn() as conn:
            urls = {row[0] for row in conn.execute("SELECT url FROM recipes").fetchall()}

        assert "https://mollybaz.com/wf/salami-and-iceberg-antipasto-pasta-salad/" in urls
        assert "https://mollybaz.com/wf/summer-chicken-parm-sandwich/" in urls

    def test_non_recipe_sitemaps_excluded(self, mem_db):
        """Category, tag, page, more, and update_posts sitemaps must be excluded."""
        tree = _mollybaz_tree()
        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=tree), \
             patch("recipes.discovery._probe_sitemap", side_effect=_mollybaz_probe), \
             patch("recipes.discovery._check_reachable", return_value=True):
            discover_site("https://mollybaz.com")

        from recipes import db
        with db.get_conn() as conn:
            urls = {row[0] for row in conn.execute("SELECT url FROM recipes").fetchall()}

        # category sitemap
        assert "https://mollybaz.com/category/chicken-licken/" not in urls
        # tag sitemap
        assert "https://mollybaz.com/tag/cozy/" not in urls
        # page sitemap (homepage URL)
        assert "https://mollybaz.com/" not in urls
        # more sitemap
        assert "https://mollybaz.com/more/latke-video/" not in urls
        # update_posts sitemap
        assert "https://mollybaz.com/update_posts/im-hosting-a-live-cooking-class-on-4-27/" not in urls
        # secondary_category sitemap
        assert "https://mollybaz.com/secondary_category/newest-recipe/" not in urls

    def test_fallback_uses_all_sitemaps_when_probe_blocked(self, mem_db):
        """
        When all probes return 0 hits (e.g. bot-blocked), discovery falls back
        to ALL leaf sitemaps. This is the current fallback behaviour — all URLs
        enter the queue and the scraper filters non-recipes at parse time.
        """
        tree = _mollybaz_tree()
        total_fixture_urls = sum(
            len(_urls_from_fixture(f))
            for f in [
                "post-sitemap.xml", "page-sitemap.xml", "more-sitemap.xml",
                "update_posts-sitemap.xml", "wf-sitemap.xml", "category-sitemap.xml",
                "post_tag-sitemap.xml", "secondary_category-sitemap.xml",
            ]
        )
        with patch("recipes.discovery.sitemap_tree_for_homepage", return_value=tree), \
             patch("recipes.discovery._probe_sitemap", return_value=(10, 0)), \
             patch("recipes.discovery._check_reachable", return_value=True):
            count = discover_site("https://mollybaz.com")

        assert count == total_fixture_urls
