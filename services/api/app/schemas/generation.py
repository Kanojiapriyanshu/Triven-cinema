from typing import Literal

from pydantic import BaseModel, Field


AspectRatio = Literal["16:9", "9:16", "1:1"]


class ScenePlanRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=3,
        max_length=5000,
    )

    aspect_ratio: AspectRatio = "16:9"

    scene_count: int = Field(
        default=4,
        ge=1,
        le=10,
    )


class Scene(BaseModel):
    id: int
    title: str
    prompt: str
    duration_seconds: int


class ScenePlanResponse(BaseModel):
    original_prompt: str
    aspect_ratio: AspectRatio
    scenes: list[Scene]


class VideoGenerationRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=10,
        max_length=5000,
    )

    aspect_ratio: AspectRatio = "16:9"

    duration_seconds: float = Field(
        default=1.0,
        ge=1.0,
        le=5.0,
    )

    seed: int = 42

    decoder: Literal[
        "conv",
        "diffusion",
    ] = "conv"


class VideoGenerationResponse(BaseModel):
    video_url: str
    seed: int
    render_details: str
    provider: str

class FullVideoScene(BaseModel):
    id: int
    prompt: str = Field(
        ...,
        min_length=10,
        max_length=5000,
    )


class FullVideoGenerationRequest(BaseModel):
    scenes: list[FullVideoScene]

    aspect_ratio: AspectRatio = "16:9"

    duration_seconds: float = Field(
        default=1.0,
        ge=1.0,
        le=5.0,
    )

    seed: int = 42

    decoder: Literal[
        "conv",
        "diffusion",
    ] = "conv"


class FullVideoGenerationResponse(BaseModel):
    final_video_url: str
    scene_video_urls: list[str]
    render_details: list[str]
    provider: str