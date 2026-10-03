from typing import Literal

from pydantic import BaseModel, Field


AspectRatio = Literal["16:9", "9:16", "1:1"]
RenderQuality = Literal["preview", "1080p"]
VideoProviderName = Literal["huggingface", "modal"]
VideoModelName = Literal["ltx-2.5", "wan", "minimax"]
DecoderName = Literal["conv", "diffusion"]


class ScenePlanRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=5000)
    aspect_ratio: AspectRatio = "16:9"
    scene_count: int = Field(default=4, ge=1, le=10)


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
    prompt: str = Field(..., min_length=10, max_length=5000)
    aspect_ratio: AspectRatio = "16:9"
    duration_seconds: float = Field(default=1.0, ge=1.0, le=5.0)
    seed: int = 42
    decoder: DecoderName = "conv"
    quality: RenderQuality = "preview"
    provider: VideoProviderName | None = None
    model: VideoModelName = "ltx-2.5"


class VideoGenerationResponse(BaseModel):
    video_url: str
    download_url: str
    filename: str
    seed: int
    render_details: str
    render_seconds: float
    provider: str
    model: str
    quality: RenderQuality
    quality_note: str


class FullVideoScene(BaseModel):
    id: int
    prompt: str = Field(..., min_length=10, max_length=5000)


class FullVideoGenerationRequest(BaseModel):
    scenes: list[FullVideoScene] = Field(..., min_length=1, max_length=20)
    aspect_ratio: AspectRatio = "16:9"
    duration_seconds: float = Field(default=1.0, ge=1.0, le=5.0)
    seed: int = 42
    decoder: DecoderName = "conv"
    quality: RenderQuality = "preview"
    provider: VideoProviderName | None = None
    model: VideoModelName = "ltx-2.5"


class FullVideoGenerationResponse(BaseModel):
    final_video_url: str
    final_download_url: str
    final_filename: str
    scene_video_urls: list[str]
    render_details: list[str]
    total_render_seconds: float
    provider: str
    model: str
    quality: RenderQuality
    quality_note: str


class CombineScenesRequest(BaseModel):
    scene_video_urls: list[str] = Field(..., min_length=1, max_length=50)
    aspect_ratio: AspectRatio = "16:9"
    quality: RenderQuality = "preview"


class CombineScenesResponse(BaseModel):
    final_video_url: str
    final_download_url: str
    final_filename: str
    scene_count: int
    quality: RenderQuality
    quality_note: str


class GenerationCapabilitiesResponse(BaseModel):
    providers: list[dict]
    models: list[dict]
    qualities: list[dict]
    aspect_ratios: list[AspectRatio]
    max_scene_duration_seconds: float
