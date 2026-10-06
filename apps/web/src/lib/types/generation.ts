export type AspectRatio = "16:9" | "9:16" | "1:1";
export type RenderQuality = "preview" | "1080p" | "4k";
export type AudioMode = "native" | "mastered" | "mute";
export type VideoProviderName = "huggingface" | "modal";
export type VideoModelName = "ltx-2.5" | "wan" | "minimax";
export type DecoderName = "conv" | "diffusion";
export type ContinuityMode = "off" | "balanced" | "strict";
export type ContinuityQCMode = "off" | "auto" | "strict";
export type GenerationMode = "factory" | "storyboard" | "direct";
export type YouTubePrivacy = "private" | "unlisted" | "public";
export type JobStatusName = "queued" | "running" | "completed" | "failed";
export type JobStageName =
  | "queued"
  | "initializing"
  | "planning"
  | "rendering"
  | "composing"
  | "delivery"
  | "probing"
  | "billing"
  | "publishing"
  | "completed"
  | "failed";

export interface PlanQualityReport {
  coverage_score: number;
  covered_terms: string[];
  missing_terms: string[];
  note: string;
}

export interface EntityLock {
  label: string;
  expected_count: number;
  description: string;
}

export interface Scene {
  id: number;
  title: string;
  prompt: string;
  duration_seconds: number;
  visible_entity_counts: Record<string, number>;
}

export interface ScenePlanRequest {
  prompt: string;
  aspect_ratio: AspectRatio;
  scene_count: number;
}

export interface ScenePlanResponse {
  original_prompt: string;
  aspect_ratio: AspectRatio;
  scenes: Scene[];
  plan_quality?: PlanQualityReport | null;
  planner_source: "gemini" | "direct" | "fallback";
  planner_note?: string | null;
  continuity_id: string;
  character_bible: string;
  style_bible: string;
  entity_locks: EntityLock[];
}

export interface VideoGenerationRequest {
  prompt: string;
  aspect_ratio: AspectRatio;
  duration_seconds: number;
  seed: number;
  decoder: DecoderName;
  enhance_prompt: boolean;
  quality: RenderQuality;
  audio_mode: AudioMode;
  audio_direction?: string | null;
  provider: VideoProviderName;
  model: VideoModelName;
  continuity_mode?: ContinuityMode;
  continuity_id?: string | null;
  scene_index?: number | null;
  scene_count?: number | null;
  character_bible?: string | null;
  style_bible?: string | null;
  entity_locks?: EntityLock[];
  visible_entity_counts?: Record<string, number>;
  continuity_qc_mode?: ContinuityQCMode;
  continuity_max_retries?: number;
  reference_frame_filename?: string | null;
  continuity_strength?: number;
}

export interface MediaInfo {
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  video_codec: string | null;
  has_audio: boolean;
  audio_codec: string | null;
  audio_channels: number | null;
  format_name: string | null;
  size_bytes: number;
}

export interface VideoGenerationResponse {
  video_url: string;
  download_url: string;
  filename: string;
  seed: number;
  render_details: string;
  render_seconds: number;
  wall_seconds: number;
  provider: string;
  model: string;
  quality: RenderQuality;
  quality_note: string;
  audio_mode: AudioMode;
  chunk_count: number;
  gpu: string | null;
  media_info: MediaInfo;
  estimated_cost_usd: number | null;
  estimated_cost_per_output_minute_usd: number | null;
  cost_note: string;
  continuity_mode: ContinuityMode;
  continuity_applied: boolean;
  reference_frame_filename: string | null;
  continuity_frame_url: string | null;
  continuity_frame_filename: string | null;
  continuity_qc_passed: boolean | null;
  continuity_regenerations: number;
  continuity_warnings: string[];
}

export interface FullVideoScene {
  id: number;
  prompt: string;
  visible_entity_counts?: Record<string, number>;
}

export interface FullVideoGenerationRequest {
  scenes: FullVideoScene[];
  aspect_ratio: AspectRatio;
  duration_seconds: number;
  seed: number;
  decoder: DecoderName;
  enhance_prompt: boolean;
  quality: RenderQuality;
  audio_mode: AudioMode;
  audio_direction?: string | null;
  provider: VideoProviderName;
  model: VideoModelName;
  continuity_mode?: ContinuityMode;
  continuity_id?: string | null;
  character_bible?: string | null;
  style_bible?: string | null;
  entity_locks?: EntityLock[];
  continuity_qc_mode?: ContinuityQCMode;
  continuity_max_retries?: number;
  continuity_strength?: number;
}

export interface FullVideoGenerationResponse {
  final_video_url: string;
  final_download_url: string;
  final_filename: string;
  scene_video_urls: string[];
  render_details: string[];
  total_render_seconds: number;
  total_wall_seconds: number;
  provider: string;
  model: string;
  quality: RenderQuality;
  quality_note: string;
  audio_mode: AudioMode;
  gpu: string | null;
  media_info: MediaInfo;
  estimated_cost_usd: number | null;
  estimated_cost_per_output_minute_usd: number | null;
  cost_note: string;
}

export interface CombineScenesRequest {
  scene_video_urls: string[];
  aspect_ratio: AspectRatio;
  quality: RenderQuality;
  audio_mode: AudioMode;
}

