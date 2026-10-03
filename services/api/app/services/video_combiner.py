import subprocess
import tempfile
from pathlib import Path


class VideoCombineError(RuntimeError):
    pass


def combine_videos(
    video_paths: list[Path],
    output_path: Path,
) -> Path:
    if not video_paths:
        raise VideoCombineError(
            "No video clips were provided."
        )

    for video_path in video_paths:
        if not video_path.exists():
            raise VideoCombineError(
                f"Video clip does not exist: {video_path}"
            )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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
                    video_path
                    .resolve()
                    .as_posix()
                    .replace("'", "'\\''")
                )

                handle.write(
                    f"file '{absolute_path}'\n"
                )

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

        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        if process.returncode != 0:
            raise VideoCombineError(
                "FFmpeg failed:\n"
                + process.stderr[-5000:]
            )

        if not output_path.exists():
            raise VideoCombineError(
                "FFmpeg completed but final video was not created."
            )

        return output_path

    finally:
        if (
            concat_file is not None
            and concat_file.exists()
        ):
            concat_file.unlink()
