import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.routes import billing, elements, factory, generations, health, youtube
from app.core.config import settings
from app.services.billing_service import initialize_billing_store
from app.services.element_service import initialize_element_store
from app.services.identity_service import (
    WORKSPACE_HEADER,
    ensure_workspace,
    workspace_id_from_request,
)
from app.services.job_service import (
    initialize_job_store,
    shutdown_job_executor,
    workspace_owns_generated_file,
)
from app.services.storage_service import resolve_generated_asset
from app.services.youtube_service import initialize_youtube_store


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
    initialize_element_store()
    initialize_billing_store()
    initialize_youtube_store()
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
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID", WORKSPACE_HEADER],
        expose_headers=[WORKSPACE_HEADER],
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


@app.post("/api/v1/identity/bootstrap")
def bootstrap_workspace(request: Request, response: Response) -> dict:
    """Establish one workspace identity before parallel UI bootstrap calls.

    The endpoint prevents several first-load billing/YouTube requests from each
    minting a different workspace concurrently. Production keeps the signed token
    HttpOnly; development may also receive a signed response header for split-origin
    localhost testing.
    """
    workspace_id = ensure_workspace(request, response)
    return {"status": "ready", "workspace_id": workspace_id}


# SECURITY: generated media is served through an ownership check rather than a
# raw StaticFiles mount. In production, knowing a random filename is not enough;
# the signed workspace cookie must own a completed job that references the asset.
@app.get("/media/generated/{filename}")
async def generated_media(filename: str, request: Request):
    try:
        path = resolve_generated_asset(filename, extensions={".mp4", ".png", ".jpg", ".jpeg", ".webp"})
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Generated media not found.") from exc

    if settings.is_production:
        workspace_id = workspace_id_from_request(request)
        if not workspace_id or not workspace_owns_generated_file(workspace_id, path.name):
            raise HTTPException(status_code=404, detail="Generated media not found.")

    media_type = "video/mp4" if path.suffix.lower() == ".mp4" else None
    return FileResponse(path, media_type=media_type, filename=None)

app.include_router(health.router, prefix="/api/v1/health", tags=["Health"])
app.include_router(generations.router, prefix="/api/v1/generations", tags=["Generations"])
app.include_router(factory.router, prefix="/api/v1/factory", tags=["Factory"])
app.include_router(elements.router, prefix="/api/v1/elements", tags=["Elements"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["Billing"])
app.include_router(youtube.router, prefix="/api/v1/youtube", tags=["YouTube"])


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
