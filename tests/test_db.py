import pytest

from recipes import db


def test_insert_discovered_urls(mem_db):
    count = db.insert_discovered_urls([
        ("https://example.com/recipes/soup", "example.com"),
        ("https://example.com/recipes/pasta", "example.com"),
    ])
    assert count == 2


def test_insert_discovered_urls_idempotent(mem_db):
    urls = [("https://example.com/recipes/soup", "example.com")]
    db.insert_discovered_urls(urls)
    count = db.insert_discovered_urls(urls)
    assert count == 0  # already exists, INSERT OR IGNORE


def test_claim_next_url_returns_none_when_empty(mem_db):
    result = db.claim_next_url()
    assert result is None


def test_claim_next_url_marks_processing(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/soup", "example.com")])
    recipe = db.claim_next_url()
    assert recipe is not None
    assert recipe.status.value == "processing"
    assert recipe.url == "https://example.com/recipes/soup"


def test_claim_next_url_fifo(mem_db):
    db.insert_discovered_urls([
        ("https://example.com/recipes/soup", "example.com"),
        ("https://example.com/recipes/pasta", "example.com"),
    ])
    first = db.claim_next_url()
    assert first.url == "https://example.com/recipes/soup"


def test_save_recipe(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/soup", "example.com")])
    recipe = db.claim_next_url()
    recipe_json = {
        "title": "Chicken Soup",
        "description": "Hearty soup",
        "ingredients": ["chicken", "carrots"],
        "keywords": ["soup", "chicken"],
        "total_time": 45,
        "yields": "4 servings",
    }
    db.save_recipe(recipe.id, recipe_json)

    saved = db.get_recipe_by_id(recipe.id)
    assert saved.status.value == "complete"
    assert saved.recipe_json["title"] == "Chicken Soup"


def test_fail_recipe_requeues_before_max_retries(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/soup", "example.com")])
    recipe = db.claim_next_url()
    db.fail_recipe(recipe.id, "Connection timeout", max_retries=3)

    requeued = db.get_recipe_by_id(recipe.id)
    assert requeued.status.value == "discovered"
    assert requeued.retry_count == 1
    assert requeued.error_msg == "Connection timeout"


def test_fail_recipe_permanent_after_max_retries(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/soup", "example.com")])
    recipe = db.claim_next_url()
    db.fail_recipe(recipe.id, "Connection timeout", max_retries=1)

    failed = db.get_recipe_by_id(recipe.id)
    assert failed.status.value == "failed"
    assert failed.retry_count == 1
    assert failed.error_msg == "Connection timeout"


def test_search_recipes(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/soup", "example.com")])
    recipe = db.claim_next_url()
    db.save_recipe(recipe.id, {
        "title": "Chicken Soup",
        "description": "Hearty chicken soup",
        "ingredients": ["chicken", "carrots", "celery"],
        "keywords": ["soup", "chicken", "comfort"],
        "total_time": 45,
        "yields": "4 servings",
    })

    results = db.search_recipes('"chicken"')
    assert len(results) >= 1
    assert results[0].title == "Chicken Soup"


def test_favorites_workflow(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/soup", "example.com")])
    recipe = db.claim_next_url()
    db.save_recipe(recipe.id, {"title": "Soup", "description": "", "ingredients": [], "keywords": []})

    db.add_favorite(recipe.id)
    favorites = db.list_favorites()
    assert len(favorites) == 1
    assert favorites[0].id == recipe.id
    assert favorites[0].is_favorite is True

    db.remove_favorite(recipe.id)
    favorites = db.list_favorites()
    assert len(favorites) == 0


def test_get_stats(mem_db):
    db.insert_discovered_urls([
        ("https://example.com/recipes/soup", "example.com"),
        ("https://example.com/recipes/pasta", "example.com"),
    ])
    stats = db.get_stats()
    assert stats.total == 2
    assert stats.discovered == 2
    assert stats.complete == 0
    assert stats.favorites == 0
