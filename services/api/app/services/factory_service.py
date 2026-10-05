import math
import uuid
from pathlib import Path
from typing import Callable

from app.core.config import settings
from app.schemas.factory import FactoryGenerationRequest, FactoryGenerationResponse
from app.schemas.generation import MediaInfo
from app.services.continuity_service import compose_continuity_prompt
from app.services.delivery_service import prepare_delivery, quality_note
from app.services.long_render_service import render_long_clip
from app.services.media_probe import probe_media
from app.services.metrics_service import estimate_gpu_cost, record_generation_metric
from app.services.scene_planner import create_scene_plan
from app.services.storage_service import ensure_minimum_free_disk
from app.services.video_combiner import combine_videos, extract_last_frame
from app.services.video_profiles import source_render_dimensions, validate_scene_duration
from app.services.youtube_service import upload_video
from inference.providers.router import get_video_provider


PROJECT_ROOT = Path(__file__).resolve().parents[4]
GENERATED_DIR = (PROJECT_ROOT / "storage" / "generated").resolve()
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
ProgressCallback = Callable[[str, int, str], None]


def _audio_prompt(prompt: str, audio_direction: str | None) -> str:
    direction = (audio_direction or "").strip()
    if not direction:
        return prompt
    return (
        f"{prompt}\n\n[AUDIO DIRECTION] Generate synchronized audio that follows the image and action. "
        f"{direction} Do not add spoken dialogue unless explicitly requested."
    )


def _media_info(path: Path) -> MediaInfo:
    return MediaInfo.model_validate(probe_media(path))


def _safe_title(prompt: str) -> str:
    compact = " ".join(prompt.split())
    return (compact[:96].rstrip(" .,:;-") or "Triven Cinema")[:100]


