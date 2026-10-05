import uuid
from pathlib import Path

from app.services.video_combiner import process_audio, transcode_delivery


GENERATED_DIR = (Path(__file__).resolve().parents[4] / "storage" / "generated").resolve()
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def quality_note(quality: str, aspect_ratio: str) -> str:
    if quality == "preview":
        return "LTX source render profile; no delivery upscale applied."

    if quality == "4k":
        if aspect_ratio == "9:16":
            delivery = "2160x3840"
        elif aspect_ratio == "1:1":
            delivery = "2160x2160"
        else:
            delivery = "3840x2160"
        return (
            f"{delivery} 4K delivery master. The current self-hosted distilled pipeline "
            "renders the validated LTX source profile first and performs one final delivery "
            "transcode. This label does not claim native-4K source generation."
        )

    if aspect_ratio == "9:16":
        delivery = "1080x1920"
    elif aspect_ratio == "1:1":
        delivery = "1080x1080"
    else:
        delivery = "1920x1080"
    return (
        f"{delivery} 1080p delivery master. Triven renders the LTX source profile first "
        "and performs one final delivery transcode."
    )


def prepare_delivery(
    source_path: Path,
    *,
    aspect_ratio: str,
    quality: str,
    audio_mode: str,
    prefix: str,
) -> Path:
    quality_path = source_path
    if quality != "preview":
        quality_path = GENERATED_DIR / f"{prefix}-{quality}-{uuid.uuid4().hex}.mp4"
        quality_path = transcode_delivery(
            input_path=source_path,
            output_path=quality_path,
            aspect_ratio=aspect_ratio,
            quality=quality,
        )

    if audio_mode == "native":
        return quality_path

    audio_path = GENERATED_DIR / f"{prefix}-{audio_mode}-{uuid.uuid4().hex}.mp4"
    processed = process_audio(quality_path, audio_path, audio_mode)
    if processed != quality_path and quality_path != source_path:
        quality_path.unlink(missing_ok=True)
    return processed
