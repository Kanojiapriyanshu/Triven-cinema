import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.generation import (
    FullVideoGenerationRequest,
    FullVideoGenerationResponse,
    ScenePlanRequest,
    ScenePlanResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from app.services.scene_planner import create_scene_plan
from app.services.video_combiner import combine_videos
from inference.providers.router import get_video_provider


router = APIRouter()


def get_render_dimensions(
    aspect_ratio: str,
) -> tuple[int, int]:
    """
    Development render sizes for LTX-2.5.

    LTX requires dimensions that are large enough
    and divisible by 64.
    """

    if aspect_ratio == "16:9":
        return 1024, 576

    if aspect_ratio == "9:16":
        return 576, 1024

    return 512, 512


@router.post(
    "/plan",
    response_model=ScenePlanResponse,
)
async def plan_generation(
    request: ScenePlanRequest,
):
    """
    Convert the user's main prompt into a structured
    storyboard using the scene planner.
    """

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
        print()
        print("SCENE PLANNING ERROR")
        print("--------------------")
        traceback.print_exc()
        print()

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post(
    "/video",
    response_model=VideoGenerationResponse,
)
async def generate_video(
    request: VideoGenerationRequest,
):
    """
    Generate one LTX video clip from one scene prompt.
    """

    try:
        provider = get_video_provider(
            "huggingface"
        )

        width, height = get_render_dimensions(
            request.aspect_ratio
        )

        print()
        print("TRIVEN CINEMA - VIDEO GENERATION")
        print("--------------------------------")
        print(
            f"Aspect ratio: "
            f"{request.aspect_ratio}"
        )
        print(
            f"Resolution: "
            f"{width}x{height}"
        )
        print(
            f"Duration: "
            f"{request.duration_seconds}s"
        )
        print(
            f"Decoder: "
            f"{request.decoder}"
        )
        print()

        result = provider.generate(
            prompt=request.prompt,
            width=width,
            height=height,
            duration_seconds=(
                request.duration_seconds
            ),
            seed=request.seed,
            decoder=request.decoder,
            enhance_prompt=False,
        )

        return VideoGenerationResponse(
            video_url=(
                "/media/generated/"
                + result["filename"]
            ),
            seed=result["seed"],
            render_details=(
                result["render_details"]
            ),
            provider=(
                "huggingface-zero-gpu"
            ),
        )

    except Exception as exc:
        print()
        print("VIDEO GENERATION ERROR")
        print("----------------------")
        traceback.print_exc()
        print()

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post(
    "/full-video",
    response_model=FullVideoGenerationResponse,
)
async def generate_full_video(
    request: FullVideoGenerationRequest,
):
    """
    Generate every requested scene and combine all
    resulting clips into one final MP4 with FFmpeg.
    """

    try:
        if not request.scenes:
            raise ValueError(
                "At least one scene is required."
            )

        provider = get_video_provider(
            "huggingface"
        )

        width, height = get_render_dimensions(
            request.aspect_ratio
        )

        generated_paths: list[Path] = []
        scene_urls: list[str] = []
        render_details: list[str] = []

        total_scenes = len(
            request.scenes
        )

        print()
        print("TRIVEN CINEMA - FULL VIDEO")
        print("--------------------------")
        print(
            f"Scenes: {total_scenes}"
        )
        print(
            f"Aspect ratio: "
            f"{request.aspect_ratio}"
        )
        print(
            f"Resolution: "
            f"{width}x{height}"
        )
        print(
            f"Duration per scene: "
            f"{request.duration_seconds}s"
        )
        print()

        for index, scene in enumerate(
            request.scenes,
            start=1,
        ):
            print()
            print(
                f"Rendering scene "
                f"{index}/{total_scenes}"
            )
            print(
                f"Scene ID: {scene.id}"
            )
            print()

            #
            # Use a different deterministic seed
            # for every scene.
            #
            scene_seed = (
                request.seed
                + index
                - 1
            )

            result = provider.generate(
                prompt=scene.prompt,
                width=width,
                height=height,
                duration_seconds=(
                    request.duration_seconds
                ),
                seed=scene_seed,
                decoder=request.decoder,
                enhance_prompt=False,
            )

            clip_path = Path(
                result["path"]
            )

            generated_paths.append(
                clip_path
            )

            scene_urls.append(
                "/media/generated/"
                + result["filename"]
            )

            render_details.append(
                result["render_details"]
            )

            print(
                f"Scene {index} complete."
            )
            print(
                f"File: "
                f"{result['filename']}"
            )

        job_id = uuid.uuid4().hex

        output_directory = (
            generated_paths[0].parent
        )

        final_filename = (
            f"final-{job_id}.mp4"
        )

        final_path = (
            output_directory
            / final_filename
        )

        print()
        print("Combining scene clips...")
        print()

        combine_videos(
            video_paths=generated_paths,
            output_path=final_path,
        )

        print()
        print("FULL VIDEO COMPLETE")
        print("-------------------")
        print(
            f"Final file: "
            f"{final_filename}"
        )
        print()

        return FullVideoGenerationResponse(
            final_video_url=(
                "/media/generated/"
                + final_filename
            ),
            scene_video_urls=(
                scene_urls
            ),
            render_details=(
                render_details
            ),
            provider=(
                "huggingface-zero-gpu"
            ),
        )

    except Exception as exc:
        print()
        print("FULL VIDEO GENERATION ERROR")
        print("---------------------------")
        traceback.print_exc()
        print()

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
