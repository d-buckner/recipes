from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RecipeStatus(str, Enum):
    DISCOVERED = "discovered"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


@dataclass
class RecipeRow:
    id: int
    url: str
    site: str
    status: RecipeStatus
    recipe_json: dict[str, Any] | None = None
    error_msg: str | None = None
    retry_count: int = 0
    claimed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class Collection:
    id: int
    name: str
    recipe_count: int
    created_at: str


@dataclass
class SearchResult:
    id: int
    url: str
    site: str
    title: str
    description: str
    total_time: int | None
    yields: str | None
    image: str | None
    site_name: str | None = None
    author: str | None = None
    cuisines: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    is_favorite: bool = False
    has_thumbnail: bool = False
    collections: list[str] = field(default_factory=list)


@dataclass
class ScrapeRunStats:
    total: int
    discovered: int
    processing: int
    complete: int
    failed: int
    unavailable: int
    favorites: int
