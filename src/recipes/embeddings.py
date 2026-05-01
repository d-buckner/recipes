"""Embedding helpers for semantic recipe search.

All operations are best-effort: failures are caught and return None so the
caller can silently degrade to keyword-only search.
"""

import logging

import requests

from .config import settings

log = logging.getLogger(__name__)


def build_recipe_text(recipe_json: dict) -> str:
    """Concatenate title + description + ingredients into one document."""
    parts: list[str] = []
    title = recipe_json.get("title") or ""
    if title:
        parts.append(title)
    description = recipe_json.get("description") or ""
    if description:
        parts.append(description)
    ingredients = recipe_json.get("ingredients") or []
    if isinstance(ingredients, list):
        parts.extend(str(i) for i in ingredients if i)
    return " ".join(parts)


def get_embedding(text: str) -> list[float] | None:
    """Return an embedding vector for *text*, or None if embedding is disabled or fails.

    Calls the Ollama-compatible POST /api/embeddings endpoint at settings.embed_url.
    """
    if not settings.embed_model:
        return None
    if not text.strip():
        return None
    try:
        resp = requests.post(
            f"{settings.embed_url.rstrip('/')}/api/embeddings",
            json={"model": settings.embed_model, "prompt": text},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        vector = data.get("embedding")
        if not isinstance(vector, list) or not vector:
            log.warning("Embedding API returned unexpected response: %s", data)
            return None
        return [float(v) for v in vector]
    except Exception as exc:
        log.debug("Embedding failed: %s", exc)
        return None
