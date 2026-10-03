export type AspectRatio = "16:9" | "9:16" | "1:1";
export type RenderQuality = "preview" | "1080p";
export type VideoProviderName = "huggingface" | "modal";
export type VideoModelName = "ltx-2.5" | "wan" | "minimax";
export type DecoderName = "conv" | "diffusion";
export type GenerationMode = "storyboard" | "direct";

export interface Scene {
  id: number;
  title: string;
  prompt: string;
  duration_seconds: number;
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
}

export interface VideoGenerationRequest {
  prompt: string;
  aspect_ratio: AspectRatio;
  duration_seconds: number;
  seed: number;
  decoder: DecoderName;
  quality: RenderQuality;
  provider: VideoProviderName;
  model: VideoModelName;
}

export interface VideoGenerationResponse {
  video_url: string;
  download_url: string;
  filename: string;
  seed: number;
  render_details: string;
  render_seconds: number;
  provider: string;
  model: string;
  quality: RenderQuality;
  quality_note: string;
}

export interface FullVideoScene {
  id: number;
  prompt: string;
}

export interface FullVideoGenerationRequest {
  scenes: FullVideoScene[];
  aspect_ratio: AspectRatio;
  duration_seconds: number;
  seed: number;
  decoder: DecoderName;
  quality: RenderQuality;
  provider: VideoProviderName;
  model: VideoModelName;
}

export interface FullVideoGenerationResponse {
  final_video_url: string;
  final_download_url: string;
  final_filename: string;
  scene_video_urls: string[];
  render_details: string[];
  total_render_seconds: number;
  provider: string;
  model: string;
  quality: RenderQuality;
  quality_note: string;
}

export interface CombineScenesRequest {
  scene_video_urls: string[];
  aspect_ratio: AspectRatio;
  quality: RenderQuality;
}

export interface CombineScenesResponse {
  final_video_url: string;
  final_download_url: string;
  final_filename: string;
  scene_count: number;
  quality: RenderQuality;
  quality_note: string;
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
  max_scene_duration_seconds: number;
}

export interface RenderedSceneVideo {
  url: string;
  downloadUrl: string;
  filename: string;
  details: string;
  renderSeconds: number;
  provider: string;
  qualityNote: string;
}
