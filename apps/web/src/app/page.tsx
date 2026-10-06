"use client";

import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  absoluteApiUrl,
  addElementAssets,
  archiveElement,
  combineSceneVideos,
  connectYouTube,
  createElement,
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
  listElements,
  updateElement,
  verifyCheckout,
  waitForFactoryGenerationJob,
  waitForVideoGenerationJob,
} from "@/lib/api/cinema";
import type {
  AspectRatio,
  AudioMode,
  BillingCatalogResponse,
  BillingMeResponse,
  CinemaElement,
  ContinuityMode,
  ElementBinding,
  ElementReferenceMode,
  ElementType,
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
type DirectorTab = "scene" | "camera" | "look" | "elements";
type CameraMove = "auto" | "static" | "dolly-in" | "dolly-out" | "pan-left" | "pan-right" | "tilt-up" | "tilt-down" | "orbit";
type LensPreset = "auto" | "18mm" | "24mm" | "35mm" | "50mm" | "85mm";
type ShotSize = "auto" | "wide" | "medium" | "close-up" | "extreme-close-up" | "over-the-shoulder";
type GenrePreset = "auto" | "general" | "drama" | "epic" | "action" | "comedy" | "horror";
type ColorPreset = "auto" | "neutral" | "warm" | "golden-hour" | "cool" | "moonlight" | "high-contrast";
type TempoPreset = "auto" | "slow" | "measured" | "dynamic";

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
  preview: [5, 10, 15, 20],
  "1080p": [5, 10, 15, 20, 30],
  "4k": [5, 10, 15],
};

const FACTORY_SCENE_OPTIONS: Record<RenderQuality, number[]> = {
  preview: [15, 20],
  "1080p": [15, 20, 30],
  "4k": [15],
};

const FACTORY_TARGETS = [30, 60, 120, 180, 300];

const CAMERA_MOVES: Array<{ value: CameraMove; label: string }> = [
  { value: "auto", label: "Auto" },
  { value: "static", label: "Static" },
  { value: "dolly-in", label: "Dolly In" },
  { value: "dolly-out", label: "Dolly Out" },
  { value: "pan-left", label: "Pan Left" },
  { value: "pan-right", label: "Pan Right" },
  { value: "tilt-up", label: "Tilt Up" },
  { value: "tilt-down", label: "Tilt Down" },
  { value: "orbit", label: "Orbit" },
];

const LENS_PRESETS: LensPreset[] = ["auto", "18mm", "24mm", "35mm", "50mm", "85mm"];
const SHOT_SIZES: Array<{ value: ShotSize; label: string }> = [
  { value: "auto", label: "Auto framing" },
  { value: "wide", label: "Wide" },
  { value: "medium", label: "Medium" },
  { value: "close-up", label: "Close-up" },
  { value: "extreme-close-up", label: "Extreme close-up" },
  { value: "over-the-shoulder", label: "Over the shoulder" },
];
const GENRE_PRESETS: GenrePreset[] = ["auto", "general", "drama", "epic", "action", "comedy", "horror"];
const COLOR_PRESETS: ColorPreset[] = ["auto", "neutral", "warm", "golden-hour", "cool", "moonlight", "high-contrast"];
const TEMPO_PRESETS: TempoPreset[] = ["auto", "slow", "measured", "dynamic"];

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

function GridIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true"><rect x="4" y="4" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.6"/><rect x="14" y="4" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.6"/><rect x="4" y="14" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.6"/><rect x="14" y="14" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.6"/></svg>;
}

function ElementsIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true"><circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.6"/><rect x="13" y="5" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.6"/><path d="M5 18h14M8 15v6M16 15v6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>;
}

function FilmIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true"><rect x="3.5" y="5" width="17" height="14" rx="2.2" stroke="currentColor" strokeWidth="1.6"/><path d="M8 5v14M16 5v14M3.5 9h4.5M3.5 15h4.5M16 9h4.5M16 15h4.5" stroke="currentColor" strokeWidth="1.35"/></svg>;
}

function SparkIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true"><path d="M12 3.5c.7 4.4 2.1 5.8 6.5 6.5-4.4.7-5.8 2.1-6.5 6.5-.7-4.4-2.1-5.8-6.5-6.5 4.4-.7 5.8-2.1 6.5-6.5Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/><path d="M18.5 15.5c.25 1.65.85 2.25 2.5 2.5-1.65.25-2.25.85-2.5 2.5-.25-1.65-.85-2.25-2.5-2.5 1.65-.25 2.25-.85 2.5-2.5Z" fill="currentColor"/></svg>;
}

function PlusIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true"><path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>;
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

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function hasElementMention(text: string, handle: string) {
  return new RegExp(`(^|[^A-Za-z0-9_])@${escapeRegExp(handle)}\\b`, "i").test(text);
}

function primaryElementAsset(element: CinemaElement) {
  return element.assets.find((asset) => asset.id === element.primary_asset_id) || element.assets[0] || null;
}

function elementTone(type: ElementType) {
  if (type === "character") return "element-character";
  if (type === "prop") return "element-prop";
  if (type === "location") return "element-location";
  return "element-style";
}

function PromptHighlight({ text, elements }: { text: string; elements: CinemaElement[] }) {
  const byHandle = new Map(elements.map((element) => [element.handle.toLowerCase(), element]));
  const parts = text.split(/(@[A-Za-z0-9_-]+)/g);
  return (
    <div className="studio-prompt-highlight" aria-hidden="true">
      {parts.map((part, index) => {
        if (!part.startsWith("@")) return <span key={`${index}-${part.slice(0, 8)}`}>{part}</span>;
        const element = byHandle.get(part.slice(1).toLowerCase());
        if (!element) return <span key={`${index}-${part}`}>{part}</span>;
        return <span key={`${index}-${part}`} className={`studio-inline-mention ${elementTone(element.type)}`}>{part}</span>;
      })}
    </div>
  );
}

