"use client";

import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  absoluteApiUrl,
  combineSceneVideos,
  connectYouTube,
  createBillingPortal,
  createCheckout,
  createFactoryGenerationJob,
  createVideoGenerationJob,
  disconnectYouTube,
  generateScenePlan,
  getBillingCatalog,
  getBillingMe,
  getGenerationCapabilities,
  getYouTubeStatus,
  verifyCheckout,
  waitForFactoryGenerationJob,
  waitForVideoGenerationJob,
} from "@/lib/api/cinema";
import type {
  AspectRatio,
  AudioMode,
  BillingCatalogResponse,
  BillingMeResponse,
  ContinuityMode,
  DecoderName,
  FactoryGenerationResponse,
  GenerationCapabilitiesResponse,
  GenerationMode,
  RenderedSceneVideo,
  RenderQuality,
  ScenePlanResponse,
  VideoModelName,
  VideoProviderName,
  YouTubePrivacy,
  YouTubeStatusResponse,
} from "@/lib/types/generation";

type ScenePromptMap = Record<number, string>;
type RenderedVideoMap = Record<number, RenderedSceneVideo>;
type ThemeMode = "light" | "dark";

type FinalVideo = {
  url: string;
  downloadUrl: string;
  filename: string;
  qualityNote: string;
  label: string;
  hasAudio: boolean;
  audioCodec: string | null;
  dimensions: string;
  estimatedCostUsd?: number | null;
  gpu?: string | null;
  youtubeUrl?: string | null;
  youtubePrivacy?: string | null;
} | null;

const DURATION_OPTIONS: Record<RenderQuality, number[]> = {
  preview: [1, 3, 5, 10],
  "1080p": [5, 10, 15, 20, 30],
  "4k": [5, 10, 15],
};

const FACTORY_TARGETS = [30, 60, 120, 180, 300];

function Spinner() {
  return <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" />;
}

function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <path d="M8 6.5 18 12 8 17.5Z" fill="currentColor" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
      <path d="M12 4v11m0 0-4-4m4 4 4-4M5 20h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5" aria-hidden="true">
      <circle cx="12" cy="12" r="3.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 2.5v2M12 19.5v2M4.5 12h-2M21.5 12h-2M5.28 5.28l1.42 1.42M17.3 17.3l1.42 1.42M18.72 5.28 17.3 6.7M6.7 17.3l-1.42 1.42" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5" aria-hidden="true">
      <path d="M20 15.1A8.2 8.2 0 0 1 8.9 4a8.2 8.2 0 1 0 11.1 11.1Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function aspectClass(aspectRatio: AspectRatio) {
  if (aspectRatio === "9:16") return "aspect-[9/16]";
  if (aspectRatio === "1:1") return "aspect-square";
  return "aspect-video";
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function formatCredits(seconds: number) {
  if (seconds >= 60) return `${(seconds / 60).toFixed(seconds % 60 === 0 ? 0 : 1)} min`;
  return `${seconds}s`;
}

function qualityLabel(quality: RenderQuality) {
  if (quality === "4k") return "4K master";
  if (quality === "1080p") return "1080p master";
  return "Source preview";
}

