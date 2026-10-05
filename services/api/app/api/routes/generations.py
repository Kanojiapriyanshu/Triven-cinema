import logging
import uuid
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, Response
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
from app.services.billing_service import (
    InsufficientCreditsError,
    consume_credits,
    refund_credits,
)
from app.services.continuity_service import compose_continuity_prompt, safe_continuity_id
from app.services.delivery_service import prepare_delivery, quality_note
from app.services.identity_service import ensure_workspace, workspace_id_from_request
from app.services.job_service import (
    JobQueueFullError,
    get_job,
    submit_job,
    update_job,
    workspace_owns_generated_file,
)
from app.services.long_render_service import render_long_clip
from app.services.media_probe import probe_media
from app.services.metrics_service import (
    estimate_gpu_cost,
    record_generation_metric,
    summarize_generation_metrics,
)
from app.services.prompt_quality import evaluate_plan_prompt_coverage
from app.services.scene_planner import create_scene_plan
from app.services.storage_service import ensure_minimum_free_disk, resolve_generated_asset
from app.services.video_combiner import combine_videos, extract_last_frame
from app.services.video_profiles import (
    duration_profile,
    source_render_dimensions,
    validate_scene_duration,
)
from inference.providers.router import get_video_provider


router = APIRouter()
LOGGER = logging.getLogger("triven.generations")

PROJECT_ROOT = Path(__file__).resolve().parents[5]
GENERATED_DIR = (PROJECT_ROOT / "storage" / "generated").resolve()
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

ProgressCallback = Callable[[str, int, str], None]


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


def _media_info(path: Path) -> MediaInfo:
    return MediaInfo.model_validate(probe_media(path))


def _audio_prompt(prompt: str, audio_direction: str | None) -> str:
    direction = (audio_direction or "").strip()
    if not direction:
        return prompt
    return (
        f"{prompt}\n\n[AUDIO DIRECTION] Generate synchronized audio that follows the visible action. "
        f"{direction} Do not invent spoken dialogue unless it is explicitly requested."
    )


