import math
import uuid
from pathlib import Path
from typing import Callable

from app.core.config import settings
from app.schemas.factory import FactoryGenerationRequest, FactoryGenerationResponse
from app.schemas.generation import MediaInfo
from app.services.audio_qc import evaluate_scene_audio
from app.services.continuity_service import compose_continuity_prompt
from app.services.continuity_qc import evaluate_scene_cardinality
from app.services.delivery_service import prepare_delivery, quality_note
from app.services.long_render_service import render_long_clip
from app.services.media_probe import probe_media
from app.services.metrics_service import estimate_gpu_cost, record_generation_metric
from app.services.scene_planner import create_prompt_only_plan, create_scene_plan
from app.services.storage_service import ensure_minimum_free_disk
from app.services.video_combiner import combine_videos, extract_continuity_frame
from app.services.video_profiles import source_render_dimensions, validate_scene_duration
from app.services.youtube_service import upload_video
from inference.providers.router import get_video_provider


PROJECT_ROOT = Path(__file__).resolve().parents[4]
GENERATED_DIR = (PROJECT_ROOT / "storage" / "generated").resolve()
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
ProgressCallback = Callable[[str, int, str], None]


def _scene_seed(base_seed: int, scene_index: int, attempt: int = 0) -> int:
    """Return a deterministic but different seed for every scene/retry.

    Reusing the same seed with the same or similar prompt at every 10-second Factory
    boundary strongly biases LTX toward replaying the same composition. First-frame
    conditioning carries identity; the seed should not also freeze scene layout.
    """
    modulus = 2_147_483_648
    return (int(base_seed) + int(scene_index) * 104_729 + int(attempt) * 7_919) % modulus


def _audio_prompt(prompt: str, audio_direction: str | None) -> str:
    direction = (audio_direction or "").strip()
    if not direction:
        return prompt
    return (
        f"{prompt}\n\n[AUDIO DIRECTION] Generate synchronized audio that follows the image and action. "
        f"{direction} Do not add spoken dialogue unless explicitly requested."
    )


def _media_info(path: Path) -> MediaInfo:
    return MediaInfo.model_validate(probe_media(path))


def _safe_title(prompt: str) -> str:
    compact = " ".join(prompt.split())
    return (compact[:96].rstrip(" .,:;-") or "Triven Cinema")[:100]