export default function Home() {
  const [theme, setTheme] = useState<ThemeMode>("light");
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<GenerationMode>("factory");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("16:9");
  const [sceneCount, setSceneCount] = useState(2);
  const [durationSeconds, setDurationSeconds] = useState(15);
  const [factoryTargetSeconds, setFactoryTargetSeconds] = useState(30);
  const [factorySceneSeconds, setFactorySceneSeconds] = useState(20);
  const [quality, setQuality] = useState<RenderQuality>("1080p");
  const [audioMode, setAudioMode] = useState<AudioMode>("mastered");
  const [audioDirection, setAudioDirection] = useState("Natural synchronized ambience and Foley matching every visible action.");
  const provider: VideoProviderName = "modal";
  const model: VideoModelName = "ltx-2.5";
  const [decoder, setDecoder] = useState<DecoderName>("conv");
  const [seed, setSeed] = useState(42);
  const [enhancePrompt, setEnhancePrompt] = useState(false);
  const [continuityMode, setContinuityMode] = useState<ContinuityMode>("strict");

  // Cinema Studio-style director controls. Defaults are intentionally "auto" so
  // prompt-only mode remains byte-for-byte user-authored until the creator opts in.
  const [directorTab, setDirectorTab] = useState<DirectorTab>("scene");
  const [cameraMove, setCameraMove] = useState<CameraMove>("auto");
  const [lensPreset, setLensPreset] = useState<LensPreset>("auto");
  const [shotSize, setShotSize] = useState<ShotSize>("auto");
  const [genrePreset, setGenrePreset] = useState<GenrePreset>("auto");
  const [colorPreset, setColorPreset] = useState<ColorPreset>("auto");
  const [tempoPreset, setTempoPreset] = useState<TempoPreset>("auto");
  const [showReferencePicker, setShowReferencePicker] = useState(false);
  const [showElementsLibrary, setShowElementsLibrary] = useState(false);

  const [elements, setElements] = useState<CinemaElement[]>([]);
  const [elementsLoading, setElementsLoading] = useState(false);
  const [elementBusy, setElementBusy] = useState(false);
  const [showElementCreator, setShowElementCreator] = useState(false);
  const [elementName, setElementName] = useState("");
  const [elementHandle, setElementHandle] = useState("");
  const [elementType, setElementType] = useState<ElementType>("character");
  const [elementFilter, setElementFilter] = useState<"all" | ElementType>("all");
  const [elementSearch, setElementSearch] = useState("");
  const [selectedElementId, setSelectedElementId] = useState<string | null>(null);
  const [elementDescription, setElementDescription] = useState("");
  const [elementFiles, setElementFiles] = useState<File[]>([]);
  const [elementModes, setElementModes] = useState<Record<string, ElementReferenceMode>>({});
  const [elementApplyAll, setElementApplyAll] = useState<Record<string, boolean>>({});
  const [elementStrengths, setElementStrengths] = useState<Record<string, number>>({});
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);

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
  const factoryDurationOptions = FACTORY_SCENE_OPTIONS[quality];
  const isBusy = planning || directGenerating || factoryGenerating || generatingScene !== null || creatingFinal;
  const renderedSceneCount = Object.keys(renderedVideos).length;
  const allScenesRendered = !!result && result.scenes.length > 0 && result.scenes.every((scene) => Boolean(renderedVideos[scene.id]));
  const plannedDuration = useMemo(() => result ? result.scenes.length * durationSeconds : 0, [result, durationSeconds]);
  const filteredElements = useMemo(() => {
    const query = elementSearch.trim().toLowerCase();
    return elements.filter((element) => {
      if (elementFilter !== "all" && element.type !== elementFilter) return false;
      if (!query) return true;
      return element.name.toLowerCase().includes(query) || element.handle.toLowerCase().includes(query);
    });
  }, [elements, elementFilter, elementSearch]);
  const referencedElements = useMemo(
    () => elements.filter((element) => hasElementMention(prompt, element.handle) || Boolean(elementApplyAll[element.id])),
    [elements, prompt, elementApplyAll]
  );
  const activeElementLimit = capabilities?.elements?.max_active_per_scene ?? 6;
  const elementBindings = useMemo<ElementBinding[]>(
    () => referencedElements.slice(0, activeElementLimit).map((element) => ({
      element_id: element.id,
      version_id: element.current_version_id,
      handle: element.handle,
      reference_mode: elementModes[element.id] || "identity",
      strength: elementStrengths[element.id] ?? 1.0,
      apply_to_all_scenes: Boolean(elementApplyAll[element.id]),
    })),
    [referencedElements, activeElementLimit, elementModes, elementStrengths, elementApplyAll]
  );
  const mentionSuggestions = useMemo(() => {
    if (mentionQuery == null) return [];
    const query = mentionQuery.toLowerCase();
    return elements.filter((element) =>
      element.handle.toLowerCase().startsWith(query) || element.name.toLowerCase().includes(query)
    ).slice(0, 8);
  }, [mentionQuery, elements]);
  const selectedElement = useMemo(
    () => elements.find((element) => element.id === selectedElementId) || referencedElements[0] || null,
    [elements, selectedElementId, referencedElements]
  );
  const studioPreviewElement = selectedElement || referencedElements[0] || null;
  const studioPreviewAsset = studioPreviewElement ? primaryElementAsset(studioPreviewElement) : null;
  const characterElements = useMemo(() => elements.filter((element) => element.type === "character"), [elements]);
  const latestRenderedVideo = useMemo(() => {
    const values = Object.values(renderedVideos);
    return values.length ? values[values.length - 1] : null;
  }, [renderedVideos]);
  const studioVideoUrl = finalVideo?.url || latestRenderedVideo?.url || null;

  useEffect(() => {
    const storedTheme = window.localStorage.getItem("triven-cinema-theme");
    const initialTheme: ThemeMode = storedTheme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = initialTheme;
    if (initialTheme !== theme) {
      const timer = window.setTimeout(() => setTheme(initialTheme), 0);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [theme]);

  function selectTheme(nextTheme: ThemeMode) {
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
    window.localStorage.setItem("triven-cinema-theme", nextTheme);
  }

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      setElementsLoading(true);
      const [caps, catalog, billing, yt, elementList] = await Promise.allSettled([
        getGenerationCapabilities(),
        getBillingCatalog(),
        getBillingMe(),
        getYouTubeStatus(),
        listElements(),
      ]);
      if (!active) return;
      if (caps.status === "fulfilled") setCapabilities(caps.value);
      if (catalog.status === "fulfilled") setBillingCatalog(catalog.value);
      if (billing.status === "fulfilled") setBillingMe(billing.value);
      if (yt.status === "fulfilled") setYoutube(yt.value);
      if (elementList.status === "fulfilled") setElements(elementList.value.elements);
      setElementsLoading(false);

      const params = new URLSearchParams(window.location.search);
      const sessionId = params.get("session_id");
      if (params.get("checkout") === "success" && sessionId) {
        try {
          const status = await verifyCheckout(sessionId);
          if (!active) return;
          setNotice(status.paid ? `Payment confirmed. ${formatCredits(status.balance_seconds)} generation credits available.` : "Payment is still processing.");
          setBillingMe(await getBillingMe());
        } catch (err) {
          if (active) setError(errorMessage(err, "Unable to verify payment."));
        }
      }
      if (params.get("youtube") === "connected") {
        if (!active) return;
        setNotice("YouTube channel connected. Factory jobs can now publish automatically.");
        try {
          const status = await getYouTubeStatus();
          if (active) setYoutube(status);
        } catch {
          // Connection succeeded; status refresh can recover on the next bootstrap.
        }
      }
      if (params.has("checkout") || params.has("youtube")) {
        window.history.replaceState({}, "", window.location.pathname);
      }
    }
    void bootstrap();
    return () => { active = false; };
  }, []);

  function handleQualityChange(nextQuality: RenderQuality) {
    setQuality(nextQuality);
    const options = DURATION_OPTIONS[nextQuality];
    const factoryOptions = FACTORY_SCENE_OPTIONS[nextQuality];
    setDurationSeconds((current) => options.includes(current) ? current : options[Math.min(2, options.length - 1)]);
    setFactorySceneSeconds((current) => factoryOptions.includes(current) ? current : factoryOptions[factoryOptions.length - 1]);
    invalidateRenderedMedia();
  }

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

  async function refreshElements() {
    setElementsLoading(true);
    try {
      const response = await listElements();
      setElements(response.elements);
    } finally {
      setElementsLoading(false);
    }
  }

  function updateMentionState(value: string) {
    setPrompt(value);
    const match = value.match(/(?:^|\s)@([A-Za-z0-9_-]*)$/);
    setMentionQuery(match ? match[1] : null);
  }

  function canActivateElement(element: CinemaElement) {
    const alreadyActive = hasElementMention(prompt, element.handle) || Boolean(elementApplyAll[element.id]);
    if (alreadyActive) return true;
    if (referencedElements.length >= activeElementLimit) {
      setError(`This LTX profile allows ${activeElementLimit} active Elements in one scene. Remove a reference before adding @${element.handle}.`);
      return false;
    }
    return true;
  }

  function insertElementMention(element: CinemaElement) {
    if (!canActivateElement(element)) return;
    setSelectedElementId(element.id);
    const mention = `@${element.handle}`;
    if (!hasElementMention(prompt, element.handle)) {
      const spacer = prompt && !/\s$/.test(prompt) ? " " : "";
      setPrompt(`${prompt}${spacer}${mention} `);
    }
    setMentionQuery(null);
    setElementModes((current) => ({ ...current, [element.id]: current[element.id] || "identity" }));
    setElementStrengths((current) => ({ ...current, [element.id]: current[element.id] ?? 1.0 }));
    setElementApplyAll((current) => ({
      ...current,
      [element.id]: current[element.id] ?? (element.type === "character" || element.type === "style"),
    }));
  }

  function removeElementFromScene(element: CinemaElement) {
    const mentionPattern = new RegExp(`(^|\\s)@${escapeRegExp(element.handle)}\\b\\s*`, "gi");
    setPrompt((current) => current.replace(mentionPattern, "$1").replace(/ {2,}/g, " ").trimStart());
    setElementApplyAll((current) => ({ ...current, [element.id]: false }));
    if (selectedElementId === element.id) setSelectedElementId(null);
  }

  function promptWithDirectorControls(rawPrompt: string) {
    const directives: string[] = [];
    if (shotSize !== "auto") directives.push(`${shotSize.replaceAll("-", " ")} framing`);
    if (cameraMove !== "auto") directives.push(`${cameraMove.replaceAll("-", " ")} camera movement`);
    if (lensPreset !== "auto") directives.push(`${lensPreset} cinema lens`);
    if (genrePreset !== "auto") directives.push(`${genrePreset} genre language`);
    if (colorPreset !== "auto") directives.push(`${colorPreset.replaceAll("-", " ")} color palette`);
    if (tempoPreset !== "auto") directives.push(`${tempoPreset} performance tempo`);
    if (!directives.length) return rawPrompt.trim();
    return `${rawPrompt.trim()}\n\nDirector controls: ${directives.join("; ")}. Preserve all @Element identities and user-authored story details.`;
  }

  function chooseMention(element: CinemaElement) {
    if (mentionQuery == null || !canActivateElement(element)) return;
    setSelectedElementId(element.id);
    const next = prompt.replace(/@([A-Za-z0-9_-]*)$/, `@${element.handle} `);
    setPrompt(next);
    setMentionQuery(null);
    setElementModes((current) => ({ ...current, [element.id]: current[element.id] || "identity" }));
    setElementStrengths((current) => ({ ...current, [element.id]: current[element.id] ?? 1.0 }));
    setElementApplyAll((current) => ({
      ...current,
      [element.id]: current[element.id] ?? (element.type === "character" || element.type === "style"),
    }));
  }

  async function handleCreateElement() {
    if (!elementName.trim() || !elementHandle.trim() || elementFiles.length === 0) {
      setError("Element needs a name, @handle and at least one reference image.");
      return;
    }
    setElementBusy(true);
    setError("");
    try {
      const created = await createElement({
        name: elementName.trim(),
        handle: elementHandle.trim().replace(/^@/, ""),
        type: elementType,
        description: elementDescription.trim(),
        files: elementFiles,
      });
      await refreshElements();
      setSelectedElementId(created.id);
      setShowElementCreator(false);
      setElementName("");
      setElementHandle("");
      setElementDescription("");
      setElementFiles([]);
      insertElementMention(created);
      setNotice(`Saved @${created.handle} as a reusable ${created.type} Element.`);
    } catch (err) {
      setError(errorMessage(err, "Unable to create Element."));
    } finally {
      setElementBusy(false);
    }
  }

  async function handleAddElementReferences(element: CinemaElement, files: FileList | null) {
    if (!files?.length) return;
    setElementBusy(true);
    setError("");
    try {
      await addElementAssets(element.id, Array.from(files));
      await refreshElements();
      setNotice(`Added reference images to @${element.handle}. A new immutable Element version was created.`);
    } catch (err) {
      setError(errorMessage(err, "Unable to add Element references."));
    } finally {
      setElementBusy(false);
    }
  }

  async function handleSetPrimaryElementAsset(element: CinemaElement, assetId: string) {
    if (assetId === element.primary_asset_id) return;
    setElementBusy(true);
    setError("");
    try {
      await updateElement(element.id, { primary_asset_id: assetId });
      await refreshElements();
      setNotice(`Updated the canonical reference for @${element.handle}. A new immutable Element version was created.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update the canonical Element reference.");
    } finally {
      setElementBusy(false);
    }
  }

  async function handleArchiveElement(element: CinemaElement) {
    setElementBusy(true);
    setError("");
    try {
      await archiveElement(element.id);
      await refreshElements();
      setNotice(`Archived @${element.handle}. Existing renders remain tied to their saved version.`);
    } catch (err) {
      setError(errorMessage(err, "Unable to archive Element."));
    } finally {
      setElementBusy(false);
    }
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
        element_bindings: elementBindings,
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
    if (referencedElements.length > activeElementLimit) {
      setError(`This LTX profile allows ${activeElementLimit} active Elements in one scene. Remove ${referencedElements.length - activeElementLimit} reference${referencedElements.length - activeElementLimit === 1 ? "" : "s"} before generating.`);
      return;
    }
    setError("");
    setNotice("");
    resetOutput();
    const renderPrompt = promptWithDirectorControls(cleanPrompt);

    try {
      if (mode === "factory") {
        await handleFactory(renderPrompt);
        return;
      }
      if (mode === "direct") {
        setDirectGenerating(true);
        setProgressMessage("Rendering your prompt with LTX 2.5...");
        const response = await generateThroughJob({
          prompt: renderPrompt,
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
          element_bindings: elementBindings,
        });
        setFinalVideo(finalFromSceneResponse(response));
        await refreshBilling();
        return;
      }

      setPlanning(true);
      setProgressMessage("Creating continuity-locked storyboard shots with audio direction...");
      const response = await generateScenePlan({ prompt: renderPrompt, aspect_ratio: aspectRatio, scene_count: sceneCount });
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
      element_bindings: elementBindings,
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
      elementsUsed: response.elements_used,
      elementReferenceMode: response.element_reference_mode,
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
    <main className="cinema-studio-page bg-[var(--page-bg)] text-[var(--text)]">
      <header className="studio-topbar">
        <div className="studio-topbar-left">
          <div className="studio-logo-mark">T</div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-semibold text-[var(--text-strong)]">Untitled project</span>
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" title="Saved locally" />
            </div>
            <div className="text-[10px] text-[var(--text-muted)]">Triven Cinema Studio</div>
          </div>
        </div>

        <div className="studio-topbar-center">
          <span className="studio-model-pill">Cinema Studio · LTX 2.5</span>
          <span className="studio-model-pill studio-model-pill-muted">Modal {capabilities?.gpu || "B200"}</span>
        </div>

        <div className="studio-topbar-right">
          <div className="theme-switch" role="group" aria-label="Color theme">
            <button type="button" className={`theme-switch-option ${theme === "light" ? "theme-switch-option-active" : ""}`} onClick={() => selectTheme("light")} aria-pressed={theme === "light"}>
              <SunIcon /><span>Light</span>
            </button>
            <button type="button" className={`theme-switch-option ${theme === "dark" ? "theme-switch-option-active" : ""}`} onClick={() => selectTheme("dark")} aria-pressed={theme === "dark"}>
              <MoonIcon /><span>Dark</span>
            </button>
          </div>
          {billingCatalog?.enabled && billingMe ? <span className="studio-status-pill">{formatCredits(billingMe.balance_seconds)} credits</span> : null}
          {youtube?.connected ? <span className="studio-status-pill">YouTube connected</span> : null}
        </div>
      </header>

      <div className="studio-workspace">
        <nav className="studio-sidebar" aria-label="Cinema Studio navigation">
          <button type="button" className="studio-nav-item studio-nav-item-active" onClick={() => { setShowElementsLibrary(false); setDirectorTab("scene"); }} title="Create">
            <SparkIcon /><span>Create</span>
          </button>
          <button type="button" className="studio-nav-item" onClick={() => setShowElementsLibrary(true)} title="My Elements">
            <ElementsIcon /><span>Elements</span>
          </button>
          <button type="button" className="studio-nav-item" onClick={() => document.getElementById("studio-output")?.scrollIntoView({ behavior: "smooth" })} title="Generations">
            <FilmIcon /><span>Takes</span>
          </button>
          <div className="studio-nav-spacer" />
          <button type="button" className="studio-nav-item" onClick={() => setDirectorTab("scene")} title="Production settings">
            <GridIcon /><span>Setup</span>
          </button>
        </nav>

        <section className="studio-main-column">
          <div className="studio-stage-shell">
            <div className="studio-stage-header">
              <div>
                <div className="text-xs font-semibold text-[var(--text-strong)]">Scene canvas</div>
                <div className="mt-0.5 text-[10px] text-[var(--text-muted)]">Characters are defined before generation. Prompts direct performance; Elements preserve identity.</div>
              </div>
              <div className="flex items-center gap-2">
                <span className="studio-mini-pill">{aspectRatio}</span>
                <span className="studio-mini-pill">{qualityLabel(quality)}</span>
                <span className="studio-mini-pill">{mode === "factory" ? `${factorySceneSeconds}s scene` : `${durationSeconds}s clip`}</span>
              </div>
            </div>

            <div className="studio-stage-area">
              <div className={`studio-canvas ${aspectRatio === "9:16" ? "studio-canvas-portrait" : aspectRatio === "1:1" ? "studio-canvas-square" : "studio-canvas-landscape"}`}>
                {studioVideoUrl ? (
                  <video src={studioVideoUrl} controls playsInline className="h-full w-full object-contain" />
                ) : studioPreviewAsset ? (
                  <img src={absoluteApiUrl(studioPreviewAsset.asset_url)} alt={studioPreviewElement?.name || "Element preview"} className="h-full w-full object-contain" />
                ) : (
                  <div className="studio-empty-stage">
                    <div className="studio-empty-orbit"><span>+</span></div>
                    <div className="mt-4 text-sm font-medium text-[var(--text-secondary)]">Build your cast, then describe the scene</div>
                    <div className="mt-1 max-w-sm text-center text-xs leading-5 text-[var(--text-muted)]">Upload a character or reference image, save it as an Element, then type <strong>@</strong> in the prompt to direct it.</div>
                    <button type="button" onClick={() => { setElementType("character"); setShowElementCreator(true); }} className="mt-4 studio-secondary-button">+ Create New Character</button>
                  </div>
                )}
              </div>
            </div>

            <div className="studio-transport-bar">
              <div className="flex items-center gap-3">
                <button type="button" className="studio-icon-button" aria-label="Play preview"><PlayIcon /></button>
                <span>00:00</span>
                <div className="studio-scrub-track"><span /></div>
                <span>{mode === "factory" ? `${factoryTargetSeconds}s` : `${durationSeconds}s`}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="studio-mini-pill">{provider}</span>
                <span className="studio-mini-pill">{decoder}</span>
              </div>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="studio-bottom-deck">
            <div className="studio-assets-grid">
              <section className="studio-asset-section">
                <div className="studio-section-title-row">
                  <div>
                    <div className="studio-section-title">Characters</div>
                    <div className="studio-section-subtitle">Reusable identities for the current production</div>
                  </div>
                  <span className="studio-count-pill">{characterElements.length}/{capabilities?.elements?.max_stored ?? 100}</span>
                </div>
                <div className="studio-cast-strip">
                  <button type="button" onClick={() => { setElementType("character"); setShowElementCreator(true); }} className="studio-create-character-card">
                    <span className="studio-create-character-plus">+</span>
                    <span>Create New Character</span>
                  </button>
                  {characterElements.map((element) => {
                    const asset = primaryElementAsset(element);
                    const active = hasElementMention(prompt, element.handle) || Boolean(elementApplyAll[element.id]);
                    return (
                      <button key={element.id} type="button" onClick={() => insertElementMention(element)} className={`studio-character-card ${active ? "studio-character-card-active" : ""}`}>
                        <span className="studio-character-avatar">{asset ? <img src={absoluteApiUrl(asset.asset_url)} alt={element.name} /> : <span>{element.name.slice(0, 1)}</span>}</span>
                        <span className="max-w-[82px] truncate text-[10px] font-medium text-[var(--text-secondary)]">{element.name}</span>
                        <span className={`text-[9px] ${elementTone(element.type)}`}>@{element.handle}</span>
                      </button>
                    );
                  })}
                </div>
              </section>

              <section className="studio-asset-section">
                <div className="studio-section-title-row">
                  <div>
                    <div className="studio-section-title">References</div>
                    <div className="studio-section-subtitle">Characters, props, locations and visual anchors used by this scene</div>
                  </div>
                  <span className="studio-count-pill">{referencedElements.length}/{capabilities?.elements?.max_active_per_scene ?? 6}</span>
                </div>
                <div className="studio-reference-strip">
                  <button type="button" onClick={() => setShowReferencePicker(true)} className="studio-add-reference-card">
                    <span className="studio-create-character-plus"><PlusIcon /></span>
                    <span>Add reference</span>
                  </button>
                  {referencedElements.map((element) => {
                    const asset = primaryElementAsset(element);
                    return (
                      <button key={element.id} type="button" onClick={() => setSelectedElementId(element.id)} className={`studio-reference-card ${selectedElement?.id === element.id ? "studio-reference-card-active" : ""}`}>
                        {asset ? <img src={absoluteApiUrl(asset.asset_url)} alt={element.name} /> : <span className="studio-reference-empty">{element.name.slice(0, 1)}</span>}
                        <span className={`studio-reference-badge ${elementTone(element.type)}`}>{element.type}</span>
                        <span className="studio-reference-label">@{element.handle}</span>
                      </button>
                    );
                  })}
                </div>
              </section>
            </div>

            <section className="studio-prompt-panel">
              <div className="studio-prompt-heading">
                <div>
                  <div className="text-xs font-semibold text-[var(--text)]">Describe your scene</div>
                  <div className="mt-0.5 text-[10px] text-[var(--text-muted)]">Type @ to pull a saved Character, Prop, Location or Style into the shot.</div>
                </div>
                <span className="studio-mini-pill">{referencedElements.length} active references</span>
              </div>

              <div className="studio-prompt-editor-wrap">
                <PromptHighlight text={prompt} elements={elements} />
                <textarea
                  value={prompt}
                  onChange={(event) => updateMentionState(event.target.value)}
                  onBlur={() => window.setTimeout(() => setMentionQuery(null), 120)}
                  rows={5}
                  placeholder="@Character walks through @Location holding @Prop. Describe motion, framing, dialogue and sound..."
                  className="studio-prompt-input"
                />
                {mentionQuery != null && mentionSuggestions.length > 0 && (
                  <div className="studio-mention-menu">
                    <div className="studio-mention-menu-title">Elements</div>
                    {mentionSuggestions.map((element) => {
                      const asset = primaryElementAsset(element);
                      return (
                        <button key={element.id} type="button" onMouseDown={(event) => { event.preventDefault(); chooseMention(element); }} className="studio-mention-option">
                          {asset ? <img src={absoluteApiUrl(asset.asset_url)} alt="" /> : <span className="studio-mention-empty">{element.name.slice(0, 1)}</span>}
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-xs font-semibold text-[var(--text)]">@{element.handle}</span>
                            <span className="block truncate text-[10px] text-[var(--text-muted)]">{element.name} · {element.type}</span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {referencedElements.length > 0 && (
                <div className="studio-prompt-references">
                  {referencedElements.map((element) => {
                    const asset = primaryElementAsset(element);
                    return (
                      <span key={element.id} className={`element-mention-chip ${elementTone(element.type)}`}>
                        {asset ? <img src={absoluteApiUrl(asset.asset_url)} alt="" className="h-5 w-5 rounded-full object-cover" /> : null}
                        @{element.handle}
                        <span className="element-hover-card">
                          {asset ? <img src={absoluteApiUrl(asset.asset_url)} alt={element.name} className="h-28 w-full rounded-lg object-cover" /> : null}
                          <span className="mt-2 block text-xs font-semibold text-[var(--text)]">{element.name}</span>
                          <span className="mt-0.5 block text-[10px] uppercase text-[var(--text-muted)]">{element.type} · v{element.current_version} · {element.assets.length} refs</span>
                        </span>
                      </span>
                    );
                  })}
                </div>
              )}

              <div className="studio-prompt-footer">
                <div className="studio-prompt-tools">
                  <select className="studio-toolbar-select" value={aspectRatio} onChange={(e) => { setAspectRatio(e.target.value as AspectRatio); invalidateRenderedMedia(); }}>
                    <option value="16:9">16:9</option><option value="9:16">9:16</option><option value="1:1">1:1</option>
                  </select>
                  <select className="studio-toolbar-select" value={quality} onChange={(e) => handleQualityChange(e.target.value as RenderQuality)}>
                    <option value="preview">Preview</option><option value="1080p">1080p</option><option value="4k">4K</option>
                  </select>
                  {mode === "factory" ? (
                    <select className="studio-toolbar-select" value={factorySceneSeconds} onChange={(e) => setFactorySceneSeconds(Number(e.target.value))}>
                      {factoryDurationOptions.map((value) => <option key={value} value={value}>{value === 30 ? "30s experimental" : `${value}s scene`}</option>)}
                    </select>
                  ) : (
                    <select className="studio-toolbar-select" value={durationSeconds} onChange={(e) => setDurationSeconds(Number(e.target.value))}>
                      {durationOptions.map((value) => <option key={value} value={value}>{value}s</option>)}
                    </select>
                  )}
                  <label className="studio-ai-toggle"><input type="checkbox" checked={enhancePrompt} onChange={(e) => setEnhancePrompt(e.target.checked)} /><span>AI Director</span></label>
                </div>

                <button type="submit" disabled={isBusy} className="studio-generate-button">
                  {isBusy ? <Spinner /> : <PlayIcon />}
                  {factoryGenerating ? "Generating film" : directGenerating ? "Generating" : planning ? "Planning" : mode === "factory" ? "Generate" : mode === "direct" ? "Generate clip" : "Create storyboard"}
                </button>
              </div>
            </section>
          </form>

          {progressMessage && <div className="studio-inline-notice studio-inline-info">{progressMessage}</div>}
          {error && <div className="studio-inline-notice studio-inline-error">{error}</div>}
          {notice && <div className="studio-inline-notice studio-inline-success">{notice}</div>}
        </section>

        <aside className="studio-inspector">
          <div className="studio-inspector-scroll">
            <section className="studio-inspector-section">
              <div className="studio-inspector-title-row">
                <div>
                  <div className="studio-inspector-eyebrow">Cinema Studio</div>
                  <div className="studio-inspector-title">Generation mode</div>
                </div>
                <span className="studio-mini-pill">v7</span>
              </div>
              <div className="studio-mode-switch">
                {(["factory", "storyboard", "direct"] as GenerationMode[]).map((item) => (
                  <button key={item} type="button" onClick={() => { setMode(item); resetOutput(); }} className={mode === item ? "studio-mode-active" : ""}>{item}</button>
                ))}
              </div>
            </section>

            <div className="studio-director-tabs" role="tablist" aria-label="Director panel">
              {([
                ["scene", "Scene"],
                ["camera", "Camera"],
                ["look", "Look"],
                ["elements", "Elements"],
              ] as Array<[DirectorTab, string]>).map(([tab, label]) => (
                <button key={tab} type="button" role="tab" aria-selected={directorTab === tab} onClick={() => setDirectorTab(tab)} className={directorTab === tab ? "studio-director-tab-active" : ""}>{label}</button>
              ))}
            </div>

            {directorTab === "elements" && (
              <section className="studio-inspector-section studio-inspector-section-flush">
                <div className="studio-inspector-title-row">
                  <div>
                    <div className="studio-inspector-eyebrow">My Elements</div>
                    <div className="studio-inspector-title">Cast & references</div>
                  </div>
                  <button type="button" onClick={() => { setElementType("character"); setShowElementCreator(true); }} className="studio-small-action">+ New</button>
                </div>

                <input value={elementSearch} onChange={(e) => setElementSearch(e.target.value)} className="studio-search-input" placeholder="Search Elements" />
                <div className="studio-filter-row">
                  {(["all", "character", "prop", "location", "style"] as const).map((value) => (
                    <button key={value} type="button" onClick={() => setElementFilter(value)} className={elementFilter === value ? "studio-filter-active" : ""}>{value === "all" ? "All" : `${value}s`}</button>
                  ))}
                </div>

                <div className="studio-element-library">
                  {elementsLoading && elements.length === 0 ? <div className="studio-empty-library">Loading Elements...</div> : null}
                  {!elementsLoading && filteredElements.length === 0 ? <div className="studio-empty-library">No matching Elements yet.</div> : null}
                  {filteredElements.map((element) => {
                    const asset = primaryElementAsset(element);
                    const active = hasElementMention(prompt, element.handle) || Boolean(elementApplyAll[element.id]);
                    return (
                      <button key={element.id} type="button" onClick={() => setSelectedElementId(element.id)} className={`studio-library-item ${selectedElement?.id === element.id ? "studio-library-item-selected" : ""}`}>
                        <span className="studio-library-thumb">{asset ? <img src={absoluteApiUrl(asset.asset_url)} alt={element.name} /> : <span>{element.name.slice(0, 1)}</span>}</span>
                        <span className="min-w-0 flex-1 text-left">
                          <span className="block truncate text-xs font-semibold text-[var(--text)]">{element.name}</span>
                          <span className="mt-0.5 block truncate text-[10px] text-[var(--text-muted)]">@{element.handle} · {element.type} · v{element.current_version}</span>
                        </span>
                        <span className={`studio-active-dot ${active ? "studio-active-dot-on" : ""}`} />
                      </button>
                    );
                  })}
                </div>

                {selectedElement && (
                  <div className="studio-selected-element">
                    <div className="flex items-center gap-3">
                      {primaryElementAsset(selectedElement) ? <img src={absoluteApiUrl(primaryElementAsset(selectedElement)!.asset_url)} alt={selectedElement.name} className="h-14 w-14 rounded-xl object-cover" /> : <div className="h-14 w-14 rounded-xl bg-[var(--empty-bg)]" />}
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-semibold text-[var(--text)]">{selectedElement.name}</div>
                        <div className={`mt-0.5 text-[10px] uppercase ${elementTone(selectedElement.type)}`}>{selectedElement.type} · @{selectedElement.handle}</div>
                      </div>
                      <button type="button" onClick={() => insertElementMention(selectedElement)} className="studio-small-action">Use</button>
                    </div>

                    <div className="mt-3 grid gap-2">
                      <label className="studio-field-label">Reference mode
                        <select value={elementModes[selectedElement.id] || "identity"} onChange={(e) => setElementModes((current) => ({ ...current, [selectedElement.id]: e.target.value as ElementReferenceMode }))} className="studio-inspector-control">
                          <option value="identity">Identity / Element reference</option>
                          <option value="start_frame">Exact starting frame</option>
                        </select>
                      </label>
                      <label className="studio-field-label">Reference strength
                        <input type="range" min="0.55" max="1.25" step="0.05" value={elementStrengths[selectedElement.id] ?? 1} onChange={(e) => setElementStrengths((current) => ({ ...current, [selectedElement.id]: Number(e.target.value) }))} className="studio-range" />
                        <span className="studio-range-value">{(elementStrengths[selectedElement.id] ?? 1).toFixed(2)}</span>
                      </label>
                      <label className="studio-check-row"><input type="checkbox" checked={Boolean(elementApplyAll[selectedElement.id])} onChange={(e) => setElementApplyAll((current) => ({ ...current, [selectedElement.id]: e.target.checked }))} /><span>Keep this Element active across all Factory scenes</span></label>
                    </div>

                    <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
                      {selectedElement.assets.map((reference) => (
                        <button key={reference.id} type="button" onClick={() => void handleSetPrimaryElementAsset(selectedElement, reference.id)} className={`studio-asset-thumb ${reference.id === selectedElement.primary_asset_id ? "studio-asset-thumb-active" : ""}`} title="Set as canonical reference">
                          <img src={absoluteApiUrl(reference.asset_url)} alt="" />
                        </button>
                      ))}
                      <label className="studio-asset-thumb studio-asset-add" title="Add references">+<input type="file" multiple accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => void handleAddElementReferences(selectedElement, e.target.files)} /></label>
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <span className="text-[10px] text-[var(--text-muted)]">{selectedElement.assets.length}/{capabilities?.elements?.max_assets_per_element ?? 8} references</span>
                      <div className="flex items-center gap-3">
                        {(hasElementMention(prompt, selectedElement.handle) || elementApplyAll[selectedElement.id]) && <button type="button" onClick={() => removeElementFromScene(selectedElement)} className="text-[10px] text-[var(--text-muted)]">Remove from scene</button>}
                        <button type="button" onClick={() => void handleArchiveElement(selectedElement)} className="text-[10px] text-[var(--danger-text)]">Archive</button>
                      </div>
                    </div>
                  </div>
                )}
              </section>
            )}

            {directorTab === "scene" && (
              <>
                <section className="studio-inspector-section studio-inspector-section-flush">
                  <div className="studio-inspector-eyebrow">Scene</div>
                  <div className="studio-inspector-title">Production settings</div>
                  <div className="mt-4 grid gap-3">
                    <Control label="Format"><select className="studio-inspector-control" value={aspectRatio} onChange={(e) => { setAspectRatio(e.target.value as AspectRatio); invalidateRenderedMedia(); }}><option value="16:9">16:9 Landscape</option><option value="9:16">9:16 Vertical</option><option value="1:1">1:1 Square</option></select></Control>
                    <Control label="Delivery"><select className="studio-inspector-control" value={quality} onChange={(e) => handleQualityChange(e.target.value as RenderQuality)}><option value="preview">Source preview</option><option value="1080p">1080p master</option><option value="4k">4K master</option></select></Control>
                    {mode === "factory" ? (
                      <>
                        <Control label="Final runtime"><select className="studio-inspector-control" value={factoryTargetSeconds} onChange={(e) => setFactoryTargetSeconds(Number(e.target.value))}>{FACTORY_TARGETS.map((value) => <option key={value} value={value}>{value < 60 ? `${value} seconds` : `${value / 60} minute${value === 60 ? "" : "s"}`}</option>)}</select></Control>
                        <Control label="Scene runtime"><select className="studio-inspector-control" value={factorySceneSeconds} onChange={(e) => setFactorySceneSeconds(Number(e.target.value))}>{factoryDurationOptions.map((value) => <option key={value} value={value}>{value === 30 && quality === "1080p" ? "30s · experimental one-pass" : `${value}s · one-pass`}</option>)}</select></Control>
                      </>
                    ) : mode === "storyboard" ? (
                      <>
                        <Control label="Scenes"><select className="studio-inspector-control" value={sceneCount} onChange={(e) => setSceneCount(Number(e.target.value))}>{[2,3,4,6,8,10,12,16,20].map((value) => <option key={value} value={value}>{value} scenes</option>)}</select></Control>
                        <Control label="Runtime / scene"><select className="studio-inspector-control" value={durationSeconds} onChange={(e) => setDurationSeconds(Number(e.target.value))}>{durationOptions.map((value) => <option key={value} value={value}>{value}s</option>)}</select></Control>
                      </>
                    ) : <Control label="Clip runtime"><select className="studio-inspector-control" value={durationSeconds} onChange={(e) => setDurationSeconds(Number(e.target.value))}>{durationOptions.map((value) => <option key={value} value={value}>{value}s</option>)}</select></Control>}
                    <Control label="Audio"><select className="studio-inspector-control" value={audioMode} onChange={(e) => setAudioMode(e.target.value as AudioMode)}><option value="mastered">Generated + mastered</option><option value="native">Native LTX audio</option><option value="mute">Mute final video</option></select></Control>
                    <Control label="Continuity"><select className="studio-inspector-control" value={continuityMode} onChange={(e) => setContinuityMode(e.target.value as ContinuityMode)}><option value="strict">Strict · identity + image</option><option value="balanced">Balanced · identity</option><option value="off">Off</option></select></Control>
                    <div className="grid grid-cols-2 gap-2"><Control label="Seed"><input className="studio-inspector-control" type="number" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value) || 0)} /></Control><Control label="Decoder"><select className="studio-inspector-control" value={decoder} onChange={(e) => setDecoder(e.target.value as DecoderName)}><option value="conv">Conv</option><option value="diffusion">Diffusion</option></select></Control></div>
                  </div>
                </section>

                <section className="studio-inspector-section">
                  <div className="studio-inspector-eyebrow">Audio</div>
                  <div className="studio-inspector-title">Sound direction</div>
                  <textarea value={audioDirection} onChange={(e) => setAudioDirection(e.target.value)} rows={4} className="studio-inspector-textarea" placeholder="Ambience, dialogue, Foley, music direction..." />
                </section>

                <section className="studio-inspector-section">
                  <label className="studio-feature-toggle">
                    <span><strong>AI Director</strong><small>Gemini scene planning + strict AI QC. Leave off to use your screenplay directly.</small></span>
                    <input type="checkbox" checked={enhancePrompt} onChange={(e) => setEnhancePrompt(e.target.checked)} />
                  </label>
                </section>

                {mode === "factory" && youtube?.enabled && (
                  <section className="studio-inspector-section">
                    <label className="studio-feature-toggle">
                      <span><strong>Publish to YouTube</strong><small>{youtube.connected ? youtube.channel_title || "Connected channel" : "Connect a channel first"}</small></span>
                      <input type="checkbox" disabled={!youtube.connected} checked={publishToYouTube} onChange={(e) => setPublishToYouTube(e.target.checked)} />
                    </label>
                    {publishToYouTube && <div className="mt-3 grid gap-2"><input className="studio-inspector-control" value={youtubeTitle} onChange={(e) => setYoutubeTitle(e.target.value)} placeholder="YouTube title" /><select className="studio-inspector-control" value={youtubePrivacy} onChange={(e) => setYoutubePrivacy(e.target.value as YouTubePrivacy)}><option value="private">Private</option><option value="unlisted" disabled={!youtube.public_uploads_allowed}>Unlisted</option><option value="public" disabled={!youtube.public_uploads_allowed}>Public</option></select><textarea className="studio-inspector-textarea" rows={3} value={youtubeDescription} onChange={(e) => setYoutubeDescription(e.target.value)} placeholder="Description" /></div>}
                  </section>
                )}
              </>
            )}

            {directorTab === "camera" && (
              <section className="studio-inspector-section studio-inspector-section-flush">
                <div className="studio-inspector-eyebrow">Director&apos;s Panel</div>
                <div className="studio-inspector-title">Camera & optics</div>
                <p className="studio-inspector-copy">These controls compile into the LTX scene prompt. Auto leaves your screenplay untouched.</p>
                <div className="mt-4 grid gap-4">
                  <Control label="Shot size"><select className="studio-inspector-control" value={shotSize} onChange={(e) => setShotSize(e.target.value as ShotSize)}>{SHOT_SIZES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></Control>
                  <div>
                    <div className="studio-field-label mb-2">Camera movement</div>
                    <div className="studio-preset-grid">
                      {CAMERA_MOVES.map((item) => <button key={item.value} type="button" onClick={() => setCameraMove(item.value)} className={cameraMove === item.value ? "studio-preset-active" : ""}>{item.label}</button>)}
                    </div>
                  </div>
                  <div>
                    <div className="studio-field-label mb-2">Lens</div>
                    <div className="studio-lens-row">{LENS_PRESETS.map((value) => <button key={value} type="button" onClick={() => setLensPreset(value)} className={lensPreset === value ? "studio-preset-active" : ""}>{value === "auto" ? "Auto" : value}</button>)}</div>
                  </div>
                </div>
              </section>
            )}

            {directorTab === "look" && (
              <section className="studio-inspector-section studio-inspector-section-flush">
                <div className="studio-inspector-eyebrow">Director&apos;s Panel</div>
                <div className="studio-inspector-title">Genre, colour & tempo</div>
                <p className="studio-inspector-copy">Use production-level direction without rewriting the story or redefining @Elements.</p>
                <div className="mt-4 grid gap-4">
                  <div><div className="studio-field-label mb-2">Genre</div><div className="studio-preset-grid studio-preset-grid-2">{GENRE_PRESETS.map((value) => <button key={value} type="button" onClick={() => setGenrePreset(value)} className={genrePreset === value ? "studio-preset-active" : ""}>{value === "auto" ? "Auto" : value}</button>)}</div></div>
                  <Control label="Colour palette"><select className="studio-inspector-control" value={colorPreset} onChange={(e) => setColorPreset(e.target.value as ColorPreset)}>{COLOR_PRESETS.map((value) => <option key={value} value={value}>{value === "auto" ? "Auto" : value.replaceAll("-", " ")}</option>)}</select></Control>
                  <div><div className="studio-field-label mb-2">Performance tempo</div><div className="studio-lens-row">{TEMPO_PRESETS.map((value) => <button key={value} type="button" onClick={() => setTempoPreset(value)} className={tempoPreset === value ? "studio-preset-active" : ""}>{value}</button>)}</div></div>
                </div>
              </section>
            )}

            <details className="studio-inspector-details">
              <summary>Production & account</summary>
              <div className="mt-3 space-y-3">
                <IntegrationCard title="Production profile" subtitle="Current factory limits">
                  <InfoRow label="1080p scene" value={`${capabilities?.max_scene_duration_seconds_by_quality?.["1080p"] ?? 30}s`} />
                  <InfoRow label="4K scene" value={`${capabilities?.max_scene_duration_seconds_by_quality?.["4k"] ?? 15}s`} />
                  <InfoRow label="Factory runtime" value={`${capabilities?.max_factory_duration_seconds ?? 300}s`} />
                  <InfoRow label="Elements / scene" value={String(capabilities?.elements?.max_active_per_scene ?? 6)} />
                </IntegrationCard>
                <IntegrationCard title="Billing" subtitle={billingCatalog?.enabled ? "Stripe generation credits" : "Billing disabled"}>
                  {billingCatalog?.enabled && billingMe ? <><div className="mb-2 text-xs text-[var(--success-text)]">Balance {formatCredits(billingMe.balance_seconds)}</div>{billingMe.stripe_customer_id && <button type="button" onClick={handleBillingPortal} className="studio-secondary-button w-full">Manage billing</button>}</> : <p className="text-[10px] leading-5 text-[var(--text-muted)]">Configure Stripe to enable customer generation credits.</p>}
                </IntegrationCard>
                {youtube?.enabled && <button type="button" disabled={integrationBusy} onClick={handleYouTubeConnection} className="studio-secondary-button w-full">{youtube.connected ? "Disconnect YouTube" : "Connect YouTube"}</button>}
              </div>
            </details>
          </div>
        </aside>
      </div>

      {showElementsLibrary && (
        <div className="studio-drawer-backdrop" role="dialog" aria-modal="true" aria-label="My Elements" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowElementsLibrary(false); }}>
          <aside className="studio-elements-drawer">
            <div className="studio-drawer-header">
              <div>
                <div className="studio-inspector-eyebrow">Production library</div>
                <h2 className="mt-1 text-lg font-semibold text-[var(--text)]">My Elements</h2>
                <p className="mt-1 text-xs text-[var(--text-muted)]">Reusable characters, props, locations and styles. Click any Element to bind it to the current scene.</p>
              </div>
              <button type="button" onClick={() => setShowElementsLibrary(false)} className="studio-icon-button" aria-label="Close Elements">×</button>
            </div>
            <div className="studio-drawer-toolbar">
              <input value={elementSearch} onChange={(e) => setElementSearch(e.target.value)} className="studio-search-input" placeholder="Search characters, props, locations..." />
              <button type="button" onClick={() => { setShowElementsLibrary(false); setShowElementCreator(true); }} className="studio-primary-button"><PlusIcon /> New Element</button>
            </div>
            <div className="studio-filter-row studio-filter-row-wide">
              {(["all", "character", "prop", "location", "style"] as const).map((value) => (
                <button key={value} type="button" onClick={() => setElementFilter(value)} className={elementFilter === value ? "studio-filter-active" : ""}>{value === "all" ? "All" : `${value}s`}</button>
              ))}
            </div>
            <div className="studio-elements-grid">
              {filteredElements.map((element) => {
                const asset = primaryElementAsset(element);
                const active = hasElementMention(prompt, element.handle) || Boolean(elementApplyAll[element.id]);
                return (
                  <article key={element.id} className={`studio-element-grid-card ${active ? "studio-element-grid-card-active" : ""}`}>
                    <button type="button" className="studio-element-grid-preview" onClick={() => { setSelectedElementId(element.id); setDirectorTab("elements"); setShowElementsLibrary(false); }}>
                      {asset ? <img src={absoluteApiUrl(asset.asset_url)} alt={element.name} /> : <span>{element.name.slice(0, 1)}</span>}
                      <span className={`studio-reference-badge ${elementTone(element.type)}`}>{element.type}</span>
                    </button>
                    <div className="studio-element-grid-meta">
                      <div className="min-w-0"><div className="truncate text-xs font-semibold text-[var(--text)]">{element.name}</div><div className="truncate text-[10px] text-[var(--text-muted)]">@{element.handle} · {element.assets.length} refs · v{element.current_version}</div></div>
                      <button type="button" onClick={() => { insertElementMention(element); setShowElementsLibrary(false); }} className="studio-small-action">Use</button>
                    </div>
                  </article>
                );
              })}
              {!elementsLoading && filteredElements.length === 0 && <div className="studio-library-empty-large">No Elements match this filter.</div>}
            </div>
          </aside>
        </div>
      )}

      {showReferencePicker && (
        <div className="studio-modal-backdrop" role="dialog" aria-modal="true" aria-label="Add scene reference" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowReferencePicker(false); }}>
          <div className="studio-reference-picker">
            <div className="studio-modal-header">
              <div><div className="studio-inspector-eyebrow">References</div><h2 className="mt-1 text-lg font-semibold text-[var(--text)]">Add to this scene</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Select a saved Element. It will be inserted into the prompt as an @mention and resolved to its canonical reference during generation.</p></div>
              <button type="button" onClick={() => setShowReferencePicker(false)} className="studio-icon-button">×</button>
            </div>
            <div className="studio-reference-picker-toolbar">
              <div className="studio-reference-picker-tabs"><button type="button" className="studio-reference-picker-tab-active">Elements</button><button type="button" onClick={() => { setShowReferencePicker(false); setShowElementCreator(true); }}>Upload new</button></div>
              <span className="studio-count-pill">{referencedElements.length}/{activeElementLimit} active</span>
            </div>
            <div className="studio-reference-picker-grid">
              {elements.map((element) => {
                const asset = primaryElementAsset(element);
                const active = hasElementMention(prompt, element.handle) || Boolean(elementApplyAll[element.id]);
                return (
                  <button key={element.id} type="button" disabled={!active && referencedElements.length >= activeElementLimit} onClick={() => { insertElementMention(element); setShowReferencePicker(false); }} className={`studio-picker-card ${active ? "studio-picker-card-active" : ""}`}>
                    <span className="studio-picker-image">{asset ? <img src={absoluteApiUrl(asset.asset_url)} alt={element.name} /> : <span>{element.name.slice(0, 1)}</span>}</span>
                    <span className="min-w-0 text-left"><span className="block truncate text-xs font-semibold text-[var(--text)]">{element.name}</span><span className={`mt-0.5 block text-[10px] ${elementTone(element.type)}`}>@{element.handle} · {element.type}</span></span>
                    {active && <span className="studio-picker-check">✓</span>}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {showElementCreator && (
        <div className="studio-modal-backdrop" role="dialog" aria-modal="true" aria-label="Create Element">
          <div className="studio-modal">
            <div className="studio-modal-header">
              <div><div className="studio-inspector-eyebrow">New Element</div><h2 className="mt-1 text-lg font-semibold text-[var(--text)]">Create a reusable visual identity</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Characters, props and locations are saved once, then reused in prompts with @mentions.</p></div>
              <button type="button" onClick={() => setShowElementCreator(false)} className="studio-icon-button">×</button>
            </div>
            <div className="studio-modal-body">
              <div className="grid gap-3 sm:grid-cols-3">
                {(["character", "prop", "location", "style"] as ElementType[]).map((type) => <button key={type} type="button" onClick={() => setElementType(type)} className={`studio-element-type-choice ${elementType === type ? "studio-element-type-choice-active" : ""}`}><span className={elementTone(type)}>{type}</span></button>)}
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="studio-field-label">Name<input className="studio-inspector-control mt-1" value={elementName} onChange={(e) => { setElementName(e.target.value); if (!elementHandle) setElementHandle(e.target.value.replace(/[^A-Za-z0-9_-]/g, "")); }} placeholder="Radha" /></label>
                <label className="studio-field-label">Prompt handle<div className="relative mt-1"><span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-[var(--text-muted)]">@</span><input className="studio-inspector-control pl-7" value={elementHandle} onChange={(e) => setElementHandle(e.target.value.replace(/^@/, "").replace(/[^A-Za-z0-9_-]/g, ""))} placeholder="Radha" /></div></label>
              </div>
              <label className="mt-3 block studio-field-label">Identity / design description<textarea rows={3} value={elementDescription} onChange={(e) => setElementDescription(e.target.value)} className="studio-inspector-textarea mt-1" placeholder="Face, costume, materials, landmarks or other traits that must remain stable." /></label>
              <label className="studio-upload-dropzone">
                <span className="studio-upload-icon">+</span>
                <strong>Drop reference images or click to upload</strong>
                <small>PNG, JPEG or WEBP · up to {capabilities?.elements?.max_assets_per_element ?? 8} references · first image is canonical</small>
                <input type="file" multiple accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => setElementFiles(Array.from(e.target.files || []))} />
              </label>
              {elementFiles.length > 0 && <div className="studio-upload-file-list">{elementFiles.map((file) => <span key={`${file.name}-${file.size}`}>{file.name}</span>)}</div>}
            </div>
            <div className="studio-modal-footer">
              <button type="button" onClick={() => setShowElementCreator(false)} className="studio-secondary-button">Cancel</button>
              <button type="button" onClick={() => void handleCreateElement()} disabled={elementBusy} className="studio-primary-button">{elementBusy ? "Saving..." : `Save @${elementHandle || "Element"}`}</button>
            </div>
          </div>
        </div>
      )}

      <div id="studio-output" className="mx-auto w-full max-w-[1500px] px-4 pb-10 pt-5 sm:px-7 lg:px-10">
        {finalVideo && (
          <section className="mt-5">
            <FinalVideoCard video={finalVideo} aspectRatio={aspectRatio} />
          </section>
        )}

        {factoryResult && (
          <section className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
            <Stat label="Scenes" value={String(factoryResult.scene_count)} detail={`${factoryResult.chunk_count} native LTX chunks`} />
            <Stat label="Runtime" value={`${(factoryResult.actual_duration_seconds ?? factoryResult.target_duration_seconds).toFixed(1)}s`} detail={`${factoryResult.scene_duration_seconds}s target scene`} />
            <Stat label="Delivery" value={qualityLabel(factoryResult.quality)} detail={`${factoryResult.width ?? "?"}×${factoryResult.height ?? "?"} · ${factoryResult.audio_mode}`} />
            <Stat label="Planner" value={factoryResult.planner_source} detail={`${factoryResult.entity_locks.length} entity lock${factoryResult.entity_locks.length === 1 ? "" : "s"}`} />
            <Stat label="Elements" value={factoryResult.elements_used.length ? String(factoryResult.elements_used.length) : "None"} detail={factoryResult.elements_used.length ? `${factoryResult.elements_used.join(", ")} · ${factoryResult.element_reference_mode || "reference"}` : "Prompt-only generation"} />
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
