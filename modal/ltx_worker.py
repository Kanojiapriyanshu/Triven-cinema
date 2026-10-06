import math
import subprocess
from pathlib import Path

from models import (
    AUDIO_VAE,
    DETAILING_LORA,
    INGREDIENTS_LORA,
    SPATIAL_UPSCALER,
    TEXT_ENCODER,
    TRANSFORMER,
    VIDEO_VAE_CONV,
    VIDEO_VAE_DIFFUSION,
)


LTX_REPO = Path("/opt/LTX-2")


def frames_for_duration(duration_seconds: float, fps: int = 24) -> int:
    """LTX clips use an 8n+1 frame count. 1s -> 25, 5s -> 121."""
    target = max(1, round(duration_seconds * fps))
    blocks = max(1, round(target / 8))
    return blocks * 8 + 1


# LTX-2.5's native duration range reaches 20s, so 15/20s clips are kept as
# one full generation. Distilled clips above 20s may use temporal windows. DFR
# final scenes never receive chunk flags: 15/20s and the explicit 30s 1080p
# experiment are submitted as a single pipeline call without application cuts.
LONG_VIDEO_PIXEL_FRAMES = 97
LONG_VIDEO_CARRY_FRAMES = 25
LONG_VIDEO_MIN_DURATION_SECONDS = 20.0
DFR_SINGLE_PASS_MAX_SECONDS = 30.0
INGREDIENTS_EXPERIMENTAL_MAX_SECONDS = 20.0
INGREDIENTS_REFERENCE_FPS = 24
INGREDIENTS_REFERENCE_MIN_FRAMES = 121


def static_reference_frame_count(duration_seconds: float, fps: int = INGREDIENTS_REFERENCE_FPS) -> int:
    """Return an Ingredients reference length that matches the generated clip.

    LTX Ingredients was trained with reference videos that are at least 121 frames
    and whose static sheet is looped across the full target clip.  The old Triven
    worker always sent a fixed five-second/120-frame guide, which under-conditioned
    15-20 second scenes and could bias the beginning toward an artificial still hold.
    """
    return max(INGREDIENTS_REFERENCE_MIN_FRAMES, frames_for_duration(duration_seconds, fps=fps))


