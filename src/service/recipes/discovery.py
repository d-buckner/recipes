import logging
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from recipe_scrapers._exceptions import NoSchemaFoundInWildMode, RecipeSchemaNotFound
from usp.tree import sitemap_tree_for_homepage

from . import db
from .config import settings
from .scraper import fetch_html, parse_recipe

log = logging.getLogger(__name__)

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Hit-rate thresholds for sitemap classification
_HIGH_HIT_RATE = 0.40   # ≥40%  → dedicated recipe sitemap
_MEDIUM_HIT_RATE = 0.10  # ≥10%  → mixed sitemap with meaningful recipe content


@dataclass(frozen=True)
class SitemapProbe:
    sitemap: object
    n_sampled: int
    n_hits: int

    @property
    def hit_rate(self) -> float:
        return self.n_hits / self.n_sampled if self.n_sampled else 0.0


@dataclass(frozen=True)
class SitemapSelection:
    sitemaps: list[object]
    reason: str
    best_rate: float


def _collect_leaf_sitemaps(node) -> list:
    """
    Recursively collect leaf (non-index) sitemap nodes from a usp tree.
    Index nodes have sub_sitemaps; leaf nodes (PagesXMLSitemap etc.) do not.
    """
    if not node.sub_sitemaps:
        return [node]
    leaves = []
    for child in node.sub_sitemaps:
        leaves.extend(_collect_leaf_sitemaps(child))
    return leaves


def _log_sample_size(n_total: int, min_n: int = 5, max_n: int = 20) -> int:
    """Logarithmic sample size: grows slowly so large sitemaps stay cheap."""
    if n_total <= min_n:
        return n_total
    return min(max_n, max(min_n, int(math.log2(n_total) * 2.5)))


def _sample_urls(urls: list[str], n_sample: int) -> list[str]:
    """Return a deterministic, evenly-spaced sample from a sitemap URL list."""
    if n_sample <= 0:
        return []
    if len(urls) <= n_sample:
        return urls
    if n_sample == 1:
        return [urls[0]]
    step = (len(urls) - 1) / (n_sample - 1)
    return [urls[round(i * step)] for i in range(n_sample)]


def _probe_sitemap(sitemap) -> tuple[int, int]:
    """
    Deterministically sample URLs from a sitemap and count recipe hits.
    Returns (n_sampled, n_hits).
    """
    all_urls = [p.url for p in sitemap.all_pages() if p.url]
    n_total = len(all_urls)
    n_sample = _log_sample_size(n_total)
    if n_sample == 0:
        return 0, 0

    sample = _sample_urls(all_urls, n_sample)
    hits = 0
    for url in sample:
        try:
            html = fetch_html(url)
            data = parse_recipe(html, url)
            if _is_valid_recipe(data):
                hits += 1
                log.debug("  probe hit: %s", url)
            else:
                log.debug("  probe miss (empty fields): %s", url)
        except (NoSchemaFoundInWildMode, RecipeSchemaNotFound):
            log.debug("  probe miss (no schema): %s", url)
        except Exception as exc:
            log.debug("  probe error (%s): %s", type(exc).__name__, url)

    return n_sample, hits


def _select_recipe_sitemaps(probes: list[SitemapProbe], leaf_sitemaps: list[object]) -> SitemapSelection:
    """Select recipe-rich sitemaps from probe results.

    The thresholds are intentionally isolated from network and parser work so
    the discovery policy can change without touching the crawler mechanics.
    """
    max_rate = max((probe.hit_rate for probe in probes), default=0.0)

    if max_rate >= _HIGH_HIT_RATE:
        selected = [probe.sitemap for probe in probes if probe.hit_rate >= _MEDIUM_HIT_RATE]
        return SitemapSelection(selected, "high_confidence", max_rate)
    if max_rate > 0:
        selected = [probe.sitemap for probe in probes if probe.hit_rate > 0]
        return SitemapSelection(selected, "any_hits", max_rate)
    return SitemapSelection(leaf_sitemaps, "fallback_all", max_rate)


