"""AI-based recipe templatization.

Sends ingredients and instructions to a local inference API (OpenAI-compatible
chat completions) and returns versions with scalable quantity numbers replaced
by {qty:N} placeholders.  The placeholders are filled in at render time using
the existing fraction arithmetic so scaling is instant and works for any factor.

Only numbers that represent ingredient amounts are marked — temperatures, times,
pan sizes, step numbers, and other fixed parameters are left as plain text.
"""

import json
import logging

import requests

from .config import settings

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a recipe scaling assistant. Given recipe ingredients and instructions as JSON, \
replace every number that represents a scalable ingredient quantity with a {qty:N} placeholder.

Rules:
- Replace ONLY numbers that are ingredient amounts (things that change when you make more or fewer servings)
- Use decimal notation: {qty:2}, {qty:0.5}, {qty:1.5}, {qty:0.25}, {qty:0.333}
- For fractions like "1/2", replace the entire fraction token with {qty:0.5}
- For mixed numbers like "1 1/2" or "1½", replace the entire quantity (both tokens) with a single {qty:1.5}
- DO NOT replace: temperatures (350°F, 180°C), cooking times (30 minutes, 2 hours), \
pan/dish sizes (9-inch, 8x8), percentages, step numbers, or any other fixed parameter
- Return valid JSON with the exact same structure and array lengths as the input
- Do not add any explanation — only the JSON object

Example input:
{"ingredients": ["2 cups flour", "1/2 tsp salt", "1 egg"], \
"instructions": ["Mix 2 cups flour with water.", "Bake at 350°F for 30 min."]}

Example output:
{"ingredients": ["{qty:2} cups flour", "{qty:0.5} tsp salt", "{qty:1} egg"], \
"instructions": ["Mix {qty:2} cups flour with water.", "Bake at 350°F for 30 min."]}
"""


def templatize_recipe(recipe_json: dict) -> tuple[list[str] | None, list[str] | None]:
    """Return (ingredients_template, instructions_list_template) for *recipe_json*.

    Both lists use the same ordering as the source data and contain {qty:N}
    placeholders wherever a scalable quantity was identified.  Returns
    (None, None) on any failure — templatization is best-effort.
    """
    if not settings.inference_model:
        return None, None

    ingredients: list[str] = recipe_json.get("ingredients") or []
    instr_list: list[str] = recipe_json.get("instructions_list") or []
    if not instr_list and recipe_json.get("instructions"):
        instr_list = [recipe_json["instructions"]]

    if not ingredients and not instr_list:
        return None, None

    payload = {"ingredients": ingredients, "instructions": instr_list}
    user_message = json.dumps(payload, ensure_ascii=False)

    try:
        resp = requests.post(
            f"{settings.inference_url.rstrip('/')}/v1/chat/completions",
            json={
                "model": settings.inference_model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=settings.inference_timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if the model wrapped the JSON
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        result = json.loads(content)

        out_ingredients: list[str] | None = result.get("ingredients")
        out_instructions: list[str] | None = result.get("instructions")

        # Validate lengths match — if not, discard that half
        if out_ingredients is not None and len(out_ingredients) != len(ingredients):
            log.warning("[templatize] ingredient count mismatch (%d vs %d)", len(out_ingredients), len(ingredients))
            out_ingredients = None
        if out_instructions is not None and len(out_instructions) != len(instr_list):
            log.warning("[templatize] instruction count mismatch (%d vs %d)", len(out_instructions), len(instr_list))
            out_instructions = None

        return out_ingredients, out_instructions

    except Exception as exc:
        log.warning("[templatize] failed: %s", exc)
        return None, None
