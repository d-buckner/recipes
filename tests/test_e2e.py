"""
End-to-end test: add alisoneroman.com via the UI, run discovery + scraping,
and verify that completed recipe cards render with real content.

This test makes live network requests and takes several minutes to run.
Run it in isolation:
    uv run python3 -m pytest tests/test_e2e.py -v -s -m e2e

Prerequisites (one-time setup):
    uv run playwright install chromium
    npm install  (inside the ui/ directory)
"""

import json
import os
import sqlite3
import subprocess
import time
import urllib.request

import pytest
from playwright.sync_api import sync_playwright, expect

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "recipes.db")
UI_DIR = os.path.join(PROJECT_ROOT, "ui")

API_URL = "http://localhost:8000"
UI_URL = "http://localhost:5173"

TARGET_SITE = "https://www.alisoneroman.com"
MIN_COMPLETE = 5           # recipes that must be fully scraped before we assert
DISCOVERY_TIMEOUT_MS = 5 * 60 * 1000   # Playwright timeout for discovery step
SCRAPE_POLL_SECS = 15 * 60             # total seconds to wait for MIN_COMPLETE recipes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for_server(url: str, timeout: float = 45.0) -> None:
    """Poll a URL until it returns HTTP 200 or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3):
                return
        except Exception:
            time.sleep(1.5)
    raise RuntimeError(f"Server at {url} did not become ready within {timeout}s")


def _get_stats() -> dict:
    try:
        with urllib.request.urlopen(f"{API_URL}/stats", timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def _titled_recipe_count() -> int:
    """Count complete recipes that have a real title (not empty/collection pages)."""
    try:
        with urllib.request.urlopen(f"{API_URL}/recipes?limit=100", timeout=5) as resp:
            recipes = json.loads(resp.read())
            return sum(
                1 for r in recipes
                if r.get("title") and r["title"] != "Untitled Recipe"
            )
    except Exception:
        return 0


def _kill_port(port: int) -> None:
    """Kill any process already listening on the given port."""
    result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
    pids = result.stdout.strip().split()
    for pid in pids:
        subprocess.run(["kill", "-9", pid], check=False)
    if pids:
        time.sleep(1)  # give the OS a moment to release the port


def _clear_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        "DELETE FROM favorites; DELETE FROM scrape_runs; DELETE FROM recipes;"
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api_server():
    # Kill → clear → start: ensures no stale process can write between clear and start
    _kill_port(8000)
    _clear_db()
    proc = subprocess.Popen(
        ["uv", "run", "recipes", "serve"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_server(f"{API_URL}/stats")
    yield
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="module")
def ui_server():
    _kill_port(5173)
    proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=UI_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_server(UI_URL, timeout=45.0)
    yield
    proc.terminate()
    proc.wait()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_add_site_scrape_and_view_recipes(api_server, ui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1. Load the app
        page.goto(UI_URL)
        expect(page.get_by_text("+ Add Site")).to_be_visible(timeout=10_000)

        # 2. Open the Add Site dropdown
        page.get_by_text("+ Add Site").click()
        expect(page.locator(".add-site-dropdown")).to_be_visible()

        # 3. Enter the site URL
        page.locator("#site-search").fill(TARGET_SITE)

        # 4. Trigger discovery + scraping in one step; probing sitemaps takes several minutes
        page.get_by_role("button", name="Add Site").click()
        expect(page.locator(".add-site-result")).to_be_visible(timeout=DISCOVERY_TIMEOUT_MS)

        # 5. Confirm URLs were discovered
        result_text = page.locator(".add-site-result").text_content() or ""
        assert "Already up to date" not in result_text, (
            f"Expected new recipe URLs to be discovered for {TARGET_SITE}, "
            f"got: {result_text!r}"
        )

        # Dropdown auto-closes after 2.5 s; no manual dismiss needed

        # 6. Poll the API until at least MIN_COMPLETE recipes with real titles are scraped
        deadline = time.time() + SCRAPE_POLL_SECS
        while time.time() < deadline:
            if _titled_recipe_count() >= MIN_COMPLETE:
                break
            time.sleep(10)
        else:
            stats = _get_stats()
            pytest.fail(
                f"Timed out waiting for {MIN_COMPLETE} titled recipes. "
                f"Stats: {stats}"
            )

        # 7. Reload so the recipe grid fetches the newly scraped recipes
        page.reload()
        expect(page.locator(".recipe-card").first).to_be_visible(timeout=15_000)

        # 8. Verify recipe cards have real content
        cards = page.locator(".recipe-card")
        card_count = cards.count()
        assert card_count >= MIN_COMPLETE, (
            f"Expected at least {MIN_COMPLETE} recipe cards, found {card_count}"
        )

        for card in cards.all()[:MIN_COMPLETE]:
            title = (card.locator(".card-title").text_content() or "").strip()
            assert title and title != "Untitled Recipe", (
                f"Recipe card has no meaningful title: {title!r}"
            )

            site = (card.locator(".card-site").text_content() or "").strip()
            assert "alisoneroman" in site.lower(), (
                f"Expected alisoneroman.com attribution, got: {site!r}"
            )

        # 9. Click the first card and verify the recipe detail page loads
        first_title = (cards.first.locator(".card-title").text_content() or "").strip()
        cards.first.click()
        page.wait_for_url("**/recipe/**", timeout=5_000)
        # Recipe page should show the title in the page heading (not a card-title)
        expect(page.locator(".recipe-page-title")).to_be_visible(timeout=5_000)
        page_title = (page.locator(".recipe-page-title").text_content() or "").strip()
        assert first_title in page_title or page_title in first_title, (
            f"Recipe page title {page_title!r} doesn't match card title {first_title!r}"
        )

        browser.close()
