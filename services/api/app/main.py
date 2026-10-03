import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import generations, health
from app.core.config import settings
from app.services.job_service import initialize_job_store, shutdown_job_executor


LOGGER = logging.getLogger("triven.api")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
STORAGE_DIR = PROJECT_ROOT / "storage"
GENERATED_DIR = STORAGE_DIR / "generated"
LOGS_DIR = STORAGE_DIR / "logs"

for directory in (STORAGE_DIR, GENERATED_DIR, LOGS_DIR):
    directory.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_job_store()
    LOGGER.info(
        "Triven Cinema API starting env=%s provider=%s",
        settings.app_env,
        settings.video_provider,
    )
    yield
    shutdown_job_executor()
    LOGGER.info("Triven Cinema API stopped")


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    debug=settings.debug and not settings.is_production,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
)


# Production browser traffic should normally stay same-origin through Next.js.
# CORS is kept only for explicitly configured origins (useful during development).
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        LOGGER.exception("Unhandled request error request_id=%s path=%s", request_id, request.url.path)
        raise

    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    quiet_poll = (
        request.method == "GET"
        and (
            request.url.path.startswith("/api/v1/generations/jobs/")
            or request.url.path.startswith("/api/v1/health")
        )
    )
    if response.status_code >= 400 or not quiet_poll:
        LOGGER.info(
            "%s %s %s %.1fms request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
    return response


# SECURITY: expose only generated media. Mounting the whole storage directory
# would make the SQLite jobs database and metrics JSONL publicly downloadable.
app.mount(
    "/media/generated",
    StaticFiles(directory=str(GENERATED_DIR)),
    name="generated-media",
)

app.include_router(health.router, prefix="/api/v1/health", tags=["Health"])
app.include_router(generations.router, prefix="/api/v1/generations", tags=["Generations"])


@app.get("/")
async def root():
    payload = {
        "name": settings.app_name,
        "status": "running",
        "environment": settings.app_env,
    }
    if not settings.is_production:
        payload["docs"] = "/docs"
    return payload