def _urls_from_sitemap_url(sitemap_url: str, hostname: str) -> list[tuple[str, str]]:
    """Fetch a specific sitemap XML and return all (url, hostname) tuples."""
    log.info("Fetching sitemap: %s", sitemap_url)
    headers = {"User-Agent": settings.user_agent}
    resp = requests.get(sitemap_url, headers=headers, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    urls = []
    for loc in root.iter(f"{{{_SITEMAP_NS}}}loc"):
        url = loc.text and loc.text.strip()
        if url:
            urls.append((url, hostname))
    log.info("Found %d URLs in sitemap", len(urls))
    return urls


def discover_from_sitemap_url(sitemap_url: str, hostname: str | None = None) -> int:
    """
    Discover all URLs directly from a specific sitemap XML (bypasses homepage crawl).
    Useful when the site's post-sitemap contains only recipe posts.
    Returns the number of new URLs inserted.
    """
    host = hostname or urlparse(sitemap_url).netloc
    urls = _urls_from_sitemap_url(sitemap_url, host)
    if not urls:
        log.warning("No URLs found in sitemap: %s", sitemap_url)
        return 0
    inserted = db.insert_discovered_urls(urls)
    log.info("Inserted %d new URLs (skipped %d duplicates)", inserted, len(urls) - inserted)
    return inserted


def _is_valid_recipe(data: dict) -> bool:
    """A real recipe must have a title and at least ingredients or instructions."""
    return bool(data.get("title")) and bool(data.get("ingredients") or data.get("instructions"))


def _check_reachable(site_url: str, timeout: float = 8.0) -> bool:
    """
    Quick connectivity probe before handing off to usp.
    Returns False only on network-level failures (unreachable / connect timeout).
    HTTP error codes (4xx/5xx) are not treated as unreachable.
    """
    try:
        requests.head(
            site_url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        )
        return True
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        log.warning("Site unreachable, skipping discovery: %s", exc)
        return False


def discover_site(site_url: str) -> int:
    """
    Crawl sitemaps for a site via robots.txt, select recipe-rich sitemaps by
    hit-rate, and insert all their URLs into the db.

    Each leaf sitemap is probed with a logarithmic deterministic sample.  Sitemaps are
    ranked by recipe hit-rate and selected as follows:
      - If the best sitemap is ≥ HIGH_HIT_RATE (40 %): keep all sitemaps
        with rate ≥ MEDIUM_HIT_RATE (10 %) — these are the recipe-specific ones.
      - If the best rate is positive but below HIGH_HIT_RATE: keep everything
        with at least one hit (the site may have no dedicated recipe sitemap).
      - If no hits at all: fall back to all leaf sitemaps (the scraper will
        filter non-recipes at parse time).

    Returns the number of new URLs discovered.
    """
    hostname = urlparse(site_url).netloc
    log.info("Crawling sitemaps for %s", hostname)

    if not _check_reachable(site_url):
        return 0

    tree = sitemap_tree_for_homepage(site_url)

    leaf_sitemaps = _collect_leaf_sitemaps(tree)
    log.info("Found %d leaf sitemap(s)", len(leaf_sitemaps))
    for s in leaf_sitemaps:
        log.debug("  sitemap: %s", s.url)

    probes: list[SitemapProbe] = []
    for s in leaf_sitemaps:
        n_sampled, n_hits = _probe_sitemap(s)
        probe = SitemapProbe(s, n_sampled, n_hits)
        log.info("  probe %s: %d/%d hits (%.0f%%)", s.url, n_hits, n_sampled, probe.hit_rate * 100)
        probes.append(probe)

    selection = _select_recipe_sitemaps(probes, leaf_sitemaps)

    if selection.reason == "high_confidence":
        log.info(
            "High-confidence recipe sitemaps found (best %.0f%%); using %d sitemap(s) with ≥%.0f%% hit rate",
            selection.best_rate * 100, len(selection.sitemaps), _MEDIUM_HIT_RATE * 100,
        )
    elif selection.reason == "any_hits":
        log.info(
            "No dedicated recipe sitemap (best %.0f%%); using %d sitemap(s) with any hits",
            selection.best_rate * 100, len(selection.sitemaps),
        )
    else:
        log.warning("Probe found no recipe hits; falling back to all %d sitemap(s)", len(selection.sitemaps))

    urls: list[tuple[str, str]] = []
    for sitemap in selection.sitemaps:
        for page in sitemap.all_pages():
            url = page.url
            if url:
                log.debug("  + %s", url)
                urls.append((url, hostname))

    log.info("Matched %d URLs for %s", len(urls), hostname)
    if not urls:
        return 0

    inserted = db.insert_discovered_urls(urls)
    log.info("Inserted %d new URLs (skipped %d duplicates)", inserted, len(urls) - inserted)
    return inserted


def discover_all_sites() -> dict[str, int]:
    """Discover recipes from all configured sites. Returns {site: new_url_count}."""
    results: dict[str, int] = {}
    for site in settings.site_list:
        results[site] = discover_site(site)
    return results
