from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import generations, health
from app.core.config import settings


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

STORAGE_DIR = (
    PROJECT_ROOT / "storage"
)

STORAGE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount(
    "/media",
    StaticFiles(
        directory=str(STORAGE_DIR),
    ),
    name="media",
)


app.include_router(
    health.router,
    prefix="/api/v1/health",
    tags=["Health"],
)

app.include_router(
    generations.router,
    prefix="/api/v1/generations",
    tags=["Generations"],
)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "status": "running",
        "docs": "/docs",
    }
