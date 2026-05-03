"""Tests for grocery list DB functions and API endpoints."""

from fractions import Fraction

import pytest
from fastapi.testclient import TestClient

from recipes import db
from recipes.api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db(mem_db):
    """Use in-memory db for all grocery list tests."""
    pass


def _seed_recipe(
    title: str = "Pasta Primavera",
    ingredients: list[str] | None = None,
    url: str = "https://example.com/recipes/pasta",
) -> int:
    """Insert a complete recipe and return its ID."""
    if ingredients is None:
        ingredients = ["2 cups flour", "1 tbsp olive oil", "3 eggs"]
    db.insert_discovered_urls([(url, "example.com")])
    recipe = db.claim_next_url()
    db.save_recipe(recipe.id, {
        "title": title,
        "description": "",
        "ingredients": ingredients,
        "keywords": [],
        "total_time": 30,
        "yields": "4 servings",
        "image": None,
    })
    return recipe.id


# ---------------------------------------------------------------------------
# DB layer — list_grocery_items
# ---------------------------------------------------------------------------


class TestListGroceryItems:
    def test_empty_list_initially(self):
        assert db.list_grocery_items() == []

    def test_returns_items_after_add(self):
        db.add_grocery_item_raw("3 eggs")
        items = db.list_grocery_items()
        assert len(items) == 1


# ---------------------------------------------------------------------------
# DB layer — add_grocery_item_raw
# ---------------------------------------------------------------------------


class TestAddGroceryItemRaw:
    def test_add_item_with_unit(self):
        item = db.add_grocery_item_raw("2 cups flour")
        assert item.qty_num == 2
        assert item.qty_den == 1
        assert item.unit == "cup"
        assert item.ingredient == "flour"

    def test_add_item_no_unit(self):
        item = db.add_grocery_item_raw("3 eggs")
        assert item.qty_num == 3
        assert item.unit is None
        assert item.ingredient == "eggs"

    def test_add_item_no_qty(self):
        item = db.add_grocery_item_raw("kosher salt")
        assert item.qty_num is None
        assert item.unit is None
        assert item.ingredient == "kosher salt"

    def test_add_item_stores_raw(self):
        item = db.add_grocery_item_raw("1½ cups broth")
        assert "1½ cups broth" in item.original_raw

    def test_add_item_with_recipe_id(self):
        recipe_id = _seed_recipe()
        item = db.add_grocery_item_raw("2 cups flour", recipe_id=recipe_id)
        assert recipe_id in item.recipe_ids

    def test_add_item_mixed_number_qty(self):
        item = db.add_grocery_item_raw("1½ cups broth")
        assert item.qty_num == 3
        assert item.qty_den == 2
        assert item.unit == "cup"

    def test_add_item_unicode_fraction_qty(self):
        item = db.add_grocery_item_raw("¼ cup butter")
        assert item.qty_num == 1
        assert item.qty_den == 4

    def test_merges_same_unit_and_ingredient(self):
        db.add_grocery_item_raw("2 cups flour")
        item = db.add_grocery_item_raw("1 cup flour")
        items = db.list_grocery_items()
        assert len(items) == 1
        # 2 + 1 = 3 cups
        assert item.qty_num == 3
        assert item.qty_den == 1
        assert item.unit == "cup"

    def test_merge_accumulates_raw_strings(self):
        db.add_grocery_item_raw("2 cups flour")
        item = db.add_grocery_item_raw("1 cup flour")
        assert len(item.original_raw) == 2

    def test_merge_accumulates_recipe_ids(self):
        r1 = _seed_recipe(url="https://example.com/r1")
        r2 = _seed_recipe(url="https://example.com/r2")
        db.add_grocery_item_raw("2 cups flour", recipe_id=r1)
        item = db.add_grocery_item_raw("1 cup flour", recipe_id=r2)
        assert r1 in item.recipe_ids
        assert r2 in item.recipe_ids

    def test_no_merge_different_unit(self):
        db.add_grocery_item_raw("2 cups butter")
        db.add_grocery_item_raw("1 tbsp butter")
        items = db.list_grocery_items()
        assert len(items) == 2

    def test_no_merge_different_ingredient(self):
        db.add_grocery_item_raw("2 cups flour")
        db.add_grocery_item_raw("2 cups sugar")
        items = db.list_grocery_items()
        assert len(items) == 2

    def test_no_merge_no_qty_items(self):
        """Two no-qty items with same name do not merge (can't sum)."""
        db.add_grocery_item_raw("salt")
        db.add_grocery_item_raw("salt")
        # Both "salt" items are treated as independent entries without quantities
        items = db.list_grocery_items()
        assert len(items) == 2

    def test_item_checked_false_by_default(self):
        item = db.add_grocery_item_raw("2 cups flour")
        assert item.checked is False

    def test_tablespoon_unit_normalization(self):
        item = db.add_grocery_item_raw("1 tablespoon oil")
        assert item.unit == "tbsp"

    def test_ingredient_name_normalizes_case(self):
        item = db.add_grocery_item_raw("2 cups All-Purpose Flour")
        assert item.ingredient == "all-purpose flour"

    def test_ingredient_strips_notes(self):
        item = db.add_grocery_item_raw("1 cup butter, divided")
        assert item.ingredient == "butter"
        assert "divided" not in item.ingredient


