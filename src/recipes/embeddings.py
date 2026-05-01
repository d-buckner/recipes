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

    Calls the OpenAI-compatible POST /v1/embeddings endpoint at settings.embed_url.
    (Ollama also exposes this endpoint, so both work with the same format.)
    """
    if not settings.embed_model:
        return None
    if not text.strip():
        return None
    try:
        resp = requests.post(
            f"{settings.embed_url.rstrip('/')}/v1/embeddings",
            json={"model": settings.embed_model, "input": text},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data")
        if not isinstance(items, list) or not items:
            log.warning("Embedding API returned unexpected response: %s", data)
            return None
        vector = items[0].get("embedding")
        if not isinstance(vector, list) or not vector:
            log.warning("Embedding API returned unexpected embedding: %s", items[0])
            return None
        return [float(v) for v in vector]
    except Exception as exc:
        log.debug("Embedding failed: %s", exc)
        return None
