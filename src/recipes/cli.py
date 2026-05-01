import logging

import click

from . import db, discovery, embeddings, scraper
from .config import settings


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet down noisy third-party loggers
    logging.getLogger("usp").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


@click.group()
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Recipe scraper CLI."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _setup_logging(verbose)
    db.init_db(settings.db_path)


@cli.command()
@click.option("--delay", default=None, type=float, help="Rate limit delay in seconds (overrides env).")
@click.option("--sitemap", default=None, help="Use a specific sitemap XML URL instead of homepage discovery.")
def scrape(delay: float | None, sitemap: str | None) -> None:
    """Discover recipes from configured sites and scrape them."""
    if sitemap:
        click.echo(f"Discovering from sitemap: {sitemap}")
        count = discovery.discover_from_sitemap_url(sitemap)
        click.echo(f"  {count} new URLs discovered")
        total_discovered = count
    else:
        sites = settings.site_list
        if not sites:
            click.echo("No sites configured. Set RECIPES_SITES env var.")
            raise SystemExit(1)

        click.echo(f"Discovering recipes from {len(sites)} site(s)...")
        results = discovery.discover_all_sites()
        for site, count in results.items():
            click.echo(f"  {site}: {count} new URLs discovered")
        total_discovered = sum(results.values())

    click.echo(f"\nTotal new URLs: {total_discovered}")
    click.echo("Starting scraper workers...")

    counts = scraper.run_workers(delay=delay)
    click.echo(
        f"\nDone. Processed: {counts['processed']}, "
        f"Succeeded: {counts['succeeded']}, "
        f"Failed: {counts['failed']}"
    )


@cli.command()
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=8000, show_default=True)
@click.option("--reload", is_flag=True, default=False)
def serve(host: str, port: int, reload: bool) -> None:
    """Start the recipe API server."""
    import uvicorn
    uvicorn.run("recipes.api:create_app", factory=True, host=host, port=port, reload=reload)


@cli.command()
@click.option("--reset", is_flag=True, default=False, help="Re-embed all complete recipes, not just missing ones.")
@click.option("--batch-size", default=50, show_default=True, help="Number of recipes to process per batch.")
def embed(reset: bool, batch_size: int) -> None:
    """Generate embeddings for recipes (requires RECIPES_EMBED_MODEL)."""
    if not settings.embed_model:
        click.echo("RECIPES_EMBED_MODEL is not set — embedding is disabled.")
        raise SystemExit(1)

    if reset:
        with db.get_conn() as conn:
            conn.execute("DELETE FROM vec_recipes")
        click.echo("Cleared all existing embeddings.")

    ids = db.get_unembedded_ids()
    if not ids:
        click.echo("No recipes need embedding.")
        return

    click.echo(f"Embedding {len(ids)} recipe(s) using model '{settings.embed_model}'...")
    succeeded = 0
    failed = 0
    for i in range(0, len(ids), batch_size):
        batch = ids[i: i + batch_size]
        for recipe_id in batch:
            recipe = db.get_recipe_by_id(recipe_id)
            if recipe is None or recipe.recipe_json is None:
                failed += 1
                continue
            text = embeddings.build_recipe_text(recipe.recipe_json)
            vector = embeddings.get_embedding(text)
            if vector:
                db.store_embedding(recipe_id, vector)
                succeeded += 1
            else:
                failed += 1
        click.echo(f"  [{min(i + batch_size, len(ids))}/{len(ids)}] succeeded={succeeded} failed={failed}")

    click.echo(f"\nDone. Embedded: {succeeded}, Failed: {failed}")


@cli.command()
def stats() -> None:
    """Print database statistics."""
    s = db.get_stats()
    click.echo(f"Total recipes : {s.total}")
    click.echo(f"  Discovered  : {s.discovered}")
    click.echo(f"  Processing  : {s.processing}")
    click.echo(f"  Complete    : {s.complete}")
    click.echo(f"  Failed      : {s.failed}")
    click.echo(f"Favorites     : {s.favorites}")
