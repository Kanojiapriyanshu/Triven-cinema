export type AspectRatio = "16:9" | "9:16" | "1:1";

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
  decoder: "conv" | "diffusion";
}

export interface VideoGenerationResponse {
  video_url: string;
  seed: number;
  render_details: string;
  provider: string;
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
  decoder: "conv" | "diffusion";
}

export interface FullVideoGenerationResponse {
  final_video_url: string;
  scene_video_urls: string[];
  render_details: string[];
  provider: string;
}