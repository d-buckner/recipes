import io
import logging
import queue
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

import requests
from PIL import Image
from recipe_scrapers import scrape_html
from recipe_scrapers._exceptions import NoSchemaFoundInWildMode, RecipeSchemaNotFound, WebsiteNotImplementedError

from . import db, embeddings, templatize
from .config import settings
from .models import RecipeRow

log = logging.getLogger(__name__)

# Sites with an active worker. Guarded by _active_lock.
# Prevents multiple workers from running against the same site in a single process.
_active_sites: set[str] = set()
_active_lock = threading.Lock()

# Embed requests from process_one() are dropped here; _run_embed_worker() drains it.
# None is the sentinel that tells the worker to stop.
_embed_queue: queue.Queue[tuple[int, dict] | None] = queue.Queue()

# Templatize requests from process_one() are dropped here; _run_templatize_worker() drains it.
_templatize_queue: queue.Queue[tuple[int, dict] | None] = queue.Queue()

CLAIM_TIMEOUT = 60  # seconds before a stale processing item is reclaimed (2x fetch timeout)
MAX_RETRIES = 3
THUMBNAIL_WIDTH = 480
HERO_WIDTH = 1200


def get_crawl_delay(hostname: str) -> float | None:
    """Fetch robots.txt for hostname and return the applicable Crawl-delay in seconds.

    Checks for our specific user-agent first, then falls back to '*'.
    Returns None if robots.txt is unreachable, missing the directive, or unparseable.
    """
    try:
        resp = requests.get(
            f"https://{hostname}/robots.txt",
            headers={"User-Agent": settings.user_agent},
            timeout=10,
        )
        if not resp.ok:
            return None
    except Exception:
        return None

    our_agent = settings.user_agent.split("/")[0].lower()
    delays: dict[str, float] = {}
    current_agents: list[str] = []

    for raw_line in resp.text.splitlines():
        line = raw_line.split("#")[0].strip()
        if not line:
            current_agents = []
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            current_agents.append(value.lower())
        elif key == "crawl-delay" and current_agents:
            try:
                delay = float(value)
                for agent in current_agents:
                    delays.setdefault(agent, delay)
            except ValueError:
                pass

    if our_agent in delays:
        return delays[our_agent]
    return delays.get("*")


def fetch_html(url: str) -> str:
    headers = {"User-Agent": settings.user_agent}
    log.debug("GET %s", url)
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    log.debug("  -> %d (%d bytes)", response.status_code, len(response.content))
    return response.text


