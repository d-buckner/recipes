import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from . import db, discovery, scraper
from .config import settings
from .models import Collection, SearchResult, ScrapeRunStats
from .search import sanitize_fts_query


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db(settings.db_path)
    yield


app = FastAPI(title="Recipes API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RecipeResponse(BaseModel):
    id: int
    url: str
    site: str
    status: str
    recipe_json: dict | None = None
    collections: list[str] = []
    has_thumbnail: bool = False
    has_image: bool = False


class FavoriteResponse(BaseModel):
    recipe_id: int
    status: str


class DiscoverRequest(BaseModel):
    site_url: str
    sitemap_url: str | None = None


class DiscoverResponse(BaseModel):
    discovered: int
    site: str


class CollectionResponse(BaseModel):
    id: int
    name: str
    recipe_count: int
    created_at: str


class CreateCollectionRequest(BaseModel):
    name: str


class RenameCollectionRequest(BaseModel):
    name: str


@app.get("/search", response_model=list[SearchResult])
def search_recipes(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    author: str | None = Query(default=None),
    cuisine: str | None = Query(default=None),
    category: str | None = Query(default=None),
    site: str | None = Query(default=None),
) -> list[SearchResult]:
    safe_query = sanitize_fts_query(q)
    return db.search_recipes(safe_query, limit=limit, offset=offset, author=author, cuisine=cuisine, category=category, site=site)


@app.get("/recipes", response_model=list[SearchResult])
def list_recipes(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    author: str | None = Query(default=None),
    cuisine: str | None = Query(default=None),
    category: str | None = Query(default=None),
    site: str | None = Query(default=None),
) -> list[SearchResult]:
    return db.list_recipes(limit=limit, offset=offset, author=author, cuisine=cuisine, category=category, site=site)


@app.get("/recipes/{recipe_id}", response_model=RecipeResponse)
def get_recipe(recipe_id: int) -> RecipeResponse:
    recipe = db.get_recipe_by_id(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    has_thumbnail, has_image = db.get_image_flags(recipe_id)
    return RecipeResponse(
        id=recipe.id,
        url=recipe.url,
        site=recipe.site,
        status=recipe.status.value,
        recipe_json=recipe.recipe_json,
        collections=db.get_recipe_collection_names(recipe.id),
        has_thumbnail=has_thumbnail,
        has_image=has_image,
    )


@app.get("/recipes/{recipe_id}/thumbnail")
def get_thumbnail(recipe_id: int) -> Response:
    data = db.get_thumbnail(recipe_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=31536000, immutable"},
    )


@app.get("/recipes/{recipe_id}/image")
def get_image(recipe_id: int) -> Response:
    data = db.get_image(recipe_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=31536000, immutable"},
    )


@app.post("/favorites/{recipe_id}", response_model=FavoriteResponse)
def add_favorite(recipe_id: int) -> FavoriteResponse:
    recipe = db.get_recipe_by_id(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    db.add_favorite(recipe_id)
    return FavoriteResponse(recipe_id=recipe_id, status="added")


@app.delete("/favorites/{recipe_id}", response_model=FavoriteResponse)
def remove_favorite(recipe_id: int) -> FavoriteResponse:
    db.remove_favorite(recipe_id)
    return FavoriteResponse(recipe_id=recipe_id, status="removed")


@app.get("/favorites", response_model=list[SearchResult])
def list_favorites() -> list[SearchResult]:
    return db.list_favorites()


@app.get("/stats", response_model=ScrapeRunStats)
def get_stats() -> ScrapeRunStats:
    return db.get_stats()


@app.get("/filters")
def get_filter_options() -> dict:
    return db.list_filter_options()


@app.get("/sites", response_model=list[str])
def list_sites() -> list[str]:
    return db.list_sites()


@app.get("/sites/supported", response_model=list[str])
def list_supported_sites() -> list[str]:
    from recipe_scrapers import SCRAPERS
    return sorted(SCRAPERS.keys())


@app.post("/sites/discover", response_model=DiscoverResponse)
async def discover_site_endpoint(req: DiscoverRequest) -> DiscoverResponse:
    if req.sitemap_url:
        count = await asyncio.to_thread(discovery.discover_from_sitemap_url, req.sitemap_url)
        site = urlparse(req.sitemap_url).netloc or urlparse(req.site_url).netloc
    else:
        count = await asyncio.to_thread(discovery.discover_site, req.site_url)
        site = urlparse(req.site_url).netloc
    return DiscoverResponse(discovered=count, site=site)


@app.post("/sites/scrape")
def start_scrape(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(scraper.run_workers)
    return {"status": "started"}


def _collection_to_response(c: Collection) -> CollectionResponse:
    return CollectionResponse(id=c.id, name=c.name, recipe_count=c.recipe_count, created_at=c.created_at)


@app.get("/collections", response_model=list[CollectionResponse])
def list_collections() -> list[CollectionResponse]:
    return [_collection_to_response(c) for c in db.list_collections()]


@app.post("/collections", response_model=CollectionResponse, status_code=201)
def create_collection(req: CreateCollectionRequest) -> CollectionResponse:
    collection_id = db.create_collection(req.name)
    collections = db.list_collections()
    match = next((c for c in collections if c.id == collection_id), None)
    if match is None:
        raise HTTPException(status_code=500, detail="Collection not found after creation")
    return _collection_to_response(match)


@app.delete("/collections/{collection_id}", status_code=204)
def delete_collection(collection_id: int) -> None:
    db.delete_collection(collection_id)


@app.patch("/collections/{collection_id}", response_model=CollectionResponse)
def rename_collection(collection_id: int, req: RenameCollectionRequest) -> CollectionResponse:
    db.rename_collection(collection_id, req.name)
    collections = db.list_collections()
    match = next((c for c in collections if c.id == collection_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return _collection_to_response(match)


@app.get("/collections/{collection_id}/recipes", response_model=list[SearchResult])
def list_collection_recipes(
    collection_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[SearchResult]:
    return db.list_collection_recipes(collection_id, limit=limit, offset=offset)


@app.post("/collections/{collection_id}/recipes/{recipe_id}", status_code=204)
def add_recipe_to_collection(collection_id: int, recipe_id: int) -> None:
    db.add_recipe_to_collection(collection_id, recipe_id)


@app.delete("/collections/{collection_id}/recipes/{recipe_id}", status_code=204)
def remove_recipe_from_collection(collection_id: int, recipe_id: int) -> None:
    db.remove_recipe_from_collection(collection_id, recipe_id)


def create_app() -> FastAPI:
    """ASGI app factory used by the serve command.

    Dev (RECIPES_STATIC_DIR unset): returns the bare API app so the Vite
    dev-server proxy can strip /api and forward to the root routes as usual.

    Production (RECIPES_STATIC_DIR set): returns a wrapper that mounts the
    API under /api and serves the compiled frontend at /.
    """
    import os
    from pathlib import Path

    static_dir_env = os.environ.get("RECIPES_STATIC_DIR", "")
    if not static_dir_env:
        return app

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    static_dir = Path(static_dir_env)
    wrapper = FastAPI()
    wrapper.mount("/api", app)

    if static_dir.exists():
        wrapper.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @wrapper.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str = "") -> FileResponse:
            return FileResponse(static_dir / "index.html")

    return wrapper
