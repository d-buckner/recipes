"""
Open WebUI Tool: Recipe Search
Searches your personal recipe database and renders recipes in markdown.
"""

from fractions import Fraction
from typing import Any

import requests
from pydantic import BaseModel, Field

from recipes.ingredients import (
    UNICODE_FRACTIONS as _UNICODE_FRACTIONS,
    REVERSE_UNICODE as _REVERSE_UNICODE,
    format_fraction as _format_fraction,
    parse_qty_token as _parse_qty_token,
    scale_ingredient as _scale_ingredient,
)


class Tools:
    class Valves(BaseModel):
        api_base_url: str = Field(
            default="http://localhost:8000",
            description=(
                "Base URL of the recipes server, e.g. http://10.0.0.20:8000. "
                "The /api prefix is added automatically."
            ),
        )

    class UserValves(BaseModel):
        api_base_url: str = Field(
            default="",
            description="Override the recipes server URL (leave blank to use the admin default)",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.user_valves = self.UserValves()

    def _api_base_url(self) -> str:
        base = self.user_valves.api_base_url.strip() or self.valves.api_base_url
        return base.rstrip("/") + "/api"

    def _resolve_recipe_id(self, title: str) -> "int | str":
        """Search for recipe by title, return numeric ID or error string."""
        url = f"{self._api_base_url()}/search"
        try:
            resp = requests.get(url, params={"q": title, "limit": 1}, timeout=10)
            resp.raise_for_status()
            results = resp.json()
        except requests.exceptions.ConnectionError:
            return f"Error: could not connect to {url}. Check that the recipes server is running."
        except Exception as exc:
            return f"Error searching for recipe: {exc}"

        if not results:
            return f"No recipe found matching '{title}'. Try search_recipes first."
        return results[0]["id"]

    def _resolve_collection_id(self, collection_name: str) -> "int | str":
        """Look up collection by name, return numeric ID or error string."""
        url = f"{self._api_base_url()}/collections"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            collections = resp.json()
        except requests.exceptions.ConnectionError:
            return f"Error: could not connect to {url}. Check that the recipes server is running."
        except Exception as exc:
            return f"Error listing collections: {exc}"

        name_lower = collection_name.strip().lower()
        for c in collections:
            if c.get("name", "").lower() == name_lower:
                return c["id"]
        return f"No collection found named '{collection_name}'."

    def search_recipes(
        self,
        query: str,
        max_time: int = None,
        cuisine: str = None,
        category: str = None,
    ) -> str:
        """
        Search the recipe database. Returns a numbered list of matching recipes.
        Use get_recipe with a recipe title to fetch the full details.

        :param query: Search terms, e.g. "chicken pasta", "vegetarian soup"
        :param max_time: Maximum total cooking time in minutes (optional)
        :param cuisine: Filter by cuisine, e.g. "Italian", "Mexican" (optional)
        :param category: Filter by category, e.g. "Dinner", "Dessert" (optional)
        """
        url = f"{self._api_base_url()}/search"
        params: dict = {"q": query, "limit": 10}
        if max_time is not None:
            params["max_time"] = max_time
        if cuisine:
            params["cuisine"] = cuisine
        if category:
            params["category"] = category

        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            results = resp.json()
        except requests.exceptions.ConnectionError:
            return f"Error searching recipes: could not connect to {url}. Check that the recipes server is running and the API URL is configured correctly in tool settings."
        except requests.exceptions.HTTPError as exc:
            return f"Error searching recipes: server returned {exc.response.status_code} — {exc.response.text[:200]}"
        except Exception as exc:
            return f"Error searching recipes: {exc}"

        if not results:
            return f"No recipes found for '{query}'."

        lines = [f"{len(results)} recipe{'s' if len(results) != 1 else ''} for \"{query}\":\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title") or "Untitled"
            time_str = f" · {r['total_time']} min" if r.get("total_time") else ""
            yields_str = f" · {r['yields']}" if r.get("yields") else ""
            fav = " ⭐" if r.get("is_favorite") else ""
            lines.append(f"{i}. {title}{time_str}{yields_str}{fav}")

        return "\n".join(lines)

    def get_recipe(self, title: str) -> str:
        """
        Get the full recipe details by name. Returns ingredients, instructions, and metadata.
        Use the exact title from search results, or a close approximation.

        :param title: Recipe name, e.g. "Salmon & Herby Edamame Spread Sandwich"
        """
        recipe_id = self._resolve_recipe_id(title)
        if isinstance(recipe_id, str):
            return recipe_id

        url = f"{self._api_base_url()}/recipes/{recipe_id}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 404:
                return f"Recipe not found."
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.ConnectionError:
            return f"Error fetching recipe: could not connect to {url}. Check the API URL in tool settings."
        except requests.exceptions.HTTPError as exc:
            return f"Error fetching recipe: server returned {exc.response.status_code} — {exc.response.text[:200]}"
        except Exception as exc:
            return f"Error fetching recipe: {exc}"

        if not data.get("recipe_json"):
            return f"Recipe exists but has not been scraped yet (status: {data.get('status', 'unknown')})."
        return _render_recipe(data["recipe_json"], data["url"])

    def scale_recipe(self, title: str, scale_factor: float) -> str:
        """
        Return scaled ingredient quantities for a recipe.

        :param title: Recipe name (from search results)
        :param scale_factor: Multiplier, e.g. 2 for double, 0.5 for half
        """
        recipe_id = self._resolve_recipe_id(title)
        if isinstance(recipe_id, str):
            return recipe_id

        url = f"{self._api_base_url()}/recipes/{recipe_id}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 404:
                return "Recipe not found."
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.ConnectionError:
            return f"Error fetching recipe: could not connect to {url}. Check the API URL in tool settings."
        except requests.exceptions.HTTPError as exc:
            return f"Error fetching recipe: server returned {exc.response.status_code} — {exc.response.text[:200]}"
        except Exception as exc:
            return f"Error fetching recipe: {exc}"

        if not data.get("recipe_json"):
            return f"Recipe has not been scraped yet (status: {data.get('status', 'unknown')})."

        rj = data["recipe_json"]
        recipe_title = rj.get("title") or "Recipe"
        ingredients = rj.get("ingredients") or []
        yields = rj.get("yields") or ""

        try:
            factor = Fraction(scale_factor).limit_denominator(100)
        except (ValueError, TypeError):
            return f"Invalid scale factor: {scale_factor!r}"

        factor_str = str(int(factor)) if factor == int(factor) else str(factor)
        scaled = [_scale_ingredient(ing, factor) for ing in ingredients]

        lines = [f"## {recipe_title} × {factor_str}\n"]
        if yields:
            lines.append(f"_Original yield: {yields}_\n")
        lines.append("**Scaled ingredients:**\n")
        for ing in scaled:
            lines.append(f"- {ing}")
        return "\n".join(lines)

    def save_to_favorites(self, title: str) -> str:
        """
        Save a recipe to your favorites.

        :param title: Recipe name (from search results)
        """
        recipe_id = self._resolve_recipe_id(title)
        if isinstance(recipe_id, str):
            return recipe_id

        try:
            resp = requests.post(
                f"{self._api_base_url()}/favorites/{recipe_id}",
                timeout=10,
            )
            if resp.status_code == 404:
                return "Recipe not found."
            resp.raise_for_status()
            return f"Saved to favorites. ⭐"
        except Exception as exc:
            return f"Error saving to favorites: {exc}"

    def remove_from_favorites(self, title: str) -> str:
        """
        Remove a recipe from your favorites.

        :param title: Recipe name
        """
        recipe_id = self._resolve_recipe_id(title)
        if isinstance(recipe_id, str):
            return recipe_id

        try:
            resp = requests.delete(
                f"{self._api_base_url()}/favorites/{recipe_id}",
                timeout=10,
            )
            resp.raise_for_status()
            return "Removed from favorites."
        except Exception as exc:
            return f"Error removing from favorites: {exc}"

    def list_favorites(self) -> str:
        """
        List all your saved (favorited) recipes.
        """
        try:
            resp = requests.get(f"{self._api_base_url()}/favorites", timeout=10)
            resp.raise_for_status()
            results = resp.json()
        except Exception as exc:
            return f"Error listing favorites: {exc}"

        if not results:
            return "You have no favorited recipes yet. Use save_to_favorites to save one."

        lines = ["## Your Favorite Recipes ⭐\n"]
        for r in results:
            title = r.get("title") or "Untitled"
            time_str = f" · {r['total_time']} min" if r.get("total_time") else ""
            yields_str = f" · {r['yields']}" if r.get("yields") else ""
            lines.append(f"- **{title}**{time_str}{yields_str}")

        return "\n".join(lines)

    def list_collections(self) -> str:
        """
        List all recipe collections and how many recipes each contains.
        """
        try:
            resp = requests.get(f"{self._api_base_url()}/collections", timeout=10)
            resp.raise_for_status()
            collections = resp.json()
        except Exception as exc:
            return f"Error listing collections: {exc}"

        if not collections:
            return "No collections yet. Use add_to_collection to create one."

        lines = ["## Collections\n"]
        for c in collections:
            name = c.get("name") or "Unnamed"
            count = c.get("recipe_count", 0)
            lines.append(f"- **{name}** ({count} recipe{'s' if count != 1 else ''})")

        return "\n".join(lines)

    def get_collection(self, collection_name: str) -> str:
        """
        List all recipes in a collection.

        :param collection_name: Name of the collection
        """
        collection_id = self._resolve_collection_id(collection_name)
        if isinstance(collection_id, str):
            return collection_id

        try:
            resp = requests.get(
                f"{self._api_base_url()}/collections/{collection_id}/recipes",
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json()
        except Exception as exc:
            return f"Error fetching collection: {exc}"

        if not results:
            return f"Collection '{collection_name}' is empty."

        lines = [f"## {collection_name}\n"]
        for r in results:
            title = r.get("title") or "Untitled"
            time_str = f" · {r['total_time']} min" if r.get("total_time") else ""
            yields_str = f" · {r['yields']}" if r.get("yields") else ""
            fav = " ⭐" if r.get("is_favorite") else ""
            lines.append(f"- **{title}**{time_str}{yields_str}{fav}")

        return "\n".join(lines)

    def add_to_collection(self, title: str, collection_name: str) -> str:
        """
        Add a recipe to a collection. Creates the collection if it doesn't exist.

        :param title: Recipe name
        :param collection_name: Collection to add it to
        """
        recipe_id = self._resolve_recipe_id(title)
        if isinstance(recipe_id, str):
            return recipe_id

        # Resolve or create collection
        collection_id = self._resolve_collection_id(collection_name)
        if isinstance(collection_id, str):
            # Create the collection
            try:
                resp = requests.post(
                    f"{self._api_base_url()}/collections",
                    json={"name": collection_name},
                    timeout=10,
                )
                resp.raise_for_status()
                collection_id = resp.json()["id"]
            except Exception as exc:
                return f"Error creating collection '{collection_name}': {exc}"

        try:
            resp = requests.post(
                f"{self._api_base_url()}/collections/{collection_id}/recipes/{recipe_id}",
                timeout=10,
            )
            resp.raise_for_status()
            return f"Added to '{collection_name}'."
        except Exception as exc:
            return f"Error adding to collection: {exc}"


def _render_recipe(r: dict[str, Any], source_url: str) -> str:
    lines: list[str] = []

    title = r.get("title") or "Recipe"
    lines.append(f"# {title}\n")

    meta_parts = []
    if r.get("total_time"):
        meta_parts.append(f"**Time:** {r['total_time']} min")
    if r.get("yields"):
        meta_parts.append(f"**Yields:** {r['yields']}")
    if r.get("cuisine"):
        cuisine = r["cuisine"]
        cuisine_str = ", ".join(cuisine) if isinstance(cuisine, list) else cuisine
        meta_parts.append(f"**Cuisine:** {cuisine_str}")
    if r.get("category"):
        category = r["category"]
        category_str = ", ".join(category) if isinstance(category, list) else category
        meta_parts.append(f"**Category:** {category_str}")
    if meta_parts:
        lines.append(" · ".join(meta_parts) + "\n")

    if r.get("description"):
        lines.append(f"> {r['description']}\n")

    ingredients = r.get("ingredients") or []
    if ingredients:
        lines.append("## Ingredients\n")
        for ing in ingredients:
            lines.append(f"- {ing}")
        lines.append("")

    instructions = r.get("instructions") or ""
    if instructions:
        lines.append("## Instructions\n")
        steps = [s.strip() for s in instructions.split("\n") if s.strip()]
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    nutrients = r.get("nutrients") or {}
    if nutrients:
        lines.append("## Nutrition\n")
        for key, val in nutrients.items():
            lines.append(f"- **{key.replace('_', ' ').title()}:** {val}")
        lines.append("")

    lines.append(f"---\n[Source]({source_url})")

    return "\n".join(lines)
