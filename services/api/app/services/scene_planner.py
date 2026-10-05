import json
import re
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.schemas.generation import EntityLock, Scene
from app.services.continuity_service import (
    compose_continuity_prompt,
    infer_local_entity_locks,
    local_character_bible,
    local_style_bible,
)


class EntityLockDraft(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    expected_count: int = Field(default=1, ge=1, le=8)
    description: str = Field(default="", max_length=1200)


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
        le=30,
        description="Recommended duration of the scene.",
    )
    visible_entity_counts: dict[str, int] = Field(default_factory=dict)


class ScenePlannerOutput(BaseModel):
    entity_locks: list[EntityLockDraft] = Field(default_factory=list, max_length=12)
    character_bible: str = Field(
        min_length=20,
        max_length=2400,
        description="Immutable recurring-character identity specification.",
    )
    style_bible: str = Field(
        min_length=20,
        max_length=1800,
        description="Immutable visual-style specification shared by every scene.",
    )
    scenes: list[SceneDraft]


@dataclass
class ScenePlanResult:
    scenes: list[Scene]
    source: str
    character_bible: str
    style_bible: str
    entity_locks: list[EntityLock]
    note: str | None = None


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _locked_scenes(
    scenes: list[Scene],
    *,
    character_bible: str,
    style_bible: str,
    entity_locks: list[EntityLock],
) -> list[Scene]:
    count = len(scenes)
    return [
        Scene(
            id=scene.id,
            title=scene.title,
            prompt=compose_continuity_prompt(
                scene_prompt=scene.prompt,
                character_bible=character_bible,
                style_bible=style_bible,
                scene_index=index,
                scene_count=count,
                entity_locks=entity_locks,
                visible_entity_counts=scene.visible_entity_counts,
            ),
            duration_seconds=scene.duration_seconds,
            visible_entity_counts=scene.visible_entity_counts,
        )
        for index, scene in enumerate(scenes)
    ]


def _local_storyboard(
    prompt: str,
    scene_count: int,
    target_duration_seconds: int = 5,
) -> tuple[list[Scene], str, str, list[EntityLock]]:
    """Fast deterministic fallback that never blocks the render pipeline."""
    base = _compact(prompt)
    character_bible = local_character_bible(base)
    style_bible = local_style_bible(base)
    entity_locks = infer_local_entity_locks(base)
    scenes: list[Scene] = []

    shot_guidance = [
        (
            "Establishing Shot",
            "Begin with a clear establishing view that introduces the recurring subject and environment. "
            "Use smooth cinematic movement and make the main action immediately readable.",
        ),
        (
            "Tracking Continuation",
            "Continue directly from the previous shot. Move closer with a smooth tracking or follow shot "
            "while the action naturally progresses.",
        ),
        (
            "Detail Progression",
            "Continue the same moment with a more intimate medium or close shot. Show a meaningful detail "
            "or action beat without redesigning any recurring subject.",
        ),
        (
            "Cinematic Reveal",
            "Advance the action with a wider reveal or motivated camera move that adds scale while keeping "
            "the recurring subject identity and environment coherent.",
        ),
        (
            "Emotional Beat",
            "Continue the story with an emotional or interaction beat. Preserve the same characters, companion, "
            "wardrobe, proportions and visual treatment.",
        ),
        (
            "Companion Progression",
            "Continue the journey with the recurring characters sharing the frame. Use a complementary angle "
            "while maintaining strict visual identity continuity.",
        ),
        (
            "Journey Continuation",
            "Progress the action naturally through the established environment with a smooth cinematic move. "
            "Keep every recurring visual identity unchanged.",
        ),
        (
            "Pre-Finale",
            "Build toward the ending with a wider cinematic composition while preserving the exact established "
            "character and companion appearance.",
        ),
        (
            "Closing Shot",
            "Finish the sequence with a visually resolved final beat and a deliberate cinematic camera move.",
        ),
        (
            "Final Hold",
            "End on a strong final composition that resolves the story while preserving the established identity "
            "and visual language exactly.",
        ),
    ]

    for index in range(scene_count):
        title, guidance = shot_guidance[min(index, len(shot_guidance) - 1)]
        scene_prompt = (
            f"{base}\n\nSHOT {index + 1} OF {scene_count}: {guidance} "
            "Describe subject action, environment, camera framing, camera movement, lighting and atmosphere. "
            "Include a concise synchronized AUDIO DIRECTION for ambience and Foley that belong to the visible action; "
            "only include dialogue, narration or music when the original request asks for it. "
            "No subtitles, logos, text overlays or watermarks unless the original request explicitly asks for them. "
            "Do not mention output resolution."
        )
        scenes.append(
            Scene(
                id=index + 1,
                title=f"{title} {index + 1}",
                prompt=scene_prompt,
                duration_seconds=max(3, min(30, int(target_duration_seconds))),
                visible_entity_counts={},
            )
        )

    return (
        _locked_scenes(
            scenes,
            character_bible=character_bible,
            style_bible=style_bible,
            entity_locks=entity_locks,
        ),
        character_bible,
        style_bible,
        entity_locks,
    )


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


