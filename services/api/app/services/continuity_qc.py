import base64
import json
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.schemas.generation import EntityLock
from app.services.continuity_service import compact_text, normalize_entity_locks
from app.services.gemini_service import generate_content
from app.services.video_combiner import extract_qc_frames


class ContinuityQCResult(BaseModel):
    passed: bool = True
    duplicate_detected: bool = False
    identity_drift_detected: bool = False
    observed_max_counts: dict[str, int] = Field(default_factory=dict)
    violations: list[str] = Field(default_factory=list)
    identity_violations: list[str] = Field(default_factory=list)
    note: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    skipped: bool = False


def _extract_json_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini continuity QC returned no candidates.")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    text_parts = [
        str(part.get("text") or "")
        for part in parts
        if not part.get("thought")
    ]
    text = "".join(text_parts).strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    if not text:
        raise RuntimeError("Gemini continuity QC returned an empty response.")
    return text


def _skipped(note: str) -> ContinuityQCResult:
    return ContinuityQCResult(passed=True, skipped=True, note=note, confidence=0.0)


def _image_part(path: Path) -> dict:
    suffix = path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "image/png")
    return {
        "inlineData": {
            "mimeType": mime,
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        }
    }


def evaluate_scene_cardinality(
    video_path: Path,
    *,
    entity_locks: list[EntityLock] | list[dict] | None,
    visible_entity_counts: dict[str, int] | None,
    character_bible: str | None,
    scene_prompt: str,
    qc_mode: str = "auto",
    reference_frame_path: Path | None = None,
    canonical_reference_paths: list[tuple[str, Path]] | None = None,
) -> ContinuityQCResult:
    """Inspect frames for duplicate subjects *and* recurring-character identity drift.

    When a previous approved frame is available it becomes the identity reference for
    the current shot. This makes QC answer both questions that matter for narrative
    continuity: "how many?" and "is this still the same character?".
    """
    if qc_mode == "off":
        return _skipped("Continuity vision QC disabled for this request.")
    if not settings.continuity_vision_qc_enabled:
        return _skipped("Continuity vision QC is disabled by deployment configuration.")
    if not settings.gemini_api_key:
        return _skipped("Gemini is not configured; prompt/cardinality guard remains active.")

    locks = normalize_entity_locks(entity_locks)
    lock_lines = [
        f"{lock.label}: canonical maximum {lock.expected_count}; {lock.description}"
        for lock in locks
    ]
    if visible_entity_counts:
        exact = ", ".join(
            f"{str(label).upper()}={max(0, int(count))}"
            for label, count in visible_entity_counts.items()
        )
    else:
        exact = "No exact per-shot counts supplied; enforce canonical maximums and reject obvious clones."

    has_reference = bool(reference_frame_path and reference_frame_path.exists())
    canonical_refs = [
        (label, path) for label, path in (canonical_reference_paths or [])
        if path and path.exists()
    ]
    reference_instruction = []
    if canonical_refs:
        reference_instruction.append(
            "The first labeled reference images are CANONICAL ELEMENT REFERENCES. They define who/what the recurring Elements must look like and outrank incidental drift in previous generated frames."
        )
    if has_reference:
        reference_instruction.append(
            "A PREVIOUS APPROVED CONTINUITY FRAME is also attached. Use it for pose, wardrobe state, geography and motion continuity, but do not let gradual drift override the canonical Element references."
        )
    if not reference_instruction:
        reference_instruction.append(
            "No external identity reference is available for this first shot; evaluate cardinality, anatomy, and consistency within the sampled clip."
        )
    prompt = f"""
You are Triven Cinema's strict visual continuity inspector.
The generated clip is represented by sampled frames attached after this instruction.
{' '.join(reference_instruction)}

CANONICAL ENTITY LOCKS:
{chr(10).join(lock_lines) if lock_lines else 'No structured locks available. Use the character bible and reject obvious duplicate copies of the same recurring subject.'}

EXPECTED COUNTS FOR THIS SHOT:
{exact}

CHARACTER BIBLE:
{compact_text(character_bible, 2200)}

SCENE INTENT:
{compact_text(scene_prompt, 1800)}

QC RULES:
- Count physical subjects WITHIN each individual generated frame; never add counts across different frames.
- A recurring subject must not appear as twins, mirrored physical duplicates, extra bodies, extra heads/faces, split bodies, fused people, or ghost clones.
- Do not count a normal shadow or a clearly readable reflection as another physical subject.
- For an expected count of 1, two simultaneously visible physical instances is a failure.
- If canonical Element references exist, recurring named characters/props/locations must match those references first: recognizable facial identity, age band, skin tone, hair, costume palette, body proportions, object design, or location landmarks as applicable.
- If a previous approved reference exists, recurring named characters must preserve the same recognizable facial identity, age band, skin tone, hair, costume palette, body proportions, and signature props unless the scene explicitly calls for a justified change.
- A face replacement, unexplained costume/body redesign, one named character turning into another, or strong identity drift is a failure.
- Ignore tiny unrelated background strangers unless they duplicate a locked recurring subject.
- Be conservative about ordinary motion blur, pose changes, expression changes, lighting, and camera perspective. Only flag identity drift when it is visually meaningful.

Return ONLY JSON with exactly this shape:
{{
  "passed": true,
  "duplicate_detected": false,
  "identity_drift_detected": false,
  "observed_max_counts": {{"ENTITY": 1}},
  "violations": [],
  "identity_violations": [],
  "note": "short reason",
  "confidence": 0.95,
  "skipped": false
}}
""".strip()

    with tempfile.TemporaryDirectory(prefix=".triven-qc-", dir=video_path.parent) as tmp:
        frames = extract_qc_frames(
            video_path,
            Path(tmp),
            prefix="continuity-qc",
            positions=(0.20, 0.50, 0.80)[: max(1, min(3, settings.continuity_qc_max_frames))],
        )
        if not frames:
            return _skipped("No QC frames could be extracted from the generated clip.")

        parts: list[dict] = [{"text": prompt}]
        if canonical_refs:
            parts.append({"text": "CANONICAL ELEMENT REFERENCES:"})
            for label, path in canonical_refs:
                parts.append({"text": f"CANONICAL {label}:"})
                parts.append(_image_part(path))
        if has_reference and reference_frame_path is not None:
            parts.append({"text": "PREVIOUS APPROVED CONTINUITY REFERENCE:"})
            parts.append(_image_part(reference_frame_path))
        if canonical_refs or has_reference:
            parts.append({"text": "GENERATED CLIP SAMPLES:"})
        for frame in frames:
            parts.append(_image_part(frame))

        try:
            response = generate_content(
                parts=parts,
                max_output_tokens=1400,
                timeout_seconds=settings.continuity_qc_timeout_seconds,
                thinking_level="low",
            )
            parsed = ContinuityQCResult.model_validate_json(_extract_json_text(response.payload))
        except (RuntimeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            return _skipped(f"Continuity vision QC unavailable ({str(exc)[:180]}). Prompt guard remains active.")

    # Never trust a model-produced pass if the same payload reports a hard violation.
    if (
        parsed.duplicate_detected
        or parsed.identity_drift_detected
        or parsed.violations
        or parsed.identity_violations
    ):
        parsed.passed = False
    return parsed
