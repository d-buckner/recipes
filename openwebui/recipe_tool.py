"""
Open WebUI Tool: Recipe Search
Searches your personal recipe database and renders recipes in markdown.
"""

import re
from fractions import Fraction
from typing import Any

import requests
from pydantic import BaseModel, Field


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

    def search_recipes(self, query: str) -> str:
        """
        Search the recipe database for recipes matching the query.
        Returns a markdown list of results.

        **Strategy: run multiple searches to find the best candidates.**
        The database uses full-text search, so different phrasings surface
        different results. For any non-trivial question, call this tool
        several times with varied queries before answering. Good angles to try:

        - Main ingredient(s): "salmon", "eggplant", "ground beef"
        - Dish name or type: "carbonara", "stir fry", "sheet pan chicken"
        - Cuisine or region: "Thai", "Mexican", "Mediterranean"
        - Cooking method: "braised", "grilled", "slow cooker", "no-bake"
        - Occasion or meal: "weeknight dinner", "holiday dessert", "meal prep"
        - Dietary angle: "vegan", "gluten free", "low carb", "dairy free"
        - Flavor profile: "spicy", "creamy", "tangy", "smoky", "umami"
        - Key secondary ingredient: "coconut milk", "miso", "lemon", "tahini"
        - Texture or form: "crispy", "one pot", "soup", "salad", "sandwich"
        - Synonyms and alternate names: "aubergine" vs "eggplant",
          "coriander" vs "cilantro", "courgette" vs "zucchini"

        Combine candidates across searches and surface the most relevant ones.

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

        lines = [
            f"## Recipe search results for '{query}'\n",
            (
                "_CONTEXT NOTE FOR MODEL: Results are numbered so you can resolve follow-up references "
                "like 'show me the 2nd one' or 'get that last recipe' by calling get_recipe with the "
                "corresponding ID. Keep this position→ID mapping in mind for the rest of the conversation. "
                "Never show raw IDs to the user — they are internal tool references only._\n"
            ),
        ]
        for i, r in enumerate(results, 1):
            title = r.get("title") or "Untitled"
            recipe_id = r["id"]
            time_str = f" · {r['total_time']} min" if r.get("total_time") else ""
            yields_str = f" · {r['yields']}" if r.get("yields") else ""
            fav = " ⭐" if r.get("is_favorite") else ""
            desc = r.get("description") or ""
            desc_str = f"\n   > {desc[:120]}..." if len(desc) > 120 else (f"\n   > {desc}" if desc else "")
            lines.append(f"{i}. **{title}**{time_str}{yields_str}{fav}{desc_str} <!-- id:{recipe_id} -->")

        lines.append(f"\n_If the user asked to see a specific recipe, call get_recipe immediately — do not ask for confirmation._")
        return "\n".join(lines)

    def get_recipe(self, recipe_id: int) -> str:
        """
        Get the full recipe details rendered as markdown.

        IMPORTANT: Never mention the numeric recipe_id to the user — it is an internal
        reference only. Just present the recipe content directly.

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

    def scale_recipe(self, recipe_id: int, scale_factor: float) -> str:
        """
        Return the ingredient list for a recipe scaled by the given factor.

        ALWAYS use this tool when the user wants to scale a recipe or build a
        grocery list — do NOT do the fraction arithmetic yourself. Python
        handles mixed numbers and unicode fractions exactly.

        Examples:
          scale_factor=4   → quadruple batch
          scale_factor=2   → double batch
          scale_factor=0.5 → half batch

        IMPORTANT: Never mention the numeric recipe_id to the user.

        :param recipe_id: The numeric ID of the recipe (from search results)
        :param scale_factor: Multiplier for ingredient quantities (e.g. 2, 4, 0.5)
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
            return f"Recipe has not been scraped yet (status: {data.get('status', 'unknown')})."

        rj = data["recipe_json"]
        title = rj.get("title") or "Recipe"
        ingredients = rj.get("ingredients") or []
        yields = rj.get("yields") or ""

        try:
            factor = Fraction(scale_factor).limit_denominator(100)
        except (ValueError, TypeError):
            return f"Invalid scale factor: {scale_factor!r}"

        factor_str = str(int(factor)) if factor == int(factor) else str(factor)
        scaled = [_scale_ingredient(ing, factor) for ing in ingredients]

        lines = [f"## {title} × {factor_str}\n"]
        if yields:
            lines.append(f"_Original yield: {yields}_\n")
        lines.append("**Scaled ingredients:**\n")
        for ing in scaled:
            lines.append(f"- {ing}")
        lines.append(
            "\n_Quantities computed by Python — use these as-is when building a grocery list._"
        )
        return "\n".join(lines)

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


_UNICODE_FRACTIONS: dict[str, Fraction] = {
    "½": Fraction(1, 2),
    "⅓": Fraction(1, 3),
    "⅔": Fraction(2, 3),
    "¼": Fraction(1, 4),
    "¾": Fraction(3, 4),
    "⅕": Fraction(1, 5),
    "⅖": Fraction(2, 5),
    "⅗": Fraction(3, 5),
    "⅘": Fraction(4, 5),
    "⅙": Fraction(1, 6),
    "⅚": Fraction(5, 6),
    "⅛": Fraction(1, 8),
    "⅜": Fraction(3, 8),
    "⅝": Fraction(5, 8),
    "⅞": Fraction(7, 8),
}
_REVERSE_UNICODE: dict[Fraction, str] = {v: k for k, v in _UNICODE_FRACTIONS.items()}


def _parse_qty_token(token: str) -> Fraction | None:
    if token in _UNICODE_FRACTIONS:
        return _UNICODE_FRACTIONS[token]
    if "/" in token:
        parts = token.split("/")
        if len(parts) == 2:
            try:
                return Fraction(int(parts[0]), int(parts[1]))
            except (ValueError, ZeroDivisionError):
                pass
    try:
        return Fraction(token).limit_denominator(1000)
    except (ValueError, ZeroDivisionError):
        return None


def _format_fraction(f: Fraction) -> str:
    whole = int(f)
    remainder = f - whole
    if remainder == 0:
        return str(whole)
    frac_str = _REVERSE_UNICODE.get(remainder) or f"{remainder.numerator}/{remainder.denominator}"
    return frac_str if whole == 0 else f"{whole}{frac_str}"


def _scale_ingredient(ingredient: str, factor: Fraction) -> str:
    # Insert space between a digit and a unicode fraction: "1½" → "1 ½"
    normalized = ingredient
    for uf in _UNICODE_FRACTIONS:
        normalized = re.sub(rf"(\d)({re.escape(uf)})", r"\1 \2", normalized)

    tokens = normalized.split()
    if not tokens:
        return ingredient

    qty: Fraction | None = None
    qty_tokens = 0

    # Try mixed number: whole integer + proper fraction (e.g. "1 ½", "1 1/2")
    if len(tokens) >= 2:
        first = _parse_qty_token(tokens[0])
        second = _parse_qty_token(tokens[1])
        if (
            first is not None
            and second is not None
            and first == int(first)
            and 0 < second < 1
        ):
            qty = first + second
            qty_tokens = 2

    if qty is None:
        first = _parse_qty_token(tokens[0])
        if first is not None:
            qty = first
            qty_tokens = 1

    if qty is None:
        return ingredient

    scaled_str = _format_fraction(qty * factor)
    rest = " ".join(tokens[qty_tokens:])
    return f"{scaled_str} {rest}".strip()


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