def _generate_video_impl(
    request: VideoGenerationRequest,
    progress: ProgressCallback | None = None,
) -> VideoGenerationResponse:
    validate_scene_duration(
        quality=request.quality,
        duration_seconds=request.duration_seconds,
    )
    if progress:
        progress("initializing", 8, "Checking storage, continuity state and render provider...")

    ensure_minimum_free_disk()
    provider_key = request.provider or settings.video_provider
    provider = get_video_provider(provider_key, model=request.model)
    width, height = source_render_dimensions(request.aspect_ratio)

    prompt_to_render = request.prompt
    provider_enhance_prompt = request.enhance_prompt
    if request.enhance_prompt and provider_key == "modal":
        enhanced = create_scene_plan(
            prompt=request.prompt,
            scene_count=1,
            aspect_ratio=request.aspect_ratio,
            force_ai=True,
        )
        prompt_to_render = enhanced.scenes[0].prompt
        provider_enhance_prompt = False

    if request.continuity_mode != "off":
        prompt_to_render = compose_continuity_prompt(
            scene_prompt=prompt_to_render,
            character_bible=request.character_bible,
            style_bible=request.style_bible,
            scene_index=request.scene_index,
            scene_count=request.scene_count,
        )
    prompt_to_render = _audio_prompt(prompt_to_render, request.audio_direction)

    reference_path: Path | None = None
    if request.continuity_mode == "strict" and request.reference_frame_filename:
        if provider_key != "modal":
            raise ValueError("Strict first-frame continuity currently requires the Modal LTX-2.5 provider.")
        reference_path = resolve_generated_asset(
            request.reference_frame_filename,
            extensions={".png", ".jpg", ".jpeg", ".webp"},
        )

    if progress:
        progress(
            "rendering",
            20,
            "Rendering with LTX-2.5" + (" using the previous scene frame..." if reference_path else "..."),
        )

    def chunk_progress(part: int, count: int, message: str) -> None:
        if progress:
            progress(
                "rendering",
                min(78, 20 + int(((part + 1) / max(1, count)) * 58)),
                message,
            )

    result = render_long_clip(
        provider=provider,
        prompt=prompt_to_render,
        width=width,
        height=height,
        duration_seconds=request.duration_seconds,
        seed=request.seed,
        decoder=request.decoder,
        enhance_prompt=provider_enhance_prompt,
        reference_image_path=str(reference_path) if reference_path else None,
        reference_strength=request.continuity_strength,
        progress=chunk_progress,
    )

    source_path = Path(result.path)
    continuity_frame_path: Path | None = None
    if request.continuity_mode != "off":
        continuity_tag = safe_continuity_id(request.continuity_id or uuid.uuid4().hex[:12])
        continuity_frame_path = GENERATED_DIR / (
            f"continuity-{continuity_tag}-scene-{(request.scene_index or 0) + 1}-{uuid.uuid4().hex[:8]}.png"
        )
        extract_last_frame(source_path, continuity_frame_path)

    if progress:
        progress("delivery", 82, f"Preparing {request.quality} delivery and {request.audio_mode} audio...")

    delivery_path = prepare_delivery(
        source_path,
        aspect_ratio=request.aspect_ratio,
        quality=request.quality,
        audio_mode=request.audio_mode,
        prefix="scene",
    )

    if progress:
        progress("probing", 92, "Validating dimensions, audio and continuity frame...")

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
            "chunk_count": result.chunk_count,
            "render_seconds": round(result.render_seconds, 3),
            "wall_seconds": round(wall_seconds, 3),
            "quality": request.quality,
            "audio_mode": request.audio_mode,
            "decoder": request.decoder,
            "seed": request.seed,
            "has_audio": media_info.has_audio,
            "audio_codec": media_info.audio_codec,
            "continuity_mode": request.continuity_mode,
            "continuity_id": request.continuity_id,
            "continuity_applied": result.reference_conditioned,
            "reference_frame_filename": request.reference_frame_filename,
            "continuity_frame_filename": continuity_frame_path.name if continuity_frame_path else None,
            "estimated_cost_usd": estimated_cost,
            "estimated_cost_per_output_minute_usd": estimated_cost_per_minute,
            "filename": filename,
        }
    )

    # Delivery masters replace their source clip for the public response. Keep
    # only the continuity PNG when needed, reducing VPS disk pressure.
    if delivery_path != source_path:
        source_path.unlink(missing_ok=True)

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
        audio_mode=request.audio_mode,
        chunk_count=result.chunk_count,
        gpu=result.gpu,
        media_info=media_info,
        estimated_cost_usd=estimated_cost,
        estimated_cost_per_output_minute_usd=estimated_cost_per_minute,
        cost_note=cost_note,
        continuity_mode=request.continuity_mode,
        continuity_applied=result.reference_conditioned,
        reference_frame_filename=request.reference_frame_filename,
        continuity_frame_url=media_url(continuity_frame_path.name) if continuity_frame_path else None,
        continuity_frame_filename=continuity_frame_path.name if continuity_frame_path else None,
    )


