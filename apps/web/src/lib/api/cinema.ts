import type {
  AsyncVideoGenerationResponse,
  CombineScenesRequest,
  CombineScenesResponse,
  FullVideoGenerationRequest,
  FullVideoGenerationResponse,
  GenerationCapabilitiesResponse,
  GenerationJobResponse,
  MetricsSummaryResponse,
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
  const controller = new AbortController();
  const timeoutMs = 25_000;
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${API_URL}/api/v1/generations/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(
        await readApiError(response, "Unable to generate scene plan.")
      );
    }
    return response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(
        "Storyboard planning exceeded 25 seconds. Triven should normally fall back automatically; retry once if the API was restarting."
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
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

export async function createVideoGenerationJob(
  payload: VideoGenerationRequest
): Promise<AsyncVideoGenerationResponse> {
  const response = await fetch(`${API_URL}/api/v1/generations/jobs/video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readApiError(response, "Unable to start generation job."));
  }
  return response.json();
}

export async function getGenerationJob(
  jobId: string
): Promise<GenerationJobResponse> {
  const response = await fetch(`${API_URL}/api/v1/generations/jobs/${jobId}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(await readApiError(response, "Unable to read generation job."));
  }
  return response.json();
}

export async function waitForVideoGenerationJob(
  jobId: string,
  onProgress?: (job: GenerationJobResponse) => void,
  pollMs = 1000
): Promise<VideoGenerationResponse> {
  for (;;) {
    const job = await getGenerationJob(jobId);
    onProgress?.(job);

    if (job.status === "completed" && job.result) {
      return job.result;
    }
    if (job.status === "failed") {
      throw new Error(job.error || "Generation job failed.");
    }

    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
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

export async function getMetricsSummary(): Promise<MetricsSummaryResponse> {
  const response = await fetch(`${API_URL}/api/v1/generations/metrics/summary`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await readApiError(response, "Unable to load render metrics."));
  }
  return response.json();
}

export function absoluteApiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_URL}${path}`;
}