export interface CombineScenesResponse {
  final_video_url: string;
  final_download_url: string;
  final_filename: string;
  scene_count: number;
  quality: RenderQuality;
  quality_note: string;
  audio_mode: AudioMode;
  media_info: MediaInfo;
}

export interface GenerationCapabilitiesResponse {
  providers: Array<{
    id: VideoProviderName;
    label: string;
    available: boolean;
    paid: boolean;
  }>;
  models: Array<{
    id: VideoModelName;
    label: string;
    available: boolean;
  }>;
  qualities: Array<{
    id: RenderQuality;
    label: string;
    description: string;
  }>;
  aspect_ratios: AspectRatio[];
  decoders: DecoderName[];
  continuity_modes: ContinuityMode[];
  audio_modes: AudioMode[];
  image_conditioning: boolean;
  entity_count_lock: boolean;
  continuity_vision_qc: boolean;
  max_scene_duration_seconds: number;
  max_scene_duration_seconds_by_quality: Record<RenderQuality, number>;
  native_chunk_seconds: number;
  max_factory_duration_seconds: number;
  async_jobs: boolean;
  audio_probe: boolean;
  cost_tracking_configured: boolean;
  production_mode: boolean;
  job_workers: number;
  job_max_pending: number;
}

export interface AsyncVideoGenerationResponse {
  job_id: string;
  status: JobStatusName;
  status_url: string;
}

export interface GenerationJobResponse {
  job_id: string;
  job_type: string;
  status: JobStatusName;
  stage: JobStageName;
  progress: number;
  message: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface MetricsSummaryResponse {
  total_events: number;
  total_render_seconds: number;
  total_estimated_cost_usd: number;
  average_render_seconds: number | null;
  average_estimated_cost_usd: number | null;
  by_gpu: Record<
    string,
    { count: number; render_seconds: number; estimated_cost_usd: number }
  >;
}

export interface RenderedSceneVideo {
  url: string;
  downloadUrl: string;
  filename: string;
  details: string;
  renderSeconds: number;
  wallSeconds: number;
  provider: string;
  gpu: string | null;
  mediaInfo: MediaInfo;
  estimatedCostUsd: number | null;
  qualityNote: string;
  audioMode: AudioMode;
  chunkCount: number;
  continuityMode: ContinuityMode;
  continuityApplied: boolean;
  referenceFrameFilename: string | null;
  continuityFrameUrl: string | null;
  continuityFrameFilename: string | null;
  continuityQcPassed: boolean | null;
  continuityRegenerations: number;
  continuityWarnings: string[];
}

export interface FactoryGenerationRequest {
  prompt: string;
  target_duration_seconds: number;
  scene_duration_seconds: number;
  aspect_ratio: AspectRatio;
  quality: RenderQuality;
  audio_mode: AudioMode;
  audio_direction?: string | null;
  provider: VideoProviderName;
  model: VideoModelName;
  decoder: DecoderName;
  seed: number;
  continuity_mode: ContinuityMode;
  continuity_strength: number;
  continuity_qc_mode?: ContinuityQCMode;
  continuity_max_retries?: number;
  enhance_prompt: boolean;
  publish_to_youtube: boolean;
  youtube_title?: string | null;
  youtube_description?: string;
  youtube_privacy?: YouTubePrivacy;
  youtube_tags?: string[];
  youtube_category_id?: string;
  youtube_publish_at?: string | null;
}

export interface FactoryGenerationResponse {
  final_video_url: string;
  final_download_url: string;
  final_filename: string;
  target_duration_seconds: number;
  actual_duration_seconds: number | null;
  scene_count: number;
  scene_duration_seconds: number;
  aspect_ratio: AspectRatio;
  quality: RenderQuality;
  quality_note: string;
  audio_mode: AudioMode;
  has_audio: boolean;
  width: number | null;
  height: number | null;
  provider: string;
  model: string;
  gpu: string | null;
  total_render_seconds: number;
  total_wall_seconds: number;
  chunk_count: number;
  estimated_cost_usd: number | null;
  estimated_cost_per_output_minute_usd: number | null;
  cost_note: string;
  planner_source: string;
  planner_note: string | null;
  continuity_id: string;
  entity_locks: EntityLock[];
  continuity_qc_passed: boolean | null;
  continuity_regenerations: number;
  continuity_warnings: string[];
  audio_qc_passed: boolean | null;
  audio_retake_count: number;
  audio_warnings: string[];
  youtube_video_id: string | null;
  youtube_url: string | null;
  youtube_privacy: YouTubePrivacy | null;
}

export interface BillingPack {
  id: string;
  label: string;
  credit_seconds: number;
  available: boolean;
}

export interface BillingCatalogResponse {
  enabled: boolean;
  enforce_credits: boolean;
  packs: BillingPack[];
}

export interface BillingMeResponse {
  workspace_id: string;
  enabled: boolean;
  enforce_credits: boolean;
  balance_seconds: number;
  email: string | null;
  stripe_customer_id: string | null;
}

export interface CheckoutStatusResponse {
  session_id: string;
  paid: boolean;
  balance_seconds: number;
}

export interface YouTubeStatusResponse {
  enabled: boolean;
  connected: boolean;
  channel_id: string | null;
  channel_title: string | null;
  public_uploads_allowed: boolean;
}

export interface YouTubePublishResponse {
  video_id: string;
  youtube_url: string;
  privacy: YouTubePrivacy;
  title: string;
}