# ---------------------------------------------------------------------------
# DB layer — add_grocery_items_from_recipe
# ---------------------------------------------------------------------------


class TestAddGroceryItemsFromRecipe:
    def test_adds_all_ingredients(self):
        recipe_id = _seed_recipe(ingredients=["2 cups flour", "3 eggs", "½ tsp salt"])
        items = db.add_grocery_items_from_recipe(recipe_id)
        assert len(items) == 3

    def test_adds_correct_quantities(self):
        recipe_id = _seed_recipe(ingredients=["2 cups flour"])
        items = db.add_grocery_items_from_recipe(recipe_id)
        assert items[0].qty_num == 2
        assert items[0].unit == "cup"

    def test_scale_factor_doubles_quantity(self):
        recipe_id = _seed_recipe(ingredients=["2 cups flour"])
        items = db.add_grocery_items_from_recipe(recipe_id, scale_factor=2.0)
        assert items[0].qty_num == 4
        assert items[0].unit == "cup"

    def test_scale_factor_halves_quantity(self):
        recipe_id = _seed_recipe(ingredients=["2 cups flour"])
        items = db.add_grocery_items_from_recipe(recipe_id, scale_factor=0.5)
        assert Fraction(items[0].qty_num, items[0].qty_den) == Fraction(1)

    def test_recipe_id_stored_on_items(self):
        recipe_id = _seed_recipe(ingredients=["2 cups flour"])
        items = db.add_grocery_items_from_recipe(recipe_id)
        assert recipe_id in items[0].recipe_ids

    def test_merges_with_existing_item(self):
        recipe_id = _seed_recipe(ingredients=["2 cups flour"])
        db.add_grocery_item_raw("1 cup flour")
        db.add_grocery_items_from_recipe(recipe_id)
        items = db.list_grocery_items()
        flour_items = [i for i in items if i.ingredient == "flour"]
        assert len(flour_items) == 1
        assert Fraction(flour_items[0].qty_num, flour_items[0].qty_den) == Fraction(3)

    def test_returns_empty_for_unknown_recipe(self):
        items = db.add_grocery_items_from_recipe(99999)
        assert items == []


# ---------------------------------------------------------------------------
# DB layer — update_grocery_item
# ---------------------------------------------------------------------------


class TestUpdateGroceryItem:
    def test_check_item(self):
        item = db.add_grocery_item_raw("2 cups flour")
        updated = db.update_grocery_item(item.id, checked=True)
        assert updated is not None
        assert updated.checked is True

    def test_uncheck_item(self):
        item = db.add_grocery_item_raw("2 cups flour")
        db.update_grocery_item(item.id, checked=True)
        updated = db.update_grocery_item(item.id, checked=False)
        assert updated.checked is False

    def test_update_nonexistent_returns_none(self):
        result = db.update_grocery_item(99999, checked=True)
        assert result is None

    def test_update_ingredient_name(self):
        item = db.add_grocery_item_raw("2 cups AP flour")
        updated = db.update_grocery_item(item.id, ingredient="all-purpose flour")
        assert updated.ingredient == "all-purpose flour"

    def test_checked_item_persists_in_list(self):
        item = db.add_grocery_item_raw("3 eggs")
        db.update_grocery_item(item.id, checked=True)
        items = db.list_grocery_items()
        assert any(i.checked for i in items)


# ---------------------------------------------------------------------------
# DB layer — delete_grocery_item
# ---------------------------------------------------------------------------


class TestDeleteGroceryItem:
    def test_delete_removes_item(self):
        item = db.add_grocery_item_raw("2 cups flour")
        db.delete_grocery_item(item.id)
        assert db.list_grocery_items() == []

    def test_delete_only_target(self):
        db.add_grocery_item_raw("2 cups flour")
        item2 = db.add_grocery_item_raw("3 eggs")
        db.delete_grocery_item(item2.id)
        items = db.list_grocery_items()
        assert len(items) == 1
        assert items[0].ingredient == "flour"

    def test_delete_nonexistent_is_noop(self):
        db.add_grocery_item_raw("2 cups flour")
        db.delete_grocery_item(99999)
        assert len(db.list_grocery_items()) == 1


