import subprocess
import tempfile
from pathlib import Path


class VideoCombineError(RuntimeError):
    pass


def _run_ffmpeg(command: list[str]) -> None:
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if process.returncode != 0:
        raise VideoCombineError(
            "FFmpeg failed:\n" + process.stderr[-5000:]
        )


def combine_videos(
    video_paths: list[Path],
    output_path: Path,
) -> Path:
    if not video_paths:
        raise VideoCombineError("No video clips were provided.")

    for video_path in video_paths:
        if not video_path.exists():
            raise VideoCombineError(
                f"Video clip does not exist: {video_path}"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            dir=output_path.parent,
            encoding="utf-8",
        ) as handle:
            concat_file = Path(handle.name)

            for video_path in video_paths:
                absolute_path = (
                    video_path.resolve().as_posix().replace("'", "'\\''")
                )
                handle.write(f"file '{absolute_path}'\n")

        command = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

        _run_ffmpeg(command)

        if not output_path.exists():
            raise VideoCombineError(
                "FFmpeg completed but final video was not created."
            )

        return output_path

    finally:
        if concat_file is not None and concat_file.exists():
            concat_file.unlink()


def upscale_to_1080p(
    input_path: Path,
    output_path: Path,
    aspect_ratio: str,
) -> Path:
    """
    Create a 1080-class delivery file.

    This is delivery upscaling for the current MVP. It does not claim that the
    source frames were natively generated at 1080p.
    """
    if not input_path.exists():
        raise VideoCombineError(
            f"Input video does not exist: {input_path}"
        )

    if aspect_ratio == "9:16":
        width, height = 1080, 1920
    elif aspect_ratio == "1:1":
        width, height = 1080, 1080
    else:
        width, height = 1920, 1080

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    _run_ffmpeg(command)

    if not output_path.exists():
        raise VideoCombineError(
            "1080p delivery transcode completed but output was not created."
        )

    return output_path
