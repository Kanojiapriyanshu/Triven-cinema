"use client";

import {
  FormEvent,
  useMemo,
  useState,
} from "react";

import {
  API_URL,
  generateFullVideo,
  generateScenePlan,
  generateVideo,
} from "@/lib/api/cinema";

import type {
  AspectRatio,
  ScenePlanResponse,
} from "@/lib/types/generation";


type ScenePromptMap = Record<number, string>;


function Spinner({
  size = "sm",
}: {
  size?: "sm" | "md";
}) {
  const dimensions =
    size === "md"
      ? "h-5 w-5"
      : "h-4 w-4";

  return (
    <span
      className={`${dimensions} inline-block animate-spin rounded-full border-2 border-current border-r-transparent`}
    />
  );
}


function IconPlay() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <path
        d="M8.5 6.5L17 12L8.5 17.5V6.5Z"
        fill="currentColor"
      />
    </svg>
  );
}


function IconDownload() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <path
        d="M12 4V15M12 15L8 11M12 15L16 11M5 19H19"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}


function IconSparkles() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <path
        d="M12 3L13.4 7.6L18 9L13.4 10.4L12 15L10.6 10.4L6 9L10.6 7.6L12 3Z"
        fill="currentColor"
      />

      <path
        d="M18.5 14L19.2 16.3L21.5 17L19.2 17.7L18.5 20L17.8 17.7L15.5 17L17.8 16.3L18.5 14Z"
        fill="currentColor"
      />
    </svg>
  );
}


function getAspectClass(
  aspectRatio: AspectRatio
) {
  if (aspectRatio === "9:16") {
    return "aspect-[9/16]";
  }

  if (aspectRatio === "1:1") {
    return "aspect-square";
  }

  return "aspect-video";
}


