import responses as rsps_lib
import pytest

from recipes import db
from recipes.scraper import fetch_html, parse_recipe, process_one


def test_parse_recipe_from_html(recipe_html):
    result = parse_recipe(recipe_html, "https://example.com/recipes/chicken-soup")
    assert result["title"] == "Classic Chicken Soup"
    assert len(result["ingredients"]) == 5
    assert result["total_time"] == 45


@rsps_lib.activate
def test_fetch_html():
    rsps_lib.add(rsps_lib.GET, "https://example.com/recipes/soup", body="<html>test</html>", status=200)
    html = fetch_html("https://example.com/recipes/soup")
    assert html == "<html>test</html>"


@rsps_lib.activate
def test_process_one_success(mem_db, recipe_html):
    db.insert_discovered_urls([("https://example.com/recipes/chicken-soup", "example.com")])
    recipe = db.claim_next_url()

    rsps_lib.add(rsps_lib.GET, recipe.url, body=recipe_html, status=200)
    success = process_one(recipe)

    assert success is True
    saved = db.get_recipe_by_id(recipe.id)
    assert saved.status.value == "complete"
    assert saved.recipe_json["title"] == "Classic Chicken Soup"


@rsps_lib.activate
def test_process_one_http_error(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/missing", "example.com")])
    recipe = db.claim_next_url()

    rsps_lib.add(rsps_lib.GET, recipe.url, status=404)
    success = process_one(recipe, max_retries=1)

    assert success is False
    failed = db.get_recipe_by_id(recipe.id)
    assert failed.status.value == "failed"
    assert failed.retry_count == 1


@rsps_lib.activate
def test_process_one_no_schema(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/noschema", "example.com")])
    recipe = db.claim_next_url()

    rsps_lib.add(rsps_lib.GET, recipe.url, body="<html><body>No recipe here</body></html>", status=200)
    success = process_one(recipe, max_retries=1)

    assert success is False
    failed = db.get_recipe_by_id(recipe.id)
    assert failed.status.value == "failed"
    assert failed.retry_count == 1


@rsps_lib.activate
def test_process_one_retries_before_permanent_failure(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/flaky", "example.com")])
    recipe = db.claim_next_url()

    rsps_lib.add(rsps_lib.GET, recipe.url, status=503)
    success = process_one(recipe, max_retries=3)

    assert success is False
    requeued = db.get_recipe_by_id(recipe.id)
    assert requeued.status.value == "discovered"
    assert requeued.retry_count == 1