@router.get("/capabilities", response_model=GenerationCapabilitiesResponse)
async def generation_capabilities():
    cost_tracking_configured = any(
        rate > 0
        for rate in (
            settings.modal_gpu_hourly_usd_b200,
            settings.modal_gpu_hourly_usd_h200,
            settings.modal_gpu_hourly_usd_h100,
        )
    )
    durations = duration_profile()
    return GenerationCapabilitiesResponse(
        providers=[
            {"id": "huggingface", "label": "ZeroGPU (development)", "available": True, "paid": False},
            {"id": "modal", "label": "Modal self-hosted LTX-2.5", "available": True, "paid": True},
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
                "description": "Validated LTX source render for iteration; up to 10 seconds per scene by default.",
            },
            {
                "id": "1080p",
                "label": "1080p master",
                "description": "Up to 30 seconds per scene using LTX-2.5 native temporal windowing with overlap/blending and one final delivery transcode.",
            },
            {
                "id": "4k",
                "label": "4K delivery master",
                "description": "Up to 15 seconds per scene. Final 4K delivery master from the validated LTX source pipeline; not a native-4K source claim.",
            },
        ],
        aspect_ratios=["16:9", "9:16", "1:1"],
        decoders=["conv", "diffusion"],
        continuity_modes=["off", "balanced", "strict"],
        audio_modes=["native", "mastered", "mute"],
        image_conditioning=True,
        max_scene_duration_seconds=max(durations.values()),
        max_scene_duration_seconds_by_quality=durations,
        native_chunk_seconds=settings.ltx_native_chunk_seconds,
        max_factory_duration_seconds=settings.max_factory_duration_seconds,
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
            continuity_id=f"story-{uuid.uuid4().hex[:16]}",
            character_bible=plan.character_bible,
            style_bible=plan.style_bible,
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
def create_video_job(
    payload: VideoGenerationRequest,
    request: Request,
    response: Response,
):
    workspace_id = ensure_workspace(request, response)
    charge_seconds = max(1, int(round(payload.duration_seconds)))
    charge_reference = f"scene:{uuid.uuid4().hex}"
    try:
        consume_credits(workspace_id, charge_seconds, charge_reference)
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    job_payload = payload.model_dump()
    job_payload["workspace_id"] = workspace_id

    def runner(job_id: str) -> dict:
        def progress(stage: str, percent: int, message: str) -> None:
            update_job(job_id, status="running", stage=stage, progress=percent, message=message)

        try:
            result = _generate_video_impl(payload, progress=progress)
            return result.model_dump()
        except Exception:
            refund_credits(workspace_id, charge_seconds, charge_reference)
            raise

    try:
        job_id = submit_job("video", job_payload, runner)
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


@router.get("/jobs/{job_id}", response_model=GenerationJobResponse)
async def generation_job_status(
    job_id: str,
    request: Request,
    response: Response,
):
    workspace_id = ensure_workspace(request, response)
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found.")

    # Paid/background jobs are scoped to the signed browser workspace. Returning
    # 404 for another workspace avoids leaking render prompts, progress or outputs.
    owner = str((job.get("payload") or {}).get("workspace_id") or "")
    if owner and owner != workspace_id:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    if settings.is_production and not owner:
        raise HTTPException(status_code=404, detail="Generation job not found.")

    return GenerationJobResponse.model_validate(job)


