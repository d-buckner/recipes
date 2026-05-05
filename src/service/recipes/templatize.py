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
import re
import time

import requests

from .config import settings

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a recipe scaling assistant. Your job is to mark ingredient quantities so a recipe \
can be scaled up or down.

The rule is simple: mark a number ONLY if doubling or halving it would make sense when \
cooking more or fewer servings. Everything else — temperatures, times, pan sizes, \
step counts, percentages — stays as plain text.

Marking rules:
- Use decimal notation for the placeholder value: {qty:2}, {qty:0.5}, {qty:1.5}
- For fractions like "1/2", replace the whole fraction with {qty:0.5}
- For mixed numbers like "1 1/2" or "1½", replace the entire quantity with a single {qty:1.5}

NEVER mark these — they do not scale with servings:
- Cooking times: "30 minutes", "2 hours", "45 seconds"
- Temperatures: "350°F", "180°C"
- Pan or dish sizes: "9-inch pan", "8x8 dish"
- Percentages, step numbers, or any other non-ingredient number
- Relational fractions — fractions that describe a proportion of another ingredient \
already in the recipe, not an absolute quantity: "add ¼ of the meringue", \
"fold in ⅓ of the batter", "reserve half of the sauce". These are always proportional \
and must never be marked.

Return valid JSON with the exact same structure and array lengths as the input. \
No explanation — only the JSON object.

Example input:
{"ingredients": ["2 cups flour", "1/2 tsp salt", "1 egg"], \
"instructions": ["Mix {qty:2} cups flour with ½ of the egg mixture.", \
"Bake at 350°F for 30 minutes.", "Divide into 12 equal pieces."]}

Example output:
{"ingredients": ["{qty:2} cups flour", "{qty:0.5} tsp salt", "{qty:1} egg"], \
"instructions": ["Mix {qty:2} cups flour with ½ of the egg mixture.", \
"Bake at 350°F for 30 minutes.", "Divide into {qty:12} equal pieces."]}
"""

# Matches a {qty:N} placeholder immediately before a time unit — these should
# never be scaled and indicate the model didn't follow instructions.
_TIME_PLACEHOLDER_RE = re.compile(
    r'\{qty:([\d.]+)\}(\s*(?:minutes?|hours?|seconds?|mins?|hrs?|secs?)(?=[\s,.;:!?)]|$))',
    re.IGNORECASE,
)

MAX_ATTEMPTS = 3
RETRY_DELAY = 2.0  # seconds between attempts


def _strip_time_placeholders(text: str) -> str:
    """Replace {qty:N} <time-unit> with the bare number, undoing model errors."""
    def restore(m: re.Match) -> str:
        n = float(m.group(1))
        formatted = str(int(n)) if n == int(n) else str(n)
        return formatted + m.group(2)
    return _TIME_PLACEHOLDER_RE.sub(restore, text)


def templatize_recipe(recipe_json: dict) -> tuple[list[str] | None, list[str] | None]:
    """Return (ingredients_template, instructions_list_template) for *recipe_json*.

    Both lists use the same ordering as the source data and contain {qty:N}
    placeholders wherever a scalable quantity was identified.  Returns
    (None, None) on any failure — templatization is best-effort.
    Retries up to MAX_ATTEMPTS times on transient errors.
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

    last_exc: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
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

            # Post-process: strip any time-unit placeholders the model generated
            if out_ingredients is not None:
                out_ingredients = [_strip_time_placeholders(s) for s in out_ingredients]
            if out_instructions is not None:
                out_instructions = [_strip_time_placeholders(s) for s in out_instructions]

            return out_ingredients, out_instructions

        except Exception as exc:
            last_exc = exc
            if attempt < MAX_ATTEMPTS - 1:
                log.debug("[templatize] attempt %d/%d failed: %s — retrying in %.0fs", attempt + 1, MAX_ATTEMPTS, exc, RETRY_DELAY)
                time.sleep(RETRY_DELAY)

    log.warning("[templatize] failed after %d attempts: %s", MAX_ATTEMPTS, last_exc)
    return None, None
