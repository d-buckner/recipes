import asyncio
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from . import db, discovery, embeddings, scraper
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


class StartJobResponse(BaseModel):
    status: str
    job_id: int
    queued: int | None = None


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
    response: Response,
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    author: list[str] = Query(default=[]),
    cuisine: list[str] = Query(default=[]),
    category: list[str] = Query(default=[]),
    site: list[str] = Query(default=[]),
    min_time: int | None = Query(default=None, ge=0),
    max_time: int | None = Query(default=None, ge=0),
    mode: Literal["keyword", "semantic", "hybrid"] = Query(default="hybrid"),
) -> list[SearchResult]:
    safe_query = sanitize_fts_query(q)
    filter_kwargs = dict(author=author, cuisine=cuisine, category=category, site=site, min_time=min_time, max_time=max_time)

    if mode == "keyword":
        _set_search_mode_headers(response, requested=mode, used="keyword")
        return db.search_recipes(safe_query, limit=limit, offset=offset, **filter_kwargs)

    # Attempt to embed the query for semantic/hybrid modes
    vector: list[float] | None = None
    degraded_reason: str | None = None
    if settings.embed_model:
        vector = embeddings.get_embedding(q)
        if vector is None:
            degraded_reason = "embedding_unavailable"
    else:
        degraded_reason = "embedding_model_not_configured"

    if mode == "semantic":
        if vector is None:
            _set_search_mode_headers(response, requested=mode, used="keyword", degraded_reason=degraded_reason)
            return db.search_recipes(safe_query, limit=limit, offset=offset, **filter_kwargs)
        _set_search_mode_headers(response, requested=mode, used="semantic")
        return db.semantic_search(vector, limit=limit, offset=offset, **filter_kwargs)

    # hybrid (default): use FTS-only if embedding unavailable
    if vector is None:
        _set_search_mode_headers(response, requested=mode, used="keyword", degraded_reason=degraded_reason)
        return db.search_recipes(safe_query, limit=limit, offset=offset, **filter_kwargs)
    _set_search_mode_headers(response, requested=mode, used="hybrid")
    return db.hybrid_search(safe_query, vector, limit=limit, offset=offset, **filter_kwargs)


def _set_search_mode_headers(
    response: Response,
    *,
    requested: str,
    used: str,
    degraded_reason: str | None = None,
) -> None:
    response.headers["X-Recipes-Search-Mode-Requested"] = requested
    response.headers["X-Recipes-Search-Mode-Used"] = used
    response.headers["X-Recipes-Search-Degraded"] = "true" if degraded_reason else "false"
    if degraded_reason:
        response.headers["X-Recipes-Search-Degraded-Reason"] = degraded_reason


@app.get("/search/capabilities")
def search_capabilities() -> dict:
    semantic_enabled = bool(settings.embed_model)
    return {
        "default_mode": "hybrid",
        "available_modes": ["keyword", "semantic", "hybrid"],
        "semantic_enabled": semantic_enabled,
        "hybrid_enabled": semantic_enabled,
    }


@app.get("/recipes", response_model=list[SearchResult])
def list_recipes(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    author: list[str] = Query(default=[]),
    cuisine: list[str] = Query(default=[]),
    category: list[str] = Query(default=[]),
    site: list[str] = Query(default=[]),
    min_time: int | None = Query(default=None, ge=0),
    max_time: int | None = Query(default=None, ge=0),
) -> list[SearchResult]:
    return db.list_recipes(limit=limit, offset=offset, author=author, cuisine=cuisine, category=category, site=site, min_time=min_time, max_time=max_time)


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


@app.get("/jobs")
def list_jobs(limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    return [job.__dict__ for job in db.list_jobs(limit=limit)]


@app.get("/jobs/{job_id}")
def get_job(job_id: int) -> dict:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.__dict__


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


_DISCOVERY_TIMEOUT = 90.0  # seconds


@app.post("/sites/discover", response_model=DiscoverResponse)
async def discover_site_endpoint(req: DiscoverRequest) -> DiscoverResponse:
    try:
        if req.sitemap_url:
            count = await asyncio.wait_for(
                asyncio.to_thread(discovery.discover_from_sitemap_url, req.sitemap_url),
                timeout=_DISCOVERY_TIMEOUT,
            )
            site = urlparse(req.sitemap_url).netloc or urlparse(req.site_url).netloc
        else:
            count = await asyncio.wait_for(
                asyncio.to_thread(discovery.discover_site, req.site_url),
                timeout=_DISCOVERY_TIMEOUT,
            )
            site = urlparse(req.site_url).netloc
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Discovery timed out — the site may be unreachable or its sitemap is too large.")
    return DiscoverResponse(discovered=count, site=site)


@app.post("/sites/scrape", response_model=StartJobResponse)
def start_scrape(background_tasks: BackgroundTasks) -> StartJobResponse:
    queued = db.count_pending_urls()
    job_id = db.create_job("scrape", total=queued, message="Queued scrape")
    background_tasks.add_task(scraper.run_workers, job_id=job_id)
    return StartJobResponse(status="started", job_id=job_id, queued=queued)


@app.delete("/sites/{hostname}")
def delete_site(hostname: str) -> dict:
    deleted = db.delete_site(hostname)
    return {"site": hostname, "deleted": deleted}


@app.post("/embed/backfill", response_model=StartJobResponse)
def start_embed_backfill(background_tasks: BackgroundTasks) -> StartJobResponse:
    if not settings.embed_model:
        raise HTTPException(status_code=400, detail="Embedding is not configured (RECIPES_EMBED_MODEL is not set)")
    job_id = db.create_job("embed_backfill", message="Queued embedding backfill")
    background_tasks.add_task(scraper.run_embed_backfill, job_id=job_id)
    return StartJobResponse(status="started", job_id=job_id)


@app.post("/sites/rescrape")
def rescrape_all(background_tasks: BackgroundTasks) -> StartJobResponse:
    queued = db.reset_complete_to_discovered()
    job_id = db.create_job("rescrape", total=queued, message="Queued rescrape")
    background_tasks.add_task(scraper.run_workers, job_id=job_id)
    return StartJobResponse(status="started", job_id=job_id, queued=queued)


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