export default function Home() {
  const [theme, setTheme] = useState<ThemeMode>("light");
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<GenerationMode>("factory");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("16:9");
  const [sceneCount, setSceneCount] = useState(2);
  const [durationSeconds, setDurationSeconds] = useState(15);
  const [factoryTargetSeconds, setFactoryTargetSeconds] = useState(30);
  const [factorySceneSeconds, setFactorySceneSeconds] = useState(10);
  const [quality, setQuality] = useState<RenderQuality>("1080p");
  const [audioMode, setAudioMode] = useState<AudioMode>("mastered");
  const [audioDirection, setAudioDirection] = useState("Natural synchronized ambience and Foley matching every visible action.");
  const [provider, setProvider] = useState<VideoProviderName>("modal");
  const [model, setModel] = useState<VideoModelName>("ltx-2.5");
  const [decoder, setDecoder] = useState<DecoderName>("conv");
  const [seed, setSeed] = useState(42);
  const [enhancePrompt, setEnhancePrompt] = useState(false);
  const [continuityMode, setContinuityMode] = useState<ContinuityMode>("strict");

  const [publishToYouTube, setPublishToYouTube] = useState(false);
  const [youtubeTitle, setYoutubeTitle] = useState("");
  const [youtubeDescription, setYoutubeDescription] = useState("");
  const [youtubePrivacy, setYoutubePrivacy] = useState<YouTubePrivacy>("private");

  const [capabilities, setCapabilities] = useState<GenerationCapabilitiesResponse | null>(null);
  const [billingCatalog, setBillingCatalog] = useState<BillingCatalogResponse | null>(null);
  const [billingMe, setBillingMe] = useState<BillingMeResponse | null>(null);
  const [youtube, setYoutube] = useState<YouTubeStatusResponse | null>(null);

  const [result, setResult] = useState<ScenePlanResponse | null>(null);
  const [scenePrompts, setScenePrompts] = useState<ScenePromptMap>({});
  const [renderedVideos, setRenderedVideos] = useState<RenderedVideoMap>({});
  const [factoryResult, setFactoryResult] = useState<FactoryGenerationResponse | null>(null);
  const [finalVideo, setFinalVideo] = useState<FinalVideo>(null);

  const [editingScene, setEditingScene] = useState<number | null>(null);
  const [planning, setPlanning] = useState(false);
  const [directGenerating, setDirectGenerating] = useState(false);
  const [factoryGenerating, setFactoryGenerating] = useState(false);
  const [generatingScene, setGeneratingScene] = useState<number | null>(null);
  const [creatingFinal, setCreatingFinal] = useState(false);
  const [integrationBusy, setIntegrationBusy] = useState(false);
  const [progressMessage, setProgressMessage] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const durationOptions = DURATION_OPTIONS[quality];
  const factoryDurationOptions = quality === "preview"
    ? durationOptions
    : durationOptions.filter((value) => value <= 10);
  const isBusy = planning || directGenerating || factoryGenerating || generatingScene !== null || creatingFinal;
  const renderedSceneCount = Object.keys(renderedVideos).length;
  const allScenesRendered = !!result && result.scenes.length > 0 && result.scenes.every((scene) => Boolean(renderedVideos[scene.id]));
  const plannedDuration = useMemo(() => result ? result.scenes.length * durationSeconds : 0, [result, durationSeconds]);

  useEffect(() => {
    const storedTheme = window.localStorage.getItem("triven-cinema-theme");
    const initialTheme: ThemeMode = storedTheme === "dark" ? "dark" : "light";
    setTheme(initialTheme);
    document.documentElement.dataset.theme = initialTheme;
  }, []);

  function selectTheme(nextTheme: ThemeMode) {
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
    window.localStorage.setItem("triven-cinema-theme", nextTheme);
  }

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      const [caps, catalog, billing, yt] = await Promise.allSettled([
        getGenerationCapabilities(),
        getBillingCatalog(),
        getBillingMe(),
        getYouTubeStatus(),
      ]);
      if (!active) return;
      if (caps.status === "fulfilled") setCapabilities(caps.value);
      if (catalog.status === "fulfilled") setBillingCatalog(catalog.value);
      if (billing.status === "fulfilled") setBillingMe(billing.value);
      if (yt.status === "fulfilled") setYoutube(yt.value);
    }
    void bootstrap();

    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id");
    if (params.get("checkout") === "success" && sessionId) {
      void verifyCheckout(sessionId)
        .then(async (status) => {
          if (!active) return;
          setNotice(status.paid ? `Payment confirmed. ${formatCredits(status.balance_seconds)} generation credits available.` : "Payment is still processing.");
          setBillingMe(await getBillingMe());
        })
        .catch((err) => active && setError(errorMessage(err, "Unable to verify payment.")));
    }
    if (params.get("youtube") === "connected") {
      setNotice("YouTube channel connected. Factory jobs can now publish automatically.");
      void getYouTubeStatus().then((status) => active && setYoutube(status)).catch(() => undefined);
    }
    if (params.has("checkout") || params.has("youtube")) {
      window.history.replaceState({}, "", window.location.pathname);
    }
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const options = DURATION_OPTIONS[quality];
    const factoryOptions = quality === "preview" ? options : options.filter((value) => value <= 10);
    if (!options.includes(durationSeconds)) setDurationSeconds(options[Math.min(2, options.length - 1)]);
    if (!factoryOptions.includes(factorySceneSeconds)) setFactorySceneSeconds(factoryOptions[factoryOptions.length - 1]);
  }, [quality, durationSeconds, factorySceneSeconds]);

  function resetOutput() {
    setResult(null);
    setScenePrompts({});
    setRenderedVideos({});
    setFactoryResult(null);
    setFinalVideo(null);
    setEditingScene(null);
    setProgressMessage("");
  }

  function invalidateRenderedMedia() {
    setRenderedVideos({});
    setFinalVideo(null);
  }

  async function refreshBilling() {
    try { setBillingMe(await getBillingMe()); } catch { /* optional integration */ }
  }

  async function generateThroughJob(payload: Parameters<typeof createVideoGenerationJob>[0]) {
    const started = await createVideoGenerationJob(payload);
    return waitForVideoGenerationJob(started.job_id, (job) => setProgressMessage(`${job.message} ${job.progress}%`));
  }

  function finalFromSceneResponse(response: Awaited<ReturnType<typeof generateThroughJob>>): FinalVideo {
    return {
      url: absoluteApiUrl(response.video_url),
      downloadUrl: absoluteApiUrl(response.download_url),
      filename: response.filename,
      qualityNote: response.quality_note,
      label: `${response.provider} · ${response.chunk_count} LTX chunk${response.chunk_count === 1 ? "" : "s"} · ${response.render_seconds.toFixed(1)}s render`,
      hasAudio: response.media_info.has_audio,
      audioCodec: response.media_info.audio_codec,
      dimensions: `${response.media_info.width ?? "?"}×${response.media_info.height ?? "?"}`,
      estimatedCostUsd: response.estimated_cost_usd,
      gpu: response.gpu,
    };
  }

  async function handleFactory(cleanPrompt: string) {
    if (publishToYouTube && (!youtube?.enabled || !youtube.connected)) {
      throw new Error("Connect a YouTube channel before enabling automatic publishing.");
    }
    setFactoryGenerating(true);
    setProgressMessage(enhancePrompt ? "Starting AI-enhanced video factory..." : "Starting direct story sequencing (no Gemini rewrite)...");
    try {
      const started = await createFactoryGenerationJob({
        prompt: cleanPrompt,
        target_duration_seconds: factoryTargetSeconds,
        scene_duration_seconds: factorySceneSeconds,
        aspect_ratio: aspectRatio,
        quality,
        audio_mode: audioMode,
        audio_direction: audioDirection.trim() || null,
        provider,
        model,
        decoder,
        seed,
        continuity_mode: continuityMode,
        continuity_strength: 0.85,
        continuity_qc_mode: enhancePrompt && quality !== "preview" ? "strict" : "auto",
        continuity_max_retries: 1,
        enhance_prompt: enhancePrompt,
        publish_to_youtube: publishToYouTube,
        youtube_title: youtubeTitle.trim() || null,
        youtube_description: youtubeDescription,
        youtube_privacy: youtubePrivacy,
        youtube_tags: [],
        youtube_category_id: "22",
        youtube_publish_at: null,
      });
      const response = await waitForFactoryGenerationJob(started.job_id, (job) => setProgressMessage(`${job.message} ${job.progress}%`));
      setFactoryResult(response);
      setFinalVideo({
        url: absoluteApiUrl(response.final_video_url),
        downloadUrl: absoluteApiUrl(response.final_download_url),
        filename: response.final_filename,
        qualityNote: response.quality_note,
        label: `${response.scene_count} scenes · ${response.chunk_count} LTX chunks · ${response.provider} · ${response.total_render_seconds.toFixed(1)}s GPU render`,
        hasAudio: response.has_audio,
        audioCodec: response.has_audio ? "AAC / generated audio" : null,
        dimensions: `${response.width ?? "?"}×${response.height ?? "?"}`,
        estimatedCostUsd: response.estimated_cost_usd,
        gpu: response.gpu,
        youtubeUrl: response.youtube_url,
        youtubePrivacy: response.youtube_privacy,
      });
      await refreshBilling();
    } finally {
      setFactoryGenerating(false);
      setProgressMessage("");
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const cleanPrompt = prompt.trim();
    if (!cleanPrompt) {
      setError("Describe the video you want to create.");
      return;
    }
    setError("");
    setNotice("");
    resetOutput();

    try {
      if (mode === "factory") {
        await handleFactory(cleanPrompt);
        return;
      }
      if (mode === "direct") {
        setDirectGenerating(true);
        setProgressMessage("Rendering your prompt with LTX 2.5...");
        const response = await generateThroughJob({
          prompt: cleanPrompt,
          aspect_ratio: aspectRatio,
          duration_seconds: durationSeconds,
          seed,
          decoder,
          enhance_prompt: enhancePrompt,
          quality,
          audio_mode: audioMode,
          audio_direction: audioDirection.trim() || null,
          provider,
          model,
          continuity_mode: "off",
        });
        setFinalVideo(finalFromSceneResponse(response));
        await refreshBilling();
        return;
      }

      setPlanning(true);
      setProgressMessage("Creating continuity-locked storyboard shots with audio direction...");
      const response = await generateScenePlan({ prompt: cleanPrompt, aspect_ratio: aspectRatio, scene_count: sceneCount });
      setResult(response);
      setScenePrompts(response.scenes.reduce((current, scene) => {
        current[scene.id] = scene.prompt;
        return current;
      }, {} as ScenePromptMap));
    } catch (err) {
      setError(errorMessage(err, "Generation failed."));
    } finally {
      setPlanning(false);
      setDirectGenerating(false);
      setProgressMessage("");
    }
  }

  async function renderScene(sceneId: number, referenceFrameFilename: string | null = null): Promise<RenderedSceneVideo> {
    if (!result) throw new Error("Storyboard is not available.");
    const scenePrompt = scenePrompts[sceneId]?.trim();
    if (!scenePrompt) throw new Error("This scene needs a prompt before rendering.");
    const sceneIndex = result.scenes.findIndex((scene) => scene.id === sceneId);
    const response = await generateThroughJob({
      prompt: scenePrompt,
      aspect_ratio: result.aspect_ratio,
      duration_seconds: durationSeconds,
      seed,
      decoder,
      enhance_prompt: false,
      quality,
      audio_mode: "native",
      audio_direction: audioDirection.trim() || null,
      provider,
      model,
      continuity_mode: continuityMode,
      continuity_id: result.continuity_id,
      scene_index: Math.max(sceneIndex, 0),
      scene_count: result.scenes.length,
      character_bible: result.character_bible,
      style_bible: result.style_bible,
      entity_locks: result.entity_locks,
      visible_entity_counts: result.scenes[Math.max(sceneIndex, 0)]?.visible_entity_counts || {},
      continuity_qc_mode: quality === "preview" ? "auto" : "strict",
      continuity_max_retries: 1,
      reference_frame_filename: continuityMode === "strict" ? referenceFrameFilename : null,
      continuity_strength: 1.0,
    });
    return {
      url: absoluteApiUrl(response.video_url),
      downloadUrl: absoluteApiUrl(response.download_url),
      filename: response.filename,
      details: response.render_details,
      renderSeconds: response.render_seconds,
      wallSeconds: response.wall_seconds,
      provider: response.provider,
      gpu: response.gpu,
      mediaInfo: response.media_info,
      estimatedCostUsd: response.estimated_cost_usd,
      qualityNote: response.quality_note,
      audioMode: response.audio_mode,
      chunkCount: response.chunk_count,
      continuityMode: response.continuity_mode,
      continuityApplied: response.continuity_applied,
      referenceFrameFilename: response.reference_frame_filename,
      continuityFrameUrl: response.continuity_frame_url ? absoluteApiUrl(response.continuity_frame_url) : null,
      continuityFrameFilename: response.continuity_frame_filename,
      continuityQcPassed: response.continuity_qc_passed,
      continuityRegenerations: response.continuity_regenerations,
      continuityWarnings: response.continuity_warnings,
    };
  }

  async function ensureScenesThrough(targetSceneId?: number): Promise<RenderedVideoMap> {
    if (!result) throw new Error("Storyboard is not available.");
    const next: RenderedVideoMap = { ...renderedVideos };
    let previousFrame: string | null = null;
    for (const scene of result.scenes) {
      if (next[scene.id]) {
        previousFrame = next[scene.id].continuityFrameFilename;
      } else {
        setGeneratingScene(scene.id);
        setProgressMessage(`Rendering scene ${scene.id}/${result.scenes.length}...`);
        const rendered = await renderScene(scene.id, previousFrame);
        next[scene.id] = rendered;
        setRenderedVideos({ ...next });
        previousFrame = rendered.continuityFrameFilename;
      }
      if (targetSceneId && scene.id === targetSceneId) break;
    }
    return next;
  }

  async function handleRenderScene(sceneId: number) {
    setError("");
    try {
      await ensureScenesThrough(sceneId);
      await refreshBilling();
    } catch (err) {
      setError(errorMessage(err, "Scene render failed."));
    } finally {
      setGeneratingScene(null);
      setProgressMessage("");
    }
  }

  async function handleRenderMissingAndCombine() {
    if (!result) return;
    setError("");
    setCreatingFinal(true);
    try {
      const completed = await ensureScenesThrough();
      setGeneratingScene(null);
      setProgressMessage("Composing scenes, delivery quality and final audio master...");
      const combined = await combineSceneVideos({
        scene_video_urls: result.scenes.map((scene) => completed[scene.id].url),
        aspect_ratio: result.aspect_ratio,
        quality,
        audio_mode: audioMode,
      });
      setFinalVideo({
        url: absoluteApiUrl(combined.final_video_url),
        downloadUrl: absoluteApiUrl(combined.final_download_url),
        filename: combined.final_filename,
        qualityNote: combined.quality_note,
        label: `${combined.scene_count} scenes · ${qualityLabel(combined.quality)} · ${combined.audio_mode} audio`,
        hasAudio: combined.media_info.has_audio,
        audioCodec: combined.media_info.audio_codec,
        dimensions: `${combined.media_info.width ?? "?"}×${combined.media_info.height ?? "?"}`,
      });
      await refreshBilling();
    } catch (err) {
      setError(errorMessage(err, "Unable to create final video."));
    } finally {
      setGeneratingScene(null);
      setCreatingFinal(false);
      setProgressMessage("");
    }
  }

  function updateScenePrompt(sceneId: number, value: string) {
    setScenePrompts((current) => ({ ...current, [sceneId]: value }));
    invalidateRenderedMedia();
  }

  async function handleCheckout(packId: string) {
    setIntegrationBusy(true);
    setError("");
    try {
      const checkout = await createCheckout(packId);
      window.location.assign(checkout.checkout_url);
    } catch (err) {
      setError(errorMessage(err, "Unable to open checkout."));
      setIntegrationBusy(false);
    }
  }

  async function handleBillingPortal() {
    setIntegrationBusy(true);
    setError("");
    try {
      const portal = await createBillingPortal();
      window.location.assign(portal.portal_url);
    } catch (err) {
      setError(errorMessage(err, "Unable to open billing portal."));
      setIntegrationBusy(false);
    }
  }

  async function handleYouTubeConnection() {
    setIntegrationBusy(true);
    setError("");
    try {
      if (youtube?.connected) {
        await disconnectYouTube();
        setYoutube(await getYouTubeStatus());
        setPublishToYouTube(false);
        setNotice("YouTube channel disconnected.");
      } else {
        const connect = await connectYouTube();
        window.location.assign(connect.authorization_url);
      }
    } catch (err) {
      setError(errorMessage(err, "Unable to update YouTube connection."));
    } finally {
      setIntegrationBusy(false);
    }
  }

  const finalActionLabel = creatingFinal
    ? "Creating final master"
    : allScenesRendered
      ? `Combine · ${qualityLabel(quality)}`
      : `Render all + ${qualityLabel(quality)}`;

  return (
    <main className="min-h-screen bg-[var(--page-bg)] text-[var(--text)]">
      <div className="mx-auto w-full max-w-[1500px] px-4 py-5 sm:px-7 lg:px-10">
        <header className="mb-5 flex flex-col gap-4 rounded-2xl border border-[var(--border)] bg-[var(--panel-bg)] px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--primary-bg)] text-sm font-black text-[var(--primary-fg)]">T</div>
              <div>
                <div className="text-sm font-semibold tracking-wide text-[var(--text-strong)]">Triven Cinema</div>
                <div className="text-[11px] text-[var(--text-muted)]">Prompt → story → synchronized AV → master → publish</div>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <div className="theme-switch" role="group" aria-label="Color theme">
              <button type="button" className={`theme-switch-option ${theme === "light" ? "theme-switch-option-active" : ""}`} onClick={() => selectTheme("light")} aria-pressed={theme === "light"}>
                <SunIcon />
                <span>Light</span>
              </button>
              <button type="button" className={`theme-switch-option ${theme === "dark" ? "theme-switch-option-active" : ""}`} onClick={() => selectTheme("dark")} aria-pressed={theme === "dark"}>
                <MoonIcon />
                <span>Dark</span>
              </button>
            </div>
            <span className="rounded-lg border border-[var(--border)] bg-[var(--panel-subtle)] px-3 py-2 text-[var(--text-secondary)]">LTX 2.5 · Modal B200</span>
            {billingCatalog?.enabled && billingMe ? (
              <span className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] px-3 py-2 text-[var(--success-text)]">Credits {formatCredits(billingMe.balance_seconds)}</span>
            ) : (
              <span className="rounded-lg border border-[var(--border)] px-3 py-2 text-[var(--text-muted)]">Billing {billingCatalog?.enabled ? (billingMe ? formatCredits(billingMe.balance_seconds) : "on") : "off"}</span>
            )}
            <span className={`rounded-lg border px-3 py-2 ${youtube?.connected ? "border-red-500/20 bg-red-500/[0.06] text-[var(--danger-text)]" : "border-[var(--border)] text-[var(--text-muted)]"}`}>
              YouTube {youtube?.connected ? youtube.channel_title || "connected" : youtube?.enabled ? "not connected" : "off"}
            </span>
          </div>
        </header>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_330px]">
          <section className="rounded-3xl border border-[var(--border)] bg-[var(--panel-bg)] p-5 sm:p-7">
            <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.25em] text-[var(--accent-text)]">AI Video Factory</div>
                <h1 className="mt-2 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">Create the finished video, not just a clip.</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">Long-form continuity, generated sound, 1080p/4K delivery, payment-ready credits and connected-channel publishing.</p>
              </div>
              <div className="inline-flex rounded-xl border border-[var(--border)] bg-[var(--input-bg)] p-1">
                {(["factory", "storyboard", "direct"] as GenerationMode[]).map((item) => (
                  <button key={item} type="button" onClick={() => { setMode(item); resetOutput(); }} className={`rounded-lg px-3 py-2 text-xs font-medium capitalize transition ${mode === item ? "bg-[var(--primary-bg)] text-[var(--primary-fg)]" : "text-[var(--text-muted)] hover:text-[var(--text)]"}`}>
                    {item}
                  </button>
                ))}
              </div>
            </div>

            <form onSubmit={handleSubmit}>
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                rows={7}
                placeholder="Example: A premium cinematic animated story about a young adventurer meeting a red fox in a snowy forest at sunrise. Keep the character and fox identical across the full film..."
                className="w-full resize-none rounded-2xl border border-[var(--border)] bg-[var(--input-bg)] p-5 text-[15px] leading-7 text-[var(--text)] outline-none placeholder:text-[var(--text-faint)] focus:border-[var(--border-strong)]"
              />

              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Control label="Format">
                  <select className="control w-full" value={aspectRatio} onChange={(e) => { setAspectRatio(e.target.value as AspectRatio); invalidateRenderedMedia(); }}>
                    <option value="16:9">16:9 Landscape</option><option value="9:16">9:16 Vertical</option><option value="1:1">1:1 Square</option>
                  </select>
                </Control>
                <Control label="Delivery">
                  <select className="control w-full" value={quality} onChange={(e) => { setQuality(e.target.value as RenderQuality); invalidateRenderedMedia(); }}>
                    <option value="preview">Source preview · ≤10s</option>
                    <option value="1080p">1080p master · ≤30s/scene</option>
                    <option value="4k">4K master · ≤15s/scene</option>
                  </select>
                </Control>
                <Control label="Audio">
                  <select className="control w-full" value={audioMode} onChange={(e) => setAudioMode(e.target.value as AudioMode)}>
                    <option value="mastered">Generated + mastered</option><option value="native">Native LTX audio</option><option value="mute">Mute final video</option>
                  </select>
                </Control>
                <Control label="Continuity">
                  <select className="control w-full" value={continuityMode} onChange={(e) => { setContinuityMode(e.target.value as ContinuityMode); invalidateRenderedMedia(); }}>
                    <option value="strict">Strict · image + identity lock</option><option value="balanced">Balanced · identity lock</option><option value="off">Off</option>
                  </select>
                </Control>
              </div>

              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {mode === "factory" ? (
                  <>
                    <Control label="Final runtime">
                      <select className="control w-full" value={factoryTargetSeconds} onChange={(e) => setFactoryTargetSeconds(Number(e.target.value))}>
                        {FACTORY_TARGETS.map((value) => <option key={value} value={value}>{value < 60 ? `${value} seconds` : `${value / 60} minute${value === 60 ? "" : "s"}`}</option>)}
                      </select>
                    </Control>
                    <Control label="Scene runtime">
                      <select className="control w-full" value={factorySceneSeconds} onChange={(e) => setFactorySceneSeconds(Number(e.target.value))}>
                        {factoryDurationOptions.map((value) => <option key={value} value={value}>{value}s / scene</option>)}
                      </select>
                    </Control>
                  </>
                ) : mode === "storyboard" ? (
                  <>
                    <Control label="Scenes">
                      <select className="control w-full" value={sceneCount} onChange={(e) => setSceneCount(Number(e.target.value))}>
                        {[2, 3, 4, 6, 8, 10, 12, 16, 20].map((value) => <option key={value} value={value}>{value} scenes</option>)}
                      </select>
                    </Control>
                    <Control label="Runtime / scene">
                      <select className="control w-full" value={durationSeconds} onChange={(e) => { setDurationSeconds(Number(e.target.value)); invalidateRenderedMedia(); }}>
                        {durationOptions.map((value) => <option key={value} value={value}>{value}s</option>)}
                      </select>
                    </Control>
                  </>
                ) : (
                  <Control label="Clip runtime">
                    <select className="control w-full" value={durationSeconds} onChange={(e) => setDurationSeconds(Number(e.target.value))}>
                      {durationOptions.map((value) => <option key={value} value={value}>{value}s</option>)}
                    </select>
                  </Control>
                )}
                <Control label="Seed">
                  <input className="control w-full" type="number" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value) || 0)} />
                </Control>
                <Control label="Decoder">
                  <select className="control w-full" value={decoder} onChange={(e) => setDecoder(e.target.value as DecoderName)}>
                    <option value="conv">Conv · fast</option><option value="diffusion">Diffusion · quality</option>
                  </select>
                </Control>
              </div>

              <div className="mt-3 rounded-2xl border border-[var(--border)] bg-[var(--panel-subtle)] p-4">
                <label className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--text-muted)]">Audio direction</label>
                <textarea value={audioDirection} onChange={(e) => setAudioDirection(e.target.value)} rows={2} className="mt-2 w-full resize-none bg-transparent text-sm leading-6 text-[var(--text-secondary)] outline-none placeholder:text-[var(--text-faint)]" placeholder="Forest ambience, footsteps in snow, subtle wind, no dialogue..." />
              </div>

              {mode === "factory" && youtube?.enabled && (
                <div className="mt-3 rounded-2xl border border-[var(--border)] bg-[var(--panel-subtle)] p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="text-xs font-medium text-[var(--text)]">Publish after final render</div>
                      <div className="mt-1 text-[11px] text-[var(--text-muted)]">Upload the finished master to the connected YouTube channel. Private is the safe default.</div>
                    </div>
                    <button type="button" disabled={!youtube.connected} onClick={() => setPublishToYouTube((value) => !value)} className={`relative h-6 w-11 rounded-full transition ${publishToYouTube ? "bg-emerald-500" : "bg-[var(--toggle-off)]"} disabled:opacity-30`}>
                      <span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${publishToYouTube ? "left-6" : "left-1"}`} />
                    </button>
                  </div>
                  {publishToYouTube && (
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <input className="control w-full" value={youtubeTitle} onChange={(e) => setYoutubeTitle(e.target.value)} placeholder="YouTube title (optional)" />
                      <select className="control w-full" value={youtubePrivacy} onChange={(e) => setYoutubePrivacy(e.target.value as YouTubePrivacy)}>
                        <option value="private">Private</option><option value="unlisted" disabled={!youtube.public_uploads_allowed}>Unlisted</option><option value="public" disabled={!youtube.public_uploads_allowed}>Public</option>
                      </select>
                      <textarea className="sm:col-span-2 w-full resize-none rounded-xl border border-[var(--border)] bg-[var(--input-bg)] p-3 text-xs leading-5 text-[var(--text-secondary)] outline-none" rows={3} value={youtubeDescription} onChange={(e) => setYoutubeDescription(e.target.value)} placeholder="Description" />
                    </div>
                  )}
                </div>
              )}

              <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] text-[var(--text-muted)]">
                  <label className="flex items-center gap-2"><input type="checkbox" checked={enhancePrompt} onChange={(e) => setEnhancePrompt(e.target.checked)} /> AI Enhancement (Gemini planning + strict AI QC)</label>
                  <span>{enhancePrompt ? "Gemini creates shot-specific story beats" : "Direct mode sequences your own prompt across shots"}</span>
                  <span>{capabilities ? `Native chunk ${capabilities.native_chunk_seconds}s` : "Long clips chain native LTX segments"}</span>
                  <span>{quality === "4k" ? "4K is a delivery master, not a native-source claim" : "Synchronized LTX audio preserved"}</span>
                </div>
                <button type="submit" disabled={isBusy} className="flex h-12 min-w-[190px] items-center justify-center gap-2 rounded-xl bg-[var(--primary-bg)] px-6 text-sm font-semibold text-[var(--primary-fg)] transition hover:bg-[var(--primary-hover)] disabled:cursor-not-allowed disabled:opacity-40">
                  {isBusy ? <Spinner /> : <PlayIcon />}
                  {factoryGenerating ? "Running factory" : directGenerating ? "Rendering" : planning ? "Planning" : mode === "factory" ? "Create finished video" : mode === "direct" ? "Generate clip" : "Create storyboard"}
                </button>
              </div>
            </form>

            {progressMessage && <div className="mt-4 rounded-xl border border-blue-500/10 bg-blue-500/[0.04] px-4 py-3 text-xs text-[var(--info-text)]">{progressMessage}</div>}
            {error && <div className="mt-4 rounded-xl border border-red-500/20 bg-red-500/[0.05] px-4 py-3 text-sm text-[var(--danger-text)]">{error}</div>}
            {notice && <div className="mt-4 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.05] px-4 py-3 text-sm text-[var(--success-text)]">{notice}</div>}
          </section>

          <aside className="space-y-4">
            <IntegrationCard title="Production profile" subtitle="Current factory limits">
              <InfoRow label="1080p scene" value={`${capabilities?.max_scene_duration_seconds_by_quality?.["1080p"] ?? 30}s`} />
              <InfoRow label="4K scene" value={`${capabilities?.max_scene_duration_seconds_by_quality?.["4k"] ?? 15}s`} />
              <InfoRow label="Factory runtime" value={`${capabilities?.max_factory_duration_seconds ?? 300}s`} />
              <InfoRow label="Audio" value="Native / mastered / mute" />
              <InfoRow label="Continuity" value="Identity + entity count + anchor frame" />
              <InfoRow label="Duplicate guard" value={capabilities?.continuity_vision_qc ? "Vision QC + auto retry" : "Prompt/cardinality lock"} />
            </IntegrationCard>

            <IntegrationCard title="Customer billing" subtitle={billingCatalog?.enabled ? "Stripe Checkout credits" : "Feature-gated until Stripe is configured"}>
              {billingCatalog?.enabled && billingMe ? (
                <>
                  <div className="mb-3 rounded-xl bg-emerald-500/[0.06] px-3 py-3 text-sm text-[var(--success-text)]">Balance · {formatCredits(billingMe.balance_seconds)}</div>
                  <div className="space-y-2">
                    {billingCatalog.packs.filter((pack) => pack.available).map((pack) => (
                      <button key={pack.id} type="button" disabled={integrationBusy} onClick={() => handleCheckout(pack.id)} className="flex w-full items-center justify-between rounded-lg border border-[var(--border)] px-3 py-2 text-left text-xs text-[var(--text-secondary)] transition hover:bg-[var(--panel-subtle)]">
                        <span>{pack.label}</span><span>Buy</span>
                      </button>
                    ))}
                    {billingMe.stripe_customer_id && <button type="button" onClick={handleBillingPortal} className="w-full rounded-lg px-3 py-2 text-xs text-[var(--text-muted)] hover:text-[var(--text)]">Manage billing</button>}
                  </div>
                </>
              ) : <p className="text-xs leading-5 text-[var(--text-muted)]">Configure Stripe keys and Price IDs, then enable billing. The render queue can enforce generation-second credits.</p>}
            </IntegrationCard>

            <IntegrationCard title="YouTube channel" subtitle={youtube?.enabled ? "Server-side OAuth + resumable upload" : "Feature-gated until Google OAuth is configured"}>
              {youtube?.enabled ? (
                <>
                  <div className="mb-3 text-xs text-[var(--text-muted)]">{youtube.connected ? `Connected to ${youtube.channel_title || youtube.channel_id || "channel"}` : "No channel connected"}</div>
                  <button type="button" disabled={integrationBusy} onClick={handleYouTubeConnection} className="w-full rounded-xl border border-[var(--border)] bg-[var(--panel-subtle)] px-4 py-2.5 text-xs font-medium text-[var(--text)] hover:bg-[var(--hover-bg)] disabled:opacity-40">
                    {youtube.connected ? "Disconnect channel" : "Connect YouTube"}
                  </button>
                </>
              ) : <p className="text-xs leading-5 text-[var(--text-muted)]">Once enabled, a customer connects their own channel and Factory mode can upload the completed master automatically.</p>}
            </IntegrationCard>
          </aside>
        </div>

        {finalVideo && (
          <section className="mt-5">
            <FinalVideoCard video={finalVideo} aspectRatio={aspectRatio} />
          </section>
        )}

        {factoryResult && (
          <section className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
            <Stat label="Scenes" value={String(factoryResult.scene_count)} detail={`${factoryResult.chunk_count} native LTX chunks`} />
            <Stat label="Runtime" value={`${(factoryResult.actual_duration_seconds ?? factoryResult.target_duration_seconds).toFixed(1)}s`} detail={`${factoryResult.scene_duration_seconds}s target scene`} />
            <Stat label="Delivery" value={qualityLabel(factoryResult.quality)} detail={`${factoryResult.width ?? "?"}×${factoryResult.height ?? "?"} · ${factoryResult.audio_mode}`} />
            <Stat label="Planner" value={factoryResult.planner_source} detail={`${factoryResult.entity_locks.length} entity lock${factoryResult.entity_locks.length === 1 ? "" : "s"}`} />
            <Stat label="Continuity QC" value={factoryResult.continuity_qc_passed === true ? "Passed" : factoryResult.continuity_qc_passed === false ? "Warning" : "Guarded"} detail={`${factoryResult.continuity_regenerations} auto-regeneration${factoryResult.continuity_regenerations === 1 ? "" : "s"}`} />
            <Stat label="Audio QC" value={factoryResult.audio_qc_passed === true ? "Passed" : factoryResult.audio_qc_passed === false ? "Failed" : "Guarded"} detail={`${factoryResult.audio_retake_count} LTX audio retake${factoryResult.audio_retake_count === 1 ? "" : "s"}`} />
          </section>
        )}

        {result && mode === "storyboard" && (
          <section className="mt-5 rounded-3xl border border-[var(--border)] bg-[var(--panel-bg)] p-5 sm:p-7">
            <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg font-semibold">Storyboard</h2>
                  <span className="rounded-full bg-[var(--panel-subtle-strong)] px-2.5 py-1 text-[10px] text-[var(--text-muted)]">{result.planner_source}</span>
                  <span className="rounded-full bg-emerald-500/[0.06] px-2.5 py-1 text-[10px] text-[var(--accent-text)]">{continuityMode} continuity</span>
                </div>
                <p className="mt-1 text-xs text-[var(--text-muted)]">{result.scenes.length} scenes · {plannedDuration}s selected runtime · same seed · previous-frame chaining</p>
              </div>
              <button type="button" onClick={handleRenderMissingAndCombine} disabled={isBusy} className="flex h-11 items-center justify-center gap-2 rounded-xl bg-[var(--primary-bg)] px-5 text-sm font-medium text-[var(--primary-fg)] hover:bg-[var(--primary-hover)] disabled:opacity-40">
                {creatingFinal ? <Spinner /> : <PlayIcon />}{creatingFinal ? progressMessage || "Creating final video" : finalActionLabel}
              </button>
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              {result.scenes.map((scene, index) => {
                const video = renderedVideos[scene.id];
                const isGenerating = generatingScene === scene.id;
                const isEditing = editingScene === scene.id;
                return (
                  <article key={scene.id} className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--panel-bg)]">
                    {video ? (
                      <div className="bg-black"><video src={video.url} controls playsInline className={`w-full object-contain ${aspectClass(result.aspect_ratio)}`} /></div>
                    ) : (
                      <div className={`relative flex items-center justify-center bg-[var(--empty-bg)] ${aspectClass(result.aspect_ratio)}`}><div className="text-center text-[var(--text-muted)]">{isGenerating ? <Spinner /> : <PlayIcon />}<div className="mt-3 text-xs">{isGenerating ? "Rendering with LTX..." : "Not rendered"}</div></div></div>
                    )}
                    <div className="p-5 sm:p-6">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0"><div className="mb-2 text-[10px] uppercase tracking-[0.2em] text-[var(--text-muted)]">Scene {String(index + 1).padStart(2, "0")}</div><h3 className="truncate text-base font-medium text-[var(--text)]">{scene.title}</h3></div>
                        <div className="shrink-0 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[10px] text-[var(--text-muted)]">{durationSeconds}s render</div>
                      </div>
                      {isEditing ? (
                        <textarea value={scenePrompts[scene.id] || ""} onChange={(e) => updateScenePrompt(scene.id, e.target.value)} rows={8} className="mt-5 w-full resize-none rounded-xl border border-[var(--border)] bg-[var(--input-bg)] p-4 text-sm leading-6 text-[var(--text)] outline-none" />
                      ) : <p className="mt-5 line-clamp-6 text-sm leading-6 text-[var(--text-muted)]">{scenePrompts[scene.id]}</p>}
                      {video && <div className="mt-4 rounded-xl bg-[var(--panel-subtle)] px-3 py-2 text-[11px] leading-5 text-[var(--text-muted)]">{video.details} · {video.chunkCount} chunk{video.chunkCount === 1 ? "" : "s"} · {video.renderSeconds.toFixed(1)}s render · {video.mediaInfo.has_audio ? `audio ${video.mediaInfo.audio_codec || "present"}` : "no audio"}{video.continuityMode === "strict" ? video.continuityApplied ? " · conditioned" : " · anchor" : ""}{video.continuityQcPassed === true ? " · QC passed" : video.continuityQcPassed === false ? " · QC warning" : ""}{video.continuityRegenerations ? ` · ${video.continuityRegenerations} auto-retry` : ""}</div>}
                      <div className="mt-5 flex items-center justify-between gap-3 border-t border-[var(--border)] pt-4">
                        <button type="button" disabled={isBusy && !isEditing} onClick={() => setEditingScene(isEditing ? null : scene.id)} className="h-9 rounded-lg px-3 text-xs text-[var(--text-muted)] hover:text-[var(--text)] disabled:opacity-40">{isEditing ? "Done editing" : "Edit prompt"}</button>
                        <div className="flex items-center gap-2">
                          {video && <a href={video.downloadUrl} className="flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-xs text-[var(--text-muted)] hover:text-[var(--text)]"><DownloadIcon /> Clip</a>}
                          <button type="button" disabled={isBusy} onClick={() => handleRenderScene(scene.id)} className="flex h-9 items-center gap-2 rounded-lg bg-[var(--primary-bg)] px-4 text-xs font-medium text-[var(--primary-fg)] hover:bg-[var(--primary-hover)] disabled:opacity-40">{isGenerating ? <Spinner /> : <PlayIcon />}{video ? "Regenerate chain" : "Render through scene"}</button>
                        </div>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
            <div className="mt-5 text-xs text-[var(--text-muted)]">{renderedSceneCount}/{result.scenes.length} rendered · {allScenesRendered ? "Ready to combine" : "Scenes render sequentially so strict continuity has the previous frame"}</div>
          </section>
        )}
      </div>
    </main>
  );
}

function Control({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block"><span className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--text-muted)]">{label}</span>{children}</label>;
}

function IntegrationCard({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return <div className="rounded-2xl border border-[var(--border)] bg-[var(--panel-bg)] p-4"><div className="text-xs font-semibold text-[var(--text)]">{title}</div><div className="mt-1 mb-4 text-[11px] leading-5 text-[var(--text-muted)]">{subtitle}</div>{children}</div>;
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between border-t border-[var(--border)] py-2 text-[11px]"><span className="text-[var(--text-muted)]">{label}</span><span className="text-[var(--text-secondary)]">{value}</span></div>;
}

function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="rounded-2xl border border-[var(--border)] bg-[var(--panel-bg)] p-4"><div className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-muted)]">{label}</div><div className="mt-2 text-lg font-semibold text-[var(--text)]">{value}</div><div className="mt-1 text-[11px] text-[var(--text-muted)]">{detail}</div></div>;
}

function FinalVideoCard({ video, aspectRatio }: { video: NonNullable<FinalVideo>; aspectRatio: AspectRatio }) {
  return (
    <div className="overflow-hidden rounded-3xl border border-[var(--border)] bg-[var(--panel-bg)]">
      <div className="flex flex-col gap-3 border-b border-[var(--border)] px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-strong)]">Final master <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[10px] text-[var(--accent-text)]">Ready</span></div>
          <div className="mt-1 text-xs text-[var(--text-muted)]">{video.label}</div>
          <div className="mt-1 text-[11px] text-[var(--text-faint)]">{video.dimensions} · {video.hasAudio ? `audio ${video.audioCodec || "present"}` : "no audio stream"}{video.gpu ? ` · ${video.gpu}` : ""}{video.estimatedCostUsd != null ? ` · est. $${video.estimatedCostUsd.toFixed(4)}` : ""}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {video.youtubeUrl && <a href={video.youtubeUrl} target="_blank" rel="noreferrer" className="flex h-10 items-center justify-center rounded-xl border border-red-500/20 bg-red-500/[0.06] px-4 text-xs font-medium text-[var(--danger-text)]">Open YouTube · {video.youtubePrivacy}</a>}
          <a href={video.downloadUrl} className="flex h-10 items-center justify-center gap-2 rounded-xl bg-[var(--primary-bg)] px-4 text-xs font-medium text-[var(--primary-fg)] hover:bg-[var(--primary-hover)]"><DownloadIcon /> Download MP4</a>
        </div>
      </div>
      <div className={`mx-auto bg-black ${aspectRatio === "9:16" ? "max-w-[430px]" : aspectRatio === "1:1" ? "max-w-[760px]" : "w-full"}`}><video src={video.url} controls playsInline className={`w-full object-contain ${aspectClass(aspectRatio)}`} /></div>
      <div className="border-t border-[var(--border)] px-5 py-4 text-[11px] leading-5 text-[var(--text-muted)] sm:px-6">{video.qualityNote}</div>
    </div>
  );
}
