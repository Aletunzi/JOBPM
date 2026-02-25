import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.auth import require_api_key
from api.cache import cache_clear
from api.database import engine
from api.models import Base
from api.routes import jobs, companies, stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="PM Job Tracker API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to Lovable domain after migration
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(companies.router)
app.include_router(stats.router)


@app.post("/api/admin/cache-clear", tags=["admin"])
async def clear_cache(_key: str = Depends(require_api_key)):
    """Invalidate the in-process cache. Called by GitHub Actions after each scraper run."""
    cache_clear()
    return {"status": "cache cleared"}


@app.post("/api/scrape", tags=["admin"])
async def trigger_scrape(_key: str = Depends(require_api_key)):
    """Manually trigger the scraper (runs in-process, may be slow)."""
    try:
        from run_scraper import main as run_main
        import asyncio
        asyncio.create_task(run_main())
        cache_clear()
        return {"status": "scrape started"}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.get("/health", tags=["system"], include_in_schema=False)
async def health_check():
    return {"status": "ok"}


# Serve frontend AFTER /api routes are registered so API takes priority
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    templates = Jinja2Templates(directory=str(frontend_dir))

    @app.get("/", include_in_schema=False)
    async def serve_frontend(request: Request):
        api_key = os.environ.get("API_KEY", "dev-insecure-key")
        return templates.TemplateResponse("index.html", {"request": request, "api_key": api_key})

    @app.get("/admin", include_in_schema=False)
    async def serve_admin(request: Request):
        api_key = os.environ.get("API_KEY", "dev-insecure-key")
        return templates.TemplateResponse("admin.html", {"request": request, "api_key": api_key})

    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
