"""
Open WebUI Tool: Recipe Search
Searches your personal recipe database and renders recipes in markdown.
"""

from typing import Any

import requests
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        api_base_url: str = Field(
            default="http://localhost:8000/api",
            description=(
                "Base URL of the recipes API server. "
                "Docker: http://host.docker.internal:8000/api — "
                "Local dev (no static dir): http://localhost:8000"
            ),
        )

    class UserValves(BaseModel):
        api_base_url: str = Field(
            default="",
            description="Override the recipes API URL (leave blank to use the admin default)",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.user_valves = self.UserValves()

    def _api_base_url(self) -> str:
        if self.user_valves.api_base_url.strip():
            return self.user_valves.api_base_url.rstrip("/")
        return self.valves.api_base_url.rstrip("/")

    def search_recipes(self, query: str) -> str:
        """
        Search the recipe database for recipes matching the query.
        Returns a markdown list of results.

        :param query: Search terms, e.g. "chicken pasta", "vegetarian soup"
        """
        url = f"{self._api_base_url()}/search"
        try:
            resp = requests.get(url, params={"q": query, "limit": 10}, timeout=10)
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

        lines = [f"## Recipe search results for '{query}'\n"]
        for r in results:
            title = r.get("title") or "Untitled"
            recipe_id = r["id"]
            time_str = f" · {r['total_time']} min" if r.get("total_time") else ""
            yields_str = f" · {r['yields']}" if r.get("yields") else ""
            fav = " ⭐" if r.get("is_favorite") else ""
            desc = r.get("description") or ""
            desc_str = f"\n  > {desc[:120]}..." if len(desc) > 120 else (f"\n  > {desc}" if desc else "")
            lines.append(f"- **[{title}]** (ID: {recipe_id}){time_str}{yields_str}{fav}{desc_str}")

        lines.append(f"\n_Use `get_recipe(recipe_id)` to see the full recipe._")
        return "\n".join(lines)

    def get_recipe(self, recipe_id: int) -> str:
        """
        Get the full recipe details rendered as markdown.

        :param recipe_id: The numeric ID of the recipe (from search results)
        """
        url = f"{self._api_base_url()}/recipes/{recipe_id}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 404:
                return f"Recipe {recipe_id} not found."
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.ConnectionError:
            return f"Error fetching recipe: could not connect to {url}. Check the API URL in tool settings."
        except requests.exceptions.HTTPError as exc:
            return f"Error fetching recipe: server returned {exc.response.status_code} — {exc.response.text[:200]}"
        except Exception as exc:
            return f"Error fetching recipe: {exc}"

        if not data.get("recipe_json"):
            return f"Recipe {recipe_id} exists but has not been scraped yet (status: {data.get('status', 'unknown')})."
        return _render_recipe(data["recipe_json"], data["url"])

    def add_favorite(self, recipe_id: int) -> str:
        """
        Save a recipe to your favorites.

        :param recipe_id: The numeric ID of the recipe to favorite
        """
        try:
            resp = requests.post(
                f"{self._api_base_url()}/favorites/{recipe_id}",
                timeout=10,
            )
            if resp.status_code == 404:
                return f"Recipe {recipe_id} not found."
            resp.raise_for_status()
            return f"Recipe {recipe_id} added to favorites. ⭐"
        except Exception as exc:
            return f"Error adding favorite: {exc}"

    def remove_favorite(self, recipe_id: int) -> str:
        """
        Remove a recipe from your favorites.

        :param recipe_id: The numeric ID of the recipe to unfavorite
        """
        try:
            resp = requests.delete(
                f"{self._api_base_url()}/favorites/{recipe_id}",
                timeout=10,
            )
            resp.raise_for_status()
            return f"Recipe {recipe_id} removed from favorites."
        except Exception as exc:
            return f"Error removing favorite: {exc}"

    def list_favorites(self) -> str:
        """
        List all favorited recipes.
        """
        try:
            resp = requests.get(f"{self._api_base_url()}/favorites", timeout=10)
            resp.raise_for_status()
            results = resp.json()
        except Exception as exc:
            return f"Error listing favorites: {exc}"

        if not results:
            return "You have no favorited recipes yet. Use `add_favorite(recipe_id)` to save one."

        lines = ["## Your Favorite Recipes ⭐\n"]
        for r in results:
            title = r.get("title") or "Untitled"
            recipe_id = r["id"]
            time_str = f" · {r['total_time']} min" if r.get("total_time") else ""
            yields_str = f" · {r['yields']}" if r.get("yields") else ""
            lines.append(f"- **{title}** (ID: {recipe_id}){time_str}{yields_str}")

        return "\n".join(lines)


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
        meta_parts.append(f"**Cuisine:** {r['cuisine']}")
    if r.get("category"):
        meta_parts.append(f"**Category:** {r['category']}")
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
        # Split on newlines if multi-line, otherwise show as-is
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
