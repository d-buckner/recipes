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
class JobRun:
    id: int
    kind: str
    status: str
    total: int | None
    processed: int
    succeeded: int
    failed: int
    message: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    updated_at: str


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
class GroceryListItem:
    id: int
    qty_num: int | None      # Fraction numerator; None = no quantity
    qty_den: int             # Fraction denominator (always ≥ 1)
    unit: str | None         # normalized unit, e.g. "tbsp", "cup"; None if absent
    ingredient: str          # normalized ingredient name (notes stripped, lowercased)
    original_raw: list[str]  # original unmodified strings before merging
    recipe_ids: list[int]    # IDs of source recipes
    checked: bool
    approximate: bool        # True if quantity was estimated by LLM
    sort_order: int
    created_at: str
    updated_at: str


@dataclass
class ScrapeRunStats:
    total: int
    discovered: int
    processing: int
    complete: int
    failed: int
    unavailable: int
    favorites: int
