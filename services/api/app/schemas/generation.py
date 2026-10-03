from typing import Literal

from pydantic import BaseModel, Field


AspectRatio = Literal["16:9", "9:16", "1:1"]
RenderQuality = Literal["preview", "1080p"]
VideoProviderName = Literal["huggingface", "modal"]
VideoModelName = Literal["ltx-2.5", "wan", "minimax"]
DecoderName = Literal["conv", "diffusion"]
JobStatusName = Literal["queued", "running", "completed", "failed"]
JobStageName = Literal[
    "queued",
    "initializing",
    "rendering",
    "delivery",
    "probing",
    "completed",
    "failed",
]


class PlanQualityReport(BaseModel):
    coverage_score: float
    covered_terms: list[str]
    missing_terms: list[str]
    note: str


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
    plan_quality: PlanQualityReport | None = None
    planner_source: Literal["gemini", "direct", "fallback"] = "gemini"
    planner_note: str | None = None


class VideoGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=5000)
    aspect_ratio: AspectRatio = "16:9"
    duration_seconds: float = Field(default=1.0, ge=1.0, le=5.0)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    decoder: DecoderName = "conv"
    enhance_prompt: bool = False
    quality: RenderQuality = "preview"
    provider: VideoProviderName | None = None
    model: VideoModelName = "ltx-2.5"


class MediaInfo(BaseModel):
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    video_codec: str | None = None
    has_audio: bool = False
    audio_codec: str | None = None
    audio_channels: int | None = None
    format_name: str | None = None
    size_bytes: int = 0


class VideoGenerationResponse(BaseModel):
    video_url: str
    download_url: str
    filename: str
    seed: int
    render_details: str
    render_seconds: float
    wall_seconds: float
    provider: str
    model: str
    quality: RenderQuality
    quality_note: str
    gpu: str | None = None
    media_info: MediaInfo
    estimated_cost_usd: float | None = None
    estimated_cost_per_output_minute_usd: float | None = None
    cost_note: str


class FullVideoScene(BaseModel):
    id: int
    prompt: str = Field(..., min_length=10, max_length=5000)


class FullVideoGenerationRequest(BaseModel):
    scenes: list[FullVideoScene] = Field(..., min_length=1, max_length=20)
    aspect_ratio: AspectRatio = "16:9"
    duration_seconds: float = Field(default=1.0, ge=1.0, le=5.0)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    decoder: DecoderName = "conv"
    enhance_prompt: bool = False
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
    total_wall_seconds: float
    provider: str
    model: str
    quality: RenderQuality
    quality_note: str
    gpu: str | None = None
    media_info: MediaInfo
    estimated_cost_usd: float | None = None
    estimated_cost_per_output_minute_usd: float | None = None
    cost_note: str


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
    media_info: MediaInfo


class GenerationCapabilitiesResponse(BaseModel):
    providers: list[dict]
    models: list[dict]
    qualities: list[dict]
    aspect_ratios: list[AspectRatio]
    decoders: list[DecoderName]
    max_scene_duration_seconds: float
    async_jobs: bool
    audio_probe: bool
    cost_tracking_configured: bool
    production_mode: bool = False
    job_workers: int = 1
    job_max_pending: int = 3


class AsyncVideoGenerationResponse(BaseModel):
    job_id: str
    status: JobStatusName
    status_url: str


class GenerationJobResponse(BaseModel):
    job_id: str
    job_type: str
    status: JobStatusName
    stage: JobStageName
    progress: int
    message: str
    payload: dict
    result: VideoGenerationResponse | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class MetricsSummaryResponse(BaseModel):
    total_events: int
    total_render_seconds: float
    total_estimated_cost_usd: float
    average_render_seconds: float | None = None
    average_estimated_cost_usd: float | None = None
    by_gpu: dict[str, dict]