def run_factory_generation(
    request: FactoryGenerationRequest,
    *,
    workspace_id: str,
    progress: ProgressCallback | None = None,
) -> FactoryGenerationResponse:
    """Run the prompt-to-publish AI video factory as one bounded background job.

    Strict continuity uses five layers together: immutable character/style bibles,
    explicit entity cardinality, first-frame latent conditioning, stable near-end
    anchor selection, and an optional vision QC/regeneration gate.
    """
    ensure_minimum_free_disk()
    if request.target_duration_seconds > settings.max_factory_duration_seconds:
        raise ValueError(
            f"Factory jobs are limited to {settings.max_factory_duration_seconds}s on this deployment."
        )
    # Character-heavy final renders are deliberately decomposed into shorter shots.
    # Long clips amplify face/body drift and make exact dialogue harder to control.
    effective_scene_seconds = float(request.scene_duration_seconds)
    if request.quality != "preview":
        effective_scene_seconds = min(effective_scene_seconds, float(settings.cinema_max_scene_seconds))
    validate_scene_duration(
        quality=request.quality,
        duration_seconds=effective_scene_seconds,
    )
    if request.provider != "modal" and effective_scene_seconds > settings.ltx_native_chunk_seconds:
        raise ValueError("Long factory scenes currently require the Modal LTX provider.")

    scene_count = max(1, math.ceil(request.target_duration_seconds / effective_scene_seconds))
    if scene_count > 20:
        raise ValueError(
            "This factory job would require more than 20 story scenes. Increase scene duration or reduce total duration."
        )

    if progress:
        progress("planning", 8, f"Planning {scene_count} identity/cardinality-locked scenes...")
    if request.enhance_prompt:
        plan = create_scene_plan(
            prompt=request.prompt,
            scene_count=scene_count,
            aspect_ratio=request.aspect_ratio,
            force_ai=True,
            target_scene_duration_seconds=effective_scene_seconds,
        )
    else:
        plan = create_prompt_only_plan(
            prompt=request.prompt,
            scene_count=scene_count,
            target_scene_duration_seconds=effective_scene_seconds,
        )

    if (
        request.enhance_prompt
        and request.quality != "preview"
        and plan.source == "fallback"
        and not settings.factory_allow_fallback_final
    ):
        raise RuntimeError(
            "Final-quality Factory planning could not use Gemini after retries/failover. "
            "The local fallback is intentionally blocked before GPU rendering because it "
            "cannot safely guarantee named-character continuity for this job. Retry when "
            "Gemini is available, or use Preview if you explicitly want fallback planning."
        )

    provider = get_video_provider(request.provider, model=request.model)
    render_mode = "dfr" if request.quality != "preview" and request.provider == "modal" else "distilled"
    effective_decoder = "diffusion" if render_mode == "dfr" else request.decoder
    width, height = source_render_dimensions(request.aspect_ratio, request.quality)
    continuity_id = f"factory-{uuid.uuid4().hex[:16]}"
    source_paths: list[Path] = []
    render_details: list[str] = []
    total_render = 0.0
    total_wall = 0.0
    total_chunks = 0
    gpu: str | None = None
    previous_frame: Path | None = None
    continuity_frames: list[Path] = []
    remaining = float(request.target_duration_seconds)
    continuity_warnings: list[str] = []
    continuity_regenerations = 0
    qc_attempted = False
    all_qc_passed = True
    audio_qc_attempted = False
    all_audio_qc_passed = True
    audio_retake_count = 0
    audio_warnings: list[str] = []

    try:
        for index, scene in enumerate(plan.scenes):
            duration = min(effective_scene_seconds, remaining)
            remaining = max(0.0, remaining - duration)
            if duration < 1.0:
                break

            base_progress = 12 + int((index / max(1, scene_count)) * 66)

            def chunk_progress(part: int, count: int, message: str) -> None:
                if not progress:
                    return
                within_scene = int(((part + 1) / max(1, count)) * max(1, 66 // max(1, scene_count)))
                progress(
                    "rendering",
                    min(78, base_progress + within_scene),
                    f"Scene {index + 1}/{scene_count} · {message}",
                )

            accepted_result = None
            accepted_path: Path | None = None
            last_qc_note = ""
            attempts = max(0, int(request.continuity_max_retries)) + 1
            # Prompt-only Factory mode must not rewrite the user's prompt. Strict
            # continuity still benefits from first-frame conditioning; Gemini-backed
            # QC becomes advisory if the service is unavailable.
            effective_qc_mode = request.continuity_qc_mode
            if not request.enhance_prompt and effective_qc_mode == "strict":
                effective_qc_mode = "auto"

            for attempt in range(attempts):
                locked_prompt = scene.prompt
                if request.enhance_prompt and request.continuity_mode != "off":
                    locked_prompt = compose_continuity_prompt(
                        scene_prompt=locked_prompt,
                        character_bible=plan.character_bible,
                        style_bible=plan.style_bible,
                        scene_index=index,
                        scene_count=scene_count,
                        entity_locks=plan.entity_locks,
                        visible_entity_counts=scene.visible_entity_counts,
                        reference_frame_present=(
                            request.continuity_mode == "strict" and previous_frame is not None
                        ),
                        retry_level=attempt,
                        qc_feedback=last_qc_note,
                    )
                locked_prompt = _audio_prompt(locked_prompt, request.audio_direction)

                if attempt > 0 and progress:
                    progress(
                        "rendering",
                        min(77, base_progress + 2),
                        f"Scene {index + 1}/{scene_count} · continuity QC retry {attempt}/{attempts - 1}",
                    )

                result = render_long_clip(
                    provider=provider,
                    prompt=locked_prompt,
                    width=width,
                    height=height,
                    duration_seconds=duration,
                    seed=_scene_seed(request.seed, index, attempt),
                    decoder=effective_decoder,
                    enhance_prompt=False,
                    render_mode=render_mode,
                    reference_image_path=(
                        str(previous_frame)
                        if request.continuity_mode == "strict" and previous_frame is not None
                        else None
                    ),
                    reference_strength=request.continuity_strength,
                    progress=chunk_progress,
                )
                path = Path(result.path)

                total_render += float(result.render_seconds)
                total_wall += float(result.wall_seconds or result.render_seconds)
                total_chunks += int(result.chunk_count or 1)
                gpu = result.gpu or gpu

                qc = None
                if request.continuity_mode != "off" and effective_qc_mode != "off":
                    if progress:
                        progress(
                            "rendering",
                            min(79, base_progress + max(2, 62 // max(1, scene_count))),
                            f"Scene {index + 1}/{scene_count} · checking entity count and duplicates...",
                        )
                    qc = evaluate_scene_cardinality(
                        path,
                        entity_locks=plan.entity_locks,
                        visible_entity_counts=scene.visible_entity_counts,
                        character_bible=plan.character_bible,
                        scene_prompt=locked_prompt,
                        qc_mode=effective_qc_mode,
                        reference_frame_path=(
                            previous_frame
                            if request.continuity_mode == "strict" and previous_frame is not None
                            else None
                        ),
                    )
                    qc_attempted = qc_attempted or not qc.skipped
                    if qc.skipped and effective_qc_mode == "strict":
                        path.unlink(missing_ok=True)
                        raise RuntimeError(
                            f"Scene {index + 1} strict continuity QC could not run: {qc.note}"
                        )

                if qc is None or (qc.passed and not qc.duplicate_detected):
                    accepted_result = result
                    accepted_path = path
                    if qc and qc.skipped and qc.note:
                        continuity_warnings.append(f"Scene {index + 1}: {qc.note}")
                    break

                last_qc_note = qc.note or "; ".join(qc.violations) or "duplicate/cardinality violation"
                if attempt < attempts - 1:
                    continuity_regenerations += 1
                    path.unlink(missing_ok=True)
                    continue

                message = f"Scene {index + 1} continuity QC failed after {attempts} attempt(s): {last_qc_note}"
                if effective_qc_mode == "strict":
                    path.unlink(missing_ok=True)
                    raise RuntimeError(message)
                all_qc_passed = False
                continuity_warnings.append(message)
                accepted_result = result
                accepted_path = path

            if accepted_result is None or accepted_path is None:
                raise RuntimeError(f"Scene {index + 1} did not produce an accepted render.")

            # Semantic audio QC happens before loudness mastering. Mastering cannot
            # repair gibberish; on Modal we get one LTX audio-only Retake and recheck.
            if request.audio_mode != "mute" and settings.factory_audio_qc_enabled:
                if progress:
                    progress(
                        "rendering",
                        min(79, base_progress + max(3, 64 // max(1, scene_count))),
                        f"Scene {index + 1}/{scene_count} · checking generated speech/audio...",
                    )
                audio_qc = evaluate_scene_audio(
                    accepted_path,
                    scene_prompt=locked_prompt,
                    audio_direction=request.audio_direction,
                )
                audio_qc_attempted = audio_qc_attempted or not audio_qc.skipped
                strict_audio = (
                    request.enhance_prompt
                    and request.quality != "preview"
                    and settings.factory_audio_qc_strict_final
                )

                if audio_qc.skipped and strict_audio:
                    accepted_path.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"Scene {index + 1} final audio QC could not run: {audio_qc.note}"
                    )

                if not audio_qc.skipped and not audio_qc.passed:
                    audio_note = audio_qc.note or "; ".join(audio_qc.violations) or "generated audio failed semantic QC"
                    if provider.supports_audio_retake and settings.factory_audio_retake_enabled:
                        if progress:
                            progress(
                                "rendering",
                                min(79, base_progress + max(4, 65 // max(1, scene_count))),
                                f"Scene {index + 1}/{scene_count} · LTX audio-only Retake...",
                            )
                        retake_prompt = (
                            f"{locked_prompt}\n\n[AUDIO RETAKE] Regenerate only the requested clean audio for this exact shot. "
                            "Preserve the video. Never invent speech. No gibberish, fake language, random chanting, "
                            "background conversation, duplicate voices, or speech-like vocal noise. If dialogue is "
                            "quoted in the shot, speak only those exact words clearly; otherwise use ambience/Foley/music only."
                        )
                        retake = provider.retake_audio(
                            video_path=str(accepted_path),
                            prompt=retake_prompt,
                            duration_seconds=duration,
                            seed=request.seed + audio_retake_count,
                        )
                        retake_path = Path(retake.path)
                        total_render += float(retake.render_seconds)
                        total_wall += float(retake.wall_seconds or retake.render_seconds)
                        total_chunks += int(retake.chunk_count or 1)
                        gpu = retake.gpu or gpu
                        audio_retake_count += 1
                        accepted_path.unlink(missing_ok=True)
                        accepted_path = retake_path
                        render_details.append(retake.render_details)

                        audio_qc = evaluate_scene_audio(
                            accepted_path,
                            scene_prompt=locked_prompt,
                            audio_direction=request.audio_direction,
                        )
                        audio_qc_attempted = audio_qc_attempted or not audio_qc.skipped
                        if audio_qc.skipped and strict_audio:
                            accepted_path.unlink(missing_ok=True)
                            raise RuntimeError(
                                f"Scene {index + 1} audio Retake could not be rechecked: {audio_qc.note}"
                            )
                        if not audio_qc.skipped and not audio_qc.passed:
                            all_audio_qc_passed = False
                            final_note = audio_qc.note or "; ".join(audio_qc.violations) or audio_note
                            if strict_audio:
                                accepted_path.unlink(missing_ok=True)
                                raise RuntimeError(
                                    f"Scene {index + 1} audio still failed after LTX Retake: {final_note}"
                                )
                            audio_warnings.append(f"Scene {index + 1}: {final_note}")
                    else:
                        all_audio_qc_passed = False
                        if strict_audio:
                            accepted_path.unlink(missing_ok=True)
                            raise RuntimeError(
                                f"Scene {index + 1} audio QC failed and audio Retake is unavailable: {audio_note}"
                            )
                        audio_warnings.append(f"Scene {index + 1}: {audio_note}")
                elif audio_qc.skipped and audio_qc.note:
                    audio_warnings.append(f"Scene {index + 1}: {audio_qc.note}")

            source_paths.append(accepted_path)
            render_details.append(accepted_result.render_details)

            if request.continuity_mode != "off" and index < scene_count - 1:
                frame = GENERATED_DIR / f".factory-continuity-{uuid.uuid4().hex}.png"
                extract_continuity_frame(accepted_path, frame)
                continuity_frames.append(frame)
                previous_frame = frame

        if not source_paths:
            raise RuntimeError("Factory produced no scene clips.")

        if progress:
            progress("composing", 80, "Composing accepted scenes and synchronized audio...")
        composed = GENERATED_DIR / f"factory-source-{uuid.uuid4().hex}.mp4"
        combine_videos(source_paths, composed)

        if progress:
            progress("delivery", 88, f"Creating {request.quality} delivery master...")
        delivery = prepare_delivery(
            composed,
            aspect_ratio=request.aspect_ratio,
            quality=request.quality,
            audio_mode=request.audio_mode,
            prefix="factory",
        )
        info = _media_info(delivery)

        estimated_cost, cost_per_minute, cost_note = estimate_gpu_cost(
            render_seconds=total_wall,
            gpu=gpu,
            output_duration_seconds=request.target_duration_seconds,
        )

        youtube_video_id: str | None = None
        youtube_url: str | None = None
        youtube_privacy: str | None = None
        if request.publish_to_youtube:
            if progress:
                progress("publishing", 95, "Uploading the finished master to the connected YouTube channel...")
            published = upload_video(
                workspace_id,
                filename=delivery.name,
                title=(request.youtube_title or _safe_title(request.prompt)),
                description=request.youtube_description,
                privacy=request.youtube_privacy,
                tags=request.youtube_tags,
                category_id=request.youtube_category_id,
                publish_at=request.youtube_publish_at,
            )
            youtube_video_id = published["video_id"]
            youtube_url = published["youtube_url"]
            youtube_privacy = published["privacy"]

        filename = delivery.name
        qc_passed: bool | None = None
        if request.continuity_mode != "off" and request.continuity_qc_mode != "off":
            qc_passed = all_qc_passed if qc_attempted else None

        record_generation_metric(
            {
                "type": "factory",
                "provider": provider.name,
                "model": request.model,
                "gpu": gpu,
                "aspect_ratio": request.aspect_ratio,
                "scene_count": len(source_paths),
                "chunk_count": total_chunks,
                "target_duration_seconds": request.target_duration_seconds,
                "scene_duration_seconds": effective_scene_seconds,
                "render_seconds": round(total_render, 3),
                "wall_seconds": round(total_wall, 3),
                "quality": request.quality,
                "audio_mode": request.audio_mode,
                "has_audio": info.has_audio,
                "entity_lock_count": len(plan.entity_locks),
                "continuity_qc_mode": request.continuity_qc_mode,
                "continuity_qc_passed": qc_passed,
                "continuity_regenerations": continuity_regenerations,
                "continuity_warning_count": len(continuity_warnings),
                "audio_qc_passed": (all_audio_qc_passed if audio_qc_attempted else None),
                "audio_retake_count": audio_retake_count,
                "audio_warning_count": len(audio_warnings),
                "render_mode": render_mode,
                "estimated_cost_usd": estimated_cost,
                "estimated_cost_per_output_minute_usd": cost_per_minute,
                "youtube_published": bool(youtube_url),
                "filename": filename,
            }
        )

        return FactoryGenerationResponse(
            final_video_url=f"/media/generated/{filename}",
            final_download_url=f"/api/v1/generations/download/{filename}",
            final_filename=filename,
            target_duration_seconds=request.target_duration_seconds,
            actual_duration_seconds=info.duration_seconds,
            scene_count=len(source_paths),
            scene_duration_seconds=effective_scene_seconds,
            aspect_ratio=request.aspect_ratio,
            quality=request.quality,
            quality_note=quality_note(request.quality, request.aspect_ratio),
            audio_mode=request.audio_mode,
            has_audio=info.has_audio,
            width=info.width,
            height=info.height,
            provider=provider.name,
            model=request.model,
            gpu=gpu,
            total_render_seconds=round(total_render, 2),
            total_wall_seconds=round(total_wall, 2),
            chunk_count=total_chunks,
            estimated_cost_usd=estimated_cost,
            estimated_cost_per_output_minute_usd=cost_per_minute,
            cost_note=cost_note,
            planner_source=plan.source,
            planner_note=plan.note,
            continuity_id=continuity_id,
            entity_locks=plan.entity_locks,
            continuity_qc_passed=qc_passed,
            continuity_regenerations=continuity_regenerations,
            continuity_warnings=continuity_warnings,
            audio_qc_passed=(all_audio_qc_passed if audio_qc_attempted else None),
            audio_retake_count=audio_retake_count,
            audio_warnings=audio_warnings,
            youtube_video_id=youtube_video_id,
            youtube_url=youtube_url,
            youtube_privacy=youtube_privacy,
        )
    finally:
        for frame in continuity_frames:
            frame.unlink(missing_ok=True)