@router.post("/combine", response_model=CombineScenesResponse)
def combine_existing_scenes(request: CombineScenesRequest):
    if settings.is_production and not settings.enable_sync_render_endpoints:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        ensure_minimum_free_disk()
        video_paths = [resolve_generated_video(url) for url in request.scene_video_urls]
        combined_path = GENERATED_DIR / f"final-source-{uuid.uuid4().hex}.mp4"
        combine_videos(video_paths, combined_path)
        delivery_path = prepare_delivery(
            combined_path,
            aspect_ratio=request.aspect_ratio,
            quality=request.quality,
            audio_mode=request.audio_mode,
            prefix="final",
        )
        media_info = _media_info(delivery_path)
        filename = delivery_path.name
        if delivery_path != combined_path:
            combined_path.unlink(missing_ok=True)

        record_generation_metric(
            {
                "type": "combine",
                "scene_count": len(video_paths),
                "aspect_ratio": request.aspect_ratio,
                "quality": request.quality,
                "audio_mode": request.audio_mode,
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
            audio_mode=request.audio_mode,
            media_info=media_info,
        )
    except Exception as exc:
        LOGGER.exception("Video combine failed")
        detail = str(exc) if settings.debug and not settings.is_production else "Video combine failed."
        raise HTTPException(status_code=500, detail=detail) from exc


@router.post("/full-video", response_model=FullVideoGenerationResponse)
def generate_full_video(request: FullVideoGenerationRequest):
    """Development compatibility route. Production uses async scene/factory jobs."""
    if settings.is_production and not settings.enable_sync_render_endpoints:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        validate_scene_duration(quality=request.quality, duration_seconds=request.duration_seconds)
        ensure_minimum_free_disk()
        provider = get_video_provider(request.provider or settings.video_provider, model=request.model)
        width, height = source_render_dimensions(request.aspect_ratio)

        generated_paths: list[Path] = []
        scene_urls: list[str] = []
        render_details: list[str] = []
        total_render_seconds = 0.0
        total_wall_seconds = 0.0
        gpu: str | None = None
        previous_frame: Path | None = None
        continuity_frames: list[Path] = []

        try:
            for index, scene in enumerate(request.scenes):
                locked_prompt = (
                    compose_continuity_prompt(
                        scene_prompt=scene.prompt,
                        character_bible=request.character_bible,
                        style_bible=request.style_bible,
                        scene_index=index,
                        scene_count=len(request.scenes),
                    )
                    if request.continuity_mode != "off"
                    else scene.prompt
                )
                locked_prompt = _audio_prompt(locked_prompt, request.audio_direction)
                result = render_long_clip(
                    provider=provider,
                    prompt=locked_prompt,
                    width=width,
                    height=height,
                    duration_seconds=request.duration_seconds,
                    seed=request.seed,
                    decoder=request.decoder,
                    enhance_prompt=request.enhance_prompt and index == 0,
                    reference_image_path=(
                        str(previous_frame)
                        if request.continuity_mode == "strict" and previous_frame
                        else None
                    ),
                    reference_strength=request.continuity_strength,
                )
                clip_path = Path(result.path)
                generated_paths.append(clip_path)
                scene_urls.append(media_url(clip_path.name))
                render_details.append(result.render_details)
                total_render_seconds += result.render_seconds
                total_wall_seconds += float(result.wall_seconds or result.render_seconds)
                gpu = result.gpu or gpu
                if request.continuity_mode != "off" and index < len(request.scenes) - 1:
                    previous_frame = GENERATED_DIR / f".continuity-full-{uuid.uuid4().hex}.png"
                    extract_last_frame(clip_path, previous_frame)
                    continuity_frames.append(previous_frame)

            combined_path = GENERATED_DIR / f"final-source-{uuid.uuid4().hex}.mp4"
            combine_videos(generated_paths, combined_path)
            delivery_path = prepare_delivery(
                combined_path,
                aspect_ratio=request.aspect_ratio,
                quality=request.quality,
                audio_mode=request.audio_mode,
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
            if delivery_path != combined_path:
                combined_path.unlink(missing_ok=True)

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
                    "audio_mode": request.audio_mode,
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
                audio_mode=request.audio_mode,
                gpu=gpu,
                media_info=media_info,
                estimated_cost_usd=estimated_cost,
                estimated_cost_per_output_minute_usd=estimated_cost_per_minute,
                cost_note=cost_note,
            )
        finally:
            for frame in continuity_frames:
                frame.unlink(missing_ok=True)
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
async def download_generated_video(filename: str, request: Request):
    try:
        path = resolve_generated_video(filename)
        if settings.is_production:
            workspace_id = workspace_id_from_request(request)
            if not workspace_id or not workspace_owns_generated_file(workspace_id, path.name):
                raise FileNotFoundError("Generated video not found.")
        return FileResponse(path, media_type="video/mp4", filename=path.name)
    except Exception as exc:
        detail = str(exc) if settings.debug and not settings.is_production else "Generated video not found."
        raise HTTPException(status_code=404, detail=detail) from exc
