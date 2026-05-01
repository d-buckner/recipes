"""Tests for embeddings module and semantic/hybrid search in db."""

import struct
from unittest.mock import MagicMock, patch

import pytest
import responses as responses_mock

from recipes import db
from recipes.embeddings import build_recipe_text, get_embedding


# ---------------------------------------------------------------------------
# build_recipe_text
# ---------------------------------------------------------------------------

def test_build_recipe_text_combines_title_description_ingredients():
    recipe = {
        "title": "Chicken Soup",
        "description": "A warm hearty soup",
        "ingredients": ["chicken", "carrots", "celery"],
    }
    text = build_recipe_text(recipe)
    assert "Chicken Soup" in text
    assert "A warm hearty soup" in text
    assert "chicken" in text
    assert "carrots" in text


def test_build_recipe_text_missing_fields():
    text = build_recipe_text({"title": "Just a title"})
    assert text == "Just a title"


def test_build_recipe_text_empty_dict():
    text = build_recipe_text({})
    assert text == ""


def test_build_recipe_text_skips_empty_ingredients():
    recipe = {"title": "Soup", "ingredients": ["", None, "onion"]}
    text = build_recipe_text(recipe)
    assert "onion" in text
    # empty/None entries are excluded from the joined text
    assert text.count("  ") == 0  # no double spaces from empty entries


# ---------------------------------------------------------------------------
# get_embedding
# ---------------------------------------------------------------------------

def test_get_embedding_disabled_when_no_model():
    """Returns None immediately when embed_model is empty."""
    with patch("recipes.embeddings.settings") as mock_settings:
        mock_settings.embed_model = ""
        result = get_embedding("some text")
    assert result is None


@responses_mock.activate
def test_get_embedding_returns_vector():
    with patch("recipes.embeddings.settings") as mock_settings:
        mock_settings.embed_model = "nomic-embed-text"
        mock_settings.embed_url = "http://localhost:11434"
        responses_mock.add(
            responses_mock.POST,
            "http://localhost:11434/api/embeddings",
            json={"embedding": [0.1, 0.2, 0.3]},
            status=200,
        )
        result = get_embedding("chicken soup")

    assert result == pytest.approx([0.1, 0.2, 0.3])


@responses_mock.activate
def test_get_embedding_returns_none_on_network_error():
    with patch("recipes.embeddings.settings") as mock_settings:
        mock_settings.embed_model = "nomic-embed-text"
        mock_settings.embed_url = "http://localhost:11434"
        responses_mock.add(
            responses_mock.POST,
            "http://localhost:11434/api/embeddings",
            body=ConnectionError("unreachable"),
        )
        result = get_embedding("chicken soup")

    assert result is None


@responses_mock.activate
def test_get_embedding_returns_none_on_bad_response():
    with patch("recipes.embeddings.settings") as mock_settings:
        mock_settings.embed_model = "nomic-embed-text"
        mock_settings.embed_url = "http://localhost:11434"
        responses_mock.add(
            responses_mock.POST,
            "http://localhost:11434/api/embeddings",
            json={"error": "model not loaded"},
            status=200,
        )
        result = get_embedding("chicken soup")

    assert result is None


def test_get_embedding_returns_none_for_empty_text():
    with patch("recipes.embeddings.settings") as mock_settings:
        mock_settings.embed_model = "nomic-embed-text"
        result = get_embedding("   ")
    assert result is None


# ---------------------------------------------------------------------------
# Helpers for db tests
# ---------------------------------------------------------------------------

def _make_vector(dim: int, value: float = 0.5) -> list[float]:
    return [value] * dim


