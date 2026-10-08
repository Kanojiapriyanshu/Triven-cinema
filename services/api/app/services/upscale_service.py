from pathlib import Path
from typing import Callable

from app.schemas.generation import MediaInfo
from app.schemas.upscale import UpscaleRequest, UpscaleResponse
from app.services.delivery_service import prepare_delivery, quality_note
from app.services.media_probe import probe_media
from app.services.metrics_service import estimate_gpu_cost, record_generation_metric
from app.services.storage_service import ensure_minimum_free_disk, resolve_generated_asset
from app.services.video_profiles import source_render_dimensions, validate_scene_duration
from inference.providers.router import get_video_provider

ProgressCallback = Callable[[str, int, str], None]


def aspect_ratio_of(width: int | None, height: int | None) -> str:
    if not width or not height:
        return "16:9"
    ratio = width / height
    if ratio >= 1.2:
        return "16:9"
    if ratio <= 0.83:
        return "9:16"
    return "1:1"


def inspect_draft(filename: str) -> tuple[Path, dict, float]:
    """Resolve the Draft and return (path, probe info, duration). Raises ValueError for unusable inputs."""
    try:
        source = resolve_generated_asset(filename, extensions={".mp4"})
    except (ValueError, FileNotFoundError) as exc:
        raise ValueError(f"The video to upscale is no longer available: {exc}") from exc
    info = probe_media(source)
    duration = float(info.get("duration_seconds") or 0.0)
    if duration <= 0:
        raise ValueError("The video to upscale has no readable duration.")
    validate_scene_duration(quality="1080p", duration_seconds=duration)
    return source, info, duration


def run_upscale(
    request: UpscaleRequest,
    *,
    workspace_id: str,
    progress: ProgressCallback | None = None,
) -> UpscaleResponse:
    ensure_minimum_free_disk()
    source, info, duration = inspect_draft(request.source_filename)
    aspect = aspect_ratio_of(info.get("width"), info.get("height"))
    width, height = source_render_dimensions(aspect, request.quality)
    if (info.get("width") or 0) >= width:
        raise ValueError("This video is already Full HD or larger, so there is nothing to upscale.")

    provider = get_video_provider("modal")
    if not provider.supports_upscale:
        raise ValueError("The active video provider cannot upscale a Draft.")

    if progress:
        progress("rendering", 15, "Sharpening your approved Draft at Full HD (same video, same voice)...")
    result = provider.upscale(
        video_path=str(source),
        width=width,
        height=height,
        duration_seconds=duration,
        seed=request.seed,
    )

    if progress:
        progress("delivery", 88, "Creating the Full HD delivery file...")
    raw = Path(result.path)
    delivery = prepare_delivery(raw, aspect_ratio=aspect, quality=request.quality, audio_mode="native", prefix="upscale")
    if delivery != raw:
        raw.unlink(missing_ok=True)
    media = MediaInfo.model_validate(probe_media(delivery))

    wall = float(result.wall_seconds or result.render_seconds)
    cost, per_minute, cost_note = estimate_gpu_cost(render_seconds=wall, gpu=result.gpu, output_duration_seconds=duration)
    record_generation_metric(
        {
            "type": "upscale",
            "provider": provider.name,
            "gpu": result.gpu,
            "aspect_ratio": aspect,
            "duration_seconds": duration,
            "render_seconds": round(float(result.render_seconds), 3),
            "wall_seconds": round(wall, 3),
            "quality": request.quality,
            "has_audio": media.has_audio,
            "estimated_cost_usd": cost,
            "estimated_cost_per_output_minute_usd": per_minute,
            "filename": delivery.name,
        }
    )

    return UpscaleResponse(
        final_video_url=f"/media/generated/{delivery.name}",
        final_download_url=f"/api/v1/generations/download/{delivery.name}",
        final_filename=delivery.name,
        source_filename=request.source_filename,
        quality=request.quality,
        aspect_ratio=aspect,
        quality_note=quality_note(request.quality, aspect)
        + " Created by refining your approved Draft, so the picture, motion, voice and timing are the same.",
        has_audio=media.has_audio,
        width=media.width,
        height=media.height,
        duration_seconds=media.duration_seconds,
        provider=result.provider,
        gpu=result.gpu,
        total_render_seconds=round(float(result.render_seconds), 2),
        estimated_cost_usd=cost,
        cost_note=cost_note,
    )
