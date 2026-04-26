import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests
from usp.tree import sitemap_tree_for_homepage

from . import db
from .config import settings

log = logging.getLogger(__name__)

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


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


def discover_site(site_url: str, url_filter: str | None = None) -> int:
    """
    Crawl sitemaps for a site via robots.txt, filter recipe URLs, insert into db.

    usp reads robots.txt automatically and follows the sitemap tree. If any leaf
    sitemaps have "recipe" in their URL they are preferred; otherwise all leaves
    are searched and the URL filter pattern is the primary gate.

    Returns the number of new URLs discovered.
    """
    pattern = re.compile(url_filter or settings.url_filter_pattern, re.IGNORECASE)
    hostname = urlparse(site_url).netloc
    log.info("Crawling sitemaps for %s (filter: %s)", hostname, pattern.pattern)

    tree = sitemap_tree_for_homepage(site_url)

    leaf_sitemaps = _collect_leaf_sitemaps(tree)
    log.info("Found %d leaf sitemap(s)", len(leaf_sitemaps))
    for s in leaf_sitemaps:
        log.debug("  sitemap: %s", s.url)

    # Prefer recipe-specific sub-sitemaps when the site names them explicitly
    recipe_leaves = [s for s in leaf_sitemaps if re.search(r"recipe", s.url or "", re.IGNORECASE)]
    if recipe_leaves:
        log.info("Using %d recipe-specific sitemap(s)", len(recipe_leaves))
        selected = recipe_leaves
    else:
        selected = leaf_sitemaps

    urls: list[tuple[str, str]] = []
    for sitemap in selected:
        for page in sitemap.all_pages():
            url = page.url
            if url and pattern.search(url):
                log.debug("  + %s", url)
                urls.append((url, hostname))

    log.info("Matched %d URLs for %s", len(urls), hostname)
    if not urls:
        return 0

    inserted = db.insert_discovered_urls(urls)
    log.info("Inserted %d new URLs (skipped %d duplicates)", inserted, len(urls) - inserted)
    return inserted


def discover_all_sites(url_filter: str | None = None) -> dict[str, int]:
    """Discover recipes from all configured sites. Returns {site: new_url_count}."""
    results: dict[str, int] = {}
    for site in settings.site_list:
        count = discover_site(site, url_filter)
        results[site] = count
    return results
