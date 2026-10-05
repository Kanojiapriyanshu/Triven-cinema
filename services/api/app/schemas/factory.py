from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.generation import (
    AspectRatio,
    AudioMode,
    ContinuityMode,
    DecoderName,
    RenderQuality,
    VideoModelName,
    VideoProviderName,
)
from app.schemas.youtube import YouTubePrivacy


class FactoryGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=8000)
    target_duration_seconds: float = Field(default=30.0, ge=5.0, le=300.0)
    scene_duration_seconds: float = Field(default=15.0, ge=1.0, le=30.0)
    aspect_ratio: AspectRatio = "16:9"
    quality: RenderQuality = "1080p"
    audio_mode: AudioMode = "mastered"
    audio_direction: str | None = Field(default=None, max_length=1200)
    provider: VideoProviderName = "modal"
    model: VideoModelName = "ltx-2.5"
    decoder: DecoderName = "conv"
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    continuity_mode: ContinuityMode = "strict"
    continuity_strength: float = Field(default=0.95, ge=0.0, le=1.0)
    enhance_prompt: bool = False

    publish_to_youtube: bool = False
    youtube_title: str | None = Field(default=None, max_length=100)
    youtube_description: str = Field(default="", max_length=5000)
    youtube_privacy: YouTubePrivacy = "private"
    youtube_tags: list[str] = Field(default_factory=list, max_length=30)
    youtube_category_id: str = Field(default="22", max_length=8)
    youtube_publish_at: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_factory_request(self):
        if self.scene_duration_seconds > self.target_duration_seconds:
            self.scene_duration_seconds = self.target_duration_seconds
        if self.publish_to_youtube and not (self.youtube_title or "").strip():
            # A safe title is also derived at runtime, so this is deliberately not an error.
            self.youtube_title = None
        return self


class FactoryGenerationResponse(BaseModel):
    final_video_url: str
    final_download_url: str
    final_filename: str
    target_duration_seconds: float
    actual_duration_seconds: float | None = None
    scene_count: int
    scene_duration_seconds: float
    aspect_ratio: AspectRatio
    quality: RenderQuality
    quality_note: str
    audio_mode: AudioMode
    has_audio: bool
    width: int | None = None
    height: int | None = None
    provider: str
    model: str
    gpu: str | None = None
    total_render_seconds: float
    total_wall_seconds: float
    chunk_count: int
    estimated_cost_usd: float | None = None
    estimated_cost_per_output_minute_usd: float | None = None
    cost_note: str
    planner_source: str
    planner_note: str | None = None
    continuity_id: str
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    youtube_privacy: Literal["private", "unlisted", "public"] | None = None
