import type {
  AsyncVideoGenerationResponse,
  BillingCatalogResponse,
  BillingMeResponse,
  CombineScenesRequest,
  CombineScenesResponse,
  FactoryGenerationRequest,
  FactoryGenerationResponse,
  FullVideoGenerationRequest,
  FullVideoGenerationResponse,
  GenerationCapabilitiesResponse,
  GenerationJobResponse,
  MetricsSummaryResponse,
  ScenePlanRequest,
  ScenePlanResponse,
  VideoGenerationRequest,
  VideoGenerationResponse,
  YouTubePublishResponse,
  YouTubeStatusResponse,
} from "@/lib/types/generation";

// Production is same-origin through host Nginx. Empty is intentional.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

const WORKSPACE_HEADER = "X-Triven-Workspace";
const WORKSPACE_STORAGE_KEY = "triven_workspace_token";
let workspaceBootstrapPromise: Promise<void> | null = null;
let workspaceBootstrapped = false;

function readWorkspaceToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(WORKSPACE_STORAGE_KEY);
}

function storeWorkspaceToken(response: Response) {
  if (typeof window === "undefined") return;
  const token = response.headers.get(WORKSPACE_HEADER);
  if (token) window.sessionStorage.setItem(WORKSPACE_STORAGE_KEY, token);
}

async function ensureWorkspaceBootstrap(): Promise<void> {
  if (typeof window === "undefined" || workspaceBootstrapped) return;
  if (!workspaceBootstrapPromise) {
    workspaceBootstrapPromise = (async () => {
      const response = await fetch(`${API_URL}/api/v1/identity/bootstrap`, {
        method: "POST",
        cache: "no-store",
        credentials: "include",
      });
      if (!response.ok) throw new Error("Unable to establish workspace session.");
      storeWorkspaceToken(response);
      workspaceBootstrapped = true;
    })().finally(() => {
      workspaceBootstrapPromise = null;
    });
  }
  await workspaceBootstrapPromise;
}

async function readApiError(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === "string") return data.detail;
    if (typeof data?.detail?.message === "string") return data.detail.message;
    if (Array.isArray(data?.detail)) {
      const messages = data.detail
        .map((item: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(item?.loc)
            ? item.loc.filter((part) => part !== "body").join(".")
            : "";
          const message = item?.msg || "Invalid value";
          return field ? `${field}: ${message}` : message;
        })
        .filter(Boolean);
      if (messages.length) return messages.join("\n");
    }
    return data?.message || fallback;
  } catch {
    return fallback;
  }
}

async function apiJson<T>(path: string, init?: RequestInit, fallback = "Request failed."): Promise<T> {
  await ensureWorkspaceBootstrap();
  const workspaceToken = readWorkspaceToken();
  const response = await fetch(`${API_URL}${path}`, {
    cache: "no-store",
    credentials: "include",
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(workspaceToken ? { [WORKSPACE_HEADER]: workspaceToken } : {}),
      ...(init?.headers || {}),
    },
  });
  storeWorkspaceToken(response);
  if (!response.ok) throw new Error(await readApiError(response, fallback));
  return response.json();
}

export async function getGenerationCapabilities(): Promise<GenerationCapabilitiesResponse> {
  return apiJson("/api/v1/generations/capabilities", undefined, "Unable to load generation capabilities.");
}

