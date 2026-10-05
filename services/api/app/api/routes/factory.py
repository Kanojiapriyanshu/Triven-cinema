import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from app.schemas.factory import FactoryGenerationRequest
from app.schemas.generation import AsyncVideoGenerationResponse
from app.services.billing_service import (
    InsufficientCreditsError,
    consume_credits,
    refund_credits,
)
from app.services.factory_service import run_factory_generation
from app.services.identity_service import ensure_workspace
from app.services.job_service import JobQueueFullError, submit_job, update_job


router = APIRouter()
LOGGER = logging.getLogger("triven.factory")


@router.post("/jobs", response_model=AsyncVideoGenerationResponse)
def create_factory_job(
    payload: FactoryGenerationRequest,
    request: Request,
    response: Response,
) -> AsyncVideoGenerationResponse:
    workspace_id = ensure_workspace(request, response)
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
