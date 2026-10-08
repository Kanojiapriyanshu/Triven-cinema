import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from app.schemas.factory import FactoryGenerationRequest, HeroFrameRequest, HeroFrameResponse
from app.schemas.generation import AsyncVideoGenerationResponse
from app.schemas.upscale import UpscaleRequest
from app.services.billing_service import (
    InsufficientCreditsError,
    consume_credits,
    refund_credits,
)
from app.services.element_service import ElementError, elements_for_scene, resolve_element_bindings
from app.services.factory_service import run_factory_generation
from app.services.hero_frame_service import (
    MAX_UPLOAD_BYTES,
    HeroFrameError,
    HeroFrameUnavailable,
    generate_hero_frame,
    save_uploaded_hero_frame,
)
from app.services.identity_service import ensure_workspace
from app.services.storage_service import media_tools_error
from app.services.upscale_service import inspect_draft, run_upscale
from app.services.job_service import JobQueueFullError, submit_job, update_job, workspace_owns_generated_file


router = APIRouter()
LOGGER = logging.getLogger("triven.factory")


@router.post("/jobs", response_model=AsyncVideoGenerationResponse)
def create_factory_job(
    payload: FactoryGenerationRequest,
    request: Request,
    response: Response,
) -> AsyncVideoGenerationResponse:
    workspace_id = ensure_workspace(request, response)
    tools_problem = media_tools_error()
    if tools_problem:
        raise HTTPException(status_code=503, detail=tools_problem)
    if payload.start_frame_filename and not workspace_owns_generated_file(workspace_id, payload.start_frame_filename):
        raise HTTPException(status_code=404, detail="The previous shot to continue from was not found in this workspace.")
    if payload.hero_frame_filename and not workspace_owns_generated_file(workspace_id, payload.hero_frame_filename):
        raise HTTPException(status_code=404, detail="The start frame was not found in this workspace. Generate it again.")
    charge_seconds = max(1, int(round(payload.target_duration_seconds)))
    charge_reference = f"factory:{uuid.uuid4().hex}"

    try:
        consume_credits(workspace_id, charge_seconds, charge_reference)
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    def runner(job_id: str) -> dict:
        def progress(stage: str, percent: int, message: str) -> None:
            update_job(
                job_id,
                status="running",
                stage=stage,
                progress=percent,
                message=message,
            )

        try:
            result = run_factory_generation(
                payload,
                workspace_id=workspace_id,
                progress=progress,
            )
            return result.model_dump()
        except Exception:
            refund_credits(workspace_id, charge_seconds, charge_reference)
            raise

    job_payload = payload.model_dump()
    job_payload["workspace_id"] = workspace_id
    try:
        job_id = submit_job("factory", job_payload, runner)
    except JobQueueFullError as exc:
        refund_credits(workspace_id, charge_seconds, charge_reference)
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception:
        refund_credits(workspace_id, charge_seconds, charge_reference)
        raise

    return AsyncVideoGenerationResponse(
        job_id=job_id,
        status="queued",
        status_url=f"/api/v1/generations/jobs/{job_id}",
    )


@router.post("/hero-frame", response_model=HeroFrameResponse)
def create_hero_frame(payload: HeroFrameRequest, request: Request, response: Response) -> HeroFrameResponse:
    """Compose the start frame (cast already in position) with an image model so it can be approved before rendering."""
    workspace_id = ensure_workspace(request, response)
    try:
        resolved = resolve_element_bindings(workspace_id, payload.element_bindings)
        bindings = elements_for_scene(payload.prompt, resolved)
        path, model = generate_hero_frame(
            workspace_id=workspace_id,
            prompt=payload.prompt,
            bindings=bindings,
            aspect_ratio=payload.aspect_ratio,
        )
    except HeroFrameUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (HeroFrameError, ElementError, ValueError) as exc:
        raise HTTPException(status_code=502 if isinstance(exc, HeroFrameError) else 400, detail=str(exc)) from exc
    return HeroFrameResponse(
        filename=Path(path).name,
        url=f"/media/generated/{Path(path).name}",
        model=model,
        elements=[f"@{item.handle}" for item in bindings],
    )


@router.post("/upscale", response_model=AsyncVideoGenerationResponse)
def create_upscale_job(payload: UpscaleRequest, request: Request, response: Response) -> AsyncVideoGenerationResponse:
    """Queue a Full HD upscale of an approved Draft: the same video with more detail, not a new generation."""
    workspace_id = ensure_workspace(request, response)
    tools_problem = media_tools_error()
    if tools_problem:
        raise HTTPException(status_code=503, detail=tools_problem)
    if not workspace_owns_generated_file(workspace_id, payload.source_filename):
        raise HTTPException(status_code=404, detail="The Draft to upscale was not found in this workspace.")
    try:
        _, _, duration = inspect_draft(payload.source_filename)
    except (ValueError, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    charge_seconds = max(1, int(round(duration)))
    charge_reference = f"upscale:{uuid.uuid4().hex}"
    try:
        consume_credits(workspace_id, charge_seconds, charge_reference)
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    def runner(job_id: str) -> dict:
        def progress(stage: str, percent: int, message: str) -> None:
            update_job(job_id, status="running", stage=stage, progress=percent, message=message)

        try:
            return run_upscale(payload, workspace_id=workspace_id, progress=progress).model_dump()
        except Exception:
            refund_credits(workspace_id, charge_seconds, charge_reference)
            raise

    job_payload = payload.model_dump()
    job_payload["workspace_id"] = workspace_id
    try:
        job_id = submit_job("upscale", job_payload, runner)
    except JobQueueFullError as exc:
        refund_credits(workspace_id, charge_seconds, charge_reference)
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception:
        refund_credits(workspace_id, charge_seconds, charge_reference)
        raise

    return AsyncVideoGenerationResponse(job_id=job_id, status="queued", status_url=f"/api/v1/generations/jobs/{job_id}")


@router.post("/hero-frame/upload", response_model=HeroFrameResponse)
async def upload_hero_frame(request: Request, response: Response, file: UploadFile = File(...)) -> HeroFrameResponse:
    """Use your own start frame, for example one made in the Gemini app, instead of generating one here."""
    workspace_id = ensure_workspace(request, response)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        path = save_uploaded_hero_frame(workspace_id, data)
    except HeroFrameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HeroFrameResponse(filename=path.name, url=f"/media/generated/{path.name}", model="uploaded", elements=[])
