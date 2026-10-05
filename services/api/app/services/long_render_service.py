import math
import uuid
from pathlib import Path
from typing import Callable

from app.core.config import settings
from app.services.video_combiner import combine_videos, extract_last_frame
from inference.providers.base import VideoGenerationResult, VideoProvider


GENERATED_DIR = (Path(__file__).resolve().parents[4] / "storage" / "generated").resolve()
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
ProgressCallback = Callable[[int, int, str], None]


def split_duration(duration_seconds: float, max_chunk_seconds: float | None = None) -> list[float]:
    total = float(duration_seconds)
    if total <= 0:
        raise ValueError("Duration must be positive.")
    maximum = float(max_chunk_seconds or settings.ltx_native_chunk_seconds)
    if maximum < 1:
        raise ValueError("LTX native chunk duration must be at least one second.")

    count = max(1, math.ceil(total / maximum))
    chunks: list[float] = []
    remaining = total
    for _ in range(count):
        value = min(maximum, remaining)
        chunks.append(round(value, 3))
        remaining -= value
    if remaining > 0.001:
        chunks.append(round(remaining, 3))
    return chunks


def _continuation_prompt(prompt: str, part: int, count: int) -> str:
    if part == 0:
        return prompt
    return (
        f"{prompt}\n\n"
        f"CONTINUATION PART {part + 1} OF {count}: Continue directly from the supplied first frame. "
        "Preserve the exact subject identity, wardrobe, environment, lighting direction, camera logic, "
        "motion trajectory and synchronized audio world. Do not restart the action or redesign anything."
    )


def render_long_clip(
    *,
    provider: VideoProvider,
    prompt: str,
    width: int,
    height: int,
    duration_seconds: float,
    seed: int,
    decoder: str,
    enhance_prompt: bool = False,
    reference_image_path: str | None = None,
    reference_strength: float = 0.95,
    progress: ProgressCallback | None = None,
) -> VideoGenerationResult:
    """Render a customer-facing long clip with the safest provider strategy.

    The Modal LTX-2.5 worker uses the upstream DistilledPipeline temporal-window
    mode for long clips, so a 15s/30s customer scene remains one multimodal LTX
    invocation with overlap/blending between native windows. Providers that do not
    expose native long-video windowing fall back to application-level continuation
    chunks when possible.
    """
    if provider.supports_native_long_video or duration_seconds <= settings.ltx_native_chunk_seconds:
        if progress:
            progress(0, 1, "Rendering LTX clip" if duration_seconds <= settings.ltx_native_chunk_seconds else "Rendering native LTX temporal windows")
        return provider.generate(
            prompt=prompt,
            width=width,
            height=height,
            duration_seconds=duration_seconds,
            seed=seed,
            decoder=decoder,
            enhance_prompt=enhance_prompt,
            reference_image_path=reference_image_path,
            reference_strength=reference_strength,
        )

    chunks = split_duration(duration_seconds)
    if len(chunks) > 1 and not provider.name.startswith("modal"):
        raise ValueError(
            "Long-form continuation currently requires a provider with native long-video "
            "windowing or first-frame conditioning."
        )

    rendered_paths: list[Path] = []
    temporary_frames: list[Path] = []
    current_reference = Path(reference_image_path) if reference_image_path else None
    total_render = 0.0
    total_wall = 0.0
    gpu: str | None = None
    any_conditioned = False
    details: list[str] = []
    last_result: VideoGenerationResult | None = None

    try:
        for index, chunk_duration in enumerate(chunks):
            if progress:
                progress(index, len(chunks), f"Rendering continuation {index + 1}/{len(chunks)}")

            result = provider.generate(
                prompt=_continuation_prompt(prompt, index, len(chunks)),
                width=width,
                height=height,
                duration_seconds=chunk_duration,
                seed=seed,
                decoder=decoder,
                enhance_prompt=enhance_prompt if index == 0 else False,
                reference_image_path=str(current_reference) if current_reference else None,
                reference_strength=reference_strength,
            )
            last_result = result
            path = Path(result.path)
            rendered_paths.append(path)
            total_render += float(result.render_seconds)
            total_wall += float(result.wall_seconds or result.render_seconds)
            gpu = result.gpu or gpu
            any_conditioned = any_conditioned or bool(result.reference_conditioned)
            details.append(result.render_details)

            if index < len(chunks) - 1:
                frame = GENERATED_DIR / f".continuation-{uuid.uuid4().hex}.png"
                extract_last_frame(path, frame)
                temporary_frames.append(frame)
                current_reference = frame

        if last_result is None:
            raise RuntimeError("No LTX chunks were rendered.")

        if len(rendered_paths) == 1:
            return VideoGenerationResult(
                filename=rendered_paths[0].name,
                path=str(rendered_paths[0]),
                seed=last_result.seed,
                render_details=details[0],
                render_seconds=total_render,
                prompt=prompt,
                provider=last_result.provider,
                model=last_result.model,
                gpu=gpu,
                wall_seconds=total_wall,
                reference_conditioned=any_conditioned,
                chunk_count=1,
            )

        combined = GENERATED_DIR / f"ltx-long-{uuid.uuid4().hex}.mp4"
        combine_videos(rendered_paths, combined)
        for path in rendered_paths:
            path.unlink(missing_ok=True)

        return VideoGenerationResult(
            filename=combined.name,
            path=str(combined),
            seed=last_result.seed,
            render_details=(
                f"{width}x{height} · {duration_seconds:.1f}s · {len(chunks)} chained LTX chunks · "
                f"{decoder} decoder · {gpu or 'GPU'}"
            ),
            render_seconds=total_render,
            prompt=prompt,
            provider=last_result.provider,
            model=last_result.model,
            gpu=gpu,
            wall_seconds=total_wall,
            reference_conditioned=any_conditioned,
            chunk_count=len(chunks),
        )
    finally:
        for frame in temporary_frames:
            frame.unlink(missing_ok=True)
