# Recipe Scraper - Implementation Plan

## Context
Build a Python recipe scraper that discovers recipes from curated sites via sitemaps, scrapes them with `recipe-scrapers`, stores structured data in SQLite with FTS5 search, and exposes an API for an Open WebUI tool.

## Project Structure
```
recipes/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── src/recipes/
│   ├── __init__.py
│   ├── cli.py          # Click CLI: scrape, serve, stats commands
│   ├── config.py       # pydantic-settings: sites, rate limits, db path
│   ├── db.py           # All SQL, schema, FTS5, connection management
│   ├── discovery.py    # Sitemap parsing → discovered URLs
│   ├── scraper.py      # Fetch HTML + recipe-scrapers → structured data
│   ├── search.py       # FTS5 query sanitization
│   ├── api.py          # FastAPI: search, recipes, favorites, stats
│   └── models.py       # RecipeStatus enum, dataclasses, Pydantic schemas
├── openwebui/
│   └── recipe_tool.py  # Standalone Open WebUI tool (calls HTTP API)
└── tests/
    ├── conftest.py
    ├── fixtures/        # Sample HTML, sitemaps
    ├── test_db.py
    ├── test_discovery.py
    ├── test_scraper.py
    ├── test_search.py
    └── test_api.py
```

## Key Dependencies
- `recipe-scrapers` — parse recipe HTML into structured data (635+ sites, wild_mode for unsupported)
- `ultimate-sitemap-parser` — handles sitemap index files, gzip, robots.txt discovery
- `fastapi` + `uvicorn` — HTTP API
- `click` — CLI
- `pydantic-settings` — config from env vars
- `requests` — HTTP fetching (no Playwright unless needed later)

## Implementation Phases

### Phase 1: Scaffolding
- `pyproject.toml` with hatchling build, all deps, `recipes` CLI entrypoint
- Directory structure + `__init__.py` files
- `Dockerfile` (python:3.11-slim, VOLUME /data)
- `docker-compose.yml` (single service, volume mount, env vars)

### Phase 2: Foundation (models, config, db)
- **models.py**: `RecipeStatus` enum (discovered/processing/complete/failed), `RecipeRow`, `SearchResult`, `ScrapeRunStats` dataclasses
- **config.py**: `Settings` class via pydantic-settings — `RECIPES_SITES` (comma-sep), `RECIPES_DB_PATH`, `RECIPES_RATE_LIMIT_DELAY` (default 2s), `RECIPES_MAX_WORKERS` (default 1), `RECIPES_USER_AGENT`
- **db.py**:
  - Schema: `recipes` table (url UNIQUE, site, status, recipe_json TEXT, error_msg, timestamps), `recipe_fts` (FTS5 trigram tokenizer, contentless), `favorites`, `scrape_runs`
  - WAL mode on every connection
  - Functions: `init_db`, `insert_discovered_urls` (INSERT OR IGNORE), `claim_next_url` (atomic select+update), `save_recipe` (update recipes + insert FTS), `fail_recipe`, `search_recipes`, `get_recipe_by_id`, `add_favorite`, `remove_favorite`, `list_favorites`, `get_stats`

### Phase 3: Discovery
- **discovery.py**: Use `ultimate-sitemap-parser` to crawl sitemap tree for each site
- Filter URLs with configurable regex patterns (default: `/recipe[s]?/` in path)
- Batch INSERT OR IGNORE into database (idempotent, safe to re-run)

### Phase 4: Scraper
- **scraper.py**:
  - `fetch_html()` — requests.get with polite User-Agent, timeout
  - `parse_recipe()` — try `scrape_html(html, org_url=url)` first, fall back to `wild_mode=True`
  - `run_worker()` — loop: claim URL → sleep (rate limit) → fetch → parse → save/fail
  - ThreadPoolExecutor for max_workers > 1

### Phase 5: CLI
- **cli.py**: Click group with 3 commands:
  - `recipes scrape` — discover all sites, then run workers until queue empty
  - `recipes serve` — start FastAPI via uvicorn
  - `recipes stats` — print database statistics

### Phase 6: Search + API
- **search.py**: `sanitize_fts_query()` — escape FTS5 special chars, handle multi-word queries
- **api.py**: FastAPI with endpoints:
  - `GET /search?q=&limit=&offset=` — FTS5 search
  - `GET /recipes/{id}` — single recipe with full JSON
  - `POST /favorites/{recipe_id}` — add favorite
  - `DELETE /favorites/{recipe_id}` — remove favorite
  - `GET /favorites` — list all favorites
  - `GET /stats` — scraping statistics
  - CORS middleware enabled

### Phase 7: Open WebUI Tool
- **recipe_tool.py**: Standalone file with `Tools` class, `Valves` (api_base_url config)
  - `search_recipes(query)` — search and return markdown list
  - `get_recipe(recipe_id)` — full recipe rendered as markdown
  - `add_favorite(recipe_id)` — favorite a recipe
  - `list_favorites()` — show all favorites
  - Markdown renderer for recipe display (title, time, servings, ingredients, instructions, source link)

### Phase 8: Tests
- In-memory SQLite for all db tests
- `responses` library to mock HTTP calls
- Sample HTML fixtures with Schema.org JSON-LD
- FastAPI TestClient for API tests

## Key Technical Decisions
- **SQLite FTS5 trigram tokenizer** — built into SQLite 3.34+, enables substring matching ("chick" → "chicken"), no extra extensions needed
- **Contentless FTS table** — avoids storing text twice; trade-off: no highlight()/snippet()
- **No ORM** — raw sqlite3 with context managers; keeps it simple for JSON-heavy workload
- **`recipe-scrapers` to_json()** — store raw dict as-is, extract fields with json_extract() at query time
- **INSERT OR IGNORE for discovery** — makes re-runs idempotent

## recipe-scrapers Library Reference
- Install: `pip install recipe-scrapers` (Python >= 3.10, 635+ supported sites)
- Primary API: `scrape_html(html, org_url=url)` — takes HTML string + URL, returns scraper object
- `wild_mode=True` for unsupported sites (falls back to Schema.org JSON-LD parsing)
- `scraper.to_json()` returns all fields as a dict
- Key fields: title, author, description, image, ingredients (list), instructions, total_time, yields, category, cuisine, nutrients, ratings, keywords
- Does NOT fetch URLs — you bring your own HTTP client
- Exception hierarchy: `WebsiteNotImplementedError` (site not supported), `NoSchemaFoundInWildMode` / `RecipeSchemaNotFound` (no recipe data found)

## Verification
1. `pip install -e ".[dev]"` and run `pytest`
2. Set `RECIPES_SITES=https://www.seriouseats.com` and run `recipes scrape` — verify URLs discovered and recipes scraped
3. Run `recipes serve` and test `curl localhost:8000/search?q=chicken`
4. Install tool in Open WebUI, search for recipes, view a recipe, add/remove favorites
