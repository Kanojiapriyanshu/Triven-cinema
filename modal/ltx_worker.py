import subprocess
from pathlib import Path

from models import (
    AUDIO_VAE,
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


def build_command(
    *,
    prompt: str,
    output_path: Path,
    width: int,
    height: int,
    duration_seconds: float,
    seed: int,
    decoder: str,
    reference_image_path: Path | None = None,
    reference_strength: float = 0.95,
) -> list[str]:
    video_vae = (
        VIDEO_VAE_DIFFUSION
        if decoder == "diffusion"
        else VIDEO_VAE_CONV
    )

    command = [
        "uv",
        "run",
        "python",
        "-m",
        "ltx_pipelines.distilled",
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
        str(frames_for_duration(duration_seconds)),
        "--seed",
        str(seed),
        "--quantization",
        "fp8-cast",
        "--output-path",
        str(output_path),
        "--prompt",
        prompt,
    ]

    # LTX-2 image conditioning syntax is:
    #   --image PATH FRAME_IDX STRENGTH [CRF]
    # Frame 0 is a first-frame latent replacement/conditioning anchor, giving
    # the next clip a real visual continuation instead of another independent T2V sample.
    if reference_image_path is not None:
        strength = max(0.0, min(1.0, float(reference_strength)))
        command.extend([
            "--image",
            str(reference_image_path),
            "0",
            f"{strength:.3f}",
        ])

    return command


def run_ltx_command(command: list[str]) -> None:
    process = subprocess.run(
        command,
        cwd=LTX_REPO,
        capture_output=True,
        text=True,
    )

    if process.returncode != 0:
        raise RuntimeError(
            "LTX-2.5 inference failed:\n" + process.stderr[-8000:]
        )
