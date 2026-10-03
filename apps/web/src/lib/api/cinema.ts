import type {
  FullVideoGenerationRequest,
  FullVideoGenerationResponse,
  ScenePlanRequest,
  ScenePlanResponse,
  VideoGenerationRequest,
  VideoGenerationResponse,
} from "@/lib/types/generation";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

export async function generateScenePlan(
  payload: ScenePlanRequest
): Promise<ScenePlanResponse> {
  const response = await fetch(
    `${API_URL}/api/v1/generations/plan`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );

  if (!response.ok) {
    let message = "Unable to generate scene plan.";

    try {
      const data = await response.json();
      message = data?.detail || data?.message || message;
    } catch {}

    throw new Error(message);
  }

  return response.json();
}

export async function generateVideo(
  payload: VideoGenerationRequest
): Promise<VideoGenerationResponse> {
  const response = await fetch(
    `${API_URL}/api/v1/generations/video`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );

  if (!response.ok) {
    let message = "Unable to generate video.";

    try {
      const data = await response.json();
      message = data?.detail || data?.message || message;
    } catch {}

    throw new Error(message);
  }

  return response.json();
}

export async function generateFullVideo(
  payload: FullVideoGenerationRequest
): Promise<FullVideoGenerationResponse> {
  const response = await fetch(
    `${API_URL}/api/v1/generations/full-video`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );

  if (!response.ok) {
    let message = "Unable to generate full video.";

    try {
      const data = await response.json();
      message =
        data?.detail ||
        data?.message ||
        message;
    } catch {}

    throw new Error(message);
  }

  return response.json();
}