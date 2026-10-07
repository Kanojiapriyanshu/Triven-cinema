from app.core.config import settings


def source_render_dimensions(aspect_ratio: str, quality: str = "preview") -> tuple[int, int]:
    """LTX target dimensions aligned to the active render pipeline.

    Preview stays inexpensive. Final-quality Modal jobs use DFR at a true
    production canvas: 1920x1088 for 1080-class output and the LTX v1.4.2
    4K grid (3840x2176) for UHD delivery before the final 16:9 crop.
    """
    if quality == "4k":
        if aspect_ratio == "16:9":
            return 3840, 2176
        if aspect_ratio == "9:16":
            return 2176, 3840
        return 2176, 2176

    if quality == "1080p":
        if aspect_ratio == "16:9":
            return 1920, 1088
        if aspect_ratio == "9:16":
            return 1088, 1920
        return 1088, 1088

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



def validate_factory_scene_duration(*, quality: str, duration_seconds: float) -> None:
    """Validate the user-selected Factory scene length.

    1080p creator shots may use any duration from the Factory minimum through the
    configured extended single-pass ceiling (30s by default).  This keeps runtime
    user-controlled instead of treating 30 seconds as a special hard-coded mode.
    4K remains capped at its validated scene ceiling.
    """
    duration = float(duration_seconds)
    minimum = max(1.0, float(settings.factory_min_scene_seconds))
    standard_max = max(minimum, float(settings.factory_standard_max_scene_seconds))

    if duration + 1e-6 < minimum:
        raise ValueError(f"Factory scenes must be at least {minimum:g}s.")

    if quality == "4k":
        maximum = max_scene_duration_seconds("4k")
        if duration > maximum + 1e-6:
            raise ValueError(f"4K Factory scenes are limited to {maximum:g}s in the validated profile.")
        return

    if quality == "1080p" and settings.factory_enable_30s_1080p_single_pass:
        maximum = min(
            max_scene_duration_seconds("1080p"),
            float(settings.factory_experimental_1080p_scene_seconds),
        )
        if duration <= maximum + 1e-6:
            validate_scene_duration(quality=quality, duration_seconds=duration)
            return
        raise ValueError(
            f"1080p Factory scenes can be selected from {minimum:g}s up to {maximum:g}s. "
            "Use a longer Final runtime to let Factory assemble multiple continuity-locked scenes."
        )

    if duration <= standard_max + 1e-6:
        validate_scene_duration(quality=quality, duration_seconds=duration)
        return

    raise ValueError(
        f"Factory scenes use {minimum:g}-{standard_max:g}s in the validated single-pass profile."
    )

def duration_profile() -> dict[str, float]:
    return {
        "preview": max_scene_duration_seconds("preview"),
        "1080p": max_scene_duration_seconds("1080p"),
        "4k": max_scene_duration_seconds("4k"),
    }