export default function Home() {
  const [prompt, setPrompt] =
    useState("");

  const [aspectRatio, setAspectRatio] =
    useState<AspectRatio>("16:9");

  const [sceneCount, setSceneCount] =
    useState(2);

  const [result, setResult] =
    useState<ScenePlanResponse | null>(
      null
    );

  const [scenePrompts, setScenePrompts] =
    useState<ScenePromptMap>({});

  const [
    editingScene,
    setEditingScene,
  ] = useState<number | null>(null);

  const [planning, setPlanning] =
    useState(false);

  const [
    generatingScene,
    setGeneratingScene,
  ] = useState<number | null>(null);

  const [
    generatingFullVideo,
    setGeneratingFullVideo,
  ] = useState(false);

  const [
    generatedVideos,
    setGeneratedVideos,
  ] = useState<
    Record<number, string>
  >({});

  const [
    finalVideo,
    setFinalVideo,
  ] = useState<string | null>(null);

  const [error, setError] =
    useState("");


  const isBusy =
    planning ||
    generatingScene !== null ||
    generatingFullVideo;


  const renderedSceneCount =
    Object.keys(
      generatedVideos
    ).length;


  const plannedDuration =
    useMemo(() => {
      if (!result) {
        return 0;
      }

      return result.scenes.reduce(
        (total, scene) =>
          total +
          scene.duration_seconds,
        0
      );
    }, [result]);


  async function handleSubmit(
    event: FormEvent
  ) {
    event.preventDefault();

    const cleanPrompt =
      prompt.trim();

    if (!cleanPrompt) {
      setError(
        "Describe the video you want to create."
      );
      return;
    }

    try {
      setPlanning(true);
      setError("");

      setResult(null);
      setScenePrompts({});
      setGeneratedVideos({});
      setFinalVideo(null);
      setEditingScene(null);

      const response =
        await generateScenePlan({
          prompt: cleanPrompt,
          aspect_ratio:
            aspectRatio,
          scene_count:
            sceneCount,
        });

      setResult(response);

      const prompts =
        response.scenes.reduce(
          (
            current,
            scene
          ) => {
            current[scene.id] =
              scene.prompt;

            return current;
          },
          {} as ScenePromptMap
        );

      setScenePrompts(
        prompts
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to create the storyboard."
      );
    } finally {
      setPlanning(false);
    }
  }


  async function handleGenerateVideo(
    sceneId: number
  ) {
    if (!result) {
      return;
    }

    const scenePrompt =
      scenePrompts[
        sceneId
      ]?.trim();

    if (!scenePrompt) {
      setError(
        "This scene needs a prompt before it can be rendered."
      );
      return;
    }

    try {
      setGeneratingScene(
        sceneId
      );

      setError("");

      const response =
        await generateVideo({
          prompt:
            scenePrompt,

          aspect_ratio:
            result.aspect_ratio,

          // Development preview.
          duration_seconds: 1,

          seed:
            42 + sceneId - 1,

          decoder: "conv",
        });

      setGeneratedVideos(
        (current) => ({
          ...current,

          [sceneId]:
            `${API_URL}${response.video_url}`,
        })
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Scene rendering failed."
      );
    } finally {
      setGeneratingScene(
        null
      );
    }
  }


  async function handleGenerateFullVideo() {
    if (!result) {
      return;
    }

    try {
      setGeneratingFullVideo(
        true
      );

      setFinalVideo(null);
      setError("");

      const scenes =
        result.scenes.map(
          (scene) => ({
            id: scene.id,

            prompt:
              scenePrompts[
                scene.id
              ]?.trim() ||
              scene.prompt,
          })
        );

      const response =
        await generateFullVideo({
          scenes,

          aspect_ratio:
            result.aspect_ratio,

          // Keep at 1s while
          // testing ZeroGPU.
          duration_seconds: 1,

          seed: 42,

          decoder: "conv",
        });

      setFinalVideo(
        `${API_URL}${response.final_video_url}`
      );

      const individualVideos =
        response.scene_video_urls.reduce(
          (
            current,
            url,
            index
          ) => {
            const scene =
              result.scenes[
                index
              ];

            if (scene) {
              current[
                scene.id
              ] =
                `${API_URL}${url}`;
            }

            return current;
          },
          {} as Record<
            number,
            string
          >
        );

      setGeneratedVideos(
        individualVideos
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Full video generation failed."
      );
    } finally {
      setGeneratingFullVideo(
        false
      );
    }
  }


  function updateScenePrompt(
    sceneId: number,
    value: string
  ) {
    setScenePrompts(
      (current) => ({
        ...current,
        [sceneId]: value,
      })
    );

    setGeneratedVideos(
      (current) => {
        const next = {
          ...current,
        };

        delete next[
          sceneId
        ];

        return next;
      }
    );

    setFinalVideo(null);
  }


  return (
    <main className="min-h-screen bg-[#070809] text-white">
      {/* Background */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-[-420px] h-[760px] w-[760px] -translate-x-1/2 rounded-full bg-white/[0.035] blur-[120px]" />

        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,#070809_75%)]" />
      </div>


      <div className="relative mx-auto w-full max-w-[1440px] px-5 pb-24 sm:px-8 lg:px-12">
        {/* Header */}
        <header className="flex h-20 items-center justify-between border-b border-white/[0.06]">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white text-sm font-bold text-black">
              T
            </div>

            <div>
              <div className="text-sm font-semibold tracking-[-0.02em]">
                Triven Cinema
              </div>

              <div className="text-[11px] text-zinc-600">
                AI video studio
              </div>
            </div>
          </div>


          <div className="flex items-center gap-2">
            <div className="hidden items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.025] px-3 py-1.5 text-xs text-zinc-500 sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />

              LTX 2.5
            </div>

            <div className="rounded-full border border-white/[0.08] bg-white/[0.025] px-3 py-1.5 text-xs text-zinc-500">
              Development
            </div>
          </div>
        </header>


        {/* Hero */}
        <section className="mx-auto max-w-4xl pb-12 pt-20 text-center sm:pt-28">
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.025] px-3 py-1.5 text-xs text-zinc-400">
            <IconSparkles />

            Text to cinematic video
          </div>

          <h1 className="text-balance text-4xl font-medium tracking-[-0.055em] text-zinc-50 sm:text-6xl lg:text-[68px] lg:leading-[1.02]">
            Create the scene
            <span className="block text-zinc-500">
              you are imagining.
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-pretty text-sm leading-7 text-zinc-500 sm:text-base">
            Describe your idea.
            Triven structures the
            storyboard, renders each
            shot with LTX and assembles
            everything into one video.
          </p>
        </section>


        {/* Composer */}
        <section className="mx-auto max-w-5xl">
          <form
            onSubmit={handleSubmit}
            className="overflow-hidden rounded-[28px] border border-white/[0.1] bg-[#111214] shadow-[0_32px_100px_rgba(0,0,0,0.45)]"
          >
            <textarea
              value={prompt}
              onChange={(
                event
              ) =>
                setPrompt(
                  event.target
                    .value
                )
              }
              placeholder="Describe a scene, story, advertisement or cinematic sequence..."
              rows={7}
              disabled={isBusy}
              className="w-full resize-none bg-transparent px-7 py-7 text-[15px] leading-7 text-zinc-100 outline-none placeholder:text-zinc-650 disabled:opacity-70 sm:px-8 sm:py-8"
            />

            <div className="flex flex-col gap-4 border-t border-white/[0.07] bg-black/10 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap gap-2">
                <div className="flex h-10 items-center rounded-xl border border-white/[0.08] bg-[#0c0d0f] px-3.5 text-xs text-zinc-400">
                  LTX 2.5
                </div>

                <select
                  value={
                    aspectRatio
                  }
                  disabled={
                    isBusy
                  }
                  onChange={(
                    event
                  ) =>
                    setAspectRatio(
                      event.target
                        .value as AspectRatio
                    )
                  }
                  className="h-10 rounded-xl border border-white/[0.08] bg-[#0c0d0f] px-3.5 text-xs text-zinc-300 outline-none disabled:opacity-50"
                >
                  <option value="16:9">
                    16:9 Landscape
                  </option>

                  <option value="9:16">
                    9:16 Portrait
                  </option>

                  <option value="1:1">
                    1:1 Square
                  </option>
                </select>

                <select
                  value={
                    sceneCount
                  }
                  disabled={
                    isBusy
                  }
                  onChange={(
                    event
                  ) =>
                    setSceneCount(
                      Number(
                        event.target
                          .value
                      )
                    )
                  }
                  className="h-10 rounded-xl border border-white/[0.08] bg-[#0c0d0f] px-3.5 text-xs text-zinc-300 outline-none disabled:opacity-50"
                >
                  {[
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                  ].map(
                    (count) => (
                      <option
                        key={count}
                        value={
                          count
                        }
                      >
                        {count}{" "}
                        {count ===
                        1
                          ? "Scene"
                          : "Scenes"}
                      </option>
                    )
                  )}
                </select>
              </div>


              <button
                type="submit"
                disabled={
                  planning ||
                  !prompt.trim()
                }
                className="flex h-11 items-center justify-center gap-2 rounded-xl bg-white px-6 text-sm font-medium text-black transition hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {planning ? (
                  <>
                    <Spinner />

                    Planning
                  </>
                ) : (
                  <>
                    <IconSparkles />

                    Create storyboard
                  </>
                )}
              </button>
            </div>
          </form>


          {error && (
            <div className="mt-4 flex items-start gap-3 rounded-xl border border-red-500/15 bg-red-500/[0.06] px-4 py-3 text-sm text-red-300">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-red-400" />

              {error}
            </div>
          )}
        </section>


        {/* Storyboard */}
        {result && (
          <section className="mx-auto mt-20 max-w-7xl">
            {/* Section header */}
            <div className="mb-7 flex flex-col gap-5 border-b border-white/[0.07] pb-7 md:flex-row md:items-end md:justify-between">
              <div>
                <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.22em] text-zinc-600">
                  Storyboard
                </div>

                <h2 className="text-2xl font-medium tracking-[-0.025em] text-zinc-100">
                  Your generated
                  scenes
                </h2>

                <p className="mt-2 text-sm text-zinc-600">
                  {result.scenes.length}{" "}
                  scenes
                  {" · "}
                  {result.aspect_ratio}
                  {" · "}
                  {plannedDuration}s
                  planned
                  {" · "}
                  1s development
                  previews
                </p>
              </div>


              <button
                type="button"
                onClick={
                  handleGenerateFullVideo
                }
                disabled={
                  isBusy
                }
                className="flex h-11 items-center justify-center gap-2 rounded-xl bg-white px-5 text-sm font-medium text-black transition hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {generatingFullVideo ? (
                  <>
                    <Spinner />

                    Rendering full
                    video
                  </>
                ) : (
                  <>
                    <IconPlay />

                    Generate full
                    video
                  </>
                )}
              </button>
            </div>


            {/* Full video render */}
            {generatingFullVideo && (
              <div className="mb-8 overflow-hidden rounded-3xl border border-white/[0.08] bg-[#101113]">
                <div className="flex min-h-[280px] items-center justify-center px-6 py-12">
                  <div className="max-w-lg text-center">
                    <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-2xl border border-white/[0.08] bg-white/[0.035] text-zinc-200">
                      <Spinner
                        size="md"
                      />
                    </div>

                    <h3 className="text-lg font-medium text-zinc-100">
                      Creating your
                      final video
                    </h3>

                    <p className="mt-2 text-sm leading-6 text-zinc-500">
                      LTX is rendering
                      each scene. Once
                      the clips are
                      ready, FFmpeg
                      will combine them
                      into the final
                      sequence.
                    </p>

                    <div className="mx-auto mt-7 flex max-w-sm items-center gap-2">
                      {result.scenes.map(
                        (
                          scene,
                          index
                        ) => (
                          <div
                            key={
                              scene.id
                            }
                            className="flex flex-1 items-center gap-2"
                          >
                            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                              <div
                                className="h-full animate-pulse rounded-full bg-zinc-500"
                                style={{
                                  animationDelay:
                                    `${index * 150}ms`,
                                }}
                              />
                            </div>
                          </div>
                        )
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}


            {finalVideo && (
              <div className="mb-10 overflow-hidden rounded-3xl border border-white/[0.1] bg-[#101113]">
                <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4 sm:px-6">
                  <div>
                    <div className="text-sm font-medium text-zinc-100">
                      Final render
                    </div>

                    <div className="mt-1 text-xs text-zinc-600">
                      {result.scenes.length}{" "}
                      scenes combined
                      with FFmpeg
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-400">
                      Ready
                    </span>
                  </div>
                </div>


                <div
                  className={`mx-auto overflow-hidden bg-black ${
                    result.aspect_ratio ===
                    "9:16"
                      ? "max-w-[430px]"
                      : result.aspect_ratio ===
                        "1:1"
                      ? "max-w-[760px]"
                      : "w-full"
                  }`}
                >
                  <video
                    src={
                      finalVideo
                    }
                    controls
                    playsInline
                    className={`w-full object-contain ${getAspectClass(
                      result.aspect_ratio
                    )}`}
                  />
                </div>


                <div className="flex flex-wrap items-center gap-3 border-t border-white/[0.07] px-5 py-4 sm:px-6">
                  <a
                    href={
                      finalVideo
                    }
                    target="_blank"
                    rel="noreferrer"
                    className="flex h-10 items-center gap-2 rounded-xl bg-white px-4 text-xs font-medium text-black transition hover:bg-zinc-200"
                  >
                    <IconDownload />

                    Open final video
                  </a>

                  <button
                    type="button"
                    onClick={
                      handleGenerateFullVideo
                    }
                    disabled={
                      isBusy
                    }
                    className="h-10 rounded-xl border border-white/[0.08] px-4 text-xs font-medium text-zinc-400 transition hover:bg-white/[0.04] hover:text-zinc-200 disabled:opacity-40"
                  >
                    Regenerate
                  </button>
                </div>
              </div>
            )}


            {/* Scene grid */}
            <div className="grid gap-5 lg:grid-cols-2">
              {result.scenes.map(
                (
                  scene,
                  index
                ) => {
                  const video =
                    generatedVideos[
                      scene.id
                    ];

                  const isGenerating =
                    generatingScene ===
                    scene.id;

                  const isEditing =
                    editingScene ===
                    scene.id;

                  return (
                    <article
                      key={
                        scene.id
                      }
                      className="overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0d0e10]"
                    >
                      {/* Scene media */}
                      {video ? (
                        <div className="bg-black">
                          <video
                            src={
                              video
                            }
                            controls
                            playsInline
                            className={`w-full object-contain ${getAspectClass(
                              result.aspect_ratio
                            )}`}
                          />
                        </div>
                      ) : (
                        <div
                          className={`relative flex items-center justify-center overflow-hidden bg-[#111214] ${getAspectClass(
                            result.aspect_ratio
                          )}`}
                        >
                          <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.04),transparent_60%)]" />

                          {isGenerating ? (
                            <div className="relative text-center">
                              <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-2xl border border-white/[0.08] bg-black/30 text-zinc-300">
                                <Spinner
                                  size="md"
                                />
                              </div>

                              <div className="text-sm font-medium text-zinc-300">
                                Rendering
                                scene
                              </div>

                              <div className="mt-1 text-xs text-zinc-600">
                                LTX 2.5 ·
                                ZeroGPU
                              </div>
                            </div>
                          ) : (
                            <div className="relative text-center">
                              <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-white/[0.08] text-zinc-600">
                                <IconPlay />
                              </div>

                              <div className="mt-3 text-xs text-zinc-650">
                                Not
                                rendered
                                yet
                              </div>
                            </div>
                          )}
                        </div>
                      )}


                      {/* Scene content */}
                      <div className="p-5 sm:p-6">
                        <div className="flex items-start justify-between gap-4">
                          <div className="min-w-0">
                            <div className="mb-2 text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-650">
                              Scene{" "}
                              {String(
                                index +
                                  1
                              ).padStart(
                                2,
                                "0"
                              )}
                            </div>

                            <h3 className="truncate text-base font-medium text-zinc-200">
                              {
                                scene.title
                              }
                            </h3>
                          </div>


                          <div className="shrink-0 rounded-lg border border-white/[0.07] bg-white/[0.025] px-2.5 py-1 text-[10px] text-zinc-600">
                            {
                              scene.duration_seconds
                            }
                            s plan
                          </div>
                        </div>


                        {isEditing ? (
                          <textarea
                            value={
                              scenePrompts[
                                scene.id
                              ] ||
                              ""
                            }
                            onChange={(
                              event
                            ) =>
                              updateScenePrompt(
                                scene.id,
                                event
                                  .target
                                  .value
                              )
                            }
                            rows={8}
                            className="mt-5 w-full resize-none rounded-xl border border-white/[0.08] bg-[#090a0b] p-4 text-sm leading-6 text-zinc-300 outline-none transition focus:border-white/[0.18]"
                          />
                        ) : (
                          <p className="mt-5 line-clamp-6 text-sm leading-6 text-zinc-500">
                            {
                              scenePrompts[
                                scene.id
                              ]
                            }
                          </p>
                        )}


                        <div className="mt-6 flex items-center justify-between gap-3 border-t border-white/[0.06] pt-4">
                          <button
                            type="button"
                            disabled={
                              isBusy &&
                              !isEditing
                            }
                            onClick={() =>
                              setEditingScene(
                                isEditing
                                  ? null
                                  : scene.id
                              )
                            }
                            className="h-9 rounded-lg px-3 text-xs font-medium text-zinc-500 transition hover:bg-white/[0.04] hover:text-zinc-300"
                          >
                            {isEditing
                              ? "Done editing"
                              : "Edit prompt"}
                          </button>


                          <button
                            type="button"
                            disabled={
                              isBusy
                            }
                            onClick={() =>
                              handleGenerateVideo(
                                scene.id
                              )
                            }
                            className="flex h-9 items-center gap-2 rounded-lg bg-white px-4 text-xs font-medium text-black transition hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            {isGenerating ? (
                              <>
                                <Spinner />

                                Rendering
                              </>
                            ) : video ? (
                              <>
                                <IconPlay />

                                Regenerate
                              </>
                            ) : (
                              <>
                                <IconPlay />

                                Render
                                preview
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                }
              )}
            </div>


            {/* Bottom summary */}
            <div className="mt-6 flex flex-col gap-3 rounded-2xl border border-white/[0.06] bg-white/[0.015] px-5 py-4 text-xs text-zinc-600 sm:flex-row sm:items-center sm:justify-between">
              <div>
                {
                  renderedSceneCount
                }
                /{result.scenes.length}{" "}
                scene previews rendered
              </div>

              <div>
                Development mode ·
                1 second per rendered
                scene · conv decoder
              </div>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}