def _split_csv_field(value: object) -> list[str]:
    """Normalise a field that recipe-scrapers may return as a comma-separated string."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(',') if v.strip()]


def parse_recipe(html: str, url: str) -> dict:
    try:
        scraper = scrape_html(html, org_url=url)
        data = scraper.to_json()
        log.debug("  parsed (supported site): %s", data.get("title"))
    except WebsiteNotImplementedError:
        log.debug("  site not supported, trying wild mode")
        scraper = scrape_html(html, org_url=url, supported_only=False)
        data = scraper.to_json()
        log.debug("  parsed (wild mode): %s", data.get("title"))
    for field in ('category', 'cuisine'):
        data[field] = _split_csv_field(data.get(field)) or None
    if not data.get('site_name'):
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ''
        data['site_name'] = host.removeprefix('www.').rpartition('.')[0] or host
    return data


def _resize_to_jpeg(img: Image.Image, max_width: int) -> bytes:
    """Resize a PIL image to at most max_width wide and return JPEG bytes."""
    w, h = img.size
    if w > max_width:
        new_h = int(h * max_width / w)
        img = img.resize((max_width, new_h), Image.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return buf.getvalue()


def download_images(image_url: str) -> tuple[bytes | None, bytes | None]:
    """
    Download an image and produce (thumbnail, hero) JPEG bytes.
    thumbnail: THUMBNAIL_WIDTH px wide — for card display.
    hero:      HERO_WIDTH px wide — for recipe detail page.
    Returns (None, None) on any failure — image download is best-effort.
    """
    try:
        resp = requests.get(image_url, headers={"User-Agent": settings.user_agent}, timeout=10)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        img.load()  # read data before BytesIO goes out of scope
        thumbnail = _resize_to_jpeg(img, THUMBNAIL_WIDTH)
        hero = _resize_to_jpeg(img, HERO_WIDTH)
        return thumbnail, hero
    except Exception as exc:
        log.debug("  image download failed for %s: %s", image_url, exc)
        return None, None


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
        thumbnail, hero = download_images(recipe_json["image"]) if recipe_json.get("image") else (None, None)
        db.save_recipe(recipe.id, recipe_json, thumbnail, hero)
        log.info("[%d] OK: %s", recipe.id, recipe_json["title"])
        if settings.embed_model:
            _embed_queue.put((recipe.id, recipe_json))
        if settings.inference_model:
            _templatize_queue.put((recipe.id, recipe_json))
        return True
    except (NoSchemaFoundInWildMode, RecipeSchemaNotFound) as exc:
        log.warning("[%d] FAIL (no schema): %s", recipe.id, exc)
        db.fail_recipe(recipe.id, f"No recipe schema found: {exc}", max_retries=max_retries)
        return False
    except Exception as exc:
        log.warning("[%d] FAIL: %s", recipe.id, exc)
        db.fail_recipe(recipe.id, str(exc), max_retries=max_retries)
        return False


def run_worker(delay: float | None = None, site: str | None = None) -> dict[str, int]:
    """
    Single-threaded worker loop for a specific site.
    Processes URLs until the queue for that site is empty.
    Returns counts: {processed, succeeded, failed}.
    """
    actual_delay = delay if delay is not None else settings.rate_limit_delay
    counts = {"processed": 0, "succeeded": 0, "failed": 0}

    while True:
        recipe = db.claim_next_url(claim_timeout=CLAIM_TIMEOUT, site=site)
        if recipe is None:
            log.info("Queue empty for site=%s, worker done.", site or "any")
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


def run_embed_backfill(job_id: int | None = None) -> dict[str, int]:
    """Re-embed all complete recipes from scratch.

    Clears existing embeddings and loops through every complete recipe as fast
    as the embedding API allows.  Intended to be run as a background task from
    the API (e.g. after changing the embedding model).
    """
    counts = {"processed": 0, "succeeded": 0, "failed": 0}
    if job_id is not None:
        db.start_job(job_id, message="Clearing existing embeddings")
    try:
        with db.get_conn() as conn:
            conn.execute("DELETE FROM vec_recipes")
        log.info("[embed backfill] cleared existing embeddings")

        ids = db.get_unembedded_ids()
        if job_id is not None:
            db.start_job(job_id, total=len(ids), message=f"Embedding {len(ids)} recipe(s)")
        log.info("[embed backfill] %d recipe(s) to embed", len(ids))
        for recipe_id in ids:
            recipe = db.get_recipe_by_id(recipe_id)
            embedded = False
            if recipe and recipe.recipe_json:
                text = embeddings.build_recipe_text(recipe.recipe_json)
                vector = embeddings.get_embedding(text)
                if vector:
                    db.store_embedding(recipe_id, vector)
                    counts["succeeded"] += 1
                    embedded = True
                    log.info("[embed backfill] %d OK: %s", recipe_id, recipe.recipe_json.get("title", ""))
                else:
                    counts["failed"] += 1
                    log.warning("[embed backfill] %d FAIL", recipe_id)
            else:
                counts["failed"] += 1
                log.warning("[embed backfill] %d FAIL — no recipe_json", recipe_id)
            counts["processed"] += 1
            if job_id is not None:
                db.update_job_progress(
                    job_id,
                    processed_delta=1,
                    succeeded_delta=1 if embedded else 0,
                    failed_delta=0 if embedded else 1,
                )
        message = "Embedding backfill complete"
        if counts["failed"]:
            message = f"Embedding backfill complete with {counts['failed']} failure(s)"
        if job_id is not None:
            db.finish_job(job_id, "succeeded", message)
        log.info("[embed backfill] done — embedded=%d failed=%d", counts["succeeded"], counts["failed"])
        return counts
    except Exception as exc:
        if job_id is not None:
            db.finish_job(job_id, "failed", str(exc))
        raise


def _run_embed_worker() -> dict[str, int]:
    """Drain _embed_queue, embedding each recipe as it arrives from process_one().

    Exits when it receives the None sentinel (sent by run_workers() after all
    scrape workers finish).
    """
    counts = {"embedded": 0, "failed": 0}
    while True:
        item = _embed_queue.get()
        if item is None:  # sentinel — scraping is done
            break
        recipe_id, recipe_json = item
        text = embeddings.build_recipe_text(recipe_json)
        vector = embeddings.get_embedding(text)
        if vector:
            db.store_embedding(recipe_id, vector)
            counts["embedded"] += 1
            log.info("[embed] %d OK: %s", recipe_id, recipe_json.get("title", ""))
        else:
            counts["failed"] += 1
            log.warning("[embed] %d FAIL", recipe_id)
    return counts


def _run_templatize_worker() -> dict[str, int]:
    """Drain _templatize_queue, templatizing each recipe as it arrives from process_one().

    Exits when it receives the None sentinel (sent by run_workers() after all
    scrape workers finish).
    """
    counts = {"templatized": 0, "failed": 0}
    while True:
        item = _templatize_queue.get()
        if item is None:
            break
        recipe_id, recipe_json = item
        ing_tmpl, instr_tmpl = templatize.templatize_recipe(recipe_json)
        if ing_tmpl is not None or instr_tmpl is not None:
            db.save_recipe_templates(recipe_id, ing_tmpl, instr_tmpl)
            counts["templatized"] += 1
            log.info("[templatize] %d OK: %s", recipe_id, recipe_json.get("title", ""))
        else:
            counts["failed"] += 1
            log.warning("[templatize] %d FAIL", recipe_id)
    return counts


def run_templatize_backfill(job_id: int | None = None) -> dict[str, int]:
    """Templatize all complete recipes that don't have templates yet.

    Intended to be run as a background task from the API (e.g. after enabling
    the inference model for the first time or changing it).
    """
    counts = {"processed": 0, "succeeded": 0, "failed": 0}
    if job_id is not None:
        db.start_job(job_id, message="Finding recipes to templatize")
    try:
        ids = db.get_untemplatized_ids()
        if job_id is not None:
            db.start_job(job_id, total=len(ids), message=f"Templatizing {len(ids)} recipe(s)")
        log.info("[templatize backfill] %d recipe(s) to process", len(ids))
        for recipe_id in ids:
            recipe = db.get_recipe_by_id(recipe_id)
            ok = False
            if recipe and recipe.recipe_json:
                ing_tmpl, instr_tmpl = templatize.templatize_recipe(recipe.recipe_json)
                if ing_tmpl is not None or instr_tmpl is not None:
                    db.save_recipe_templates(recipe_id, ing_tmpl, instr_tmpl)
                    counts["succeeded"] += 1
                    ok = True
                    log.info("[templatize backfill] %d OK: %s", recipe_id, recipe.recipe_json.get("title", ""))
                else:
                    counts["failed"] += 1
                    log.warning("[templatize backfill] %d FAIL", recipe_id)
            else:
                counts["failed"] += 1
                log.warning("[templatize backfill] %d FAIL — no recipe_json", recipe_id)
            counts["processed"] += 1
            if job_id is not None:
                db.update_job_progress(
                    job_id,
                    processed_delta=1,
                    succeeded_delta=1 if ok else 0,
                    failed_delta=0 if ok else 1,
                )
        message = "Templatize backfill complete"
        if counts["failed"]:
            message = f"Templatize backfill complete with {counts['failed']} failure(s)"
        if job_id is not None:
            db.finish_job(job_id, "succeeded", message)
        log.info("[templatize backfill] done — succeeded=%d failed=%d", counts["succeeded"], counts["failed"])
        return counts
    except Exception as exc:
        if job_id is not None:
            db.finish_job(job_id, "failed", str(exc))
        raise


def run_workers(delay: float | None = None, job_id: int | None = None) -> dict[str, int]:
    """
    Spawn one worker thread per site that has pending work.
    Sites that already have an active worker (from a previous call still running)
    are skipped, so at most one worker per site is ever active in this process.
    If RECIPES_EMBED_MODEL is configured, also runs a background embed worker
    that throttles embedding requests alongside scraping.
    Returns combined counts for the workers started by this call.
    """
    totals: dict[str, int] = {"processed": 0, "succeeded": 0, "failed": 0}
    try:
        actual_delay = delay if delay is not None else settings.rate_limit_delay

        reset = db.reset_stale_processing()
        if reset:
            log.info("Reset %d stale processing item(s) back to discovered", reset)

        pending_sites = db.list_pending_sites()

        with _active_lock:
            sites_to_start = [s for s in pending_sites if s not in _active_sites]
            _active_sites.update(sites_to_start)

        total_pending = db.count_pending_urls(sites_to_start)
        if job_id is not None:
            db.start_job(job_id, total=total_pending, message=f"Starting workers for {len(sites_to_start)} site(s)")

        if not sites_to_start:
            log.info("No new sites to start (all pending sites already have active workers).")
            if job_id is not None:
                db.finish_job(job_id, "succeeded", "No pending sites to scrape")
            return totals

        log.info("Starting workers for: %s", sites_to_start)

        def _run_and_release(site: str) -> dict[str, int]:
            crawl_delay = get_crawl_delay(site)
            if crawl_delay is not None:
                log.info("robots.txt Crawl-delay for %s: %.1fs", site, crawl_delay)
            else:
                crawl_delay = actual_delay
                log.info("No Crawl-delay in robots.txt for %s, using default %.1fs", site, crawl_delay)
            try:
                return run_worker(crawl_delay, site)
            finally:
                with _active_lock:
                    _active_sites.discard(site)

        embed_future: Future | None = None
        templatize_future: Future | None = None

        n_workers = len(sites_to_start) + (1 if settings.embed_model else 0) + (1 if settings.inference_model else 0)
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            if settings.embed_model:
                embed_future = executor.submit(_run_embed_worker)
                log.info("Embed worker started")
            if settings.inference_model:
                templatize_future = executor.submit(_run_templatize_worker)
                log.info("Templatize worker started")

            scrape_futures = [executor.submit(_run_and_release, site) for site in sites_to_start]
            for future in as_completed(scrape_futures):
                result = future.result()
                for key in totals:
                    totals[key] += result[key]
                if job_id is not None:
                    db.update_job_progress(
                        job_id,
                        processed_delta=result["processed"],
                        succeeded_delta=result["succeeded"],
                        failed_delta=result["failed"],
                    )

            # All scrape workers done — send sentinels to stop background workers
            if embed_future is not None:
                _embed_queue.put(None)
                embed_result = embed_future.result()
                log.info("Embed worker done: embedded=%d failed=%d", embed_result["embedded"], embed_result["failed"])
            if templatize_future is not None:
                _templatize_queue.put(None)
                templatize_result = templatize_future.result()
                log.info("Templatize worker done: templatized=%d failed=%d", templatize_result["templatized"], templatize_result["failed"])

        if job_id is not None:
            db.finish_job(job_id, "succeeded", "Scrape complete")
        return totals
    except Exception as exc:
        if job_id is not None:
            db.finish_job(job_id, "failed", str(exc))
        raise