export async function generateScenePlan(payload: ScenePlanRequest): Promise<ScenePlanResponse> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 25_000);
  try {
    return await apiJson(
      "/api/v1/generations/plan",
      { method: "POST", body: JSON.stringify(payload), signal: controller.signal },
      "Unable to generate scene plan."
    );
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Storyboard planning timed out. Retry, or use Direct for a single-shot render.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function generateVideo(payload: VideoGenerationRequest): Promise<VideoGenerationResponse> {
  return apiJson(
    "/api/v1/generations/video",
    { method: "POST", body: JSON.stringify(payload) },
    "Unable to generate video."
  );
}

export async function createVideoGenerationJob(payload: VideoGenerationRequest): Promise<AsyncVideoGenerationResponse> {
  return apiJson(
    "/api/v1/generations/jobs/video",
    { method: "POST", body: JSON.stringify(payload) },
    "Unable to start generation job."
  );
}

export async function createFactoryGenerationJob(payload: FactoryGenerationRequest): Promise<AsyncVideoGenerationResponse> {
  return apiJson(
    "/api/v1/factory/jobs",
    { method: "POST", body: JSON.stringify(payload) },
    "Unable to start AI factory job."
  );
}

export async function getGenerationJob(jobId: string): Promise<GenerationJobResponse> {
  return apiJson(`/api/v1/generations/jobs/${jobId}`, undefined, "Unable to read generation job.");
}

export async function waitForJobResult<T>(
  jobId: string,
  onProgress?: (job: GenerationJobResponse) => void,
  pollMs = 1000
): Promise<T> {
  for (;;) {
    const job = await getGenerationJob(jobId);
    onProgress?.(job);
    if (job.status === "completed" && job.result) return job.result as unknown as T;
    if (job.status === "failed") throw new Error(job.error || "Generation job failed.");
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
}

export function waitForVideoGenerationJob(
  jobId: string,
  onProgress?: (job: GenerationJobResponse) => void,
  pollMs = 1000
): Promise<VideoGenerationResponse> {
  return waitForJobResult<VideoGenerationResponse>(jobId, onProgress, pollMs);
}

export function waitForFactoryGenerationJob(
  jobId: string,
  onProgress?: (job: GenerationJobResponse) => void,
  pollMs = 1200
): Promise<FactoryGenerationResponse> {
  return waitForJobResult<FactoryGenerationResponse>(jobId, onProgress, pollMs);
}

export async function combineSceneVideos(payload: CombineScenesRequest): Promise<CombineScenesResponse> {
  return apiJson(
    "/api/v1/generations/combine",
    { method: "POST", body: JSON.stringify(payload) },
    "Unable to combine scene videos."
  );
}

export async function generateFullVideo(payload: FullVideoGenerationRequest): Promise<FullVideoGenerationResponse> {
  return apiJson(
    "/api/v1/generations/full-video",
    { method: "POST", body: JSON.stringify(payload) },
    "Unable to generate full video."
  );
}

export async function getMetricsSummary(): Promise<MetricsSummaryResponse> {
  return apiJson("/api/v1/generations/metrics/summary", undefined, "Unable to load render metrics.");
}

export async function getBillingCatalog(): Promise<BillingCatalogResponse> {
  return apiJson("/api/v1/billing/catalog", undefined, "Unable to load billing options.");
}

export async function getBillingMe(): Promise<BillingMeResponse> {
  return apiJson("/api/v1/billing/me", undefined, "Unable to load credit balance.");
}

export async function createCheckout(packId: string): Promise<{ checkout_url: string; session_id: string }> {
  return apiJson(
    "/api/v1/billing/checkout",
    { method: "POST", body: JSON.stringify({ pack_id: packId }) },
    "Unable to start Stripe Checkout."
  );
}

export async function verifyCheckout(sessionId: string): Promise<{ session_id: string; paid: boolean; balance_seconds: number }> {
  return apiJson(
    `/api/v1/billing/checkout/status?session_id=${encodeURIComponent(sessionId)}`,
    undefined,
    "Unable to verify Stripe Checkout."
  );
}

export async function createBillingPortal(): Promise<{ portal_url: string }> {
  return apiJson(
    "/api/v1/billing/portal",
    { method: "POST" },
    "Unable to open billing portal."
  );
}

export async function getYouTubeStatus(): Promise<YouTubeStatusResponse> {
  return apiJson("/api/v1/youtube/status", undefined, "Unable to load YouTube connection.");
}

export async function connectYouTube(): Promise<{ authorization_url: string }> {
  return apiJson(
    "/api/v1/youtube/connect",
    { method: "POST" },
    "Unable to start YouTube connection."
  );
}

export async function disconnectYouTube(): Promise<{ disconnected: boolean }> {
  return apiJson(
    "/api/v1/youtube/connection",
    { method: "DELETE" },
    "Unable to disconnect YouTube."
  );
}

export async function publishToYouTube(payload: {
  filename: string;
  title: string;
  description?: string;
  privacy?: "private" | "unlisted" | "public";
  tags?: string[];
  category_id?: string;
  publish_at?: string | null;
}): Promise<YouTubePublishResponse> {
  return apiJson(
    "/api/v1/youtube/publish",
    { method: "POST", body: JSON.stringify(payload) },
    "Unable to upload video to YouTube."
  );
}

export function absoluteApiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_URL}${path}`;
}