def run_factory_generation(
    request: FactoryGenerationRequest,
    *,
    workspace_id: str,
    progress: ProgressCallback | None = None,
) -> FactoryGenerationResponse:
    """Run the prompt-to-publish AI video factory as one bounded background job."""
    ensure_minimum_free_disk()
    if request.target_duration_seconds > settings.max_factory_duration_seconds:
        raise ValueError(
            f"Factory jobs are limited to {settings.max_factory_duration_seconds}s on this deployment."
        )
    validate_scene_duration(
        quality=request.quality,
        duration_seconds=request.scene_duration_seconds,
    )
    if request.provider != "modal" and request.scene_duration_seconds > settings.ltx_native_chunk_seconds:
        raise ValueError("Long factory scenes currently require the Modal LTX provider.")

    scene_count = max(1, math.ceil(request.target_duration_seconds / request.scene_duration_seconds))
    if scene_count > 20:
        raise ValueError(
            "This factory job would require more than 20 story scenes. Increase scene duration or reduce total duration."
        )

    if progress:
        progress("planning", 8, f"Planning {scene_count} continuity-locked scenes...")
    plan = create_scene_plan(
        prompt=request.prompt,
        scene_count=scene_count,
        aspect_ratio=request.aspect_ratio,
        force_ai=request.enhance_prompt,
        target_scene_duration_seconds=request.scene_duration_seconds,
    )

    provider = get_video_provider(request.provider, model=request.model)
    width, height = source_render_dimensions(request.aspect_ratio)
    continuity_id = f"factory-{uuid.uuid4().hex[:16]}"
    source_paths: list[Path] = []
    render_details: list[str] = []
    total_render = 0.0
    total_wall = 0.0
    total_chunks = 0
    gpu: str | None = None
    previous_frame: Path | None = None
    continuity_frames: list[Path] = []
    remaining = float(request.target_duration_seconds)

    try:
        for index, scene in enumerate(plan.scenes):
            duration = min(float(request.scene_duration_seconds), remaining)
            remaining = max(0.0, remaining - duration)
            if duration < 1.0:
                break

            locked_prompt = scene.prompt
            if request.continuity_mode != "off":
                locked_prompt = compose_continuity_prompt(
                    scene_prompt=locked_prompt,
                    character_bible=plan.character_bible,
                    style_bible=plan.style_bible,
                    scene_index=index,
                    scene_count=scene_count,
                )
            locked_prompt = _audio_prompt(locked_prompt, request.audio_direction)

            base_progress = 12 + int((index / max(1, scene_count)) * 66)

            def chunk_progress(part: int, count: int, message: str) -> None:
                if not progress:
                    return
                within_scene = int(((part + 1) / max(1, count)) * max(1, 66 // max(1, scene_count)))
                progress(
                    "rendering",
                    min(78, base_progress + within_scene),
                    f"Scene {index + 1}/{scene_count} · {message}",
                )

            result = render_long_clip(
                provider=provider,
                prompt=locked_prompt,
                width=width,
                height=height,
                duration_seconds=duration,
                seed=request.seed,
                decoder=request.decoder,
                enhance_prompt=False,
                reference_image_path=(
                    str(previous_frame)
                    if request.continuity_mode == "strict" and previous_frame is not None
                    else None
                ),
                reference_strength=request.continuity_strength,
                progress=chunk_progress,
            )
            path = Path(result.path)
            source_paths.append(path)
            render_details.append(result.render_details)
            total_render += float(result.render_seconds)
            total_wall += float(result.wall_seconds or result.render_seconds)
            total_chunks += int(result.chunk_count or 1)
            gpu = result.gpu or gpu

            if request.continuity_mode != "off" and index < scene_count - 1:
                frame = GENERATED_DIR / f".factory-continuity-{uuid.uuid4().hex}.png"
                extract_last_frame(path, frame)
                continuity_frames.append(frame)
                previous_frame = frame

        if not source_paths:
            raise RuntimeError("Factory produced no scene clips.")

        if progress:
            progress("composing", 80, "Composing generated scenes and synchronized audio...")
        composed = GENERATED_DIR / f"factory-source-{uuid.uuid4().hex}.mp4"
        combine_videos(source_paths, composed)

        if progress:
            progress("delivery", 88, f"Creating {request.quality} delivery master...")
        delivery = prepare_delivery(
            composed,
            aspect_ratio=request.aspect_ratio,
            quality=request.quality,
            audio_mode=request.audio_mode,
            prefix="factory",
        )
        info = _media_info(delivery)

        estimated_cost, cost_per_minute, cost_note = estimate_gpu_cost(
            render_seconds=total_wall,
            gpu=gpu,
            output_duration_seconds=request.target_duration_seconds,
        )

        youtube_video_id: str | None = None
        youtube_url: str | None = None
        youtube_privacy: str | None = None
        if request.publish_to_youtube:
            if progress:
                progress("publishing", 95, "Uploading the finished master to the connected YouTube channel...")
            published = upload_video(
                workspace_id,
                filename=delivery.name,
                title=(request.youtube_title or _safe_title(request.prompt)),
                description=request.youtube_description,
                privacy=request.youtube_privacy,
                tags=request.youtube_tags,
                category_id=request.youtube_category_id,
                publish_at=request.youtube_publish_at,
            )
            youtube_video_id = published["video_id"]
            youtube_url = published["youtube_url"]
            youtube_privacy = published["privacy"]

        filename = delivery.name
        record_generation_metric(
            {
                "type": "factory",
                "provider": provider.name,
                "model": request.model,
                "gpu": gpu,
                "aspect_ratio": request.aspect_ratio,
                "scene_count": len(source_paths),
                "chunk_count": total_chunks,
                "target_duration_seconds": request.target_duration_seconds,
                "scene_duration_seconds": request.scene_duration_seconds,
                "render_seconds": round(total_render, 3),
                "wall_seconds": round(total_wall, 3),
                "quality": request.quality,
                "audio_mode": request.audio_mode,
                "has_audio": info.has_audio,
                "estimated_cost_usd": estimated_cost,
                "estimated_cost_per_output_minute_usd": cost_per_minute,
                "youtube_published": bool(youtube_url),
                "filename": filename,
            }
        )

        return FactoryGenerationResponse(
            final_video_url=f"/media/generated/{filename}",
            final_download_url=f"/api/v1/generations/download/{filename}",
            final_filename=filename,
            target_duration_seconds=request.target_duration_seconds,
            actual_duration_seconds=info.duration_seconds,
            scene_count=len(source_paths),
            scene_duration_seconds=request.scene_duration_seconds,
            aspect_ratio=request.aspect_ratio,
            quality=request.quality,
            quality_note=quality_note(request.quality, request.aspect_ratio),
            audio_mode=request.audio_mode,
            has_audio=info.has_audio,
            width=info.width,
            height=info.height,
            provider=provider.name,
            model=request.model,
            gpu=gpu,
            total_render_seconds=round(total_render, 2),
            total_wall_seconds=round(total_wall, 2),
            chunk_count=total_chunks,
            estimated_cost_usd=estimated_cost,
            estimated_cost_per_output_minute_usd=cost_per_minute,
            cost_note=cost_note,
            planner_source=plan.source,
            planner_note=plan.note,
            continuity_id=continuity_id,
            youtube_video_id=youtube_video_id,
            youtube_url=youtube_url,
            youtube_privacy=youtube_privacy,
        )
    finally:
        for frame in continuity_frames:
            frame.unlink(missing_ok=True)
