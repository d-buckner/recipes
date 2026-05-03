import pytest
from fastapi.testclient import TestClient

from recipes import db
from recipes.api import app
from recipes.config import settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db(mem_db):
    """Use in-memory db for all API tests."""
    pass


def _seed_recipe(title: str = "Chicken Soup", url: str = "https://example.com/recipes/soup") -> int:
    db.insert_discovered_urls([(url, "example.com")])
    recipe = db.claim_next_url()
    db.save_recipe(recipe.id, {
        "title": title,
        "description": "A hearty soup",
        "ingredients": ["chicken", "carrots"],
        "keywords": ["soup", "chicken"],
        "total_time": 45,
        "yields": "4 servings",
        "image": None,
    })
    return recipe.id


def test_search_returns_results(monkeypatch):
    monkeypatch.setattr(settings, "embed_model", "")
    _seed_recipe()
    resp = client.get("/search", params={"q": "chicken"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["title"] == "Chicken Soup"
    assert resp.headers["X-Recipes-Search-Mode-Requested"] == "hybrid"
    assert resp.headers["X-Recipes-Search-Mode-Used"] == "keyword"
    assert resp.headers["X-Recipes-Search-Degraded"] == "true"
    assert resp.headers["X-Recipes-Search-Degraded-Reason"] == "embedding_model_not_configured"


def test_keyword_search_reports_mode_without_degradation():
    _seed_recipe()
    resp = client.get("/search", params={"q": "chicken", "mode": "keyword"})
    assert resp.status_code == 200
    assert resp.headers["X-Recipes-Search-Mode-Requested"] == "keyword"
    assert resp.headers["X-Recipes-Search-Mode-Used"] == "keyword"
    assert resp.headers["X-Recipes-Search-Degraded"] == "false"


def test_search_capabilities(monkeypatch):
    monkeypatch.setattr(settings, "embed_model", "")
    resp = client.get("/search/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_mode"] == "hybrid"
    assert data["semantic_enabled"] is False


def test_search_no_results():
    resp = client.get("/search", params={"q": "zzznoresults"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_recipe():
    recipe_id = _seed_recipe()
    resp = client.get(f"/recipes/{recipe_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == recipe_id
    assert data["recipe_json"]["title"] == "Chicken Soup"


def test_get_recipe_not_found():
    resp = client.get("/recipes/99999")
    assert resp.status_code == 404


def test_add_and_remove_favorite():
    recipe_id = _seed_recipe()

    resp = client.post(f"/favorites/{recipe_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "added"

    resp = client.get("/favorites")
    assert resp.status_code == 200
    favs = resp.json()
    assert any(f["id"] == recipe_id for f in favs)

    resp = client.delete(f"/favorites/{recipe_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "removed"

    resp = client.get("/favorites")
    assert resp.json() == []


def test_add_favorite_not_found():
    resp = client.post("/favorites/99999")
    assert resp.status_code == 404


def test_stats():
    _seed_recipe()
    resp = client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["complete"] >= 1


def test_start_scrape_returns_trackable_job():
    resp = client.post("/sites/scrape")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert isinstance(data["job_id"], int)

    job_resp = client.get(f"/jobs/{data['job_id']}")
    assert job_resp.status_code == 200
    job = job_resp.json()
    assert job["kind"] == "scrape"
    assert job["status"] == "succeeded"
    assert job["processed"] == 0


def test_list_jobs():
    db.create_job("scrape")
    resp = client.get("/jobs")
    assert resp.status_code == 200
    assert resp.json()[0]["kind"] == "scrape"
