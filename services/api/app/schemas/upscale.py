from typing import Literal

from pydantic import BaseModel, Field


class UpscaleRequest(BaseModel):
    """Make a sharper, larger version of an approved Draft. The picture, motion, voice and timing stay the same."""

    source_filename: str = Field(..., min_length=5, max_length=160)
    quality: Literal["1080p"] = "1080p"
    seed: int = Field(default=42, ge=0, le=2_147_483_647)


class UpscaleResponse(BaseModel):
    final_video_url: str
    final_download_url: str
    final_filename: str
    source_filename: str
    quality: Literal["1080p"] = "1080p"
    aspect_ratio: str
    quality_note: str
    has_audio: bool
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    provider: str
    gpu: str | None = None
    total_render_seconds: float
    estimated_cost_usd: float | None = None
    cost_note: str = ""
