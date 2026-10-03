import subprocess
import tempfile
from pathlib import Path

from app.core.config import settings
from app.services.media_probe import probe_media


class VideoCombineError(RuntimeError):
    pass


def _run_ffmpeg(command: list[str]) -> None:
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(30, int(settings.ffmpeg_timeout_seconds)),
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoCombineError("FFmpeg timed out while processing the video.") from exc

    if process.returncode != 0:
        raise VideoCombineError(
            "FFmpeg failed:\n" + process.stderr[-5000:]
        )


def delivery_dimensions(aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio == "9:16":
        return 1080, 1920
    if aspect_ratio == "1:1":
        return 1080, 1080
    return 1920, 1080


def _add_silent_audio(input_path: Path, output_path: Path) -> Path:
    info = probe_media(input_path)
    duration = float(info.get("duration_seconds") or 1.0)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-f",
        "lavfi",
        "-t",
        f"{duration:.3f}",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_path),
    ]
    _run_ffmpeg(command)
    return output_path


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
    concat_file: Path | None = None
    temporary_normalized: list[Path] = []

    try:
        media = [probe_media(path) for path in video_paths]
        any_audio = any(item.get("has_audio") for item in media)
        all_audio = all(item.get("has_audio") for item in media)

        normalized_paths = list(video_paths)
        if any_audio and not all_audio:
            normalized_paths = []
            for index, (path, info) in enumerate(zip(video_paths, media, strict=True)):
                if info.get("has_audio"):
                    normalized_paths.append(path)
                    continue
                normalized = output_path.parent / f".normalized-{index}-{path.name}"
                _add_silent_audio(path, normalized)
                temporary_normalized.append(normalized)
                normalized_paths.append(normalized)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            dir=output_path.parent,
            encoding="utf-8",
        ) as handle:
            concat_file = Path(handle.name)

            for video_path in normalized_paths:
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
        ]

        if any_audio:
            command.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            command.append("-an")

        command.extend([
            "-movflags",
            "+faststart",
            str(output_path),
        ])

        _run_ffmpeg(command)

        if not output_path.exists():
            raise VideoCombineError(
                "FFmpeg completed but final video was not created."
            )

        return output_path

    finally:
        if concat_file is not None and concat_file.exists():
            concat_file.unlink()
        for path in temporary_normalized:
            if path.exists():
                path.unlink()


def upscale_to_1080p(
    input_path: Path,
    output_path: Path,
    aspect_ratio: str,
) -> Path:
    """
    Create a 1080-class delivery file exactly once.

    If the input already has the requested delivery dimensions, it is reused to
    avoid an unnecessary second lossy encode. This still does not claim that
    source detail was natively generated at 1080p.
    """
    if not input_path.exists():
        raise VideoCombineError(
            f"Input video does not exist: {input_path}"
        )

    width, height = delivery_dimensions(aspect_ratio)
    info = probe_media(input_path)
    if info.get("width") == width and info.get("height") == height:
        return input_path

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
    ]

    if info.get("has_audio"):
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    else:
        command.append("-an")

    command.extend([
        "-movflags",
        "+faststart",
        str(output_path),
    ])

    _run_ffmpeg(command)

    if not output_path.exists():
        raise VideoCombineError(
            "1080p delivery transcode completed but output was not created."
        )

    return output_path
