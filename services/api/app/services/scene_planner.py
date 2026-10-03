from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field

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


@dataclass(frozen=True)
class ScenePlanResult:
    scenes: list[Scene]
    source: str
    note: str | None = None


_FALLBACK_BEATS = [
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
        "Detail and Motion",
        "Preserve continuity, then emphasize a meaningful visual detail or movement with a medium-close shot. "
        "Keep the action natural and cinematic rather than static.",
    ),
    (
        "Alternate Perspective",
        "Continue the same moment from a complementary cinematic angle while preserving character, wardrobe, "
        "lighting and environment continuity.",
    ),
    (
        "Hero Moment",
        "Build toward the strongest visual moment of the sequence with confident camera movement and clear subject focus. "
        "Keep the visual style consistent with all previous shots.",
    ),
    (
        "Resolution Shot",
        "Finish the sequence with a visually satisfying continuation or reveal. Maintain the same subject, setting, "
        "lighting and cinematic style, and end on a clean composition.",
    ),
]


def _single_scene(prompt: str) -> list[Scene]:
    return [
        Scene(
            id=1,
            title="Single Shot",
            prompt=prompt.strip(),
            duration_seconds=5,
        )
    ]


def _fallback_scene_plan(prompt: str, scene_count: int) -> list[Scene]:
    if scene_count == 1:
        return _single_scene(prompt)

    scenes: list[Scene] = []
    clean_prompt = prompt.strip()
    for index in range(scene_count):
        title, beat = _FALLBACK_BEATS[index % len(_FALLBACK_BEATS)]
        scene_prompt = (
            f"{clean_prompt}\n\n"
            f"SHOT {index + 1} OF {scene_count}: {beat} "
            "Maintain strict visual continuity across shots. Include subject action, environment, camera framing, "
            "camera movement, lighting and atmosphere. No subtitles, logos, text overlays or watermarks unless the "
            "original request explicitly asks for them. Do not mention output resolution."
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


def _planner_prompt(prompt: str, scene_count: int, aspect_ratio: str) -> str:
    return f"""
You are the cinematic scene-planning engine for Triven Cinema.

Convert the user's idea into exactly {scene_count} video-generation scenes.

ORIGINAL USER REQUEST:
{prompt}

TARGET ASPECT RATIO:
{aspect_ratio}

REQUIREMENTS:
- Return exactly {scene_count} scenes.
- Each scene must represent one continuous shot.
- Maintain visual consistency between scenes.
- Maintain the same characters, clothing and environment where needed.
- Clearly describe the main subject, action and environment.
- Include camera framing and camera movement where appropriate.
- Include lighting, atmosphere and cinematic visual style.
- Avoid vague language.
- Avoid subtitles, text overlays, logos and watermarks unless requested.
- Each prompt must be directly usable by a video-generation model such as LTX-2.5.
- Scenes should flow naturally from one to the next.
- Normally use approximately 5 seconds per scene.
- Keep every scene prompt below 180 words.
- Do not mention output resolutions such as 4K, 8K, 1080p or UHD.
- Resolution, frame rate and aspect ratio are controlled separately by the renderer.
- Start with the main action, then movement, appearance, environment, camera and lighting.

Return JSON only and follow the supplied schema exactly.
""".strip()


def _response_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")

    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    text = "".join(str(part.get("text") or "") for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned an empty scene plan.")
    return text


def _generate_with_gemini(
    prompt: str,
    scene_count: int,
    aspect_ratio: str,
) -> list[Scene]:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    request_body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": _planner_prompt(
                            prompt=prompt,
                            scene_count=scene_count,
                            aspect_ratio=aspect_ratio,
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": min(8192, max(1200, scene_count * 900)),
            "thinkingConfig": {
                "thinkingLevel": settings.gemini_thinking_level,
            },
            "responseMimeType": "application/json",
            "responseSchema": ScenePlannerOutput.model_json_schema(),
        },
    }

    timeout = httpx.Timeout(
        timeout=settings.gemini_timeout_seconds,
        connect=min(5.0, settings.gemini_timeout_seconds),
    )
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            url,
            headers={
                "x-goog-api-key": settings.gemini_api_key,
                "Content-Type": "application/json",
            },
            json=request_body,
        )
        response.raise_for_status()
        payload = response.json()

    parsed = ScenePlannerOutput.model_validate_json(_response_text(payload))
    if len(parsed.scenes) != scene_count:
        raise RuntimeError(
            f"Expected {scene_count} scenes but Gemini returned {len(parsed.scenes)}."
        )

    return [
        Scene(
            id=index + 1,
            title=scene.title,
            prompt=scene.prompt,
            duration_seconds=scene.duration_seconds,
        )
        for index, scene in enumerate(parsed.scenes)
    ]


def create_scene_plan_with_meta(
    prompt: str,
    scene_count: int,
    aspect_ratio: str = "16:9",
    *,
    force_ai: bool = False,
) -> ScenePlanResult:
    # A one-shot storyboard does not need an LLM round-trip unless the user
    # explicitly asked Triven to enhance a direct prompt.
    if scene_count == 1 and not force_ai:
        return ScenePlanResult(
            scenes=_single_scene(prompt),
            source="direct",
            note="Single-scene storyboard used the original prompt directly, so no Gemini quota or latency was needed.",
        )

    try:
        scenes = _generate_with_gemini(
            prompt=prompt,
            scene_count=scene_count,
            aspect_ratio=aspect_ratio,
        )
        return ScenePlanResult(
            scenes=scenes,
            source="gemini",
            note=None,
        )
    except httpx.TimeoutException:
        return ScenePlanResult(
            scenes=_fallback_scene_plan(prompt, scene_count),
            source="fallback",
            note=(
                f"Gemini exceeded the {settings.gemini_timeout_seconds:.0f}s planning limit, "
                "so Triven created an editable local storyboard instead."
            ),
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 429:
            note = "Gemini quota/rate limit was reached, so Triven created an editable local storyboard instead."
        else:
            note = f"Gemini returned HTTP {status}, so Triven created an editable local storyboard instead."
        return ScenePlanResult(
            scenes=_fallback_scene_plan(prompt, scene_count),
            source="fallback",
            note=note,
        )
    except Exception as exc:
        return ScenePlanResult(
            scenes=_fallback_scene_plan(prompt, scene_count),
            source="fallback",
            note=f"Gemini planning was unavailable ({type(exc).__name__}); Triven created an editable local storyboard instead.",
        )


def create_scene_plan(
    prompt: str,
    scene_count: int,
    aspect_ratio: str = "16:9",
    *,
    force_ai: bool = False,
) -> list[Scene]:
    return create_scene_plan_with_meta(
        prompt=prompt,
        scene_count=scene_count,
        aspect_ratio=aspect_ratio,
        force_ai=force_ai,
    ).scenes
