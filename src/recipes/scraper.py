import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image
from recipe_scrapers import scrape_html
from recipe_scrapers._exceptions import NoSchemaFoundInWildMode, RecipeSchemaNotFound, WebsiteNotImplementedError

from . import db
from .config import settings
from .models import RecipeRow

log = logging.getLogger(__name__)

CLAIM_TIMEOUT = 60  # seconds before a stale processing item is reclaimed (2x fetch timeout)
MAX_RETRIES = 3
THUMBNAIL_WIDTH = 480


def fetch_html(url: str) -> str:
    headers = {"User-Agent": settings.user_agent}
    log.debug("GET %s", url)
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    log.debug("  -> %d (%d bytes)", response.status_code, len(response.content))
    return response.text


def parse_recipe(html: str, url: str) -> dict:
    try:
        scraper = scrape_html(html, org_url=url)
        data = scraper.to_json()
        log.debug("  parsed (supported site): %s", data.get("title"))
        return data
    except WebsiteNotImplementedError:
        log.debug("  site not supported, trying wild mode")
        scraper = scrape_html(html, org_url=url, supported_only=False)
        data = scraper.to_json()
        log.debug("  parsed (wild mode): %s", data.get("title"))
        return data


def make_thumbnail(image_url: str) -> bytes | None:
    """
    Download an image and resize it to a THUMBNAIL_WIDTH-wide JPEG.
    Returns None on any failure — thumbnail generation is best-effort.
    """
    try:
        resp = requests.get(image_url, headers={"User-Agent": settings.user_agent}, timeout=10)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        img.load()  # read data before BytesIO goes out of scope
        w, h = img.size
        if w > THUMBNAIL_WIDTH:
            new_h = int(h * THUMBNAIL_WIDTH / w)
            img = img.resize((THUMBNAIL_WIDTH, new_h), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82, optimize=True)
        return buf.getvalue()
    except Exception as exc:
        log.debug("  thumbnail failed for %s: %s", image_url, exc)
        return None


def _has_recipe_content(data: dict) -> bool:
    """A saved recipe must have a title and at least ingredients or instructions."""
    return bool(data.get("title")) and bool(data.get("ingredients") or data.get("instructions"))


def process_one(recipe: RecipeRow, max_retries: int = MAX_RETRIES) -> bool:
    """Fetch, parse, and save a single recipe. Returns True on success."""
    attempt = recipe.retry_count + 1
    log.info("[%d] Scraping %s (attempt %d/%d)", recipe.id, recipe.url, attempt, max_retries)
    try:
        html = fetch_html(recipe.url)
        recipe_json = parse_recipe(html, recipe.url)
        if not _has_recipe_content(recipe_json):
            log.warning("[%d] UNAVAILABLE (no recipe content): %s", recipe.id, recipe.url)
            db.mark_unavailable(recipe.id, "No recipe content found (possible paywall)")
            return False
        thumbnail = make_thumbnail(recipe_json["image"]) if recipe_json.get("image") else None
        db.save_recipe(recipe.id, recipe_json, thumbnail)
        log.info("[%d] OK: %s", recipe.id, recipe_json["title"])
        return True
    except (NoSchemaFoundInWildMode, RecipeSchemaNotFound) as exc:
        log.warning("[%d] FAIL (no schema): %s", recipe.id, exc)
        db.fail_recipe(recipe.id, f"No recipe schema found: {exc}", max_retries=max_retries)
        return False
    except Exception as exc:
        log.warning("[%d] FAIL: %s", recipe.id, exc)
        db.fail_recipe(recipe.id, str(exc), max_retries=max_retries)
        return False


def run_worker(delay: float | None = None) -> dict[str, int]:
    """
    Single-threaded worker loop. Processes URLs until the queue is empty.
    Returns counts: {processed, succeeded, failed}.
    """
    actual_delay = delay if delay is not None else settings.rate_limit_delay
    counts = {"processed": 0, "succeeded": 0, "failed": 0}

    while True:
        recipe = db.claim_next_url(claim_timeout=CLAIM_TIMEOUT)
        if recipe is None:
            log.info("Queue empty, worker done.")
            break
        if counts["processed"] > 0:
            log.debug("Rate limit: sleeping %.1fs", actual_delay)
            time.sleep(actual_delay)
        success = process_one(recipe)
        counts["processed"] += 1
        if success:
            counts["succeeded"] += 1
        else:
            counts["failed"] += 1

    return counts


def run_workers(max_workers: int | None = None, delay: float | None = None) -> dict[str, int]:
    """
    Multi-threaded worker pool. Each thread runs its own loop.
    Returns combined counts.
    """
    workers = max_workers if max_workers is not None else settings.max_workers
    actual_delay = delay if delay is not None else settings.rate_limit_delay

    reset = db.reset_stale_processing()
    if reset:
        log.info("Reset %d stale processing item(s) back to discovered", reset)

    log.info("Starting %d worker(s) with %.1fs delay", workers, actual_delay)

    if workers <= 1:
        return run_worker(actual_delay)

    totals = {"processed": 0, "succeeded": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(run_worker, actual_delay) for _ in range(workers)]
        for future in as_completed(futures):
            result = future.result()
            for key in totals:
                totals[key] += result[key]

    return totals