def _pack_vector(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _insert_complete_recipe(conn, recipe_id: int, title: str = "Test Recipe") -> None:
    """Insert a complete recipe row with FTS entry directly via conn."""
    import json
    recipe_json = json.dumps({
        "title": title,
        "description": f"Description for {title}",
        "ingredients": ["ingredient1", "ingredient2"],
        "total_time": 30,
    })
    conn.execute(
        "INSERT INTO recipes (id, url, site, status, recipe_json) VALUES (?, ?, ?, 'complete', ?)",
        (recipe_id, f"https://example.com/recipe/{recipe_id}", "example.com", recipe_json),
    )
    conn.execute(
        "INSERT OR REPLACE INTO recipe_fts (id, title, description, ingredients, keywords) VALUES (?, ?, ?, ?, ?)",
        (recipe_id, title, f"Description for {title}", "ingredient1 ingredient2", ""),
    )


# ---------------------------------------------------------------------------
# RRF merge logic (pure Python, no DB)
# ---------------------------------------------------------------------------

def test_rrf_merge_favours_results_appearing_in_both_lists():
    """A result in both FTS and semantic lists should outscore exclusive ones."""
    from recipes.models import SearchResult

    def _sr(id_: int) -> SearchResult:
        return SearchResult(
            id=id_, url=f"https://x.com/{id_}", site="x.com",
            title=f"Recipe {id_}", description="", total_time=None,
            yields=None, image=None, site_name=None, author=None,
            cuisines=[], categories=[], is_favorite=False,
            has_thumbnail=False, collections=[],
        )

    fts_results = [_sr(1), _sr(2), _sr(3)]
    sem_results = [_sr(2), _sr(4), _sr(5)]

    k = 60
    scores: dict[int, float] = {}
    for rank, r in enumerate(fts_results, start=1):
        scores[r.id] = scores.get(r.id, 0.0) + 1.0 / (k + rank)
    for rank, r in enumerate(sem_results, start=1):
        scores[r.id] = scores.get(r.id, 0.0) + 1.0 / (k + rank)

    # Recipe 2 appears in both lists — should have the highest score
    ranked = sorted(scores, key=lambda rid: scores[rid], reverse=True)
    assert ranked[0] == 2


# ---------------------------------------------------------------------------
# store_embedding / get_unembedded_ids
# ---------------------------------------------------------------------------

def test_store_and_get_unembedded(mem_db):
    """store_embedding inserts a row; get_unembedded_ids excludes it afterward."""
    from recipes import db as recipe_db

    # All db calls in this test need sqlite-vec loaded; patch settings globally.
    with patch("recipes.config.settings") as mock_settings:
        mock_settings.embed_model = "nomic-embed-text"
        mock_settings.embed_dim = 3

        # Set up: two complete recipes + vec_recipes table
        with recipe_db.get_conn() as conn:
            _insert_complete_recipe(conn, 1, "Soup")
            _insert_complete_recipe(conn, 2, "Salad")
            conn.execute("DELETE FROM recipe_embedding_meta")
            conn.executescript("DROP TABLE IF EXISTS vec_recipes;")
            recipe_db._ensure_vec_table(conn, 3)

        unembedded = recipe_db.get_unembedded_ids()
        assert set(unembedded) == {1, 2}

        recipe_db.store_embedding(1, _make_vector(3, 0.1))

        unembedded_after = recipe_db.get_unembedded_ids()
        assert unembedded_after == [2]


# ---------------------------------------------------------------------------
# hybrid_search RRF integration (mocked FTS + semantic)
# ---------------------------------------------------------------------------

def test_hybrid_search_merges_results(mem_db):
    """hybrid_search returns a merged ranked list via RRF."""
    from recipes.models import SearchResult

    def _sr(id_: int) -> SearchResult:
        return SearchResult(
            id=id_, url=f"https://x.com/{id_}", site="x.com",
            title=f"Recipe {id_}", description="", total_time=None,
            yields=None, image=None, site_name=None, author=None,
            cuisines=[], categories=[], is_favorite=False,
            has_thumbnail=False, collections=[],
        )

    fts_list = [_sr(1), _sr(2), _sr(3)]
    sem_list = [_sr(2), _sr(4)]

    with patch("recipes.db.search_recipes", return_value=fts_list) as mock_fts, \
         patch("recipes.db.semantic_search", return_value=sem_list) as mock_sem:
        results = db.hybrid_search(
            fts_query="soup",
            query_vector=[0.1, 0.2, 0.3],
            limit=5,
            offset=0,
        )

    mock_fts.assert_called_once()
    mock_sem.assert_called_once()

    result_ids = [r.id for r in results]
    # Recipe 2 is in both lists so should rank highest
    assert result_ids[0] == 2
    # All unique IDs should be present
    assert set(result_ids) == {1, 2, 3, 4}


def test_hybrid_search_offset(mem_db):
    """hybrid_search respects offset."""
    from recipes.models import SearchResult

    def _sr(id_: int) -> SearchResult:
        return SearchResult(
            id=id_, url=f"https://x.com/{id_}", site="x.com",
            title=f"Recipe {id_}", description="", total_time=None,
            yields=None, image=None, site_name=None, author=None,
            cuisines=[], categories=[], is_favorite=False,
            has_thumbnail=False, collections=[],
        )

    fts_list = [_sr(1), _sr(2), _sr(3), _sr(4)]
    sem_list = [_sr(2), _sr(3), _sr(5)]

    with patch("recipes.db.search_recipes", return_value=fts_list), \
         patch("recipes.db.semantic_search", return_value=sem_list):
        page1 = db.hybrid_search("soup", [0.1], limit=2, offset=0)
        page2 = db.hybrid_search("soup", [0.1], limit=2, offset=2)

    assert len(page1) == 2
    assert len(page2) == 2
    # No overlap between pages
    assert not set(r.id for r in page1) & set(r.id for r in page2)