# ---------------------------------------------------------------------------
# DB layer — clear_grocery_list
# ---------------------------------------------------------------------------


class TestClearGroceryList:
    def test_clear_all_removes_everything(self):
        db.add_grocery_item_raw("2 cups flour")
        db.add_grocery_item_raw("3 eggs")
        db.clear_grocery_list()
        assert db.list_grocery_items() == []

    def test_clear_checked_only(self):
        item1 = db.add_grocery_item_raw("2 cups flour")
        item2 = db.add_grocery_item_raw("3 eggs")
        db.update_grocery_item(item1.id, checked=True)
        db.clear_grocery_list(checked_only=True)
        items = db.list_grocery_items()
        assert len(items) == 1
        assert items[0].id == item2.id

    def test_clear_checked_only_with_no_checked_items(self):
        db.add_grocery_item_raw("2 cups flour")
        db.clear_grocery_list(checked_only=True)
        assert len(db.list_grocery_items()) == 1


# ---------------------------------------------------------------------------
# DB layer — merge_grocery_items
# ---------------------------------------------------------------------------


class TestMergeGroceryItems:
    def test_merge_same_unit_sums_quantity(self):
        item1 = db.add_grocery_item_raw("2 cups flour")
        item2 = db.add_grocery_item_raw("2 cups sugar")
        # Manually merge (even though ingredients differ — user-driven)
        merged = db.merge_grocery_items(item1.id, item2.id)
        assert merged is not None
        assert Fraction(merged.qty_num, merged.qty_den) == Fraction(4)

    def test_merge_removes_second_item(self):
        # Use different ingredients so they don't auto-merge on insert
        item1 = db.add_grocery_item_raw("2 cups flour")
        item2 = db.add_grocery_item_raw("2 cups sugar")
        db.merge_grocery_items(item1.id, item2.id)
        items = db.list_grocery_items()
        assert len(items) == 1

    def test_merge_combines_raw_strings(self):
        item1 = db.add_grocery_item_raw("2 cups flour")
        item2 = db.add_grocery_item_raw("1 cup all-purpose flour")  # different norm name
        merged = db.merge_grocery_items(item1.id, item2.id)
        assert len(merged.original_raw) == 2

    def test_merge_combines_recipe_ids(self):
        r1 = _seed_recipe(url="https://example.com/r1")
        r2 = _seed_recipe(url="https://example.com/r2")
        # Use different ingredients so they don't auto-merge on insert
        item1 = db.add_grocery_item_raw("2 cups flour", recipe_id=r1)
        item2 = db.add_grocery_item_raw("2 cups sugar", recipe_id=r2)
        merged = db.merge_grocery_items(item1.id, item2.id)
        assert r1 in merged.recipe_ids
        assert r2 in merged.recipe_ids

    def test_merge_nonexistent_returns_none(self):
        item = db.add_grocery_item_raw("2 cups flour")
        result = db.merge_grocery_items(item.id, 99999)
        assert result is None


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


