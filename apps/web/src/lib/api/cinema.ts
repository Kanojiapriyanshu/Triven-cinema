import type {
  CombineScenesRequest,
  CombineScenesResponse,
  FullVideoGenerationRequest,
  FullVideoGenerationResponse,
  GenerationCapabilitiesResponse,
  ScenePlanRequest,
  ScenePlanResponse,
  VideoGenerationRequest,
  VideoGenerationResponse,
} from "@/lib/types/generation";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function readApiError(
  response: Response,
  fallback: string
): Promise<string> {
  try {
    const data = await response.json();
    return data?.detail || data?.message || fallback;
  } catch {
    return fallback;
  }
}

export async function getGenerationCapabilities(): Promise<GenerationCapabilitiesResponse> {
  const response = await fetch(`${API_URL}/api/v1/generations/capabilities`);
  if (!response.ok) {
    throw new Error(
      await readApiError(response, "Unable to load generation capabilities.")
    );
  }
  return response.json();
}

export async function generateScenePlan(
  payload: ScenePlanRequest
): Promise<ScenePlanResponse> {
  const response = await fetch(`${API_URL}/api/v1/generations/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readApiError(response, "Unable to generate scene plan."));
  }
  return response.json();
}

export async function generateVideo(
  payload: VideoGenerationRequest
): Promise<VideoGenerationResponse> {
  const response = await fetch(`${API_URL}/api/v1/generations/video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readApiError(response, "Unable to generate video."));
  }
  return response.json();
}

export async function combineSceneVideos(
  payload: CombineScenesRequest
): Promise<CombineScenesResponse> {
  const response = await fetch(`${API_URL}/api/v1/generations/combine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readApiError(response, "Unable to combine scene videos."));
  }
  return response.json();
}

export async function generateFullVideo(
  payload: FullVideoGenerationRequest
): Promise<FullVideoGenerationResponse> {
  const response = await fetch(`${API_URL}/api/v1/generations/full-video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readApiError(response, "Unable to generate full video."));
  }
  return response.json();
}

export function absoluteApiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_URL}${path}`;
}
