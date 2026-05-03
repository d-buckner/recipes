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
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT title, author, total_time, cuisine_json, category_json FROM recipes WHERE id = ?",
            (recipe.id,),
        ).fetchone()
    assert row["title"] == "Chicken Soup"
    assert row["total_time"] == 45


def test_list_recipes_uses_canonical_filters(mem_db):
    db.insert_discovered_urls([
        ("https://example.com/recipes/soup", "example.com"),
        ("https://example.com/recipes/tacos", "example.com"),
    ])
    soup = db.claim_next_url()
    db.save_recipe(soup.id, {
        "title": "Chicken Soup",
        "description": "",
        "ingredients": ["chicken"],
        "keywords": [],
        "author": "Alice",
        "total_time": 45,
        "cuisine": ["American"],
        "category": ["Soup"],
    })
    tacos = db.claim_next_url()
    db.save_recipe(tacos.id, {
        "title": "Fish Tacos",
        "description": "",
        "ingredients": ["fish"],
        "keywords": [],
        "author": "Bob",
        "total_time": 20,
        "cuisine": ["Mexican"],
        "category": ["Dinner"],
    })

    results = db.list_recipes(author=["Alice"], cuisine=["American"], max_time=60)
    assert [r.title for r in results] == ["Chicken Soup"]


def test_init_db_backfills_canonical_columns(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/soup", "example.com")])
    recipe = db.claim_next_url()
    db.save_recipe(recipe.id, {
        "title": "Chicken Soup",
        "description": "",
        "ingredients": ["chicken"],
        "keywords": [],
        "author": "Alice",
        "total_time": 45,
        "cuisine": ["American"],
        "category": ["Soup"],
    })
    with db.get_conn() as conn:
        conn.execute(
            """
            UPDATE recipes
            SET title = NULL, author = NULL, total_time = NULL,
                cuisine_json = NULL, category_json = NULL
            WHERE id = ?
            """,
            (recipe.id,),
        )

    db.init_db()

    results = db.list_recipes(author=["Alice"], cuisine=["American"], max_time=60)
    assert [r.title for r in results] == ["Chicken Soup"]


def test_mark_unavailable(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/paywalled", "example.com")])
    recipe = db.claim_next_url()
    db.mark_unavailable(recipe.id, "No recipe content found (possible paywall)")

    saved = db.get_recipe_by_id(recipe.id)
    assert saved.status.value == "unavailable"
    assert saved.retry_count == 0  # not incremented — no retries
    assert "paywall" in saved.error_msg


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
    assert stats.unavailable == 0
    assert stats.favorites == 0


def test_get_stats_counts_unavailable(mem_db):
    db.insert_discovered_urls([("https://example.com/recipes/paywalled", "example.com")])
    recipe = db.claim_next_url()
    db.mark_unavailable(recipe.id, "No recipe content found (possible paywall)")

    stats = db.get_stats()
    assert stats.unavailable == 1
    assert stats.failed == 0


def test_job_lifecycle(mem_db):
    job_id = db.create_job("scrape", total=2, message="Queued")
    job = db.get_job(job_id)
    assert job is not None
    assert job.status == "queued"
    assert job.total == 2

    db.start_job(job_id, message="Running")
    db.update_job_progress(job_id, processed_delta=1, succeeded_delta=1)
    db.finish_job(job_id, "succeeded", "Done")

    job = db.get_job(job_id)
    assert job.status == "succeeded"
    assert job.processed == 1
    assert job.succeeded == 1
    assert job.failed == 0
    assert job.message == "Done"
    assert job.started_at is not None
    assert job.finished_at is not None
