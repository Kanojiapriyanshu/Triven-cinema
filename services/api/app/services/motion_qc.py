"""Detect a "frozen still" render: the reference image held for the whole clip with audio on top.

Image- and Element-conditioned LTX renders can collapse to a single held frame when the reference is
conditioned too hard or the prompt gives the subject nothing to do. The clip still has valid video and
audio streams, so no other check notices it. This guard samples frames across the clip and measures how
much the picture actually changes.
"""
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from PIL import Image

from app.core.config import settings
from app.services.media_probe import probe_media
from app.services.video_combiner import _extract_png

SAMPLE_POSITIONS: tuple[float, ...] = (0.08, 0.25, 0.42, 0.59, 0.76, 0.92)
COMPARE_SIZE = (48, 48)


@dataclass(frozen=True)
class MotionReport:
    mean_diff: float
    max_diff: float
    frames: int
    still: bool

    @property
    def note(self) -> str:
        return (
            f"the video is almost a frozen still (average frame change {self.mean_diff:.2f} on a 0-255 scale, "
            f"threshold {settings.motion_guard_min_mean_diff:.2f})"
        )


def _gray(image: Image.Image) -> list[int]:
    return list(image.convert("L").resize(COMPARE_SIZE, Image.Resampling.BILINEAR).tobytes())


def motion_report(frames: Sequence[Image.Image], *, min_mean_diff: float | None = None) -> MotionReport:
    """Mean absolute grey-level change between consecutive sampled frames."""
    threshold = settings.motion_guard_min_mean_diff if min_mean_diff is None else min_mean_diff
    grays = [_gray(frame) for frame in frames]
    if len(grays) < 2:
        return MotionReport(mean_diff=0.0, max_diff=0.0, frames=len(grays), still=False)
    diffs = [
        sum(abs(a - b) for a, b in zip(left, right)) / len(left)
        for left, right in zip(grays, grays[1:])
    ]
    mean_diff = sum(diffs) / len(diffs)
    return MotionReport(mean_diff=mean_diff, max_diff=max(diffs), frames=len(grays), still=mean_diff < threshold)


def _load_frames(path: Path) -> list[Image.Image]:
    duration = max(0.5, float(probe_media(path).get("duration_seconds") or 0.5))
    frames: list[Image.Image] = []
    with tempfile.TemporaryDirectory() as tmp:
        for index, position in enumerate(SAMPLE_POSITIONS):
            target = Path(tmp) / f"motion-{index}.png"
            _extract_png(path, target, seek_seconds=min(duration * position, max(0.0, duration - 0.1)))
            with Image.open(target) as image:
                frames.append(image.convert("L").copy())
    return frames


def measure_motion(
    path: Path,
    *,
    frame_loader: Callable[[Path], Sequence[Image.Image]] | None = None,
) -> MotionReport | None:
    """Return a MotionReport, or None when the guard is disabled or frames cannot be sampled.

    Failing to measure must never discard an expensive render, so any ffmpeg/probe problem is a skip.
    """
    if not settings.factory_motion_guard_enabled:
        return None
    try:
        frames = (frame_loader or _load_frames)(path)
    except Exception:  # noqa: BLE001 - best-effort guard
        return None
    return motion_report(frames)
