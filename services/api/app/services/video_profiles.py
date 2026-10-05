from app.core.config import settings


def source_render_dimensions(aspect_ratio: str) -> tuple[int, int]:
    """Fast/source LTX dimensions, all divisible by 64."""
    if aspect_ratio == "16:9":
        return 1024, 576
    if aspect_ratio == "9:16":
        return 576, 1024
    return 512, 512


def max_scene_duration_seconds(quality: str) -> float:
    if quality == "4k":
        return max(1.0, float(settings.max_4k_scene_seconds))
    if quality == "1080p":
        return max(1.0, float(settings.max_1080p_scene_seconds))
    return max(1.0, float(settings.max_preview_scene_seconds))


def validate_scene_duration(*, quality: str, duration_seconds: float) -> None:
    maximum = max_scene_duration_seconds(quality)
    if duration_seconds > maximum + 1e-6:
        label = "4K" if quality == "4k" else quality
        raise ValueError(
            f"{label} scenes are limited to {maximum:g}s in the validated production profile. "
            "Use multiple scenes/factory mode for longer videos."
        )


def duration_profile() -> dict[str, float]:
    return {
        "preview": max_scene_duration_seconds("preview"),
        "1080p": max_scene_duration_seconds("1080p"),
        "4k": max_scene_duration_seconds("4k"),
    }
