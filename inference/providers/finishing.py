"""Finishing pass applied to every generated clip before it is stored.

Two artefacts are visible on raw LTX-2.5 output and are what this pass removes:

* temporal luminance instability - the overall brightness drifts up and down
  across the clip (worst across the ~5s chunk boundaries of identity-conditioned
  shots). `deflicker` smooths the per-frame average luminance over a short moving
  window, so a shot that is meant to hold its exposure actually holds it.
* highlight bloom - bright skin and the brightest parts of the face glow/blow
  out. A gentle highlight roll-off compresses only the top of the tonal range,
  leaving shadows and mid-tones (where skin sits) untouched.

The pass runs on the application host with ffmpeg (CPU), so it needs no GPU and
no Modal redeploy, and it is reprocessable. It is deliberately conservative and
fail-open: if ffmpeg is missing or the pass errors, the original clip is kept so
a paid render is never lost to a cosmetic step.
"""
import logging
import os
import shutil
import subprocess
from pathlib import Path

LOGGER = logging.getLogger("triven.finishing")

# ~1.3s moving-average window at 24fps: wide enough to flatten both frame-to-frame
# flicker and the slower exposure swell across identity-chunk boundaries, still short
# enough to let a deliberate lighting change (longer than the window) through. Raise
# TRIVEN_VIDEO_DEFLICKER_SIZE toward 129 (~5s) for a shot that must hold one exposure.
DEFAULT_DEFLICKER_SIZE = 31
# Fraction the brightest tone is pulled down. 0.10 is barely perceptible on a
# correctly exposed shot but visibly calms a bloomed one. 0 disables the roll-off.
DEFAULT_HIGHLIGHT_ROLLOFF = 0.10
FINISH_TIMEOUT_SECONDS = 15 * 60


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, "").strip()))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default


def finishing_enabled() -> bool:
    return _env_flag("TRIVEN_VIDEO_FINISHING", True)


def deflicker_size() -> int:
    return max(0, _env_int("TRIVEN_VIDEO_DEFLICKER_SIZE", DEFAULT_DEFLICKER_SIZE))


def highlight_rolloff() -> float:
    return max(0.0, min(0.4, _env_float("TRIVEN_VIDEO_HIGHLIGHT_ROLLOFF", DEFAULT_HIGHLIGHT_ROLLOFF)))


def ffmpeg_binary() -> str | None:
    override = os.getenv("TRIVEN_FFMPEG", "").strip()
    if override:
        return override
    return shutil.which("ffmpeg")


def _highlight_curve(rolloff: float) -> str:
    """A monotone curve that leaves everything up to the mid-tones alone and
    compresses only the highlights. Skin mid-tones (~0.6) are protected."""
    rolloff = max(0.0, min(0.4, float(rolloff)))
    hi = round(1.0 - rolloff, 4)
    knee = round(0.8 - rolloff * 0.5, 4)
    return f"curves=all='0/0 0.6/0.6 0.8/{knee} 1/{hi}'"


def build_video_filters(*, deflicker_window: int, rolloff: float) -> str:
    filters: list[str] = []
    if deflicker_window and deflicker_window >= 2:
        filters.append(f"deflicker=mode=am:size={int(deflicker_window)}")
    if rolloff > 0:
        filters.append(_highlight_curve(rolloff))
    filters.append("format=yuv420p")
    return ",".join(filters)


def build_finish_command(
    *,
    input_path: Path,
    output_path: Path,
    binary: str = "ffmpeg",
    deflicker_window: int = DEFAULT_DEFLICKER_SIZE,
    rolloff: float = DEFAULT_HIGHLIGHT_ROLLOFF,
    crf: int = 14,
) -> list[str]:
    """ffmpeg command for the finishing pass. Picture is re-encoded; audio is
    stream-copied untouched so the voice and timing are identical."""
    return [
        binary, "-y", "-loglevel", "error",
        "-i", str(input_path),
        "-vf", build_video_filters(deflicker_window=deflicker_window, rolloff=rolloff),
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(int(crf)),
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]


def finish_video(source: Path, *, tame_highlights: bool = True) -> Path | None:
    """Produce a finished sibling of ``source`` and return its path, or ``None``
    when finishing is disabled, unavailable, or fails (the caller then keeps the
    original). ``tame_highlights=False`` runs the temporal pass only - used when
    the input already had its highlights managed (e.g. upscaling an approved Draft)."""
    if not finishing_enabled():
        return None
    window = deflicker_size()
    rolloff = highlight_rolloff() if tame_highlights else 0.0
    if window < 2 and rolloff <= 0:
        return None
    binary = ffmpeg_binary()
    if binary is None:
        LOGGER.warning("ffmpeg not found on PATH; skipping the video finishing pass")
        return None
    output = source.with_name(source.stem + "-finished.mp4")
    command = build_finish_command(
        input_path=source,
        output_path=output,
        binary=binary,
        deflicker_window=window,
        rolloff=rolloff,
    )
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=FINISH_TIMEOUT_SECONDS)
    except Exception:
        LOGGER.exception("Video finishing pass could not run; keeping the raw clip")
        output.unlink(missing_ok=True)
        return None
    if process.returncode != 0 or not output.exists():
        LOGGER.warning("Video finishing pass failed (keeping the raw clip): %s", (process.stderr or "")[-800:])
        output.unlink(missing_ok=True)
        return None
    return output