class TestGroceryListAPI:
    def test_get_empty_list(self):
        resp = client.get("/grocery-list")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_add_item_manual(self):
        resp = client.post("/grocery-list/items", json={"raw": "2 cups flour"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["ingredient"] == "flour"
        assert data["unit"] == "cup"
        assert data["qty_num"] == 2

    def test_add_item_appears_in_list(self):
        client.post("/grocery-list/items", json={"raw": "3 eggs"})
        resp = client.get("/grocery-list")
        assert len(resp.json()) == 1

    def test_add_item_merges_duplicate(self):
        client.post("/grocery-list/items", json={"raw": "2 cups flour"})
        client.post("/grocery-list/items", json={"raw": "1 cup flour"})
        resp = client.get("/grocery-list")
        assert len(resp.json()) == 1
        assert resp.json()[0]["qty_num"] == 3

    def test_add_from_recipe(self):
        recipe_id = _seed_recipe(ingredients=["2 cups flour", "3 eggs"])
        resp = client.post(f"/grocery-list/from-recipe/{recipe_id}")
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 2

    def test_add_from_recipe_with_scale_factor(self):
        recipe_id = _seed_recipe(ingredients=["2 cups flour"])
        resp = client.post(f"/grocery-list/from-recipe/{recipe_id}?scale_factor=2")
        assert resp.status_code == 201
        data = resp.json()
        assert data[0]["qty_num"] == 4

    def test_add_from_recipe_not_found(self):
        resp = client.post("/grocery-list/from-recipe/99999")
        assert resp.status_code == 404

    def test_update_item_checked(self):
        resp = client.post("/grocery-list/items", json={"raw": "3 eggs"})
        item_id = resp.json()["id"]
        resp = client.patch(f"/grocery-list/items/{item_id}", json={"checked": True})
        assert resp.status_code == 200
        assert resp.json()["checked"] is True

    def test_update_item_not_found(self):
        resp = client.patch("/grocery-list/items/99999", json={"checked": True})
        assert resp.status_code == 404

    def test_delete_item(self):
        resp = client.post("/grocery-list/items", json={"raw": "3 eggs"})
        item_id = resp.json()["id"]
        resp = client.delete(f"/grocery-list/items/{item_id}")
        assert resp.status_code == 204
        assert client.get("/grocery-list").json() == []

    def test_delete_item_not_found(self):
        resp = client.delete("/grocery-list/items/99999")
        assert resp.status_code == 404

    def test_clear_list(self):
        client.post("/grocery-list/items", json={"raw": "2 cups flour"})
        client.post("/grocery-list/items", json={"raw": "3 eggs"})
        resp = client.delete("/grocery-list")
        assert resp.status_code == 204
        assert client.get("/grocery-list").json() == []

    def test_clear_checked_only(self):
        resp1 = client.post("/grocery-list/items", json={"raw": "2 cups flour"})
        resp2 = client.post("/grocery-list/items", json={"raw": "3 eggs"})
        client.patch(f"/grocery-list/items/{resp1.json()['id']}", json={"checked": True})
        client.delete("/grocery-list?checked_only=true")
        items = client.get("/grocery-list").json()
        assert len(items) == 1
        assert items[0]["id"] == resp2.json()["id"]

    def test_merge_items(self):
        resp1 = client.post("/grocery-list/items", json={"raw": "2 cups flour"})
        resp2 = client.post("/grocery-list/items", json={"raw": "1 cup sugar"})
        id1, id2 = resp1.json()["id"], resp2.json()["id"]
        resp = client.post(f"/grocery-list/items/{id1}/merge/{id2}")
        assert resp.status_code == 200
        assert client.get("/grocery-list").json().__len__() == 1

    def test_qty_display_present(self):
        resp = client.post("/grocery-list/items", json={"raw": "1½ cups broth"})
        assert resp.status_code == 201
        data = resp.json()
        assert "qty_display" in data
        assert data["qty_display"] == "1½"

    def test_qty_display_none_for_no_qty(self):
        resp = client.post("/grocery-list/items", json={"raw": "salt"})
        data = resp.json()
        assert data["qty_display"] is None

    def test_recipe_titles_empty_when_no_recipes(self):
        resp = client.post("/grocery-list/items", json={"raw": "3 eggs"})
        data = resp.json()
        assert data["recipe_titles"] == {}

    def test_recipe_titles_populated_from_recipe(self):
        recipe_id = _seed_recipe(title="Pasta Primavera", ingredients=["2 cups flour"])
        client.post(f"/grocery-list/from-recipe/{recipe_id}")
        resp = client.get("/grocery-list")
        items = resp.json()
        assert len(items) == 1
        assert str(recipe_id) in items[0]["recipe_titles"]
        assert items[0]["recipe_titles"][str(recipe_id)] == "Pasta Primavera"


# ---------------------------------------------------------------------------
# DB layer — get_recipe_titles
# ---------------------------------------------------------------------------


class TestGetRecipeTitles:
    def test_empty_ids_returns_empty_dict(self):
        assert db.get_recipe_titles([]) == {}

    def test_unknown_ids_returns_empty_dict(self):
        assert db.get_recipe_titles([99999]) == {}

    def test_returns_title_for_known_recipe(self):
        recipe_id = _seed_recipe(title="Kale Salad")
        titles = db.get_recipe_titles([recipe_id])
        assert titles == {recipe_id: "Kale Salad"}

    def test_returns_multiple_titles(self):
        id1 = _seed_recipe(title="Kale Salad", url="https://example.com/kale")
        id2 = _seed_recipe(title="Bean Stew", url="https://example.com/bean")
        titles = db.get_recipe_titles([id1, id2])
        assert titles[id1] == "Kale Salad"
        assert titles[id2] == "Bean Stew"

    def test_ignores_ids_not_in_list(self):
        id1 = _seed_recipe(title="Kale Salad", url="https://example.com/kale")
        _seed_recipe(title="Bean Stew", url="https://example.com/bean")
        titles = db.get_recipe_titles([id1])
        assert len(titles) == 1
        assert id1 in titles