def build_static_reference_video_command(
    image_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
    frame_count: int,
    fps: int = INGREDIENTS_REFERENCE_FPS,
) -> list[str]:
    target_width = max(64, int(width))
    target_height = max(64, int(height))
    target_frames = max(INGREDIENTS_REFERENCE_MIN_FRAMES, int(frame_count))
    target_fps = max(1, int(fps))
    return [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", str(target_fps),
        "-i", str(image_path),
        "-vf", (
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={target_fps},format=yuv420p"
        ),
        "-frames:v", str(target_frames),
        "-r", str(target_fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "12",
        "-movflags", "+faststart", "-an", str(output_path),
    ]


def make_static_reference_video(
    image_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
    frame_count: int,
    fps: int = INGREDIENTS_REFERENCE_FPS,
) -> None:
    """Build the full-length static guide video expected by Ingredients IC-LoRA."""
    command = build_static_reference_video_command(
        image_path,
        output_path,
        width=width,
        height=height,
        frame_count=frame_count,
        fps=fps,
    )
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0 or not output_path.exists():
        raise RuntimeError("Unable to build LTX Ingredients reference video: " + process.stderr[-2000:])


def temporal_chunk_count(
    duration_seconds: float,
    *,
    fps: int = 24,
    pixel_frames: int = LONG_VIDEO_PIXEL_FRAMES,
    carry_frames: int = LONG_VIDEO_CARRY_FRAMES,
) -> int:
    if duration_seconds <= LONG_VIDEO_MIN_DURATION_SECONDS:
        return 1
    total_frames = frames_for_duration(duration_seconds, fps=fps)
    stride = pixel_frames - carry_frames
    if stride <= 0:
        raise ValueError("Temporal chunk carry must be smaller than the chunk window.")
    return 1 + math.ceil((total_frames - pixel_frames) / stride)


def build_command(
    *,
    prompt: str,
    output_path: Path,
    width: int,
    height: int,
    duration_seconds: float,
    seed: int,
    decoder: str,
    render_mode: str = "distilled",
    reference_image_path: Path | None = None,
    reference_strength: float = 0.95,
    element_reference_video_path: Path | None = None,
    element_reference_strength: float = 1.0,
) -> list[str]:
    mode = (render_mode or "distilled").strip().lower()
    if mode not in {"distilled", "dfr"}:
        raise ValueError(f"Unsupported LTX render mode: {render_mode}")
    use_ingredients = element_reference_video_path is not None
    if mode == "dfr" and not use_ingredients and duration_seconds > DFR_SINGLE_PASS_MAX_SECONDS + 1e-6:
        raise ValueError(
            f"DFR single-pass scenes are limited to {DFR_SINGLE_PASS_MAX_SECONDS:g}s in this deployment."
        )
    if use_ingredients and duration_seconds > INGREDIENTS_EXPERIMENTAL_MAX_SECONDS + 1e-6:
        raise ValueError(
            f"Element identity-conditioned scenes are limited to {INGREDIENTS_EXPERIMENTAL_MAX_SECONDS:g}s "
            "until the Ingredients profile is benchmarked beyond its training bucket."
        )

    # Production DFR needs the diffusion decoder. Ingredients runs on the distilled
    # base by design, while still allowing a first-frame image alongside its guide.
    video_vae = VIDEO_VAE_DIFFUSION if (mode == "dfr" and not use_ingredients) or decoder == "diffusion" else VIDEO_VAE_CONV
    num_frames = frames_for_duration(duration_seconds)
    pipeline_module = "ltx_pipelines.ic_lora" if use_ingredients else ("ltx_pipelines.dfr_pipeline" if mode == "dfr" else "ltx_pipelines.distilled")

    command = [
        "uv",
        "run",
        "python",
        "-m",
        pipeline_module,
        "--transformer-path",
        str(TRANSFORMER),
        "--text-encoder-path",
        str(TEXT_ENCODER),
        "--video-vae-path",
        str(video_vae),
        "--audio-vae-path",
        str(AUDIO_VAE),
        "--spatial-upsampler-path",
        str(SPATIAL_UPSCALER),
        "--width",
        str(width),
        "--height",
        str(height),
        "--num-frames",
        str(num_frames),
        "--seed",
        str(seed),
        "--quantization",
        "fp8-cast",
        "--output-path",
        str(output_path),
        "--prompt",
        prompt,
    ]

    if use_ingredients:
        strength = max(0.0, min(1.5, float(element_reference_strength)))
        command.extend(
            [
                "--lora", str(INGREDIENTS_LORA), f"{strength:.3f}",
                "--video-conditioning", str(element_reference_video_path), f"{strength:.3f}",
            ]
        )
    elif mode == "dfr":
        command.extend(
            [
                "--detailing-lora",
                str(DETAILING_LORA),
                "--spatial-upscalings",
                "2" if max(width, height) >= 3000 else "1",
                "--temporal-upscalings",
                "0",
            ]
        )
    elif duration_seconds > LONG_VIDEO_MIN_DURATION_SECONDS:
        command.extend(
            [
                "--chunk-pixel-frames",
                str(LONG_VIDEO_PIXEL_FRAMES),
                "--chunk-carry-frames",
                str(LONG_VIDEO_CARRY_FRAMES),
            ]
        )

    # DFR and Distilled both support image-to-video conditioning. Once this is
    # supplied, the application prompt describes the next action/change rather
    # than replaying the whole character bible into every continuation shot.
    if reference_image_path is not None:
        strength = max(0.0, min(1.0, float(reference_strength)))
        command.extend(
            [
                "--image",
                str(reference_image_path),
                "0",
                f"{strength:.3f}",
                "0",
            ]
        )

    return command


def run_ltx_command(command: list[str]) -> None:
    process = subprocess.run(
        command,
        cwd=LTX_REPO,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise RuntimeError("LTX-2.5 inference failed:\n" + process.stderr[-8000:])
