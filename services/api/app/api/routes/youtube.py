from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.schemas.youtube import (
    YouTubeConnectResponse,
    YouTubePublishRequest,
    YouTubePublishResponse,
    YouTubeStatusResponse,
)
from app.services.identity_service import ensure_workspace
from app.services.youtube_service import (
    YouTubeIntegrationError,
    complete_oauth,
    connection_status,
    create_authorization_url,
    disconnect,
    upload_video,
)


router = APIRouter()


@router.get("/status", response_model=YouTubeStatusResponse)
def youtube_status(request: Request, response: Response) -> YouTubeStatusResponse:
    workspace_id = ensure_workspace(request, response)
    status = connection_status(workspace_id)
    return YouTubeStatusResponse(
        enabled=settings.youtube_enabled,
        connected=bool(status["connected"]),
        channel_id=status.get("channel_id"),
        channel_title=status.get("channel_title"),
        public_uploads_allowed=settings.youtube_allow_public,
    )


@router.post("/connect", response_model=YouTubeConnectResponse)
def youtube_connect(request: Request, response: Response) -> YouTubeConnectResponse:
    workspace_id = ensure_workspace(request, response)
    try:
        return YouTubeConnectResponse(
            authorization_url=create_authorization_url(workspace_id)
        )
    except YouTubeIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/callback")
def youtube_callback(state: str, code: str | None = None, error: str | None = None):
    base = settings.frontend_url.rstrip("/")
    if error:
        return RedirectResponse(f"{base}/?youtube=error&reason={quote(error[:120])}", status_code=303)
    if not code:
        return RedirectResponse(f"{base}/?youtube=error&reason=missing_code", status_code=303)
    try:
        complete_oauth(state, code)
        return RedirectResponse(f"{base}/?youtube=connected", status_code=303)
    except YouTubeIntegrationError as exc:
        return RedirectResponse(
            f"{base}/?youtube=error&reason={quote(str(exc)[:180])}",
            status_code=303,
        )


@router.delete("/connection")
def youtube_disconnect(request: Request, response: Response) -> dict:
    workspace_id = ensure_workspace(request, response)
    disconnect(workspace_id)
    return {"disconnected": True}


@router.post("/publish", response_model=YouTubePublishResponse)
def youtube_publish(
    payload: YouTubePublishRequest,
    request: Request,
    response: Response,
) -> YouTubePublishResponse:
    workspace_id = ensure_workspace(request, response)
    try:
        result = upload_video(
            workspace_id,
            filename=payload.filename,
            title=payload.title,
            description=payload.description,
            privacy=payload.privacy,
            tags=payload.tags,
            category_id=payload.category_id,
            publish_at=payload.publish_at,
        )
        return YouTubePublishResponse.model_validate(result)
    except YouTubeIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
