import traceback
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.generation import (
    CombineScenesRequest,
    CombineScenesResponse,
    FullVideoGenerationRequest,
    FullVideoGenerationResponse,
    GenerationCapabilitiesResponse,
    ScenePlanRequest,
    ScenePlanResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from app.services.metrics_service import record_generation_metric
from app.services.scene_planner import create_scene_plan
from app.services.video_combiner import combine_videos, upscale_to_1080p
from inference.providers.router import get_video_provider


router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[5]
GENERATED_DIR = (PROJECT_ROOT / "storage" / "generated").resolve()
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def get_render_dimensions(aspect_ratio: str) -> tuple[int, int]:
    """Fast LTX development/source dimensions, all divisible by 64."""
    if aspect_ratio == "16:9":
        return 1024, 576
    if aspect_ratio == "9:16":
        return 576, 1024
    return 512, 512


def quality_note(quality: str, aspect_ratio: str) -> str:
    if quality != "1080p":
        return "Development/source render profile; no delivery upscale applied."

    if aspect_ratio == "9:16":
        delivery = "1080x1920"
    elif aspect_ratio == "1:1":
        delivery = "1080x1080"
    else:
        delivery = "1920x1080"

    return (
        f"{delivery} delivery file. The current MVP renders LTX at its "
        "development source profile and performs an FFmpeg delivery upscale; "
        "this is not a claim of native 1080p generation."
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


@router.get(
    "/capabilities",
    response_model=GenerationCapabilitiesResponse,
)
async def generation_capabilities():
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
                "description": "Fast development render.",
            },
            {
                "id": "1080p",
                "label": "1080p delivery",
                "description": "FFmpeg delivery upscale for the MVP.",
            },
        ],
        aspect_ratios=["16:9", "9:16", "1:1"],
        max_scene_duration_seconds=5.0,
    )


@router.post("/plan", response_model=ScenePlanResponse)
async def plan_generation(request: ScenePlanRequest):
    try:
        scenes = create_scene_plan(
            prompt=request.prompt,
            scene_count=request.scene_count,
            aspect_ratio=request.aspect_ratio,
        )
        return ScenePlanResponse(
            original_prompt=request.prompt,
            aspect_ratio=request.aspect_ratio,
            scenes=scenes,
        )
    except Exception as exc:
        print("\nSCENE PLANNING ERROR\n--------------------")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/video", response_model=VideoGenerationResponse)
async def generate_video(request: VideoGenerationRequest):
    try:
        provider = get_video_provider(
            request.provider or settings.video_provider,
            model=request.model,
        )
        width, height = get_render_dimensions(request.aspect_ratio)

        result = provider.generate(
            prompt=request.prompt,
            width=width,
            height=height,
            duration_seconds=request.duration_seconds,
            seed=request.seed,
            decoder=request.decoder,
            enhance_prompt=False,
        )

        source_path = Path(result.path)
        delivery_path = apply_delivery_quality(
            source_path,
            aspect_ratio=request.aspect_ratio,
            quality=request.quality,
            prefix="scene",
        )
        filename = delivery_path.name

        record_generation_metric(
            {
                "type": "scene",
                "provider": result.provider,
                "model": request.model,
                "aspect_ratio": request.aspect_ratio,
                "source_width": width,
                "source_height": height,
                "duration_seconds": request.duration_seconds,
                "render_seconds": round(result.render_seconds, 3),
                "quality": request.quality,
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
            provider=result.provider,
            model=request.model,
            quality=request.quality,
            quality_note=quality_note(request.quality, request.aspect_ratio),
        )
    except Exception as exc:
        print("\nVIDEO GENERATION ERROR\n----------------------")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/combine", response_model=CombineScenesResponse)
async def combine_existing_scenes(request: CombineScenesRequest):
    try:
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
        filename = delivery_path.name

        return CombineScenesResponse(
            final_video_url=media_url(filename),
            final_download_url=download_url(filename),
            final_filename=filename,
            scene_count=len(video_paths),
            quality=request.quality,
            quality_note=quality_note(request.quality, request.aspect_ratio),
        )
    except Exception as exc:
        print("\nVIDEO COMBINE ERROR\n-------------------")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/full-video", response_model=FullVideoGenerationResponse)
async def generate_full_video(request: FullVideoGenerationRequest):
    """Render every scene from scratch and combine it.

    Prefer /combine when scene previews already exist so GPU work is not repeated.
    """
    try:
        provider = get_video_provider(
            request.provider or settings.video_provider,
            model=request.model,
        )
        width, height = get_render_dimensions(request.aspect_ratio)

        generated_paths: list[Path] = []
        scene_urls: list[str] = []
        render_details: list[str] = []
        total_render_seconds = 0.0

        for index, scene in enumerate(request.scenes):
            result = provider.generate(
                prompt=scene.prompt,
                width=width,
                height=height,
                duration_seconds=request.duration_seconds,
                seed=request.seed + index,
                decoder=request.decoder,
                enhance_prompt=False,
            )
            clip_path = Path(result.path)
            generated_paths.append(clip_path)
            scene_urls.append(media_url(clip_path.name))
            render_details.append(result.render_details)
            total_render_seconds += result.render_seconds

        combined_path = GENERATED_DIR / f"final-{uuid.uuid4().hex}.mp4"
        combine_videos(generated_paths, combined_path)

        delivery_path = apply_delivery_quality(
            combined_path,
            aspect_ratio=request.aspect_ratio,
            quality=request.quality,
            prefix="final",
        )
        filename = delivery_path.name

        record_generation_metric(
            {
                "type": "full-video",
                "provider": provider.name,
                "model": request.model,
                "aspect_ratio": request.aspect_ratio,
                "scene_count": len(request.scenes),
                "duration_seconds_per_scene": request.duration_seconds,
                "render_seconds": round(total_render_seconds, 3),
                "quality": request.quality,
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
            provider=provider.name,
            model=request.model,
            quality=request.quality,
            quality_note=quality_note(request.quality, request.aspect_ratio),
        )
    except Exception as exc:
        print("\nFULL VIDEO GENERATION ERROR\n---------------------------")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
