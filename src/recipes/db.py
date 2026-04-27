import json
import sqlite3
from contextlib import contextmanager
from typing import Generator

from .models import Collection, RecipeRow, RecipeStatus, SearchResult, ScrapeRunStats

_db_path: str = "recipes.db"


def configure(db_path: str) -> None:
    global _db_path
    _db_path = db_path


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT    NOT NULL UNIQUE,
    site        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'discovered',
    recipe_json TEXT,
    error_msg   TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    claimed_at  TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recipe_fts (
    id          INTEGER PRIMARY KEY,
    title       TEXT,
    description TEXT,
    ingredients TEXT,
    keywords    TEXT
) STRICT;

CREATE VIRTUAL TABLE IF NOT EXISTS recipe_fts_search USING fts5(
    title,
    description,
    ingredients,
    keywords,
    content=recipe_fts,
    content_rowid=id,
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS recipe_fts_insert
AFTER INSERT ON recipe_fts BEGIN
    INSERT INTO recipe_fts_search(rowid, title, description, ingredients, keywords)
    VALUES (new.id, new.title, new.description, new.ingredients, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS recipe_fts_update
AFTER UPDATE ON recipe_fts BEGIN
    INSERT INTO recipe_fts_search(recipe_fts_search, rowid, title, description, ingredients, keywords)
    VALUES ('delete', old.id, old.title, old.description, old.ingredients, old.keywords);
    INSERT INTO recipe_fts_search(rowid, title, description, ingredients, keywords)
    VALUES (new.id, new.title, new.description, new.ingredients, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS recipe_fts_delete
AFTER DELETE ON recipe_fts BEGIN
    INSERT INTO recipe_fts_search(recipe_fts_search, rowid, title, description, ingredients, keywords)
    VALUES ('delete', old.id, old.title, old.description, old.ingredients, old.keywords);
END;

CREATE TABLE IF NOT EXISTS favorites (
    recipe_id   INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (recipe_id)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site        TEXT    NOT NULL,
    started_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    urls_found  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS collections (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS collection_recipes (
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    recipe_id     INTEGER NOT NULL REFERENCES recipes(id)     ON DELETE CASCADE,
    added_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (collection_id, recipe_id)
);
"""


_MIGRATIONS = [
    "ALTER TABLE recipes ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE recipes ADD COLUMN claimed_at TEXT",
    "ALTER TABLE recipes ADD COLUMN thumbnail BLOB",
]


def _migrate_list_fields() -> None:
    """Convert legacy comma-separated category/cuisine strings to JSON arrays.
    Safe to run on every startup — skips rows already storing arrays."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, recipe_json FROM recipes WHERE recipe_json IS NOT NULL"
        ).fetchall()
        for row in rows:
            data = json.loads(row["recipe_json"])
            changed = False
            for field in ("category", "cuisine"):
                val = data.get(field)
                if isinstance(val, str):
                    data[field] = [v.strip() for v in val.split(",") if v.strip()] or None
                    changed = True
            if changed:
                conn.execute(
                    "UPDATE recipes SET recipe_json = ? WHERE id = ?",
                    (json.dumps(data), row["id"]),
                )


def init_db(db_path: str | None = None) -> None:
    if db_path:
        configure(db_path)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Run additive migrations; silently skip if column already exists
        for migration in _MIGRATIONS:
            try:
                conn.execute(migration)
            except sqlite3.OperationalError:
                pass
    _migrate_list_fields()


def reset_stale_processing() -> int:
    """
    Reset any 'processing' rows back to 'discovered'.
    Call at the start of each scrape run — any processing items at that point
    must belong to a crashed previous run.
    Returns the number of rows reset.
    """
    with get_conn() as conn:
        cursor = conn.execute(
            """
            UPDATE recipes SET status = 'discovered', claimed_at = NULL, updated_at = datetime('now')
            WHERE status = 'processing'
            """
        )
        return cursor.rowcount


def insert_discovered_urls(urls: list[tuple[str, str]]) -> int:
    """Insert (url, site) pairs; returns number of new rows inserted."""
    with get_conn() as conn:
        cursor = conn.executemany(
            "INSERT OR IGNORE INTO recipes (url, site, status) VALUES (?, ?, 'discovered')",
            urls,
        )
        return cursor.rowcount


def claim_next_url(claim_timeout: int = 300) -> RecipeRow | None:
    """
    Atomically claim the next URL for processing.
    Picks from:
      - status = 'discovered' (normal queue), OR
      - status = 'processing' AND claimed_at is stale (crash recovery)
    """
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE recipes
            SET status = 'processing',
                claimed_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = (
                SELECT id FROM recipes
                WHERE status = 'discovered'
                   OR (
                       status = 'processing'
                       AND claimed_at < datetime('now', ? || ' seconds')
                   )
                ORDER BY created_at ASC LIMIT 1
            )
            RETURNING id, url, site, status, recipe_json, error_msg,
                      retry_count, claimed_at, created_at, updated_at
            """,
            (f"-{claim_timeout}",),
        ).fetchone()
        if row is None:
            return None
        return _row_to_recipe(row)


def save_recipe(recipe_id: int, recipe_json: dict, thumbnail: bytes | None = None) -> None:
    title = recipe_json.get("title", "")
    description = recipe_json.get("description", "") or ""
    ingredients = " ".join(recipe_json.get("ingredients", []) or [])
    keywords = " ".join(recipe_json.get("keywords", []) or []) if isinstance(recipe_json.get("keywords"), list) else (recipe_json.get("keywords") or "")

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE recipes
            SET status = 'complete', recipe_json = ?, thumbnail = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (json.dumps(recipe_json), thumbnail, recipe_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO recipe_fts (id, title, description, ingredients, keywords) VALUES (?, ?, ?, ?, ?)",
            (recipe_id, title, description, ingredients, keywords),
        )


def get_thumbnail(recipe_id: int) -> bytes | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT thumbnail FROM recipes WHERE id = ?", (recipe_id,)
        ).fetchone()
        if row is None:
            return None
        return row["thumbnail"]


def mark_unavailable(recipe_id: int, error_msg: str) -> None:
    """
    Permanently mark a recipe as unavailable (e.g. behind a paywall).
    Unlike fail_recipe, this never requeues — retrying won't help.
    """
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE recipes
            SET status     = 'unavailable',
                error_msg  = ?,
                claimed_at = NULL,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (error_msg, recipe_id),
        )


def fail_recipe(recipe_id: int, error_msg: str, max_retries: int = 3) -> None:
    """
    Record a scrape failure. If retry_count < max_retries, requeue as
    'discovered' for another attempt. Otherwise mark permanently 'failed'.
    """
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE recipes
            SET retry_count  = retry_count + 1,
                error_msg    = ?,
                claimed_at   = NULL,
                status       = CASE
                                   WHEN retry_count + 1 < ? THEN 'discovered'
                                   ELSE 'failed'
                               END,
                updated_at   = datetime('now')
            WHERE id = ?
            """,
            (error_msg, max_retries, recipe_id),
        )


def search_recipes(
    query: str,
    limit: int = 20,
    offset: int = 0,
    author: str | None = None,
    cuisine: str | None = None,
    category: str | None = None,
    site: str | None = None,
) -> list[SearchResult]:
    extra_conditions: list[str] = []
    extra_params: list[str] = []
    if author:
        extra_conditions.append("json_extract(r.recipe_json, '$.author') = ?")
        extra_params.append(author)
    if cuisine:
        extra_conditions.append("EXISTS (SELECT 1 FROM json_each(r.recipe_json, '$.cuisine') WHERE value = ?)")
        extra_params.append(cuisine)
    if category:
        extra_conditions.append("EXISTS (SELECT 1 FROM json_each(r.recipe_json, '$.category') WHERE value = ?)")
        extra_params.append(category)
    if site:
        extra_conditions.append("r.site = ?")
        extra_params.append(site)
    extra_where = (" AND " + " AND ".join(extra_conditions)) if extra_conditions else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT r.id, r.url, r.site,
                   json_extract(r.recipe_json, '$.title') AS title,
                   json_extract(r.recipe_json, '$.description') AS description,
                   json_extract(r.recipe_json, '$.total_time') AS total_time,
                   json_extract(r.recipe_json, '$.yields') AS yields,
                   json_extract(r.recipe_json, '$.image') AS image,
                   json_extract(r.recipe_json, '$.site_name') AS site_name,
                   json_extract(r.recipe_json, '$.author') AS author,
                   json_extract(r.recipe_json, '$.cuisine') AS cuisine,
                   json_extract(r.recipe_json, '$.category') AS category,
                   (r.thumbnail IS NOT NULL) AS has_thumbnail,
                   CASE WHEN f.recipe_id IS NOT NULL THEN 1 ELSE 0 END AS is_favorite,
                   COALESCE(
                     (SELECT GROUP_CONCAT(c.name, '||')
                      FROM collection_recipes cr JOIN collections c ON c.id = cr.collection_id
                      WHERE cr.recipe_id = r.id),
                     ''
                   ) AS collection_names
            FROM recipe_fts_search fs
            JOIN recipes r ON r.id = fs.rowid
            LEFT JOIN favorites f ON f.recipe_id = r.id
            WHERE recipe_fts_search MATCH ? AND r.status = 'complete'{extra_where}
            ORDER BY rank
            LIMIT ? OFFSET ?
            """,
            [query, *extra_params, limit, offset],
        ).fetchall()
        return [_row_to_search_result(r) for r in rows]


def get_recipe_collection_names(recipe_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.name FROM collections c
            JOIN collection_recipes cr ON cr.collection_id = c.id
            WHERE cr.recipe_id = ?
            ORDER BY c.name
            """,
            (recipe_id,),
        ).fetchall()
        return [row["name"] for row in rows]


def get_recipe_by_id(recipe_id: int) -> RecipeRow | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, url, site, status, recipe_json, error_msg, retry_count, claimed_at, created_at, updated_at FROM recipes WHERE id = ?",
            (recipe_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_recipe(row)


def add_favorite(recipe_id: int) -> None:
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO favorites (recipe_id) VALUES (?)", (recipe_id,))


def remove_favorite(recipe_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM favorites WHERE recipe_id = ?", (recipe_id,))


def list_favorites() -> list[SearchResult]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.url, r.site,
                   json_extract(r.recipe_json, '$.title') AS title,
                   json_extract(r.recipe_json, '$.description') AS description,
                   json_extract(r.recipe_json, '$.total_time') AS total_time,
                   json_extract(r.recipe_json, '$.yields') AS yields,
                   json_extract(r.recipe_json, '$.image') AS image,
                   json_extract(r.recipe_json, '$.site_name') AS site_name,
                   json_extract(r.recipe_json, '$.author') AS author,
                   json_extract(r.recipe_json, '$.cuisine') AS cuisine,
                   json_extract(r.recipe_json, '$.category') AS category,
                   (r.thumbnail IS NOT NULL) AS has_thumbnail,
                   1 AS is_favorite,
                   COALESCE(
                     (SELECT GROUP_CONCAT(c.name, '||')
                      FROM collection_recipes cr JOIN collections c ON c.id = cr.collection_id
                      WHERE cr.recipe_id = r.id),
                     ''
                   ) AS collection_names
            FROM favorites f
            JOIN recipes r ON r.id = f.recipe_id
            WHERE r.status = 'complete'
            ORDER BY f.created_at DESC
            """
        ).fetchall()
        return [_row_to_search_result(r) for r in rows]


def get_stats() -> ScrapeRunStats:
    with get_conn() as conn:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(status = 'discovered') AS discovered,
                SUM(status = 'processing') AS processing,
                SUM(status = 'complete') AS complete,
                SUM(status = 'failed') AS failed,
                SUM(status = 'unavailable') AS unavailable
            FROM recipes
            """
        ).fetchone()
        fav_count = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
        return ScrapeRunStats(
            total=totals["total"] or 0,
            discovered=totals["discovered"] or 0,
            processing=totals["processing"] or 0,
            complete=totals["complete"] or 0,
            failed=totals["failed"] or 0,
            unavailable=totals["unavailable"] or 0,
            favorites=fav_count,
        )


def list_recipes(
    limit: int = 20,
    offset: int = 0,
    author: str | None = None,
    cuisine: str | None = None,
    category: str | None = None,
    site: str | None = None,
) -> list[SearchResult]:
    conditions = ["r.status = 'complete'"]
    params: list[str | int] = []
    if author:
        conditions.append("json_extract(r.recipe_json, '$.author') = ?")
        params.append(author)
    if cuisine:
        conditions.append("EXISTS (SELECT 1 FROM json_each(r.recipe_json, '$.cuisine') WHERE value = ?)")
        params.append(cuisine)
    if category:
        conditions.append("EXISTS (SELECT 1 FROM json_each(r.recipe_json, '$.category') WHERE value = ?)")
        params.append(category)
    if site:
        conditions.append("r.site = ?")
        params.append(site)
    where = " AND ".join(conditions)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT r.id, r.url, r.site,
                   json_extract(r.recipe_json, '$.title') AS title,
                   json_extract(r.recipe_json, '$.description') AS description,
                   json_extract(r.recipe_json, '$.total_time') AS total_time,
                   json_extract(r.recipe_json, '$.yields') AS yields,
                   json_extract(r.recipe_json, '$.image') AS image,
                   json_extract(r.recipe_json, '$.site_name') AS site_name,
                   json_extract(r.recipe_json, '$.author') AS author,
                   json_extract(r.recipe_json, '$.cuisine') AS cuisine,
                   json_extract(r.recipe_json, '$.category') AS category,
                   (r.thumbnail IS NOT NULL) AS has_thumbnail,
                   CASE WHEN f.recipe_id IS NOT NULL THEN 1 ELSE 0 END AS is_favorite,
                   COALESCE(
                     (SELECT GROUP_CONCAT(c.name, '||')
                      FROM collection_recipes cr JOIN collections c ON c.id = cr.collection_id
                      WHERE cr.recipe_id = r.id),
                     ''
                   ) AS collection_names
            FROM recipes r
            LEFT JOIN favorites f ON f.recipe_id = r.id
            WHERE {where}
            ORDER BY r.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        return [_row_to_search_result(r) for r in rows]


def list_sites() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT site FROM recipes ORDER BY site").fetchall()
        return [row["site"] for row in rows]


def list_filter_options() -> dict[str, list[dict[str, str | int]]]:
    """Return distinct values + counts for each filterable dimension."""
    with get_conn() as conn:
        cuisine_rows = conn.execute(
            """
            SELECT je.value, COUNT(*) AS cnt
            FROM recipes r, json_each(r.recipe_json, '$.cuisine') je
            WHERE r.status = 'complete' AND je.value != ''
            GROUP BY je.value
            ORDER BY cnt DESC, je.value
            LIMIT 100
            """
        ).fetchall()

        category_rows = conn.execute(
            """
            SELECT je.value, COUNT(*) AS cnt
            FROM recipes r, json_each(r.recipe_json, '$.category') je
            WHERE r.status = 'complete' AND je.value != ''
            GROUP BY je.value
            ORDER BY cnt DESC, je.value
            LIMIT 100
            """
        ).fetchall()

        author_rows = conn.execute(
            """
            SELECT json_extract(recipe_json, '$.author') AS value, COUNT(*) AS cnt
            FROM recipes
            WHERE status = 'complete'
              AND json_extract(recipe_json, '$.author') IS NOT NULL
              AND json_extract(recipe_json, '$.author') != ''
            GROUP BY value
            ORDER BY cnt DESC, value
            LIMIT 100
            """
        ).fetchall()

        site_rows = conn.execute(
            """
            SELECT site AS value, COUNT(*) AS cnt
            FROM recipes
            WHERE status = 'complete'
            GROUP BY site
            ORDER BY cnt DESC, site
            LIMIT 100
            """
        ).fetchall()

    return {
        "cuisine": [{"value": r["value"], "count": r["cnt"]} for r in cuisine_rows],
        "category": [{"value": r["value"], "count": r["cnt"]} for r in category_rows],
        "author": [{"value": r["value"], "count": r["cnt"]} for r in author_rows],
        "site": [{"value": r["value"], "count": r["cnt"]} for r in site_rows],
    }


def create_collection(name: str) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO collections (name) VALUES (?)",
            (name,),
        )
        return cursor.lastrowid  # type: ignore[return-value]


def delete_collection(collection_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))


def rename_collection(collection_id: int, name: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE collections SET name = ? WHERE id = ?", (name, collection_id))


def list_collections() -> list[Collection]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.created_at,
                   COUNT(cr.recipe_id) AS recipe_count
            FROM collections c
            LEFT JOIN collection_recipes cr ON cr.collection_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at ASC
            """
        ).fetchall()
        return [
            Collection(
                id=row["id"],
                name=row["name"],
                recipe_count=row["recipe_count"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


def add_recipe_to_collection(collection_id: int, recipe_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO collection_recipes (collection_id, recipe_id) VALUES (?, ?)",
            (collection_id, recipe_id),
        )


def remove_recipe_from_collection(collection_id: int, recipe_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM collection_recipes WHERE collection_id = ? AND recipe_id = ?",
            (collection_id, recipe_id),
        )


def list_collection_recipes(collection_id: int, limit: int = 20, offset: int = 0) -> list[SearchResult]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.url, r.site,
                   json_extract(r.recipe_json, '$.title') AS title,
                   json_extract(r.recipe_json, '$.description') AS description,
                   json_extract(r.recipe_json, '$.total_time') AS total_time,
                   json_extract(r.recipe_json, '$.yields') AS yields,
                   json_extract(r.recipe_json, '$.image') AS image,
                   json_extract(r.recipe_json, '$.site_name') AS site_name,
                   json_extract(r.recipe_json, '$.author') AS author,
                   json_extract(r.recipe_json, '$.cuisine') AS cuisine,
                   json_extract(r.recipe_json, '$.category') AS category,
                   (r.thumbnail IS NOT NULL) AS has_thumbnail,
                   CASE WHEN f.recipe_id IS NOT NULL THEN 1 ELSE 0 END AS is_favorite,
                   COALESCE(
                     (SELECT GROUP_CONCAT(c2.name, '||')
                      FROM collection_recipes cr2 JOIN collections c2 ON c2.id = cr2.collection_id
                      WHERE cr2.recipe_id = r.id),
                     ''
                   ) AS collection_names
            FROM collection_recipes cr
            JOIN recipes r ON r.id = cr.recipe_id
            LEFT JOIN favorites f ON f.recipe_id = r.id
            WHERE cr.collection_id = ? AND r.status = 'complete'
            ORDER BY cr.added_at DESC
            LIMIT ? OFFSET ?
            """,
            (collection_id, limit, offset),
        ).fetchall()
        return [_row_to_search_result(r) for r in rows]


def _row_to_recipe(row: sqlite3.Row) -> RecipeRow:
    recipe_json = json.loads(row["recipe_json"]) if row["recipe_json"] else None
    return RecipeRow(
        id=row["id"],
        url=row["url"],
        site=row["site"],
        status=RecipeStatus(row["status"]),
        recipe_json=recipe_json,
        error_msg=row["error_msg"],
        retry_count=row["retry_count"] or 0,
        claimed_at=row["claimed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _parse_json_list(value: str | None) -> list[str]:
    """Parse a JSON array field from recipe_json. Returns [] for null/missing."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(v).strip() for v in parsed if str(v).strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _row_to_search_result(row: sqlite3.Row) -> SearchResult:
    raw_names = row["collection_names"] or ""
    collections = [n for n in raw_names.split("||") if n] if raw_names else []
    return SearchResult(
        id=row["id"],
        url=row["url"],
        site=row["site"],
        title=row["title"] or "",
        description=row["description"] or "",
        total_time=row["total_time"],
        yields=row["yields"],
        image=row["image"],
        site_name=row["site_name"] or None,
        author=row["author"] or None,
        cuisines=_parse_json_list(row["cuisine"]),
        categories=_parse_json_list(row["category"]),
        is_favorite=bool(row["is_favorite"]),
        has_thumbnail=bool(row["has_thumbnail"]),
        collections=collections,
    )