def _gemini_storyboard(
    prompt: str,
    scene_count: int,
    aspect_ratio: str,
    target_duration_seconds: int = 5,
) -> tuple[list[Scene], str, str, list[EntityLock]]:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    planner_prompt = f"""
You are the cinematic continuity and scene-planning engine for Triven Cinema.

Convert the user's idea into exactly {scene_count} video-generation scenes. The shots will be rendered
separately by LTX-2.5, so you MUST establish one immutable identity specification and one immutable
visual-style specification before writing the individual shots.

ORIGINAL USER REQUEST:
{prompt}

TARGET ASPECT RATIO:
{aspect_ratio}

Return ONLY valid JSON with this exact top-level shape:
{{
  "entity_locks": [{{"label": "ADVENTURER", "expected_count": 1, "description": "canonical recurring subject"}}],
  "character_bible": "one explicit immutable description of every recurring human/creature",
  "style_bible": "one explicit immutable visual/style description shared by the whole film",
  "scenes": [
    {{
      "title": "short title",
      "prompt": "scene-specific generation-ready video prompt",
      "duration_seconds": 5,
      "visible_entity_counts": {{"ADVENTURER": 1}}
    }}
  ]
}}

ENTITY/CARDINALITY RULES:
- Create one stable UPPERCASE label for every recurring physical subject.
- expected_count is the canonical number of physical instances allowed in the story; default to 1 unless the user explicitly requests multiples.
- Every scene must include visible_entity_counts for recurring entities that are actually visible in that shot. Use 0 only when the entity is intentionally absent.
- Never increase a visible count just because a character is named again. A recurring subject already on screen is the same physical instance.
- Do not treat shadows or reflections as additional physical instances.

CHARACTER BIBLE RULES:
- Write the recurring subject identity ONCE, with stable labels such as ADVENTURER and FOX when relevant.
- For each recurring human, explicitly lock apparent age, face shape/structure, skin tone, eye color, hair color,
  hairstyle, build/body proportions, wardrobe pieces and colors, footwear and recurring accessories.
- For each recurring animal/creature, explicitly lock species, size/proportions, fur/skin colors, markings,
  eye color and distinctive features.
- If the user did not specify a visual trait needed for continuity, choose one reasonable trait ONCE and lock it.
- Never describe camera action or a temporary pose in the character bible.
- Never change a locked trait later in the storyboard.

STYLE BIBLE RULES:
- Lock the visual medium (for example feature-animation vs photorealistic), rendering treatment, palette,
  material/skin/fur treatment, lens language, lighting logic and atmosphere.
- Preserve the user's requested style. Do not silently switch between animated and photorealistic treatment.

SCENE RULES:
- Return exactly {scene_count} scenes.
- Each scene is one continuous shot and should progress the story rather than restating the full story.
- For scene 2 onward, write the action as a continuation of the existing recurring subjects, not as a new introduction or re-entry, unless the story explicitly introduces a new entity at that moment.
- Never use wording that can imply a second copy such as "another ADVENTURER", "a new FOX", or re-describing the same subject as if it just appeared.
- Refer to recurring subjects using the exact labels established by the character bible.
- Do NOT invent a different face, hair, wardrobe, body build, companion design or color palette per scene.
- Describe only the scene-specific action, environment state, framing, camera movement, expression and lighting change.
- Every scene prompt must include an AUDIO DIRECTION sentence for synchronized ambience/Foley that matches visible action.
- Add spoken dialogue, narration or music only when the original user request asks for it; never invent speech.
- Keep the audio world continuous across cuts unless the story intentionally changes location.
- Prompts must be directly usable by LTX-2.5.
- Pace each shot for about {target_duration_seconds} seconds, always between 3 and 30 seconds.
- Longer 15-30 second shots need multiple meaningful action beats and sustained camera motion; do not describe a five-second action and then leave dead time.
- Keep each scene-specific prompt below 180 words.
- No subtitles, logos, text overlays or watermarks unless requested.
- Do not mention 4K, 8K, 1080p, UHD or unsupported quality claims.
- Do not include any explanation outside the JSON object.
""".strip()

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )

    try:
        response = httpx.post(
            url,
            params={"key": settings.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": planner_prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 6144,
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

    character_bible = _compact(parsed.character_bible)[:2400]
    style_bible = _compact(parsed.style_bible)[:1800]
    entity_locks = [
        EntityLock(
            label=_compact(lock.label).upper()[:64],
            expected_count=lock.expected_count,
            description=_compact(lock.description)[:1200],
        )
        for lock in parsed.entity_locks
    ]
    scenes = [
        Scene(
            id=index + 1,
            title=_compact(scene.title)[:120] or f"Scene {index + 1}",
            prompt=_compact(scene.prompt),
            duration_seconds=scene.duration_seconds,
            visible_entity_counts={str(k).upper(): max(0, min(8, int(v))) for k, v in scene.visible_entity_counts.items()},
        )
        for index, scene in enumerate(parsed.scenes)
    ]
    return (
        _locked_scenes(
            scenes,
            character_bible=character_bible,
            style_bible=style_bible,
            entity_locks=entity_locks,
        ),
        character_bible,
        style_bible,
        entity_locks,
    )


def create_scene_plan(
    prompt: str,
    scene_count: int,
    aspect_ratio: str = "16:9",
    *,
    force_ai: bool = False,
    target_scene_duration_seconds: float | None = None,
) -> ScenePlanResult:
    clean_prompt = _compact(prompt)
    target_duration = max(3, min(30, int(round(target_scene_duration_seconds or 5))))

    # One scene does not need an LLM round-trip unless the caller explicitly asks
    # for prompt enhancement. Identity/style locks are still created locally so
    # the same API contract works for one- and multi-scene storyboards.
    if scene_count == 1 and not force_ai:
        scenes, character_bible, style_bible, entity_locks = _local_storyboard(
            clean_prompt, 1, target_duration_seconds=target_duration
        )
        return ScenePlanResult(
            scenes=scenes,
            source="direct",
            character_bible=character_bible,
            style_bible=style_bible,
            entity_locks=entity_locks,
            note="Single-scene storyboard created locally without spending a Gemini request.",
        )

    try:
        scenes, character_bible, style_bible, entity_locks = _gemini_storyboard(
            clean_prompt,
            scene_count,
            aspect_ratio,
            target_duration_seconds=target_duration,
        )
        return ScenePlanResult(
            scenes=scenes,
            source="gemini",
            character_bible=character_bible,
            style_bible=style_bible,
            entity_locks=entity_locks,
            note="Storyboard generated by Gemini with shared identity, entity-count and style locks.",
        )
    except Exception as exc:  # reliability boundary: rendering must remain usable
        scenes, character_bible, style_bible, entity_locks = _local_storyboard(
            clean_prompt, scene_count, target_duration_seconds=target_duration
        )
        return ScenePlanResult(
            scenes=scenes,
            source="fallback",
            character_bible=character_bible,
            style_bible=style_bible,
            entity_locks=entity_locks,
            note=f"{str(exc)} Triven created an editable continuity-locked local storyboard instead.",
        )
