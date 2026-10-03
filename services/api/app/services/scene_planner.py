import json
import re
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.schemas.generation import Scene


class SceneDraft(BaseModel):
    title: str = Field(description="Short cinematic title for the scene.")
    prompt: str = Field(
        description=(
            "Detailed generation-ready AI video prompt including subject, action, "
            "environment, camera, lighting and style."
        )
    )
    duration_seconds: int = Field(
        ge=3,
        le=10,
        description="Recommended duration of the scene.",
    )


class ScenePlannerOutput(BaseModel):
    scenes: list[SceneDraft]


@dataclass
class ScenePlanResult:
    scenes: list[Scene]
    source: str
    note: str | None = None


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _local_storyboard(prompt: str, scene_count: int) -> list[Scene]:
    """Fast deterministic fallback that never blocks the render pipeline."""
    base = _compact(prompt)
    scenes: list[Scene] = []

    shot_guidance = [
        (
            "Establishing Shot",
            "Begin with a clear establishing view that introduces the subject and environment. "
            "Use smooth cinematic movement and make the main action immediately readable.",
        ),
        (
            "Tracking Continuation",
            "Continue the same subject, appearance and environment from the previous shot. "
            "Move closer with a smooth tracking or follow shot while the action naturally progresses.",
        ),
        (
            "Detail Progression",
            "Continue the same moment with a more intimate medium or close shot. Show a meaningful "
            "detail or action beat while preserving strict visual continuity.",
        ),
        (
            "Cinematic Reveal",
            "Advance the action with a wider reveal or motivated camera move that adds scale while "
            "keeping the subject identity and environment consistent.",
        ),
        (
            "Closing Shot",
            "Finish the sequence with a visually resolved final beat and a deliberate cinematic camera move.",
        ),
    ]

    for index in range(scene_count):
        title, guidance = shot_guidance[min(index, len(shot_guidance) - 1)]
        if index >= len(shot_guidance):
            title = "Continuation Shot"
            guidance = (
                "Continue the same subject and environment with a new complementary camera angle. "
                "Progress the action naturally and preserve strict visual continuity."
            )

        scene_prompt = (
            f"{base}\n\nSHOT {index + 1} OF {scene_count}: {guidance} "
            "Maintain strict visual continuity across shots. Include subject action, environment, "
            "camera framing, camera movement, lighting and atmosphere. No subtitles, logos, text "
            "overlays or watermarks unless the original request explicitly asks for them. Do not "
            "mention output resolution."
        )
        scenes.append(
            Scene(
                id=index + 1,
                title=f"{title} {index + 1}",
                prompt=scene_prompt,
                duration_seconds=5,
            )
        )
    return scenes


def _extract_json_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    text = "".join(str(part.get("text") or "") for part in parts).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    if not text:
        raise RuntimeError("Gemini returned an empty scene plan.")
    return text


def _gemini_storyboard(prompt: str, scene_count: int, aspect_ratio: str) -> list[Scene]:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    planner_prompt = f"""
You are the cinematic scene-planning engine for Triven Cinema.

Convert the user's idea into exactly {scene_count} video-generation scenes.

ORIGINAL USER REQUEST:
{prompt}

TARGET ASPECT RATIO:
{aspect_ratio}

Return ONLY valid JSON with this exact top-level shape:
{{
  "scenes": [
    {{
      "title": "short title",
      "prompt": "generation-ready video prompt",
      "duration_seconds": 5
    }}
  ]
}}

REQUIREMENTS:
- Return exactly {scene_count} scenes.
- Each scene is one continuous shot.
- Preserve the original request and maintain visual continuity.
- Describe subject, action, environment, framing, camera movement, lighting and atmosphere.
- Prompts must be directly usable by LTX-2.5.
- Normally use 5 seconds per scene, always between 3 and 10 seconds.
- Keep each prompt below 180 words.
- No subtitles, logos, text overlays or watermarks unless requested.
- Do not mention 4K, 8K, 1080p, UHD or unsupported quality claims.
- Do not include any explanation outside the JSON object.
""".strip()

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )

    # Direct REST avoids the SDK's automatic retry loop, which previously made
    # quota errors look like an indefinitely stuck storyboard request.
    try:
        response = httpx.post(
            url,
            params={"key": settings.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": planner_prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 4096,
                },
            },
            timeout=httpx.Timeout(settings.gemini_timeout_seconds),
        )
    except httpx.TimeoutException as exc:
        raise RuntimeError("Gemini storyboard request timed out.") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("Gemini storyboard request could not be completed.") from exc

    if response.status_code != 200:
        safe_detail = ""
        try:
            error_payload = response.json().get("error") or {}
            safe_detail = str(error_payload.get("status") or error_payload.get("message") or "")
        except Exception:
            safe_detail = ""
        # Never include the request URL because it contains the API key.
        suffix = f" ({safe_detail[:180]})" if safe_detail else ""
        raise RuntimeError(f"Gemini returned HTTP {response.status_code}{suffix}")

    try:
        payload = response.json()
        raw_text = _extract_json_text(payload)
        parsed = ScenePlannerOutput.model_validate_json(raw_text)
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError("Gemini returned an invalid storyboard JSON response.") from exc

    if len(parsed.scenes) != scene_count:
        raise RuntimeError(
            f"Expected {scene_count} scenes but Gemini returned {len(parsed.scenes)}."
        )

    return [
        Scene(
            id=index + 1,
            title=_compact(scene.title)[:120] or f"Scene {index + 1}",
            prompt=_compact(scene.prompt),
            duration_seconds=scene.duration_seconds,
        )
        for index, scene in enumerate(parsed.scenes)
    ]


def create_scene_plan(
    prompt: str,
    scene_count: int,
    aspect_ratio: str = "16:9",
    *,
    force_ai: bool = False,
) -> ScenePlanResult:
    clean_prompt = _compact(prompt)

    # One scene does not need an LLM round-trip unless the caller explicitly asks
    # for prompt enhancement. This saves quota and removes 5-20 seconds of latency.
    if scene_count == 1 and not force_ai:
        return ScenePlanResult(
            scenes=_local_storyboard(clean_prompt, 1),
            source="direct",
            note="Single-scene storyboard created locally without spending a Gemini request.",
        )

    try:
        scenes = _gemini_storyboard(clean_prompt, scene_count, aspect_ratio)
        return ScenePlanResult(
            scenes=scenes,
            source="gemini",
            note="Storyboard generated by Gemini.",
        )
    except Exception as exc:  # reliability boundary: rendering must remain usable
        scenes = _local_storyboard(clean_prompt, scene_count)
        return ScenePlanResult(
            scenes=scenes,
            source="fallback",
            note=f"{str(exc)} Triven created an editable local storyboard instead.",
        )
