import logging
import uuid
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.generation import (
    AsyncVideoGenerationResponse,
    CombineScenesRequest,
    CombineScenesResponse,
    FullVideoGenerationRequest,
    FullVideoGenerationResponse,
    GenerationCapabilitiesResponse,
    GenerationJobResponse,
    MediaInfo,
    MetricsSummaryResponse,
    ScenePlanRequest,
    ScenePlanResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from app.services.job_service import (
    JobQueueFullError,
    get_job,
    submit_job,
    update_job,
)
from app.services.media_probe import probe_media
from app.services.metrics_service import (
    estimate_gpu_cost,
    record_generation_metric,
    summarize_generation_metrics,
)
from app.services.prompt_quality import evaluate_plan_prompt_coverage
from app.services.scene_planner import create_scene_plan
from app.services.storage_service import ensure_minimum_free_disk
from app.services.video_combiner import combine_videos, upscale_to_1080p
from app.services.video_profiles import source_render_dimensions
from inference.providers.router import get_video_provider


router = APIRouter()
LOGGER = logging.getLogger("triven.generations")

PROJECT_ROOT = Path(__file__).resolve().parents[5]
GENERATED_DIR = (PROJECT_ROOT / "storage" / "generated").resolve()
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

ProgressCallback = Callable[[str, int, str], None]


def quality_note(quality: str, aspect_ratio: str) -> str:
    if quality != "1080p":
        return "Source render profile; no delivery upscale applied."

    if aspect_ratio == "9:16":
        delivery = "1080x1920"
    elif aspect_ratio == "1:1":
        delivery = "1080x1080"
    else:
        delivery = "1920x1080"

    return (
        f"{delivery} delivery file. Triven renders the LTX source profile first "
        "and performs at most one FFmpeg delivery upscale. This is not a claim "
        "that the source frames were natively generated at 1080p."
    )


def media_url(filename: str) -> str:
    return f"/media/generated/{filename}"


def download_url(filename: str) -> str:
    return f"/api/v1/generations/download/{filename}"


def resolve_generated_video(video_url: str) -> Path:
    parsed = urlparse(video_url)
    filename = Path(parsed.path).name

    if not filename or not filename.lower().endswith(".mp4"):
        raise ValueError(f"Invalid generated MP4 URL: {video_url}")

    path = (GENERATED_DIR / filename).resolve()
    if path.parent != GENERATED_DIR:
        raise ValueError("Invalid generated video path.")
    if not path.exists():
        raise FileNotFoundError(f"Generated scene not found: {filename}")

    return path


def apply_delivery_quality(
    source_path: Path,
    *,
    aspect_ratio: str,
    quality: str,
    prefix: str,
) -> Path:
    if quality != "1080p":
        return source_path

    destination = GENERATED_DIR / f"{prefix}-1080p-{uuid.uuid4().hex}.mp4"
    return upscale_to_1080p(
        input_path=source_path,
        output_path=destination,
        aspect_ratio=aspect_ratio,
    )


def _media_info(path: Path) -> MediaInfo:
    return MediaInfo.model_validate(probe_media(path))


def _generate_video_impl(
    request: VideoGenerationRequest,
    progress: ProgressCallback | None = None,
) -> VideoGenerationResponse:
    if progress:
        progress("initializing", 8, "Checking local storage and selecting the render provider...")

    ensure_minimum_free_disk()
    provider_key = request.provider or settings.video_provider
    provider = get_video_provider(
        provider_key,
        model=request.model,
    )
    width, height = source_render_dimensions(request.aspect_ratio)

    prompt_to_render = request.prompt
    provider_enhance_prompt = request.enhance_prompt
    if request.enhance_prompt and provider_key == "modal":
        # The self-hosted Modal CLI does not expose the public Space prompt enhancer.
        # Reuse Triven's Gemini planner to create one generation-ready direct shot.
        prompt_to_render = create_scene_plan(
            prompt=request.prompt,
            scene_count=1,
            aspect_ratio=request.aspect_ratio,
            force_ai=True,
        ).scenes[0].prompt
        provider_enhance_prompt = False

    if progress:
        progress(
            "rendering",
            20,
            "Allocating GPU, loading LTX-2.5 and rendering the clip...",
        )

    result = provider.generate(
        prompt=prompt_to_render,
        width=width,
        height=height,
        duration_seconds=request.duration_seconds,
        seed=request.seed,
        decoder=request.decoder,
        enhance_prompt=provider_enhance_prompt,
    )

    source_path = Path(result.path)
    if progress:
        progress("delivery", 82, "Preparing the requested delivery file...")

    delivery_path = apply_delivery_quality(
        source_path,
        aspect_ratio=request.aspect_ratio,
        quality=request.quality,
        prefix="scene",
    )

    if progress:
        progress("probing", 92, "Validating video dimensions and native audio stream...")

    media_info = _media_info(delivery_path)
    wall_seconds = float(result.wall_seconds or result.render_seconds)
    estimated_cost, estimated_cost_per_minute, cost_note = estimate_gpu_cost(
        render_seconds=wall_seconds,
        gpu=result.gpu,
        output_duration_seconds=request.duration_seconds,
    )

    filename = delivery_path.name
    record_generation_metric(
        {
            "type": "scene",
            "provider": result.provider,
            "model": request.model,
            "gpu": result.gpu,
            "aspect_ratio": request.aspect_ratio,
            "source_width": width,
            "source_height": height,
            "delivery_width": media_info.width,
            "delivery_height": media_info.height,
            "duration_seconds": request.duration_seconds,
            "render_seconds": round(result.render_seconds, 3),
            "wall_seconds": round(wall_seconds, 3),
            "quality": request.quality,
            "decoder": request.decoder,
            "seed": request.seed,
            "has_audio": media_info.has_audio,
            "audio_codec": media_info.audio_codec,
            "estimated_cost_usd": estimated_cost,
            "estimated_cost_per_output_minute_usd": estimated_cost_per_minute,
            "filename": filename,
        }
    )

    return VideoGenerationResponse(
        video_url=media_url(filename),
        download_url=download_url(filename),
        filename=filename,
        seed=result.seed,
        render_details=result.render_details,
        render_seconds=round(result.render_seconds, 2),
        wall_seconds=round(wall_seconds, 2),
        provider=result.provider,
        model=request.model,
        quality=request.quality,
        quality_note=quality_note(request.quality, request.aspect_ratio),
        gpu=result.gpu,
        media_info=media_info,
        estimated_cost_usd=estimated_cost,
        estimated_cost_per_output_minute_usd=estimated_cost_per_minute,
        cost_note=cost_note,
    )


@router.get(
    "/capabilities",
    response_model=GenerationCapabilitiesResponse,
)
async def generation_capabilities():
    cost_tracking_configured = any(
        rate > 0
        for rate in (
            settings.modal_gpu_hourly_usd_b200,
            settings.modal_gpu_hourly_usd_h200,
            settings.modal_gpu_hourly_usd_h100,
        )
    )
    return GenerationCapabilitiesResponse(
        providers=[
            {
                "id": "huggingface",
                "label": "ZeroGPU (development)",
                "available": True,
                "paid": False,
            },
            {
                "id": "modal",
                "label": "Modal self-hosted LTX-2.5",
                "available": True,
                "paid": True,
            },
        ],
        models=[
            {"id": "ltx-2.5", "label": "LTX 2.5", "available": True},
            {"id": "wan", "label": "WAN", "available": False},
            {"id": "minimax", "label": "MiniMax", "available": False},
        ],
        qualities=[
            {
                "id": "preview",
                "label": "Source preview",
                "description": "Fast source render; best for prompt iteration.",
            },
            {
                "id": "1080p",
                "label": "1080p delivery",
                "description": "Single FFmpeg delivery upscale after source generation.",
            },
        ],
        aspect_ratios=["16:9", "9:16", "1:1"],
        decoders=["conv", "diffusion"],
        max_scene_duration_seconds=5.0,
        async_jobs=True,
        audio_probe=True,
        cost_tracking_configured=cost_tracking_configured,
        production_mode=settings.is_production,
        job_workers=settings.job_workers,
        job_max_pending=settings.job_max_pending,
    )


@router.post("/plan", response_model=ScenePlanResponse)
def plan_generation(request: ScenePlanRequest):
    try:
        plan = create_scene_plan(
            prompt=request.prompt,
            scene_count=request.scene_count,
            aspect_ratio=request.aspect_ratio,
        )
        plan_quality = evaluate_plan_prompt_coverage(
            request.prompt,
            [scene.prompt for scene in plan.scenes],
        )
        return ScenePlanResponse(
            original_prompt=request.prompt,
            aspect_ratio=request.aspect_ratio,
            scenes=plan.scenes,
            plan_quality=plan_quality,
            planner_source=plan.source,
            planner_note=plan.note,
        )
    except Exception as exc:
        LOGGER.exception("Scene planning failed")
        detail = str(exc) if settings.debug and not settings.is_production else "Scene planning failed."
        raise HTTPException(status_code=500, detail=detail) from exc


@router.post("/video", response_model=VideoGenerationResponse)
def generate_video(request: VideoGenerationRequest):
    """Synchronous compatibility endpoint. Prefer /jobs/video in the UI."""
    if settings.is_production and not settings.enable_sync_render_endpoints:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        return _generate_video_impl(request)
    except Exception as exc:
        LOGGER.exception("Video generation failed")
        detail = str(exc) if settings.debug and not settings.is_production else "Video generation failed."
        raise HTTPException(status_code=500, detail=detail) from exc


@router.post("/jobs/video", response_model=AsyncVideoGenerationResponse)
async def create_video_job(request: VideoGenerationRequest):
    payload = request.model_dump()

    def runner(job_id: str) -> dict:
        def progress(stage: str, percent: int, message: str) -> None:
            update_job(
                job_id,
                status="running",
                stage=stage,
                progress=percent,
                message=message,
            )

        result = _generate_video_impl(request, progress=progress)
        return result.model_dump()

    try:
        job_id = submit_job("video", payload, runner)
    except JobQueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    return AsyncVideoGenerationResponse(
        job_id=job_id,
        status="queued",
        status_url=f"/api/v1/generations/jobs/{job_id}",
    )


@router.get("/jobs/{job_id}", response_model=GenerationJobResponse)
async def generation_job_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    return GenerationJobResponse.model_validate(job)


@router.post("/combine", response_model=CombineScenesResponse)
def combine_existing_scenes(request: CombineScenesRequest):
    try:
        ensure_minimum_free_disk()
        video_paths = [
            resolve_generated_video(url)
            for url in request.scene_video_urls
        ]

        combined_path = GENERATED_DIR / f"final-{uuid.uuid4().hex}.mp4"
        combine_videos(video_paths, combined_path)

        delivery_path = apply_delivery_quality(
            combined_path,
            aspect_ratio=request.aspect_ratio,
            quality=request.quality,
            prefix="final",
        )
        media_info = _media_info(delivery_path)
        filename = delivery_path.name

        record_generation_metric(
            {
                "type": "combine",
                "scene_count": len(video_paths),
                "aspect_ratio": request.aspect_ratio,
                "quality": request.quality,
                "delivery_width": media_info.width,
                "delivery_height": media_info.height,
                "has_audio": media_info.has_audio,
                "audio_codec": media_info.audio_codec,
                "filename": filename,
            }
        )

        return CombineScenesResponse(
            final_video_url=media_url(filename),
            final_download_url=download_url(filename),
            final_filename=filename,
            scene_count=len(video_paths),
            quality=request.quality,
            quality_note=quality_note(request.quality, request.aspect_ratio),
            media_info=media_info,
        )
    except Exception as exc:
        LOGGER.exception("Video combine failed")
        detail = str(exc) if settings.debug and not settings.is_production else "Video combine failed."
        raise HTTPException(status_code=500, detail=detail) from exc


@router.post("/full-video", response_model=FullVideoGenerationResponse)
def generate_full_video(request: FullVideoGenerationRequest):
    """Render every scene from scratch and combine it.

    Prefer /combine when scene previews already exist so GPU work is not repeated.
    """
    if settings.is_production and not settings.enable_sync_render_endpoints:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        ensure_minimum_free_disk()
        provider = get_video_provider(
            request.provider or settings.video_provider,
            model=request.model,
        )
        width, height = source_render_dimensions(request.aspect_ratio)

        generated_paths: list[Path] = []
        scene_urls: list[str] = []
        render_details: list[str] = []
        total_render_seconds = 0.0
        total_wall_seconds = 0.0
        gpu: str | None = None

        for index, scene in enumerate(request.scenes):
            result = provider.generate(
                prompt=scene.prompt,
                width=width,
                height=height,
                duration_seconds=request.duration_seconds,
                seed=request.seed + index,
                decoder=request.decoder,
                enhance_prompt=request.enhance_prompt,
            )
            clip_path = Path(result.path)
            generated_paths.append(clip_path)
            scene_urls.append(media_url(clip_path.name))
            render_details.append(result.render_details)
            total_render_seconds += result.render_seconds
            total_wall_seconds += float(result.wall_seconds or result.render_seconds)
            gpu = result.gpu or gpu

        combined_path = GENERATED_DIR / f"final-{uuid.uuid4().hex}.mp4"
        combine_videos(generated_paths, combined_path)

        delivery_path = apply_delivery_quality(
            combined_path,
            aspect_ratio=request.aspect_ratio,
            quality=request.quality,
            prefix="final",
        )
        media_info = _media_info(delivery_path)
        filename = delivery_path.name
        output_duration = request.duration_seconds * len(request.scenes)
        estimated_cost, estimated_cost_per_minute, cost_note = estimate_gpu_cost(
            render_seconds=total_wall_seconds,
            gpu=gpu,
            output_duration_seconds=output_duration,
        )

        record_generation_metric(
            {
                "type": "full-video",
                "provider": provider.name,
                "model": request.model,
                "gpu": gpu,
                "aspect_ratio": request.aspect_ratio,
                "scene_count": len(request.scenes),
                "duration_seconds_per_scene": request.duration_seconds,
                "render_seconds": round(total_render_seconds, 3),
                "wall_seconds": round(total_wall_seconds, 3),
                "quality": request.quality,
                "decoder": request.decoder,
                "has_audio": media_info.has_audio,
                "audio_codec": media_info.audio_codec,
                "estimated_cost_usd": estimated_cost,
                "estimated_cost_per_output_minute_usd": estimated_cost_per_minute,
                "filename": filename,
            }
        )

        return FullVideoGenerationResponse(
            final_video_url=media_url(filename),
            final_download_url=download_url(filename),
            final_filename=filename,
            scene_video_urls=scene_urls,
            render_details=render_details,
            total_render_seconds=round(total_render_seconds, 2),
            total_wall_seconds=round(total_wall_seconds, 2),
            provider=provider.name,
            model=request.model,
            quality=request.quality,
            quality_note=quality_note(request.quality, request.aspect_ratio),
            gpu=gpu,
            media_info=media_info,
            estimated_cost_usd=estimated_cost,
            estimated_cost_per_output_minute_usd=estimated_cost_per_minute,
            cost_note=cost_note,
        )
    except Exception as exc:
        LOGGER.exception("Full video generation failed")
        detail = str(exc) if settings.debug and not settings.is_production else "Full video generation failed."
        raise HTTPException(status_code=500, detail=detail) from exc


@router.get("/metrics/summary", response_model=MetricsSummaryResponse)
async def metrics_summary():
    if settings.is_production and not settings.enable_metrics_endpoint:
        raise HTTPException(status_code=404, detail="Not found.")
    return MetricsSummaryResponse.model_validate(summarize_generation_metrics())


@router.get("/download/{filename}")
async def download_generated_video(filename: str):
    try:
        path = resolve_generated_video(filename)
        return FileResponse(
            path,
            media_type="video/mp4",
            filename=path.name,
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
