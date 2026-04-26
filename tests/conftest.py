import sqlite3
from pathlib import Path
from typing import Generator

import pytest

from recipes import db as recipe_db

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def mem_db(tmp_path) -> Generator[None, None, None]:
    """Configure recipes db to use a fresh temp-dir SQLite for each test."""
    db_file = str(tmp_path / "test.db")
    recipe_db.configure(db_file)
    recipe_db.init_db(db_file)
    yield
    recipe_db.configure("recipes.db")  # reset to default


@pytest.fixture()
def recipe_html() -> str:
    return (FIXTURES_DIR / "recipe.html").read_text()


@pytest.fixture()
def sitemap_xml() -> str:
    return (FIXTURES_DIR / "sitemap.xml").read_text()
