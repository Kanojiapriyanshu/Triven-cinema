from google import genai
from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.generation import Scene


class SceneDraft(BaseModel):
    title: str = Field(
        description="Short cinematic title for the scene."
    )

    prompt: str = Field(
        description=(
            "Detailed generation-ready AI video prompt including "
            "subject, action, environment, camera, lighting and style."
        )
    )

    duration_seconds: int = Field(
        ge=3,
        le=10,
        description="Recommended duration of the scene."
    )


class ScenePlannerOutput(BaseModel):
    scenes: list[SceneDraft]


def create_scene_plan(
    prompt: str,
    scene_count: int,
    aspect_ratio: str = "16:9",
) -> list[Scene]:

    if not settings.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    client = genai.Client(
        api_key=settings.gemini_api_key
    )

    planner_prompt = f"""
You are the cinematic scene-planning engine for Triven Cinema.

Convert the user's idea into exactly {scene_count}
video-generation scenes.

ORIGINAL USER REQUEST:
{prompt}

TARGET ASPECT RATIO:
{aspect_ratio}

REQUIREMENTS:

- Return exactly {scene_count} scenes.
- Each scene must represent one continuous shot.
- Maintain visual consistency between scenes.
- Maintain the same characters, clothing and environment where needed.
- Clearly describe the main subject.
- Clearly describe the action.
- Clearly describe the environment.
- Include camera framing.
- Include camera movement where appropriate.
- Include lighting and atmosphere.
- Include cinematic visual style.
- Avoid vague language.
- Avoid subtitles, text overlays, logos and watermarks unless requested.
- Each prompt must be directly usable by a video-generation model such as LTX-2.5.
- Scenes should flow naturally from one to the next.
- Normally use approximately 5 seconds per scene.
- Keep every scene prompt below 180 words.
- Do not mention output resolutions such as 4K, 8K, 1080p or UHD.
- Do not mention unsupported technical quality claims.
- Resolution, frame rate and aspect ratio are controlled separately by the renderer.
- Start with the main action, then movement, appearance, environment, camera and lighting.

Do not include explanations outside the structured output.
""".strip()

    interaction = client.interactions.create(
        model=settings.gemini_model,
        input=planner_prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": ScenePlannerOutput.model_json_schema(),
        },
    )

    if not interaction.output_text:
        raise RuntimeError(
            "Gemini returned an empty scene plan."
        )

    parsed = ScenePlannerOutput.model_validate_json(
        interaction.output_text
    )

    if len(parsed.scenes) != scene_count:
        raise RuntimeError(
            f"Expected {scene_count} scenes but Gemini returned "
            f"{len(parsed.scenes)}."
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
