"use client";

import { FormEvent, useMemo, useState } from "react";

import {
  absoluteApiUrl,
  combineSceneVideos,
  createVideoGenerationJob,
  generateScenePlan,
  waitForVideoGenerationJob,
} from "@/lib/api/cinema";
import type {
  AspectRatio,
  DecoderName,
  GenerationMode,
  RenderedSceneVideo,
  RenderQuality,
  ScenePlanResponse,
  VideoModelName,
  VideoProviderName,
} from "@/lib/types/generation";

type ScenePromptMap = Record<number, string>;
type RenderedVideoMap = Record<number, RenderedSceneVideo>;

type FinalVideo = {
  url: string;
  downloadUrl: string;
  qualityNote: string;
  label: string;
  hasAudio: boolean;
  audioCodec: string | null;
  dimensions: string;
  estimatedCostUsd?: number | null;
  gpu?: string | null;
} | null;

function Spinner() {
  return (
    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" />
  );
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
      <path
        d="M12 4v11m0 0-4-4m4 4 4-4M5 20h14"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SparklesIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <path d="m12 3 1.4 4.6L18 9l-4.6 1.4L12 15l-1.4-4.6L6 9l4.6-1.4L12 3Z" fill="currentColor" />
      <path d="m18.5 14 .7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7.7-2.3Z" fill="currentColor" />
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

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<GenerationMode>("storyboard");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("16:9");
  const [sceneCount, setSceneCount] = useState(2);
  const [durationSeconds, setDurationSeconds] = useState(1);
  const [quality, setQuality] = useState<RenderQuality>("preview");
  const [provider, setProvider] = useState<VideoProviderName>("modal");
  const [model, setModel] = useState<VideoModelName>("ltx-2.5");
  const [decoder, setDecoder] = useState<DecoderName>("conv");
  const [seed, setSeed] = useState(42);
  const [enhancePrompt, setEnhancePrompt] = useState(false);

  const [result, setResult] = useState<ScenePlanResponse | null>(null);
  const [scenePrompts, setScenePrompts] = useState<ScenePromptMap>({});
  const [renderedVideos, setRenderedVideos] = useState<RenderedVideoMap>({});
  const [finalVideo, setFinalVideo] = useState<FinalVideo>(null);

  const [editingScene, setEditingScene] = useState<number | null>(null);
  const [planning, setPlanning] = useState(false);
  const [directGenerating, setDirectGenerating] = useState(false);
  const [generatingScene, setGeneratingScene] = useState<number | null>(null);
  const [creatingFinal, setCreatingFinal] = useState(false);
  const [progressMessage, setProgressMessage] = useState("");
  const [error, setError] = useState("");

  const isBusy =
    planning || directGenerating || generatingScene !== null || creatingFinal;

  const renderedSceneCount = Object.keys(renderedVideos).length;

  const allScenesRendered =
    !!result &&
    result.scenes.length > 0 &&
    result.scenes.every((scene) => Boolean(renderedVideos[scene.id]));

  const plannedDuration = useMemo(() => {
    if (!result) return 0;
    return result.scenes.reduce((total, scene) => total + scene.duration_seconds, 0);
  }, [result]);

  function resetOutput() {
    setResult(null);
    setScenePrompts({});
    setRenderedVideos({});
    setFinalVideo(null);
    setEditingScene(null);
    setProgressMessage("");
  }

  function invalidateRenderedMedia() {
    setRenderedVideos({});
    setFinalVideo(null);
  }

  async function generateThroughJob(
    payload: Parameters<typeof createVideoGenerationJob>[0]
  ) {
    const started = await createVideoGenerationJob(payload);
    return waitForVideoGenerationJob(started.job_id, (job) => {
      setProgressMessage(`${job.message} ${job.progress}%`);
    });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const cleanPrompt = prompt.trim();

    if (!cleanPrompt) {
      setError("Describe the video you want to create.");
      return;
    }

    setError("");
    resetOutput();

    if (mode === "direct") {
      try {
        setDirectGenerating(true);
        setProgressMessage("Sending your prompt directly to LTX 2.5...");

        const response = await generateThroughJob({
          prompt: cleanPrompt,
          aspect_ratio: aspectRatio,
          duration_seconds: durationSeconds,
          seed,
          decoder,
          enhance_prompt: enhancePrompt,
          quality,
          provider,
          model,
        });

        setFinalVideo({
          url: absoluteApiUrl(response.video_url),
          downloadUrl: absoluteApiUrl(response.download_url),
          qualityNote: response.quality_note,
          label: `${response.provider} · ${response.render_seconds.toFixed(1)}s render · ${response.wall_seconds.toFixed(1)}s wall`,
          hasAudio: response.media_info.has_audio,
          audioCodec: response.media_info.audio_codec,
          dimensions: `${response.media_info.width ?? "?"}×${response.media_info.height ?? "?"}`,
          estimatedCostUsd: response.estimated_cost_usd,
          gpu: response.gpu,
        });
      } catch (err) {
        setError(errorMessage(err, "Direct generation failed."));
      } finally {
        setDirectGenerating(false);
        setProgressMessage("");
      }
      return;
    }

    try {
      setPlanning(true);
      setProgressMessage("Gemini is converting your idea into generation-ready shots...");

      const response = await generateScenePlan({
        prompt: cleanPrompt,
        aspect_ratio: aspectRatio,
        scene_count: sceneCount,
      });

      setResult(response);
      setScenePrompts(
        response.scenes.reduce((current, scene) => {
          current[scene.id] = scene.prompt;
          return current;
        }, {} as ScenePromptMap)
      );
    } catch (err) {
      setError(errorMessage(err, "Unable to create the storyboard."));
    } finally {
      setPlanning(false);
      setProgressMessage("");
    }
  }

  async function renderScene(sceneId: number): Promise<RenderedSceneVideo> {
    if (!result) throw new Error("Storyboard is not available.");

    const scenePrompt = scenePrompts[sceneId]?.trim();
    if (!scenePrompt) throw new Error("This scene needs a prompt before rendering.");

    const sceneIndex = result.scenes.findIndex((scene) => scene.id === sceneId);
    const response = await generateThroughJob({
      prompt: scenePrompt,
      aspect_ratio: result.aspect_ratio,
      duration_seconds: durationSeconds,
      seed: seed + Math.max(sceneIndex, 0),
      decoder,
      enhance_prompt: false,
      // Storyboard prompts are already Gemini-generated; avoid enhancing them twice.
      // Storyboard clips stay at source quality; 1080p is applied once to the final combine.
      quality: "preview",
      provider,
      model,
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
    };
  }

  async function handleRenderScene(sceneId: number) {
    try {
      setGeneratingScene(sceneId);
      setError("");
      setFinalVideo(null);
      setProgressMessage(`Rendering scene ${sceneId} with ${model.toUpperCase()}...`);

      const rendered = await renderScene(sceneId);
      setRenderedVideos((current) => ({ ...current, [sceneId]: rendered }));
    } catch (err) {
      setError(errorMessage(err, "Scene rendering failed."));
    } finally {
      setGeneratingScene(null);
      setProgressMessage("");
    }
  }

  async function handleRenderMissingAndCombine() {
    if (!result) return;

    try {
      setCreatingFinal(true);
      setFinalVideo(null);
      setError("");

      const available: RenderedVideoMap = { ...renderedVideos };
      const total = result.scenes.length;

      for (let index = 0; index < total; index += 1) {
        const scene = result.scenes[index];
        if (available[scene.id]) continue;

        setGeneratingScene(scene.id);
        setProgressMessage(`Rendering scene ${index + 1} of ${total}...`);

        const rendered = await renderScene(scene.id);
        available[scene.id] = rendered;
        setRenderedVideos((current) => ({ ...current, [scene.id]: rendered }));
      }

      setGeneratingScene(null);
      setProgressMessage("Combining rendered clips with FFmpeg...");

      const orderedUrls = result.scenes.map((scene) => available[scene.id]?.url);
      if (orderedUrls.some((url) => !url)) {
        throw new Error("One or more scenes could not be rendered.");
      }

      const combined = await combineSceneVideos({
        scene_video_urls: orderedUrls as string[],
        aspect_ratio: result.aspect_ratio,
        quality,
      });

      const sceneCosts = Object.values(available)
        .map((item) => item.estimatedCostUsd)
        .filter((value): value is number => value != null);
      const totalEstimatedCost = sceneCosts.length
        ? sceneCosts.reduce((total, value) => total + value, 0)
        : null;
      const gpuNames = Array.from(
        new Set(
          Object.values(available)
            .map((item) => item.gpu)
            .filter((value): value is string => Boolean(value))
        )
      );

      setFinalVideo({
        url: absoluteApiUrl(combined.final_video_url),
        downloadUrl: absoluteApiUrl(combined.final_download_url),
        qualityNote: combined.quality_note,
        label: `${combined.scene_count} scenes · FFmpeg final`,
        hasAudio: combined.media_info.has_audio,
        audioCodec: combined.media_info.audio_codec,
        dimensions: `${combined.media_info.width ?? "?"}×${combined.media_info.height ?? "?"}`,
        estimatedCostUsd: totalEstimatedCost,
        gpu: gpuNames.length === 1 ? gpuNames[0] : gpuNames.join(" + ") || null,
      });
    } catch (err) {
      setError(errorMessage(err, "Unable to create the final video."));
    } finally {
      setGeneratingScene(null);
      setCreatingFinal(false);
      setProgressMessage("");
    }
  }

  function updateScenePrompt(sceneId: number, value: string) {
    setScenePrompts((current) => ({ ...current, [sceneId]: value }));
    setRenderedVideos((current) => {
      const next = { ...current };
      delete next[sceneId];
      return next;
    });
    setFinalVideo(null);
  }

  const finalActionLabel = allScenesRendered
    ? finalVideo
      ? "Recombine scenes"
      : "Combine scenes"
    : renderedSceneCount > 0
      ? "Render missing & combine"
      : "Render all & combine";

  return (
    <main className="min-h-screen bg-[#070809] text-white">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-[-430px] h-[820px] w-[820px] -translate-x-1/2 rounded-full bg-violet-400/[0.045] blur-[130px]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,#070809_78%)]" />
      </div>

      <div className="relative mx-auto max-w-[1440px] px-5 pb-24 sm:px-8 lg:px-12">
        <header className="flex h-20 items-center justify-between border-b border-white/[0.06]">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-sm font-bold text-black">T</div>
            <div>
              <div className="text-sm font-semibold tracking-tight">Triven Cinema</div>
              <div className="text-[11px] text-zinc-600">AI video studio</div>
            </div>
          </div>

          <div className="flex items-center gap-2 text-[11px]">
            <span className="hidden rounded-full border border-white/[0.08] bg-white/[0.025] px-3 py-1.5 text-zinc-500 sm:inline-flex">
              LTX 2.5
            </span>
            <span className="rounded-full border border-white/[0.08] bg-white/[0.025] px-3 py-1.5 text-zinc-500">
              {provider === "modal" ? "Modal production" : "ZeroGPU development"}
            </span>
          </div>
        </header>

        <section className="mx-auto max-w-4xl pb-10 pt-16 text-center sm:pt-24">
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.025] px-3 py-1.5 text-xs text-zinc-400">
            <SparklesIcon /> Prompt to finished video
          </div>
          <h1 className="text-balance text-4xl font-medium tracking-[-0.055em] text-zinc-50 sm:text-6xl lg:text-[68px] lg:leading-[1.02]">
            Build cinematic video
            <span className="block text-zinc-500">from one idea.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-sm leading-7 text-zinc-500 sm:text-base">
            Generate directly from your prompt or let Triven break it into editable shots, render them with LTX, and combine the final sequence automatically.
          </p>
        </section>

        <section className="mx-auto max-w-5xl">
          <div className="mb-3 flex w-fit rounded-xl border border-white/[0.08] bg-[#0d0e10] p-1">
            {(["storyboard", "direct"] as GenerationMode[]).map((item) => (
              <button
                key={item}
                type="button"
                disabled={isBusy}
                onClick={() => {
                  setMode(item);
                  resetOutput();
                  setError("");
                }}
                className={`rounded-lg px-4 py-2 text-xs font-medium transition ${
                  mode === item ? "bg-white text-black" : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {item === "storyboard" ? "Storyboard mode" : "Direct prompt"}
              </button>
            ))}
          </div>

          <form
            onSubmit={handleSubmit}
            className="overflow-hidden rounded-[26px] border border-white/[0.1] bg-[#111214] shadow-[0_32px_100px_rgba(0,0,0,0.45)]"
          >
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={
                mode === "storyboard"
                  ? "Describe a story, ad, reel or cinematic sequence..."
                  : "Write the exact shot you want LTX to generate..."
              }
              rows={7}
              disabled={isBusy}
              className="w-full resize-none bg-transparent px-7 py-7 text-[15px] leading-7 text-zinc-100 outline-none placeholder:text-zinc-600 disabled:opacity-70 sm:px-8"
            />

            <div className="border-t border-white/[0.07] bg-black/10 p-4">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                <div className="flex flex-wrap gap-2">
                  <select
                    value={model}
                    disabled={isBusy}
                    onChange={(event) => {
                      setModel(event.target.value as VideoModelName);
                      invalidateRenderedMedia();
                    }}
                    className="control"
                  >
                    <option value="ltx-2.5">LTX 2.5</option>
                    <option value="wan" disabled>WAN · next</option>
                    <option value="minimax" disabled>MiniMax · next</option>
                  </select>

                  <select
                    value={provider}
                    disabled={isBusy}
                    onChange={(event) => {
                      setProvider(event.target.value as VideoProviderName);
                      invalidateRenderedMedia();
                    }}
                    className="control"
                  >
                    <option value="huggingface">ZeroGPU · dev</option>
                    <option value="modal">Modal · production</option>
                  </select>

                  <select
                    value={aspectRatio}
                    disabled={isBusy}
                    onChange={(event) => {
                      setAspectRatio(event.target.value as AspectRatio);
                      resetOutput();
                    }}
                    className="control"
                  >
                    <option value="16:9">16:9 Landscape</option>
                    <option value="9:16">9:16 Portrait</option>
                    <option value="1:1">1:1 Square</option>
                  </select>

                  {mode === "storyboard" && (
                    <select
                      value={sceneCount}
                      disabled={isBusy}
                      onChange={(event) => setSceneCount(Number(event.target.value))}
                      className="control"
                    >
                      {[1, 2, 3, 4, 5, 6].map((count) => (
                        <option key={count} value={count}>{count} {count === 1 ? "Scene" : "Scenes"}</option>
                      ))}
                    </select>
                  )}

                  <select
                    value={durationSeconds}
                    disabled={isBusy}
                    onChange={(event) => {
                      setDurationSeconds(Number(event.target.value));
                      invalidateRenderedMedia();
                    }}
                    className="control"
                  >
                    {[1, 2, 3, 5].map((seconds) => (
                      <option key={seconds} value={seconds}>{seconds}s / scene</option>
                    ))}
                  </select>

                  <select
                    value={quality}
                    disabled={isBusy}
                    onChange={(event) => {
                      setQuality(event.target.value as RenderQuality);
                      setFinalVideo(null);
                    }}
                    className="control"
                  >
                    <option value="preview">Source preview</option>
                    <option value="1080p">1080p delivery</option>
                  </select>

                  <select
                    value={decoder}
                    disabled={isBusy}
                    onChange={(event) => {
                      setDecoder(event.target.value as DecoderName);
                      invalidateRenderedMedia();
                    }}
                    className="control"
                  >
                    <option value="conv">Conv decoder</option>
                    <option value="diffusion">Diffusion decoder</option>
                  </select>

                  <label className="control flex items-center gap-2">
                    <span className="text-zinc-600">Seed</span>
                    <input
                      type="number"
                      min={0}
                      max={2147483647}
                      value={seed}
                      disabled={isBusy}
                      onChange={(event) => {
                        setSeed(Math.max(0, Number(event.target.value) || 0));
                        invalidateRenderedMedia();
                      }}
                      className="w-20 bg-transparent text-zinc-300 outline-none"
                    />
                  </label>

                  <label className="control flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      checked={enhancePrompt}
                      disabled={isBusy || mode === "storyboard"}
                      onChange={(event) => {
                        setEnhancePrompt(event.target.checked);
                        invalidateRenderedMedia();
                      }}
                    />
                    Enhance direct prompt
                  </label>
                </div>

                <button
                  type="submit"
                  disabled={isBusy || !prompt.trim()}
                  className="flex h-11 shrink-0 items-center justify-center gap-2 rounded-xl bg-white px-6 text-sm font-medium text-black transition hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {planning || directGenerating ? <Spinner /> : <SparklesIcon />}
                  {mode === "storyboard"
                    ? planning ? "Planning..." : "Create storyboard"
                    : directGenerating ? "Generating..." : "Generate video"}
                </button>
              </div>

              <div className="mt-3 text-[11px] text-zinc-600">
                {quality === "1080p"
                  ? "Storyboard scenes stay at source quality and the final sequence is upscaled once to 1080-class delivery dimensions."
                  : "Source preview avoids unnecessary upscaling while you test prompts and scene composition."}
              </div>
            </div>
          </form>

          {(progressMessage || error) && (
            <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${
              error
                ? "border-red-500/15 bg-red-500/[0.06] text-red-300"
                : "border-white/[0.08] bg-white/[0.025] text-zinc-400"
            }`}>
              <div className="flex items-center gap-3">
                {!error && <Spinner />}
                <span>{error || progressMessage}</span>
              </div>
            </div>
          )}
        </section>

        {finalVideo && mode === "direct" && (
          <section className="mx-auto mt-12 max-w-5xl">
            <FinalVideoCard video={finalVideo} aspectRatio={aspectRatio} />
          </section>
        )}

        {result && mode === "storyboard" && (
          <section className="mx-auto mt-16 max-w-7xl">
            <div className="mb-7 flex flex-col gap-5 border-b border-white/[0.07] pb-7 md:flex-row md:items-end md:justify-between">
              <div>
                <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.22em] text-zinc-600">Storyboard</div>
                <h2 className="text-2xl font-medium tracking-[-0.025em] text-zinc-100">Review the shots before the final render</h2>
                <p className="mt-2 text-sm text-zinc-600">
                  {result.scenes.length} scenes · {result.aspect_ratio} · {plannedDuration}s AI plan · {durationSeconds}s render per scene
                </p>
                {result.planner_note && (
                  <p
                    className={`mt-2 text-[11px] ${result.planner_source === "fallback" ? "text-amber-500/80" : "text-zinc-600"}`}
                  >
                    {result.planner_note}
                  </p>
                )}
                {result.plan_quality && (
                  <p className="mt-2 text-[11px] text-zinc-700" title={result.plan_quality.note}>
                    Storyboard prompt coverage: {Math.round(result.plan_quality.coverage_score * 100)}%
                    {result.plan_quality.missing_terms.length > 0
                      ? ` · review: ${result.plan_quality.missing_terms.slice(0, 5).join(", ")}`
                      : " · key prompt terms preserved"}
                  </p>
                )}
              </div>

              <button
                type="button"
                onClick={handleRenderMissingAndCombine}
                disabled={isBusy}
                className="flex h-11 items-center justify-center gap-2 rounded-xl bg-white px-5 text-sm font-medium text-black transition hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {creatingFinal ? <Spinner /> : <PlayIcon />}
                {creatingFinal ? (progressMessage || "Creating final video") : finalActionLabel}
              </button>
            </div>

            {finalVideo && (
              <div className="mb-8">
                <FinalVideoCard video={finalVideo} aspectRatio={result.aspect_ratio} />
              </div>
            )}

            <div className="grid gap-5 lg:grid-cols-2">
              {result.scenes.map((scene, index) => {
                const video = renderedVideos[scene.id];
                const isGenerating = generatingScene === scene.id;
                const isEditing = editingScene === scene.id;

                return (
                  <article key={scene.id} className="overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0d0e10]">
                    {video ? (
                      <div className="bg-black">
                        <video src={video.url} controls playsInline className={`w-full object-contain ${aspectClass(result.aspect_ratio)}`} />
                      </div>
                    ) : (
                      <div className={`relative flex items-center justify-center bg-[#111214] ${aspectClass(result.aspect_ratio)}`}>
                        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.05),transparent_60%)]" />
                        <div className="relative text-center text-zinc-600">
                          {isGenerating ? <Spinner /> : <PlayIcon />}
                          <div className="mt-3 text-xs">{isGenerating ? "Rendering with LTX..." : "Preview not rendered"}</div>
                        </div>
                      </div>
                    )}

                    <div className="p-5 sm:p-6">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="mb-2 text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-600">Scene {String(index + 1).padStart(2, "0")}</div>
                          <h3 className="truncate text-base font-medium text-zinc-200">{scene.title}</h3>
                        </div>
                        <div className="shrink-0 rounded-lg border border-white/[0.07] bg-white/[0.025] px-2.5 py-1 text-[10px] text-zinc-600">
                          {scene.duration_seconds}s AI plan
                        </div>
                      </div>

                      {isEditing ? (
                        <textarea
                          value={scenePrompts[scene.id] || ""}
                          onChange={(event) => updateScenePrompt(scene.id, event.target.value)}
                          rows={8}
                          className="mt-5 w-full resize-none rounded-xl border border-white/[0.08] bg-[#090a0b] p-4 text-sm leading-6 text-zinc-300 outline-none focus:border-white/[0.18]"
                        />
                      ) : (
                        <p className="mt-5 line-clamp-6 text-sm leading-6 text-zinc-500">{scenePrompts[scene.id]}</p>
                      )}

                      {video && (
                        <div className="mt-4 rounded-xl bg-white/[0.025] px-3 py-2 text-[11px] leading-5 text-zinc-600">
                          {video.details} · {video.renderSeconds.toFixed(1)}s render · {video.wallSeconds.toFixed(1)}s wall · {video.provider}
                          {video.gpu ? ` · ${video.gpu}` : ""}
                          {video.mediaInfo.has_audio ? ` · audio ${video.mediaInfo.audio_codec || "present"}` : " · no audio stream"}
                          {video.estimatedCostUsd != null ? ` · est. $${video.estimatedCostUsd.toFixed(4)}` : ""}
                        </div>
                      )}

                      <div className="mt-5 flex items-center justify-between gap-3 border-t border-white/[0.06] pt-4">
                        <button
                          type="button"
                          disabled={isBusy && !isEditing}
                          onClick={() => setEditingScene(isEditing ? null : scene.id)}
                          className="h-9 rounded-lg px-3 text-xs font-medium text-zinc-500 transition hover:bg-white/[0.04] hover:text-zinc-300 disabled:opacity-40"
                        >
                          {isEditing ? "Done editing" : "Edit prompt"}
                        </button>

                        <div className="flex items-center gap-2">
                          {video && (
                            <a
                              href={video.downloadUrl}
                              className="flex h-9 items-center gap-2 rounded-lg border border-white/[0.08] px-3 text-xs text-zinc-500 transition hover:text-zinc-300"
                            >
                              <DownloadIcon /> Clip
                            </a>
                          )}
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => handleRenderScene(scene.id)}
                            className="flex h-9 items-center gap-2 rounded-lg bg-white px-4 text-xs font-medium text-black transition hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            {isGenerating ? <Spinner /> : <PlayIcon />}
                            {video ? "Regenerate" : "Render preview"}
                          </button>
                        </div>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>

            <div className="mt-6 flex flex-col gap-3 rounded-2xl border border-white/[0.06] bg-white/[0.015] px-5 py-4 text-xs text-zinc-600 sm:flex-row sm:items-center sm:justify-between">
              <div>{renderedSceneCount}/{result.scenes.length} scene previews rendered</div>
              <div>{allScenesRendered ? "Ready to combine without another GPU render" : "Missing scenes are rendered only when needed"}</div>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

function FinalVideoCard({
  video,
  aspectRatio,
}: {
  video: NonNullable<FinalVideo>;
  aspectRatio: AspectRatio;
}) {
  return (
    <div className="overflow-hidden rounded-3xl border border-white/[0.1] bg-[#101113]">
      <div className="flex flex-col gap-3 border-b border-white/[0.07] px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
            Final render
            <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[10px] font-medium text-emerald-400">Ready</span>
          </div>
          <div className="mt-1 text-xs text-zinc-600">{video.label}</div>
          <div className="mt-1 text-[11px] text-zinc-700">
            {video.dimensions} · {video.hasAudio ? `audio ${video.audioCodec || "present"}` : "no audio stream"}
            {video.gpu ? ` · ${video.gpu}` : ""}
            {video.estimatedCostUsd != null ? ` · est. $${video.estimatedCostUsd.toFixed(4)}` : ""}
          </div>
        </div>
        <a
          href={video.downloadUrl}
          className="flex h-10 items-center justify-center gap-2 rounded-xl bg-white px-4 text-xs font-medium text-black transition hover:bg-zinc-200"
        >
          <DownloadIcon /> Download MP4
        </a>
      </div>

      <div className={`mx-auto bg-black ${aspectRatio === "9:16" ? "max-w-[430px]" : aspectRatio === "1:1" ? "max-w-[760px]" : "w-full"}`}>
        <video src={video.url} controls playsInline className={`w-full object-contain ${aspectClass(aspectRatio)}`} />
      </div>

      <div className="border-t border-white/[0.07] px-5 py-4 text-[11px] leading-5 text-zinc-600 sm:px-6">
        {video.qualityNote}
      </div>
    </div>
  );
}
