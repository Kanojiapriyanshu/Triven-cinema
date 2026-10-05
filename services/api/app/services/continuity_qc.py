import base64
import json
import tempfile
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.schemas.generation import EntityLock
from app.services.continuity_service import compact_text, normalize_entity_locks
from app.services.video_combiner import extract_qc_frames


class ContinuityQCResult(BaseModel):
    passed: bool = True
    duplicate_detected: bool = False
    observed_max_counts: dict[str, int] = Field(default_factory=dict)
    violations: list[str] = Field(default_factory=list)
    note: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    skipped: bool = False


def _extract_json_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini continuity QC returned no candidates.")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    text = "".join(str(part.get("text") or "") for part in parts).strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    if not text:
        raise RuntimeError("Gemini continuity QC returned an empty response.")
    return text


def _skipped(note: str) -> ContinuityQCResult:
    return ContinuityQCResult(passed=True, skipped=True, note=note, confidence=0.0)


def evaluate_scene_cardinality(
    video_path: Path,
    *,
    entity_locks: list[EntityLock] | list[dict] | None,
    visible_entity_counts: dict[str, int] | None,
    character_bible: str | None,
    scene_prompt: str,
    qc_mode: str = "auto",
) -> ContinuityQCResult:
    """Inspect representative frames for obvious duplicate recurring subjects.

    This is a quality-control gate, not an identity recognition system. It is
    intentionally conservative: fail only when the sampled frames show a clear
    extra physical instance or an obvious clone of a recurring subject.
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

    prompt = f"""
You are Triven Cinema's continuity/cardinality quality-control inspector.
The attached images are THREE SAMPLED FRAMES FROM THE SAME GENERATED VIDEO CLIP.
Judge physical subject count WITHIN EACH INDIVIDUAL FRAME. Do not count the same subject across different frames as multiple.

CANONICAL ENTITY LOCKS:
{chr(10).join(lock_lines) if lock_lines else 'No structured locks available. Use the character bible and reject obvious duplicate copies of the same recurring subject.'}

EXPECTED COUNTS FOR THIS SHOT:
{exact}

CHARACTER BIBLE:
{compact_text(character_bible, 2200)}

SCENE INTENT:
{compact_text(scene_prompt, 1800)}

QC RULES:
- A recurring physical subject must not appear as two copies, twins, mirrored physical duplicates, extra bodies, extra heads/faces, or a ghost clone.
- Do NOT count a normal shadow as another subject.
- Do NOT count a clearly readable mirror/window reflection as another physical instance.
- If a reflection visually looks like an unexplained second physical character and is ambiguous, flag it.
- For an entity with expected/visible count 1, two simultaneously visible physical instances is a failure.
- Ignore tiny background strangers unless they are a look-alike duplicate of the locked recurring subject.
- Be conservative: only fail when the duplicate/cardinality problem is visually clear.

Return ONLY JSON with exactly this shape:
{{
  "passed": true,
  "duplicate_detected": false,
  "observed_max_counts": {{"ENTITY": 1}},
  "violations": [],
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
        for frame in frames:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": base64.b64encode(frame.read_bytes()).decode("ascii"),
                    }
                }
            )

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_model}:generateContent"
        )
        try:
            response = httpx.post(
                url,
                params={"key": settings.gemini_api_key},
                json={
                    "contents": [{"parts": parts}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "maxOutputTokens": 1200,
                    },
                },
                timeout=httpx.Timeout(settings.continuity_qc_timeout_seconds),
            )
            if response.status_code != 200:
                return _skipped(f"Continuity vision QC returned HTTP {response.status_code}; prompt guard remains active.")
            parsed = ContinuityQCResult.model_validate_json(_extract_json_text(response.json()))
        except (httpx.HTTPError, RuntimeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            return _skipped(f"Continuity vision QC unavailable ({str(exc)[:180]}). Prompt guard remains active.")

    # Never trust a model-produced pass when it simultaneously reports a duplicate.
    if parsed.duplicate_detected or parsed.violations:
        parsed.passed = False
    return parsed
