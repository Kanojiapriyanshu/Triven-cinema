"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";

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
  createHeroFrame,
  createUpscaleJob,
  uploadHeroFrame,
  createVideoGenerationJob,
  deleteChatHistoryItem,
  disconnectYouTube,
  generateScenePlan,
  getAuthMe,
  getBillingCatalog,
  getBillingMe,
  getGenerationCapabilities,
  getYouTubeStatus,
  listChatHistory,
  listElements,
  logoutCinema,
  requestLoginOtp,
  saveChatHistoryItem,
  updateElement,
  verifyCheckout,
  verifyLoginOtp,
  waitForFactoryGenerationJob,
  waitForJobResult,
  waitForVideoGenerationJob,
} from "@/lib/api/cinema";
import type { AuthUser, ServerChatSession } from "@/lib/api/cinema";
import type {
  AspectRatio,
  AudioMode,
  BillingCatalogResponse,
  BillingMeResponse,
  CinemaElement,
  ContinuityMode,
  ElementAssetRole,
  ElementBinding,
  ElementReferenceMode,
  ElementType,
  ElementWardrobePolicy,
  DecoderName,
  FactoryGenerationResponse,
  GenerationCapabilitiesResponse,
  GenerationMode,
  RenderedSceneVideo,
  UpscaleResponse,
  RenderQuality,
  RealismProfile,
  ScenePlanResponse,
  VideoModelName,
  VideoProviderName,
  YouTubePrivacy,
  YouTubeStatusResponse,
} from "@/lib/types/generation";

type ScenePromptMap = Record<number, string>;
type RenderedVideoMap = Record<number, RenderedSceneVideo>;
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
  continuityFrameFilename?: string | null;
  continuityFrameUrl?: string | null;
  warnings?: string[];
  quality?: RenderQuality;
} | null;

type ContinueFrame = { filename: string; url: string };
type HeroFrame = { filename: string; url: string; model: string };

type StudioChatWorkspace = {
  prompt: string;
  mode: GenerationMode;
  aspectRatio: AspectRatio;
  sceneCount: number;
  durationSeconds: number;
  factoryTargetSeconds: number;
  factorySceneSeconds: number;
  quality: RenderQuality;
  audioMode: AudioMode;
  audioDirection: string;
  decoder: DecoderName;
  realismProfile: RealismProfile;
  seed: number;
  enhancePrompt: boolean;
  continuityMode: ContinuityMode;
  cameraMove: CameraMove;
  lensPreset: LensPreset;
  shotSize: ShotSize;
  genrePreset: GenrePreset;
  colorPreset: ColorPreset;
  tempoPreset: TempoPreset;
  selectedElementId: string | null;
  elementModes: Record<string, ElementReferenceMode>;
  elementWardrobePolicies: Record<string, ElementWardrobePolicy>;
  elementApplyAll: Record<string, boolean>;
  elementStrengths: Record<string, number>;
  elementKeepInShot: Record<string, boolean>;
  result: ScenePlanResponse | null;
  scenePrompts: ScenePromptMap;
  renderedVideos: RenderedVideoMap;
  factoryResult: FactoryGenerationResponse | null;
  finalVideo: FinalVideo;
};

type StudioChatSession = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  workspace: StudioChatWorkspace;
};

const CHAT_HISTORY_STORAGE_PREFIX = "triven-cinema-chat-history-v2";
const LEGACY_CHAT_HISTORY_STORAGE_KEY = "triven-cinema-chat-history-v1";
const DEFAULT_AUDIO_DIRECTION = "Natural synchronized ambience and Foley matching every visible action.";

function createEmptyChatWorkspace(): StudioChatWorkspace {
  return {
    prompt: "",
    mode: "factory",
    aspectRatio: "16:9",
    sceneCount: 2,
    durationSeconds: 15,
    // Draft first: Preview + one 15 s scene renders in about a minute and a half. Switch to 1080p and
    // Real Skin for the final pass once the shot, face and voice are right.
    factoryTargetSeconds: 15,
    factorySceneSeconds: 15,
    quality: "preview",
    audioMode: "mastered",
    audioDirection: DEFAULT_AUDIO_DIRECTION,
    decoder: "conv",
    realismProfile: "standard",
    seed: 42,
    enhancePrompt: false,
    continuityMode: "strict",
    cameraMove: "auto",
    lensPreset: "auto",
    shotSize: "auto",
    genrePreset: "auto",
    colorPreset: "auto",
    tempoPreset: "auto",
    selectedElementId: null,
    elementModes: {},
    elementWardrobePolicies: {},
    elementApplyAll: {},
    elementStrengths: {},
    elementKeepInShot: {},
    result: null,
    scenePrompts: {},
    renderedVideos: {},
    factoryResult: null,
    finalVideo: null,
  };
}

function normalizeChatWorkspace(value: Partial<StudioChatWorkspace> | null | undefined): StudioChatWorkspace {
  const empty = createEmptyChatWorkspace();
  return {
    ...empty,
    ...(value || {}),
    elementModes: value?.elementModes || {},
    elementWardrobePolicies: value?.elementWardrobePolicies || {},
    elementApplyAll: value?.elementApplyAll || {},
    elementStrengths: value?.elementStrengths || {},
    elementKeepInShot: value?.elementKeepInShot || {},
    scenePrompts: value?.scenePrompts || {},
    renderedVideos: value?.renderedVideos || {},
  };
}

function chatTitleFromPrompt(value: string) {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (!normalized) return "New chat";
  return normalized.length > 38 ? `${normalized.slice(0, 38).trimEnd()}…` : normalized;
}

function createChatId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `chat-${crypto.randomUUID()}`;
  }
  return `chat-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function createChatSession(workspace = createEmptyChatWorkspace()): StudioChatSession {
  const now = Date.now();
  return {
    id: createChatId(),
    title: chatTitleFromPrompt(workspace.prompt),
    createdAt: now,
    updatedAt: now,
    workspace,
  };
}

function chatFromServer(entry: ServerChatSession): StudioChatSession {
  return {
    id: entry.id,
    title: entry.title || chatTitleFromPrompt(String(entry.workspace.prompt || "")),
    createdAt: entry.created_at,
    updatedAt: entry.updated_at,
    workspace: normalizeChatWorkspace(entry.workspace as Partial<StudioChatWorkspace>),
  };
}

function chatToServer(entry: StudioChatSession): ServerChatSession {
  return {
    id: entry.id,
    title: entry.title,
    created_at: entry.createdAt,
    updated_at: entry.updatedAt,
    workspace: entry.workspace as unknown as Record<string, unknown>,
  };
}

function parseStoredChatSessions(raw: string | null) {
  if (!raw) return [] as StudioChatSession[];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [] as StudioChatSession[];
    return parsed
      .filter((entry): entry is StudioChatSession => Boolean(
        entry &&
        typeof entry === "object" &&
        "id" in entry && typeof entry.id === "string" &&
        "workspace" in entry && entry.workspace && typeof entry.workspace === "object"
      ))
      .map((entry) => ({
        ...entry,
        title: typeof entry.title === "string" && entry.title.trim() ? entry.title : chatTitleFromPrompt((entry.workspace as StudioChatWorkspace).prompt || ""),
        createdAt: Number.isFinite(entry.createdAt) ? entry.createdAt : Date.now(),
        updatedAt: Number.isFinite(entry.updatedAt) ? entry.updatedAt : Date.now(),
        workspace: normalizeChatWorkspace(entry.workspace),
      }))
      .sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [] as StudioChatSession[];
  }
}

function chatStorageKey(userId: string | null | undefined) {
  return userId ? `${CHAT_HISTORY_STORAGE_PREFIX}:${userId}` : null;
}

function readStoredChatSessions(userId: string | null | undefined, includeLegacy = false) {
  if (typeof window === "undefined") return [] as StudioChatSession[];
  const key = chatStorageKey(userId);
  const scoped = key ? parseStoredChatSessions(window.localStorage.getItem(key)) : [];
  if (scoped.length || !includeLegacy) return scoped;
  return parseStoredChatSessions(window.localStorage.getItem(LEGACY_CHAT_HISTORY_STORAGE_KEY));
}

function persistChatSessions(sessions: StudioChatSession[], userId: string | null | undefined) {
  if (typeof window === "undefined") return;
  const key = chatStorageKey(userId);
  if (!key) return;
  try {
    window.localStorage.setItem(key, JSON.stringify(sessions));
  } catch {
    // A full localStorage should never break the actual Cinema generation flow.
  }
}

const DURATION_OPTIONS: Record<RenderQuality, number[]> = {
  preview: [5, 10, 15, 20],
  "1080p": [5, 10, 15, 20, 30],
  "4k": [5, 10, 15],
};

const FACTORY_SCENE_OPTIONS: Record<RenderQuality, number[]> = {
  preview: [15, 20],
  "1080p": [15, 20, 25, 30],
  "4k": [15],
};

// Final runtime is a user choice. The creator-grade preset must never overwrite it.
// Longer runtimes are assembled from continuity-locked scenes by Factory mode.
const FACTORY_TARGETS = [15, 20, 25, 30, 45, 60, 90, 120, 180, 300];

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

function ElementsIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true"><circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.6"/><rect x="13" y="5" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.6"/><path d="M5 18h14M8 15v6M16 15v6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>;
}

function FilmIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true"><rect x="3.5" y="5" width="17" height="14" rx="2.2" stroke="currentColor" strokeWidth="1.6"/><path d="M8 5v14M16 5v14M3.5 9h4.5M3.5 15h4.5M16 9h4.5M16 15h4.5" stroke="currentColor" strokeWidth="1.35"/></svg>;
}

function PlusIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true"><path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>;
}

function TrashIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5" aria-hidden="true"><path d="M4.5 7h15M9 7V4.8h6V7m-8.5 0 .7 12h9.6l.7-12M10 10.5v5M14 10.5v5" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round"/></svg>;
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

// Mirrors the API's cast resolution (element_service.split_trailing_tags): a run of @handles that
// follows the last sentence is a list of reference tags, not part of the shot.
function splitTrailingTags(value: string): { story: string; tags: string[] } {
  const text = value.replace(/\s+$/, "");
  const match = /(?<![A-Za-z0-9_@])((?:@[A-Za-z][A-Za-z0-9_-]{0,31}[ \t,;]+)*@[A-Za-z][A-Za-z0-9_-]{0,31})$/.exec(text);
  if (!match) return { story: text, tags: [] };
  const before = text.slice(0, match.index);
  const stripped = before.replace(/\s+$/, "");
  const startsClean = !stripped || /[.!?…"”’)\]]$/.test(stripped) || before.slice(stripped.length).includes("\n");
  if (!startsClean) return { story: text, tags: [] };
  return { story: before, tags: (match[1].match(/@[A-Za-z][A-Za-z0-9_-]{0,31}/g) || []).map((tag) => tag.slice(1)) };
}

type GalleryItem = { id: string; title: string; video: NonNullable<FinalVideo>; updatedAt: number };

function sortedChatSessionsForGallery(sessions: StudioChatSession[]): GalleryItem[] {
  return sessions
    .filter((session) => Boolean(session.workspace.finalVideo?.url))
    .map((session) => ({
      id: session.id,
      title: session.title,
      video: session.workspace.finalVideo as NonNullable<FinalVideo>,
      updatedAt: session.updatedAt,
    }))
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, 12);
}

// Measured on this deployment (B200): Preview + Standard ~85 s for 15 s of video; 1080p + Real Skin ~560 s for
// 15 s and ~1190 s for 30 s. Other combinations have not been timed, so they are described, not guessed.
function estimateRender(quality: RenderQuality, realism: RealismProfile, outputSeconds: number): { label: string; slow: boolean } {
  const minutes = (seconds: number) => {
    const m = seconds / 60;
    return m < 1.5 ? `${Math.round(seconds)} s` : `${Math.round(m)} min`;
  };
  if (quality === "preview" && realism === "standard") return { label: `Draft · about ${minutes(Math.max(60, outputSeconds * 5.7))}`, slow: false };
  if (quality === "1080p" && realism === "real_skin") return { label: `Final · about ${minutes(outputSeconds * 38)}`, slow: true };
  if (quality === "preview") return { label: `Preview · slower with ${realism === "identity_max" ? "Identity Max" : "Real Skin"}`, slow: true };
  return { label: quality === "4k" ? "4K · slowest, untimed" : "1080p · several minutes", slow: true };
}

const MODE_OPTIONS: Array<{ value: GenerationMode; label: string; hint: string }> = [
  { value: "factory", label: "Video", hint: "Describe it and get a finished video. Long videos are built shot by shot with the same characters." },
  { value: "storyboard", label: "Storyboard", hint: "Plan the shots first, edit each prompt, then render them one by one." },
  { value: "direct", label: "Single clip", hint: "One shot, rendered exactly as you write it." },
];

const QUALITY_OPTIONS: Array<{ value: RenderQuality; label: string; sub: string }> = [
  { value: "preview", label: "Draft", sub: "fast" },
  { value: "1080p", label: "Full HD", sub: "1080p" },
  { value: "4k", label: "4K", sub: "slow" },
];

const RATIO_OPTIONS: Array<{ value: AspectRatio; title: string }> = [
  { value: "16:9", title: "Wide, for YouTube and film" },
  { value: "9:16", title: "Tall, for phones and Shorts" },
  { value: "1:1", title: "Square" },
];

function qualityName(quality: RenderQuality) {
  return quality === "preview" ? "Draft" : quality === "1080p" ? "Full HD" : "4K";
}

function isDraftVideo(video: NonNullable<FinalVideo>) {
  if (video.quality) return video.quality === "preview";
  const width = Number.parseInt(video.dimensions.split("×")[0], 10);
  return Number.isFinite(width) && width > 0 && width < 1500;
}

function formatElapsed(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

const SAMPLE_PROMPTS = [
  "A lone astronaut walks across a red desert at dusk, slow push-in, wind and distant thunder.",
  "Close-up of a chef plating a dessert in a warm kitchen, shallow depth of field, soft jazz.",
  "A founder talks to camera in a bright studio and says: “Here is what changed this year.”",
];

// Advisory only: a reference image plus a prompt that never says what happens tends to come back as a still.
const PERFORMANCE_CUE = /["“”«»]|\b(?:says?|said|speaks?|talks?|asks?|walks?|runs?|turns?|looks?|smiles?|laughs?|waves?|nods?|moves?|leans?|steps?|sits?|stands?|holds?|raises?|explains?|presents?|reaches?|opens?|closes?|picks?|points?|enters?|exits?|dances?|jumps?|drives?|rides?)\b/i;

const REFERENCE_FRAME_CUE = /\b(?:as in|exactly as in|same as|matching)\s+the\s+reference\b|\bopens?\s+exactly\s+on\b|\bcontinu(?:es|ing)\s+the\s+exact\s+shot\b/i;

function primaryElementAsset(element: CinemaElement) {
  return element.assets.find((asset) => asset.id === element.primary_asset_id) || element.assets[0] || null;
}

function suggestedElementRoles(
  type: ElementType,
  count: number,
  existing: ElementAssetRole[] = []
): ElementAssetRole[] {
  if (type === "character") {
    const preferred: ElementAssetRole[] = ["face", "full_body", "profile", "costume"];
    const available = preferred.filter((role) => !existing.includes(role));
    return Array.from({ length: count }, (_, index) => available[index] || "support");
  }
  const role: ElementAssetRole = type === "prop" ? "object" : type === "location" ? "location" : "style";
  return Array.from({ length: count }, () => role);
}

function elementRoleLabel(role: ElementAssetRole) {
  return role.replaceAll("_", " ");
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
    <div className="prompt-highlight" aria-hidden="true">
      {parts.map((part, index) => {
        if (!part.startsWith("@")) return <span key={`${index}-${part.slice(0, 8)}`}>{part}</span>;
        const element = byHandle.get(part.slice(1).toLowerCase());
        if (!element) return <span key={`${index}-${part}`}>{part}</span>;
        return <span key={`${index}-${part}`} className={`mention ${elementTone(element.type)}`}>{part}</span>;
      })}
    </div>
  );
}

export default function Home() {
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginOtp, setLoginOtp] = useState("");
  const [demoOtp, setDemoOtp] = useState<string | null>(null);
  const [loginStep, setLoginStep] = useState<"email" | "otp">("email");
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<GenerationMode>("factory");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("16:9");
  const [sceneCount, setSceneCount] = useState(2);
  const [durationSeconds, setDurationSeconds] = useState(15);
  const [factoryTargetSeconds, setFactoryTargetSeconds] = useState(15);
  const [factorySceneSeconds, setFactorySceneSeconds] = useState(15);
  const [quality, setQuality] = useState<RenderQuality>("preview");
  const [audioMode, setAudioMode] = useState<AudioMode>("mastered");
  const [audioDirection, setAudioDirection] = useState(DEFAULT_AUDIO_DIRECTION);
  const provider: VideoProviderName = "modal";
  const model: VideoModelName = "ltx-2.5";
  const [decoder, setDecoder] = useState<DecoderName>("conv");
  const [realismProfile, setRealismProfile] = useState<RealismProfile>("standard");
  const [seed, setSeed] = useState(42);
  const [enhancePrompt, setEnhancePrompt] = useState(false);
  const [continuityMode, setContinuityMode] = useState<ContinuityMode>("strict");

  // Cinema Studio-style director controls. Defaults are intentionally "auto" so
  // prompt-only mode remains byte-for-byte user-authored until the creator opts in.
  const [cameraMove, setCameraMove] = useState<CameraMove>("auto");
  const [lensPreset, setLensPreset] = useState<LensPreset>("auto");
  const [shotSize, setShotSize] = useState<ShotSize>("auto");
  const [genrePreset, setGenrePreset] = useState<GenrePreset>("auto");
  const [colorPreset, setColorPreset] = useState<ColorPreset>("auto");
  const [tempoPreset, setTempoPreset] = useState<TempoPreset>("auto");
  const [showElementsLibrary, setShowElementsLibrary] = useState(false);
  const [chatSessions, setChatSessions] = useState<StudioChatSession[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [chatHistoryReady, setChatHistoryReady] = useState(false);

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
  const [elementWardrobePolicies, setElementWardrobePolicies] = useState<Record<string, ElementWardrobePolicy>>({});
  const [elementApplyAll, setElementApplyAll] = useState<Record<string, boolean>>({});
  const [elementStrengths, setElementStrengths] = useState<Record<string, number>>({});
  const [railOpen, setRailOpen] = useState(false);
  const [elementDetailOpen, setElementDetailOpen] = useState(false);
  const [elementFilePreviews, setElementFilePreviews] = useState<string[]>([]);
  const [elementKeepInShot, setElementKeepInShot] = useState<Record<string, boolean>>({});
  const [continueFrame, setContinueFrame] = useState<ContinueFrame | null>(null);
  const [heroFrame, setHeroFrame] = useState<HeroFrame | null>(null);
  const [heroBusy, setHeroBusy] = useState(false);
  const [upscaling, setUpscaling] = useState(false);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  const stageVideoRef = useRef<HTMLVideoElement | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const caretRef = useRef<number | null>(null);

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
  const factoryDurationOptions = FACTORY_SCENE_OPTIONS[quality].filter((value) => value <= factoryTargetSeconds);
  const isBusy = planning || directGenerating || factoryGenerating || generatingScene !== null || creatingFinal || heroBusy || upscaling;
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
  // Only Elements that are actually @mentioned take part in a shot. A hidden "keep active" flag on an
  // Element whose @mention was deleted used to keep feeding its face into the identity sheet.
  const referencedElements = useMemo(
    () => elements.filter((element) => hasElementMention(prompt, element.handle)),
    [elements, prompt]
  );
  const parkedHandles = useMemo(() => {
    const { story, tags } = splitTrailingTags(prompt);
    if (!tags.length) return new Set<string>();
    const inStory = (element: CinemaElement) => hasElementMention(story, element.handle);
    const hasNarrativeCharacter = referencedElements.some((element) => element.type === "character" && inStory(element));
    if (!hasNarrativeCharacter) return new Set<string>();
    const tagSet = new Set(tags.map((tag) => tag.toLowerCase()));
    return new Set(
      referencedElements
        .filter((element) => element.type === "character" && !inStory(element) && tagSet.has(element.handle.toLowerCase()) && !elementKeepInShot[element.id])
        .map((element) => element.id)
    );
  }, [prompt, referencedElements, elementKeepInShot]);
  const stillRisk = useMemo(() => {
    const { story } = splitTrailingTags(prompt);
    if (story.trim().length < 20) return null;
    const cast = referencedElements.find((element) => element.type === "character" && hasElementMention(story, element.handle) && !parkedHandles.has(element.id));
    if (!cast || PERFORMANCE_CUE.test(story)) return null;
    // The Element's own description belongs in the Element, not in the shot prompt.
    return cast;
  }, [prompt, referencedElements, parkedHandles]);
  const referenceFrameCandidate = useMemo(() => {
    if (!REFERENCE_FRAME_CUE.test(prompt) || continueFrame) return null;
    if (referencedElements.some((element) => (elementModes[element.id] || "identity") === "start_frame")) return null;
    const { story } = splitTrailingTags(prompt);
    return referencedElements.find((element) => element.type === "character" && hasElementMention(story, element.handle) && !parkedHandles.has(element.id)) || null;
  }, [prompt, continueFrame, referencedElements, elementModes, parkedHandles]);
  const activeElementLimit = capabilities?.elements?.max_active_per_scene ?? 6;
  const elementBindings = useMemo<ElementBinding[]>(
    () => referencedElements.slice(0, activeElementLimit).map((element) => ({
      element_id: element.id,
      version_id: element.current_version_id,
      handle: element.handle,
      reference_mode: elementModes[element.id] || "identity",
      wardrobe_policy: element.type === "character" ? (elementWardrobePolicies[element.id] || "prompt") : "reference",
      strength: Math.max(0, Math.min(1, elementStrengths[element.id] ?? 1.0)),
      apply_to_all_scenes: Boolean(elementApplyAll[element.id]),
      cast_role: elementKeepInShot[element.id] ? "cast" : "auto",
    })),
    [referencedElements, activeElementLimit, elementModes, elementWardrobePolicies, elementStrengths, elementApplyAll, elementKeepInShot]
  );
  const mentionSuggestions = useMemo(() => {
    if (mentionQuery == null) return [];
    const query = mentionQuery.toLowerCase();
    const matches = elements.filter((element) =>
      element.handle.toLowerCase().startsWith(query) || element.name.toLowerCase().includes(query)
    ).slice(0, 8);
    // A handle that is already complete needs no suggestion menu.
    if (matches.length === 1 && matches[0].handle.toLowerCase() === query) return [];
    return matches;
  }, [mentionQuery, elements]);
  const characterElements = useMemo(() => elements.filter((element) => element.type === "character"), [elements]);
  const quickCharacterElements = useMemo(
    () => characterElements.filter((element) => !referencedElements.some((active) => active.id === element.id)).slice(0, 4),
    [characterElements, referencedElements]
  );
  const latestRenderedVideo = useMemo(() => {
    const values = Object.values(renderedVideos);
    return values.length ? values[values.length - 1] : null;
  }, [renderedVideos]);
  const studioVideoUrl = finalVideo?.url || latestRenderedVideo?.url || null;
  const renderEstimate = useMemo(
    () => estimateRender(quality, realismProfile, mode === "factory" ? factoryTargetSeconds : durationSeconds),
    [quality, realismProfile, mode, factoryTargetSeconds, durationSeconds]
  );
  const progressPercent = useMemo(() => {
    const match = progressMessage.match(/(\d{1,3})%\s*$/);
    return match ? Math.min(100, Number(match[1])) : null;
  }, [progressMessage]);
  const progressLabel = useMemo(() => progressMessage.replace(/\s*\d{1,3}%\s*$/, "").trim(), [progressMessage]);
  const recentGenerations = useMemo(
    () => sortedChatSessionsForGallery(chatSessions),
    [chatSessions]
  );
  const sortedChatSessions = useMemo(
    () => [...chatSessions].sort((a, b) => b.updatedAt - a.updatedAt),
    [chatSessions]
  );
  const activeChatTitle = useMemo(
    () => chatSessions.find((session) => session.id === activeChatId)?.title || chatTitleFromPrompt(prompt),
    [chatSessions, activeChatId, prompt]
  );

  useEffect(() => {
    let active = true;
    async function restoreLogin() {
      try {
        const session = await getAuthMe();
        if (!active) return;
        setAuthUser(session.authenticated ? session.user : null);
      } catch {
        if (active) setAuthUser(null);
      } finally {
        if (active) setAuthChecking(false);
      }
    }
    void restoreLogin();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!isBusy) return undefined;
    const started = Date.now();
    const timer = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => {
      window.clearInterval(timer);
      setElapsedSeconds(0);
    };
  }, [isBusy]);

  useEffect(() => {
    // Close the account menu when clicking anywhere else.
    function closeAccountMenu(event: MouseEvent) {
      const menu = document.querySelector<HTMLDetailsElement>("details.account[open]");
      if (menu && event.target instanceof Node && !menu.contains(event.target)) menu.removeAttribute("open");
    }
    document.addEventListener("click", closeAccountMenu);
    return () => document.removeEventListener("click", closeAccountMenu);
  }, []);

  useEffect(() => {
    // The studio ships a single light theme. Clear any dark preference saved by older builds.
    document.documentElement.dataset.theme = "light";
    try { window.localStorage.removeItem("triven-cinema-theme"); } catch { /* storage may be blocked */ }
  }, []);

  useEffect(() => {
    if (!authUser) {
      // Intentional: clear the project list the moment the signed-in account goes away.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setChatSessions([]);
      setActiveChatId(null);
      setChatHistoryReady(false);
      return;
    }
    let active = true;
    setChatHistoryReady(false);
    setActiveChatId(null);
    async function loadHistory() {
      try {
        const response = await listChatHistory();
        if (!active) return;
        let sessions = response.chats.map(chatFromServer).sort((a, b) => b.updatedAt - a.updatedAt);
        if (sessions.length === 0) {
          // One-time migration from the pre-login browser history. Only migrate
          // after a successful empty server response, so shared-browser data is
          // never used as a fallback for an existing account.
          const localMigration = readStoredChatSessions(authUser?.id, true);
          if (localMigration.length) {
            sessions = localMigration;
            void Promise.allSettled(localMigration.map((item) => saveChatHistoryItem(chatToServer(item))));
            window.localStorage.removeItem(LEGACY_CHAT_HISTORY_STORAGE_KEY);
          }
        }
        setChatSessions(sessions);
        persistChatSessions(sessions, authUser?.id);
      } catch {
        if (!active) return;
        // Server history is canonical. Offline fallback is account-scoped only.
        setChatSessions(readStoredChatSessions(authUser?.id));
      } finally {
        if (active) setChatHistoryReady(true);
      }
    }
    void loadHistory();
    return () => { active = false; };
  }, [authUser?.id]);

  useEffect(() => {
    if (!chatHistoryReady) return;
    const workspace: StudioChatWorkspace = {
      prompt,
      mode,
      aspectRatio,
      sceneCount,
      durationSeconds,
      factoryTargetSeconds,
      factorySceneSeconds,
      quality,
      audioMode,
      audioDirection,
      decoder,
      realismProfile,
      seed,
      enhancePrompt,
      continuityMode,
      cameraMove,
      lensPreset,
      shotSize,
      genrePreset,
      colorPreset,
      tempoPreset,
      selectedElementId,
      elementModes,
      elementWardrobePolicies,
      elementApplyAll,
      elementStrengths,
      elementKeepInShot,
      result,
      scenePrompts,
      renderedVideos,
      factoryResult,
      finalVideo,
    };

    // Do not put a blank landing-state chat into history. The draft becomes a
    // real chat as soon as the creator starts writing a prompt.
    if (!activeChatId) {
      if (!prompt.trim()) return;
      const session = createChatSession(workspace);
      // Intentional: the project is created the moment the first prompt is typed.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveChatId(session.id);
      setChatSessions((current) => {
        const sorted = [session, ...current].sort((a, b) => b.updatedAt - a.updatedAt);
        persistChatSessions(sorted, authUser?.id);
        return sorted;
      });
      return;
    }

    setChatSessions((current) => {
      const now = Date.now();
      let found = false;
      const next = current.map((session) => {
        if (session.id !== activeChatId) return session;
        found = true;
        return {
          ...session,
          title: prompt.trim() ? chatTitleFromPrompt(prompt) : session.title,
          updatedAt: now,
          workspace,
        };
      });
      if (!found) return current;
      const sorted = next.sort((a, b) => b.updatedAt - a.updatedAt);
      persistChatSessions(sorted, authUser?.id);
      return sorted;
    });
  }, [
    chatHistoryReady,
    activeChatId,
    prompt,
    mode,
    aspectRatio,
    sceneCount,
    durationSeconds,
    factoryTargetSeconds,
    factorySceneSeconds,
    quality,
    audioMode,
    audioDirection,
    decoder,
    realismProfile,
    seed,
    enhancePrompt,
    continuityMode,
    cameraMove,
    lensPreset,
    shotSize,
    genrePreset,
    colorPreset,
    tempoPreset,
    selectedElementId,
    elementModes,
    elementWardrobePolicies,
    elementApplyAll,
    elementStrengths,
    elementKeepInShot,
    result,
    scenePrompts,
    renderedVideos,
    factoryResult,
    finalVideo,
  ]);

  useEffect(() => {
    if (!authUser || !chatHistoryReady || !activeChatId) return;
    const session = chatSessions.find((item) => item.id === activeChatId);
    if (!session) return;
    const timer = window.setTimeout(() => {
      void saveChatHistoryItem(chatToServer(session)).catch(() => {
        // Keep the local cache as a resilience fallback; the next edit retries.
      });
    }, 700);
    return () => window.clearTimeout(timer);
  }, [authUser?.id, chatHistoryReady, activeChatId, chatSessions]);

  useEffect(() => {
    if (!authUser) return;
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
  }, [authUser?.id]);

  function applyChatWorkspace(rawWorkspace: StudioChatWorkspace) {
    const workspace = normalizeChatWorkspace(rawWorkspace);
    setPrompt(workspace.prompt);
    setMode(workspace.mode);
    setAspectRatio(workspace.aspectRatio);
    setSceneCount(workspace.sceneCount);
    setDurationSeconds(workspace.durationSeconds);
    setFactoryTargetSeconds(workspace.factoryTargetSeconds);
    setFactorySceneSeconds(workspace.factorySceneSeconds);
    setQuality(workspace.quality);
    setAudioMode(workspace.audioMode);
    setAudioDirection(workspace.audioDirection);
    setDecoder(workspace.decoder);
    setRealismProfile(workspace.realismProfile);
    setSeed(workspace.seed);
    setEnhancePrompt(workspace.enhancePrompt);
    setContinuityMode(workspace.continuityMode);
    setCameraMove(workspace.cameraMove);
    setLensPreset(workspace.lensPreset);
    setShotSize(workspace.shotSize);
    setGenrePreset(workspace.genrePreset);
    setColorPreset(workspace.colorPreset);
    setTempoPreset(workspace.tempoPreset);
    setSelectedElementId(workspace.selectedElementId);
    setElementModes(workspace.elementModes);
    setElementWardrobePolicies(workspace.elementWardrobePolicies);
    setElementApplyAll(workspace.elementApplyAll);
    setElementStrengths(workspace.elementStrengths);
    setElementKeepInShot(workspace.elementKeepInShot);
    setContinueFrame(null);
    setHeroFrame(null);
    setResult(workspace.result);
    setScenePrompts(workspace.scenePrompts);
    setRenderedVideos(workspace.renderedVideos);
    setFactoryResult(workspace.factoryResult);
    setFinalVideo(workspace.finalVideo);
    setEditingScene(null);
    setProgressMessage("");
    setError("");
    setNotice("");
    setMentionQuery(null);
    setShowElementsLibrary(false);
  }

  function handleNewChat() {
    if (isBusy) {
      setNotice("Wait for the current render to finish before starting a new chat.");
      return;
    }

    // The active chat is already kept in chatSessions by the workspace sync effect.
    // New Chat only switches the UI to a fresh unsaved draft; it will not appear in
    // Previous chats until the creator starts typing a prompt.
    persistChatSessions(chatSessions, authUser?.id);
    setActiveChatId(null);
    applyChatWorkspace(createEmptyChatWorkspace());
  }

  function handleOpenChat(session: StudioChatSession) {
    if (session.id === activeChatId) return;
    if (isBusy) {
      setNotice("Wait for the current render to finish before switching chats.");
      return;
    }
    setActiveChatId(session.id);
    applyChatWorkspace(session.workspace);
    persistChatSessions(chatSessions, authUser?.id);
  }

  async function handleDeleteChat(chatId: string) {
    // The current working chat is intentionally protected from deletion.
    if (chatId === activeChatId) return;
    const target = chatSessions.find((session) => session.id === chatId);
    if (!target) return;
    if (!window.confirm(`Delete “${target.title}” from chat history? Rendered media files will not be deleted.`)) return;

    const remaining = chatSessions.filter((session) => session.id !== chatId);
    setChatSessions(remaining);
    persistChatSessions(remaining, authUser?.id);
    try {
      await deleteChatHistoryItem(chatId);
    } catch (err) {
      setError(errorMessage(err, "Unable to delete chat from your account."));
      setChatSessions((current) => [target, ...current].sort((a, b) => b.updatedAt - a.updatedAt));
    }
  }

  function handleQualityChange(nextQuality: RenderQuality) {
    setQuality(nextQuality);
    const options = DURATION_OPTIONS[nextQuality];
    const factoryOptions = FACTORY_SCENE_OPTIONS[nextQuality].filter((value) => value <= factoryTargetSeconds);
    setDurationSeconds((current) => options.includes(current) ? current : options[Math.min(2, options.length - 1)]);
    setFactorySceneSeconds((current) => {
      if (factoryOptions.includes(current)) return current;
      return factoryOptions[factoryOptions.length - 1] ?? Math.min(factoryTargetSeconds, 15);
    });
    invalidateRenderedMedia();
  }

  function handleFactoryTargetChange(nextTarget: number) {
    const maximum = capabilities?.max_factory_duration_seconds ?? 300;
    const next = Math.max(15, Math.min(maximum, Number(nextTarget) || 15));
    setFactoryTargetSeconds(next);
    setFactorySceneSeconds((current) => Math.min(current, next));
    invalidateRenderedMedia();
  }

  function handleFactorySceneDurationChange(nextSceneSeconds: number) {
    const next = Math.max(15, Math.min(factoryTargetSeconds, Number(nextSceneSeconds) || 15));
    setFactorySceneSeconds(next);
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

  function updateMentionState(value: string, caret: number = value.length) {
    setPrompt(value);
    caretRef.current = caret;
    const match = value.slice(0, caret).match(/(?:^|\s)@([A-Za-z0-9_-]*)$/);
    setMentionQuery(match ? match[1] : null);
  }

  function rememberCaret(target: HTMLTextAreaElement) {
    caretRef.current = target.selectionStart ?? target.value.length;
  }

  // Place text where the creator was typing instead of tacking it on after the last sentence,
  // where a mention becomes a detached tag that says nothing about the shot.
  function insertAtCaret(text: string) {
    const caret = Math.min(caretRef.current ?? prompt.length, prompt.length);
    const before = prompt.slice(0, caret);
    const after = prompt.slice(caret);
    const lead = before && !/\s$/.test(before) ? " " : "";
    const trail = after && !/^\s/.test(after) ? " " : after ? "" : " ";
    setPrompt(`${before}${lead}${text}${trail}${after}`);
    const next = before.length + lead.length + text.length + trail.length;
    caretRef.current = next;
    window.setTimeout(() => {
      promptRef.current?.focus();
      promptRef.current?.setSelectionRange(next, next);
    }, 0);
  }

  function canActivateElement(element: CinemaElement) {
    const alreadyActive = hasElementMention(prompt, element.handle);
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
    if (!hasElementMention(prompt, element.handle)) insertAtCaret(mention);
    setMentionQuery(null);
    setElementModes((current) => ({ ...current, [element.id]: current[element.id] || "identity" }));
    if (element.type === "character") setElementWardrobePolicies((current) => ({ ...current, [element.id]: current[element.id] || "prompt" }));
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
    const caret = Math.min(caretRef.current ?? prompt.length, prompt.length);
    const before = prompt.slice(0, caret).replace(/@([A-Za-z0-9_-]*)$/, `@${element.handle} `);
    setPrompt(`${before}${prompt.slice(caret)}`);
    caretRef.current = before.length;
    window.setTimeout(() => {
      promptRef.current?.focus();
      promptRef.current?.setSelectionRange(before.length, before.length);
    }, 0);
    setMentionQuery(null);
    setElementModes((current) => ({ ...current, [element.id]: current[element.id] || "identity" }));
    if (element.type === "character") setElementWardrobePolicies((current) => ({ ...current, [element.id]: current[element.id] || "prompt" }));
    setElementStrengths((current) => ({ ...current, [element.id]: current[element.id] ?? 1.0 }));
    setElementApplyAll((current) => ({
      ...current,
      [element.id]: current[element.id] ?? (element.type === "character" || element.type === "style"),
    }));
  }

  function applyCreatorGradePreset() {
    const activeCharacters = referencedElements.filter((element) => element.type === "character");
    // Creator-grade is a quality/consistency preset, not a duration preset.
    // Preserve the runtime and scene length the user selected.
    setQuality("1080p");
    setDecoder("diffusion");
    setContinuityMode("strict");
    setEnhancePrompt(false);
    invalidateRenderedMedia();
    if (activeCharacters.length > 1) {
      setRealismProfile("real_skin");
      setError(
        `Creator-grade solo presenter mode found ${activeCharacters.length} Character Elements (${activeCharacters.map((element) => `@${element.handle}`).join(", ")}). Keep only the one person who should appear in this shot; multiple identity sheets can blend faces.`
      );
      return;
    }
    if (activeCharacters.length) {
      setRealismProfile("identity_max");
      setElementModes((current) => {
        const next = { ...current };
        activeCharacters.forEach((element) => { next[element.id] = "identity"; });
        return next;
      });
      setElementWardrobePolicies((current) => {
        const next = { ...current };
        activeCharacters.forEach((element) => { next[element.id] = "prompt"; });
        return next;
      });
      setElementStrengths((current) => {
        const next = { ...current };
        activeCharacters.forEach((element) => { next[element.id] = 1.0; });
        return next;
      });
      setElementApplyAll((current) => {
        const next = { ...current };
        activeCharacters.forEach((element) => { next[element.id] = true; });
        return next;
      });
      setNotice(`Creator-grade preset applied for your selected ${factoryTargetSeconds}s runtime: 1080p Diffusion final, Identity Max, strict continuity, stage-2 Character lock and prompt-authoritative wardrobe.`);
    } else {
      setRealismProfile("real_skin");
      setNotice(`Creator-grade render settings applied for your selected ${factoryTargetSeconds}s runtime. Add a Character Element to enable Identity Max face locking.`);
    }
  }

  function clearCreatorFiles() {
    elementFilePreviews.forEach((url) => URL.revokeObjectURL(url));
    setElementFilePreviews([]);
    setElementFiles([]);
  }

  function chooseCreatorFiles(files: File[]) {
    elementFilePreviews.forEach((url) => URL.revokeObjectURL(url));
    setElementFiles(files);
    setElementFilePreviews(files.map((file) => URL.createObjectURL(file)));
  }

  function closeElementCreator() {
    setShowElementCreator(false);
    clearCreatorFiles();
    setError("");
  }

  function switchToDraft() {
    handleQualityChange("preview");
    setRealismProfile("standard");
    setNotice("Switched to Draft: Preview quality and Standard detail. It renders in about a minute and a half.");
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
        roles: suggestedElementRoles(elementType, elementFiles.length),
      });
      await refreshElements();
      setSelectedElementId(created.id);
      setShowElementCreator(false);
      setElementName("");
      setElementHandle("");
      setElementDescription("");
      clearCreatorFiles();
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
      const incoming = Array.from(files);
      await addElementAssets(
        element.id,
        incoming,
        suggestedElementRoles(element.type, incoming.length, element.assets.map((asset) => asset.role))
      );
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

  function continueFromFinalVideo() {
    if (!finalVideo?.continuityFrameFilename) return;
    setContinueFrame({
      filename: finalVideo.continuityFrameFilename,
      url: finalVideo.continuityFrameUrl || "",
    });
    setContinuityMode("strict");
    setHeroFrame(null);
    if (mode === "storyboard") setMode("factory");
    setError("");
    setNotice("Continuing this scene: the next video opens on this video's last frame. Describe what happens next, keeping the same @Elements.");
    window.setTimeout(() => {
      document.querySelector(".studio-prompt-panel")?.scrollIntoView({ behavior: "smooth", block: "center" });
      promptRef.current?.focus();
    }, 0);
  }

  async function handleUploadHeroFrame(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setError("");
    setNotice("");
    setHeroBusy(true);
    try {
      const frame = await uploadHeroFrame(file);
      setHeroFrame({ filename: frame.filename, url: absoluteApiUrl(frame.url), model: "your upload" });
      setContinueFrame(null);
      setNotice("Your start frame is ready. Check it, then press Generate to animate it.");
    } catch (err) {
      setError(errorMessage(err, "Unable to upload the start frame."));
    } finally {
      setHeroBusy(false);
    }
  }

  async function handleUpscale() {
    if (!finalVideo?.filename || isBusy) return;
    setError("");
    setNotice("");
    setUpscaling(true);
    setProgressMessage("Sharpening your approved Draft at Full HD…");
    try {
      const started = await createUpscaleJob({ source_filename: finalVideo.filename });
      const response = await waitForJobResult<UpscaleResponse>(started.job_id, (job) => setProgressMessage(`${job.message} ${job.progress}%`));
      setFinalVideo({
        url: absoluteApiUrl(response.final_video_url),
        downloadUrl: absoluteApiUrl(response.final_download_url),
        filename: response.final_filename,
        qualityNote: response.quality_note,
        label: `Full HD upscale of your Draft · ${response.gpu || "GPU"} · ${response.total_render_seconds.toFixed(0)}s`,
        hasAudio: response.has_audio,
        audioCodec: response.has_audio ? "AAC" : null,
        dimensions: `${response.width ?? "?"}×${response.height ?? "?"}`,
        estimatedCostUsd: response.estimated_cost_usd,
        gpu: response.gpu,
        quality: "1080p",
      });
      setNotice("Full HD ready. It is your approved Draft with more detail: the same picture, motion and voice.");
      await refreshBilling();
    } catch (err) {
      setError(errorMessage(err, "Unable to upscale the Draft."));
    } finally {
      setUpscaling(false);
      setProgressMessage("");
    }
  }

  async function handleCreateHeroFrame() {
    if (!prompt.trim()) {
      setError("Describe the shot first, including who holds what, then create the start frame.");
      return;
    }
    if (referencedElements.length === 0) {
      setError("Add a character or product with @ first. The start frame is built from your saved photos.");
      return;
    }
    setError("");
    setNotice("");
    setHeroBusy(true);
    setProgressMessage("Creating your start frame from the saved photos…");
    try {
      const frame = await createHeroFrame({ prompt: promptWithDirectorControls(prompt), aspect_ratio: aspectRatio, element_bindings: elementBindings });
      setHeroFrame({ filename: frame.filename, url: absoluteApiUrl(frame.url), model: frame.model });
      setContinueFrame(null);
      setNotice(`Start frame ready (made with ${frame.model}). Check the face, hands and product. If it looks right, press Generate to animate it.`);
    } catch (err) {
      setError(errorMessage(err, "Unable to create the start frame."));
    } finally {
      setHeroBusy(false);
      setProgressMessage("");
    }
  }

  function applyExactStartFrame(element: CinemaElement) {
    setElementModes((current) => ({ ...current, [element.id]: "start_frame" }));
    setNotice(`@${element.handle} will open the shot as the exact starting frame, then animate forward from it.`);
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
      label: `${response.provider} · ${response.chunk_count} LTX chunk${response.chunk_count === 1 ? "" : "s"} · ${response.render_seconds.toFixed(1)}s render${response.detail_refined ? " · Real Skin refined" : ""}`,
      hasAudio: response.media_info.has_audio,
      audioCodec: response.media_info.audio_codec,
      dimensions: `${response.media_info.width ?? "?"}×${response.media_info.height ?? "?"}`,
      estimatedCostUsd: response.estimated_cost_usd,
      gpu: response.gpu,
      continuityFrameFilename: response.continuity_frame_filename,
      continuityFrameUrl: response.continuity_frame_url ? absoluteApiUrl(response.continuity_frame_url) : null,
      warnings: response.continuity_warnings,
      quality: response.quality,
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
        realism_profile: realismProfile,
        audio_mode: audioMode,
        audio_direction: audioDirection.trim() || null,
        provider,
        model,
        decoder,
        seed,
        continuity_mode: continuityMode,
        continuity_strength: referencedElements.some((element) => element.type === "character")
          ? (realismProfile === "identity_max" ? 1.0 : 0.95)
          : 0.9,
        continuity_qc_mode: quality !== "preview" ? "strict" : "auto",
        continuity_max_retries: realismProfile === "identity_max" ? 2 : 1,
        enhance_prompt: enhancePrompt,
        element_bindings: elementBindings,
        start_frame_filename: continueFrame?.filename ?? null,
        hero_frame_filename: heroFrame?.filename ?? null,
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
        label: `${response.scene_count} scenes · ${response.chunk_count} LTX chunks · ${response.provider} · ${response.total_render_seconds.toFixed(1)}s GPU render${response.detail_refined ? " · Real Skin refined" : ""}`,
        hasAudio: response.has_audio,
        audioCodec: response.has_audio ? "AAC / generated audio" : null,
        dimensions: `${response.width ?? "?"}×${response.height ?? "?"}`,
        estimatedCostUsd: response.estimated_cost_usd,
        gpu: response.gpu,
        youtubeUrl: response.youtube_url,
        youtubePrivacy: response.youtube_privacy,
        continuityFrameFilename: response.continuity_frame_filename,
        continuityFrameUrl: response.continuity_frame_url ? absoluteApiUrl(response.continuity_frame_url) : null,
        warnings: response.continuity_warnings,
        quality: response.quality,
      });
      setContinueFrame(null);
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
    if (realismProfile === "identity_max" && !referencedElements.some((element) => element.type === "character" && (elementModes[element.id] || "identity") === "identity")) {
      setError("Identity Max needs an active Character Element in Identity mode. Add @your-character or enable it across Factory scenes, then use a sharp real photo as the primary reference.");
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
          realism_profile: realismProfile,
          audio_mode: audioMode,
          audio_direction: audioDirection.trim() || null,
          provider,
          model,
          continuity_mode: continueFrame ? "strict" : "off",
          reference_frame_filename: continueFrame?.filename ?? null,
          continuity_strength: continueFrame ? 1.0 : undefined,
          element_bindings: elementBindings,
        });
        setFinalVideo(finalFromSceneResponse(response));
        setContinueFrame(null);
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
      realism_profile: realismProfile,
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
      continuity_max_retries: realismProfile === "identity_max" ? 2 : 1,
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
      realismProfile: response.realism_profile,
      detailRefined: response.detail_refined,
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

  async function handleRequestLoginOtp(event: FormEvent) {
    event.preventDefault();
    setLoginBusy(true);
    setLoginError("");
    try {
      const response = await requestLoginOtp(loginEmail);
      setDemoOtp(response.demo_otp);
      setLoginOtp(response.demo_otp || "");
      setLoginStep("otp");
    } catch (err) {
      setLoginError(errorMessage(err, "Unable to create login code."));
    } finally {
      setLoginBusy(false);
    }
  }

  async function handleVerifyLoginOtp(event: FormEvent) {
    event.preventDefault();
    setLoginBusy(true);
    setLoginError("");
    try {
      const response = await verifyLoginOtp(loginEmail, loginOtp);
      if (!response.authenticated || !response.user) throw new Error("Login did not return an account session.");
      setAuthUser(response.user);
      setDemoOtp(null);
      setLoginOtp("");
      setLoginStep("email");
    } catch (err) {
      setLoginError(errorMessage(err, "Unable to sign in."));
    } finally {
      setLoginBusy(false);
    }
  }

  async function handleLogout() {
    if (isBusy) {
      setNotice("Finish the current render before signing out.");
      return;
    }
    try {
      await logoutCinema();
    } catch {
      // Clear the local UI even if the network response is interrupted.
    }
    setAuthUser(null);
    setChatSessions([]);
    setActiveChatId(null);
    setChatHistoryReady(false);
    applyChatWorkspace(createEmptyChatWorkspace());
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

  if (authChecking) {
    return (
      <main className="login-loading">
        <div className="row"><span className="brand-mark">T</span><span className="spinner" /><span>Opening Triven Cinema…</span></div>
      </main>
    );
  }

  if (!authUser) {
    return (
      <main className="login">
        <section className="login-hero" aria-hidden="true">
          <div className="brand"><span className="brand-mark">T</span><span className="brand-name">Triven Cinema</span></div>
          <div>
            <h2>Make films with characters that stay the same.</h2>
            <p>Describe a shot, add your cast, and get a finished video with voice. Continue any scene without losing the face.</p>
            <ul className="login-points">
              <li>Save characters once, use them with @name</li>
              <li>Draft in about a minute, finish in 1080p</li>
              <li>Continue a scene from its last frame</li>
            </ul>
          </div>
          <small>AI filmmaking studio</small>
        </section>
        <section className="login-main">
          <div className="login-card">
            <h1>{loginStep === "email" ? "Sign in" : "Enter your code"}</h1>
            <p>{loginStep === "email" ? "Your projects, characters and videos stay connected to this email." : `We created a one-time code for ${loginEmail}.`}</p>
            {loginStep === "email" ? (
              <form onSubmit={handleRequestLoginOtp} className="stack">
                <div>
                  <label className="label" htmlFor="login-email">Email address</label>
                  <input id="login-email" className="field" type="email" required autoComplete="email" value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} placeholder="you@company.com" />
                </div>
                <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={loginBusy || !loginEmail.trim()}>{loginBusy ? <span className="spinner" /> : null}Continue</button>
              </form>
            ) : (
              <form onSubmit={handleVerifyLoginOtp} className="stack">
                {demoOtp ? <div className="otp-box"><small>Demo code (shown because demo sign-in is on)</small><strong>{demoOtp}</strong></div> : null}
                <div>
                  <label className="label" htmlFor="login-otp">One-time code</label>
                  <input id="login-otp" className="field" inputMode="numeric" autoComplete="one-time-code" required value={loginOtp} onChange={(event) => setLoginOtp(event.target.value.replace(/\D/g, "").slice(0, 8))} placeholder="6-digit code" />
                </div>
                <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={loginBusy || loginOtp.length < 4}>{loginBusy ? <span className="spinner" /> : null}Open the studio</button>
                <button type="button" className="btn btn-ghost btn-block" onClick={() => { setLoginStep("email"); setLoginOtp(""); setDemoOtp(null); setLoginError(""); }}>Use another email</button>
              </form>
            )}
            {loginError ? <div className="notice notice-error" role="alert" style={{ marginTop: "1rem" }}><span>{loginError}</span></div> : null}
          </div>
        </section>
      </main>
    );
  }

  const activeModeHint = MODE_OPTIONS.find((item) => item.value === mode)?.hint || "";
  const lengthSeconds = mode === "factory" ? factoryTargetSeconds : durationSeconds;
  const generateLabel = mode === "factory" ? "Generate video" : mode === "direct" ? "Generate clip" : "Create storyboard";
  const parkedElements = referencedElements.filter((element) => parkedHandles.has(element.id));
  const detailElement = elements.find((element) => element.id === selectedElementId) || null;
  const detailAsset = detailElement ? primaryElementAsset(detailElement) : null;
  const detailActive = detailElement ? hasElementMention(prompt, detailElement.handle) : false;
  const finalActionLabel = creatingFinal ? "Creating final video…" : allScenesRendered ? "Combine into final video" : "Render all scenes";

  return (
    <main className="app">
      <header className="topbar">
        <button type="button" className="icon-btn rail-toggle" aria-label="Open projects" onClick={() => setRailOpen(true)}>☰</button>
        <div className="brand"><span className="brand-mark">T</span><span className="brand-name">Triven Cinema</span></div>
        <div className="topbar-project"><strong title={activeChatTitle}>{activeChatTitle}</strong><span className="saved">Saved</span></div>
        <div className="topbar-right">
          {billingCatalog?.enabled && billingMe ? <span className="chip chip-accent" title="Generation credits">{formatCredits(billingMe.balance_seconds)} credits</span> : null}
          {youtube?.connected ? <span className="chip chip-ok">YouTube connected</span> : null}
          <details className="account">
            <summary aria-label="Account menu"><span className="avatar">{authUser.email.slice(0, 1)}</span></summary>
            <div className="account-menu">
              <div className="email">{authUser.email}</div>
              <div className="kv"><span>Video model</span><span>LTX 2.5 · {capabilities?.gpu || "B200"}</span></div>
              <div className="kv"><span>Longest 1080p shot</span><span>{capabilities?.max_scene_duration_seconds_by_quality?.["1080p"] ?? 30}s</span></div>
              <div className="kv"><span>Longest video</span><span>{capabilities?.max_factory_duration_seconds ?? 300}s</span></div>
              <div className="kv"><span>Characters per shot</span><span>{capabilities?.elements?.max_active_per_scene ?? 6}</span></div>
              {billingCatalog?.enabled && billingMe?.stripe_customer_id ? <button type="button" onClick={handleBillingPortal} className="btn btn-secondary btn-sm btn-block" style={{ marginTop: "0.6rem" }} disabled={integrationBusy}>Manage billing</button> : null}
              {youtube?.enabled ? <button type="button" disabled={integrationBusy} onClick={handleYouTubeConnection} className="btn btn-secondary btn-sm btn-block" style={{ marginTop: "0.5rem" }}>{youtube.connected ? "Disconnect YouTube" : "Connect YouTube"}</button> : null}
              <button type="button" onClick={handleLogout} disabled={isBusy} className="btn btn-ghost btn-sm btn-block" style={{ marginTop: "0.5rem" }}>Sign out</button>
            </div>
          </details>
        </div>
      </header>

      <div className="shell">
        <div className="rail-backdrop" data-open={railOpen} onClick={() => setRailOpen(false)} />
        <aside className="rail" data-open={railOpen} aria-label="Projects and library">
          <button type="button" className="btn btn-primary btn-block" onClick={() => { handleNewChat(); setRailOpen(false); }} disabled={isBusy}><PlusIcon />New project</button>
          <nav className="rail-nav" aria-label="Main">
            <button type="button" className="rail-link" aria-current="page"><FilmIcon />Create</button>
            <button type="button" className="rail-link" onClick={() => { setElementDetailOpen(false); setShowElementsLibrary(true); setRailOpen(false); }}><ElementsIcon />Elements<span className="chip" style={{ marginLeft: "auto" }}>{elements.length}</span></button>
          </nav>
          <div className="rail-title">Projects</div>
          <div className="rail-list" role="list">
            {chatHistoryReady && sortedChatSessions.length === 0 ? <div className="rail-empty">Your projects appear here once you start writing a prompt.</div> : null}
            {sortedChatSessions.map((session) => {
              const active = session.id === activeChatId;
              return (
                <div key={session.id} className="rail-item" role="listitem" aria-current={active}>
                  <button type="button" onClick={() => { handleOpenChat(session); setRailOpen(false); }} disabled={isBusy && !active} title={session.title}><span>{session.title}</span></button>
                  {!active ? <button type="button" className="icon-btn" onClick={() => handleDeleteChat(session.id)} aria-label={`Delete ${session.title}`} title="Delete project"><TrashIcon /></button> : null}
                </div>
              );
            })}
          </div>
        </aside>

        <section className="workspace" aria-label="Preview and history">
          <div className="stage-card">
            <div className="stage-head">
              <h1>Preview</h1>
              <div className="stage-chips">
                <span className="chip">{aspectRatio}</span>
                <span className="chip">{qualityName(quality)}</span>
                <span className="chip">{mode === "storyboard" ? `${sceneCount} scenes` : formatCredits(lengthSeconds)}</span>
              </div>
            </div>
            <div className="stage-area">
              <div className={`canvas ${aspectRatio === "9:16" ? "canvas-portrait" : aspectRatio === "1:1" ? "canvas-square" : "canvas-landscape"} ${studioVideoUrl || heroFrame ? "canvas-media" : "canvas-empty"}`}>
                {studioVideoUrl ? (
                  <video ref={stageVideoRef} src={studioVideoUrl} controls playsInline preload="metadata" />
                ) : heroFrame ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img className="fit" src={heroFrame.url} alt="Start frame waiting to be animated" />
                ) : (
                  <div className="empty-stage">
                    <span className="empty-icon"><FilmIcon /></span>
                    <h2>Your video appears here</h2>
                    <p>Describe your shot in Create and press Generate. Type @ to add a saved character and keep their face the same.</p>
                    <div className="samples" aria-label="Sample prompts">
                      {SAMPLE_PROMPTS.map((sample) => (
                        <button key={sample} type="button" onClick={() => { setPrompt(sample); window.setTimeout(() => promptRef.current?.focus(), 0); }}>{sample}</button>
                      ))}
                    </div>
                  </div>
                )}
                {isBusy && (
                  <div className="render-overlay" role="status" aria-live="polite">
                    <div className="render-card">
                      <div className="render-ring" style={{ ["--pct" as string]: `${progressPercent ?? 8}%` }}>
                        <span>{progressPercent != null ? `${progressPercent}%` : <span className="spinner" />}</span>
                      </div>
                      <div className="render-title">{upscaling ? "Upscaling your Draft" : factoryGenerating || directGenerating ? "Generating your video" : creatingFinal ? "Creating the final video" : planning ? "Planning your shots" : "Rendering a scene"}</div>
                      <div className="render-message">{progressLabel || "Preparing the render…"}</div>
                      <div className="render-bar"><span style={{ width: `${progressPercent ?? 6}%` }} /></div>
                      <div className="render-meta">Elapsed {formatElapsed(elapsedSeconds)} · keep this tab open</div>
                    </div>
                  </div>
                )}
              </div>
            </div>
            <div className="transport">
              {studioVideoUrl ? (
                <>
                  <span className="transport-meta">{finalVideo ? `${finalVideo.dimensions} · ${finalVideo.hasAudio ? "with audio" : "no audio"}${finalVideo.gpu ? ` · ${finalVideo.gpu}` : ""}` : "Latest scene"}</span>
                  <span className="transport-actions">
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => void stageVideoRef.current?.requestFullscreen?.()}>Full screen</button>
                    {finalVideo && isDraftVideo(finalVideo) && finalVideo.filename && (
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => void handleUpscale()} disabled={isBusy} title="Same video, voice and timing, rendered sharper at 1920×1080. It refines this Draft; it does not generate a new one.">Upscale to Full HD</button>
                    )}
                    {finalVideo?.continuityFrameFilename && <button type="button" className="btn btn-secondary btn-sm" onClick={continueFromFinalVideo}>Continue this scene</button>}
                    {finalVideo && <a className="btn btn-primary btn-sm" href={finalVideo.downloadUrl}><DownloadIcon />Download</a>}
                  </span>
                </>
              ) : (
                <span className="transport-meta">{heroFrame ? "This start frame is not animated yet. Press Generate to bring it to life." : "Nothing generated yet in this project."}</span>
              )}
            </div>
          </div>

          {finalVideo?.youtubeUrl && (
            <div className="notice notice-success"><span>Published to YouTube ({finalVideo.youtubePrivacy}). <a href={finalVideo.youtubeUrl} target="_blank" rel="noreferrer"><b>Open on YouTube</b></a></span></div>
          )}

          {(factoryResult?.continuity_warnings.length || factoryResult?.audio_warnings.length) ? (
            <div className="notice notice-warn" role="status">
              <span><b>Review before sharing.</b>{factoryResult.continuity_warnings.concat(factoryResult.audio_warnings).slice(0, 4).map((warning, index) => (<span key={index} style={{ display: "block", marginTop: "0.25rem" }}>{warning}</span>))}</span>
            </div>
          ) : null}

          {factoryResult && (
            <details className="report">
              <summary>Render report</summary>
              <dl className="report-grid">
                <div><dt>Scenes</dt><dd>{factoryResult.scene_count}</dd><small>{factoryResult.chunk_count} LTX chunks</small></div>
                <div><dt>Length</dt><dd>{(factoryResult.actual_duration_seconds ?? factoryResult.target_duration_seconds).toFixed(1)}s</dd><small>{factoryResult.scene_duration_seconds}s per scene</small></div>
                <div><dt>Delivery</dt><dd>{qualityLabel(factoryResult.quality)}</dd><small>{factoryResult.width ?? "?"}×{factoryResult.height ?? "?"} · {factoryResult.audio_mode}</small></div>
                <div><dt>Characters</dt><dd>{factoryResult.elements_used.length ? factoryResult.elements_used.join(", ") : "None"}</dd><small>{factoryResult.element_reference_mode || "prompt only"}</small></div>
                <div><dt>Visual check</dt><dd>{factoryResult.continuity_qc_passed === true ? "Passed" : factoryResult.continuity_qc_passed === false ? "Needs review" : "Not run"}</dd><small>{factoryResult.continuity_regenerations} automatic retr{factoryResult.continuity_regenerations === 1 ? "y" : "ies"}</small></div>
                <div><dt>Audio check</dt><dd>{factoryResult.audio_qc_passed === true ? "Passed" : factoryResult.audio_qc_passed === false ? "Needs review" : "Not run"}</dd><small>{factoryResult.audio_retake_count} audio retake{factoryResult.audio_retake_count === 1 ? "" : "s"}</small></div>
                <div><dt>GPU time</dt><dd>{factoryResult.total_render_seconds.toFixed(0)}s</dd><small>{factoryResult.gpu || "GPU"}{factoryResult.estimated_cost_usd != null ? ` · est. $${factoryResult.estimated_cost_usd.toFixed(2)}` : ""}</small></div>
              </dl>
            </details>
          )}

          {recentGenerations.length > 0 && (
            <section aria-label="History">
              <div className="section-head"><h2>History</h2><span>{recentGenerations.length} video{recentGenerations.length === 1 ? "" : "s"}</span></div>
              <div className="gallery-row">
                {recentGenerations.map((item) => (
                  <button key={item.id} type="button" className="gallery-card" aria-current={item.id === activeChatId} onClick={() => { const target = chatSessions.find((session) => session.id === item.id); if (target) handleOpenChat(target); }} disabled={isBusy && item.id !== activeChatId} title={item.title}>
                    <video src={item.video.url} muted playsInline preload="metadata" />
                    <span className="badge">{item.video.dimensions}</span>
                    <span className="title">{item.title}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {result && mode === "storyboard" && (
            <section id="studio-output" className="sb" aria-label="Storyboard">
              <div className="row-between" style={{ flexWrap: "wrap" }}>
                <div>
                  <div className="row" style={{ flexWrap: "wrap" }}><h2 style={{ margin: 0, fontSize: "1.0625rem" }}>Storyboard</h2><span className="chip">{result.planner_source}</span><span className="chip chip-ok">{continuityMode} consistency</span></div>
                  <p className="help">{result.scenes.length} scenes · {plannedDuration}s · each scene starts from the last frame of the one before.</p>
                </div>
                <button type="button" onClick={handleRenderMissingAndCombine} disabled={isBusy} className="btn btn-primary">{creatingFinal ? <span className="spinner" /> : <PlayIcon />}{finalActionLabel}</button>
              </div>
              <div className="sb-grid">
                {result.scenes.map((scene, index) => {
                  const video = renderedVideos[scene.id];
                  const isGenerating = generatingScene === scene.id;
                  const isEditing = editingScene === scene.id;
                  return (
                    <article key={scene.id} className="sb-card">
                      <div className="sb-media">{video ? <video src={video.url} controls playsInline /> : isGenerating ? <span className="row"><span className="spinner" />Rendering…</span> : "Not rendered yet"}</div>
                      <div className="sb-body">
                        <div className="row-between"><strong className="truncate">Scene {index + 1} · {scene.title}</strong><span className="chip">{durationSeconds}s</span></div>
                        {isEditing ? <textarea className="field" value={scenePrompts[scene.id] || ""} onChange={(e) => updateScenePrompt(scene.id, e.target.value)} /> : <p className="line-clamp-5">{scenePrompts[scene.id]}</p>}
                        {video && <p className="help">{video.details} · {video.renderSeconds.toFixed(0)}s render · {video.mediaInfo.has_audio ? "with audio" : "no audio"}{video.continuityQcPassed === true ? " · check passed" : video.continuityQcPassed === false ? " · needs review" : ""}</p>}
                        <div className="row-between">
                          <button type="button" className="btn btn-ghost btn-sm" disabled={isBusy && !isEditing} onClick={() => setEditingScene(isEditing ? null : scene.id)}>{isEditing ? "Done" : "Edit prompt"}</button>
                          <span className="row">
                            {video && <a className="btn btn-secondary btn-sm" href={video.downloadUrl}><DownloadIcon />Clip</a>}
                            <button type="button" disabled={isBusy} onClick={() => handleRenderScene(scene.id)} className="btn btn-primary btn-sm">{isGenerating ? <span className="spinner" /> : <PlayIcon />}{video ? "Re-render" : "Render"}</button>
                          </span>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
              <p className="help">{renderedSceneCount}/{result.scenes.length} rendered · {allScenesRendered ? "Ready to combine." : "Scenes render in order so each one can continue from the last frame."}</p>
            </section>
          )}
        </section>

        <form className="panel" onSubmit={handleSubmit} aria-label="Create">
          <div className="panel-body">
            <h2 className="panel-title">Create</h2>

            <div className="block">
              <div className="segmented" role="group" aria-label="What to create">
                {MODE_OPTIONS.map((item) => (
                  <button key={item.value} type="button" aria-pressed={mode === item.value} onClick={() => { setMode(item.value); resetOutput(); }}>{item.label}</button>
                ))}
              </div>
              <p className="mode-hint">{activeModeHint}</p>
            </div>

            <div className="block">
              <div className="block-head"><h3>Cast</h3><span>{referencedElements.length}/{activeElementLimit} in this shot</span></div>
              <div className="cast-row">
                {referencedElements.map((element) => {
                  const asset = primaryElementAsset(element);
                  const parked = parkedHandles.has(element.id);
                  return (
                    <span key={element.id} className="cast-chip" data-parked={parked}>
                      {asset ? <img src={absoluteApiUrl(asset.asset_url)} alt="" /> : <span className="ph">{element.name.slice(0, 1)}</span>}
                      <b className={elementTone(element.type)} title={`${element.name} · ${element.type}`}>@{element.handle}</b>
                      {parked ? <em>reference only</em> : (elementModes[element.id] || "identity") === "start_frame" ? <em>opens the shot</em> : null}
                      <button type="button" aria-label={`Settings for @${element.handle}`} title="Settings" onClick={() => { setSelectedElementId(element.id); setElementDetailOpen(true); setShowElementsLibrary(true); }}>⚙</button>
                      <button type="button" aria-label={`Remove @${element.handle} from this shot`} title="Remove" onClick={() => removeElementFromScene(element)}>×</button>
                    </span>
                  );
                })}
                <button type="button" className="cast-add" onClick={() => { setElementDetailOpen(false); setShowElementsLibrary(true); }}><PlusIcon />{referencedElements.length ? "Add" : "Add a character, prop or place"}</button>
              </div>
              {quickCharacterElements.length > 0 && referencedElements.length === 0 && (
                <div className="cast-suggest">Saved:{quickCharacterElements.slice(0, 3).map((element) => (
                  <button key={element.id} type="button" onClick={() => insertElementMention(element)}>@{element.handle}</button>
                ))}</div>
              )}
            </div>

            <div className="block">
              <div className="block-head"><h3>Describe the shot</h3><span>Type @ to add a character</span></div>
              <div className="prompt-wrap">
                <PromptHighlight text={prompt} elements={elements} />
                <textarea
                  ref={promptRef}
                  value={prompt}
                  onChange={(event) => updateMentionState(event.target.value, event.target.selectionStart ?? event.target.value.length)}
                  onSelect={(event) => rememberCaret(event.currentTarget)}
                  onClick={(event) => rememberCaret(event.currentTarget)}
                  onKeyUp={(event) => rememberCaret(event.currentTarget)}
                  onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }}
                  onBlur={() => window.setTimeout(() => setMentionQuery(null), 120)}
                  placeholder="@Maya looks into the lens, smiles and says: “Welcome back.” Describe what she does, what she says, and the camera."
                  className="prompt-input"
                  aria-label="Describe the shot"
                />
                {mentionQuery != null && mentionSuggestions.length > 0 && (
                  <div className="mention-menu">
                    <div>Characters &amp; elements</div>
                    {mentionSuggestions.map((element) => {
                      const asset = primaryElementAsset(element);
                      return (
                        <button key={element.id} type="button" onMouseDown={(event) => { event.preventDefault(); chooseMention(element); }}>
                          {asset ? <img src={absoluteApiUrl(asset.asset_url)} alt="" /> : <span className="ph">{element.name.slice(0, 1)}</span>}
                          <span><b>@{element.handle}</b><small>{element.name} · {element.type}</small></span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
              <div className="prompt-hint"><span>Write what happens and what is said.</span><span>Ctrl + Enter to generate</span></div>

              <div className="hints">
                {continueFrame && mode !== "storyboard" && (
                  <div className="notice notice-success">
                    {continueFrame.url ? <img src={continueFrame.url} alt="Last frame of the previous video" style={{ width: 64, height: 36, borderRadius: 6, objectFit: "cover" }} /> : null}
                    <span><b>Continuing the previous video.</b> It opens on that video&apos;s last frame. Keep the same @characters and describe what happens next.</span>
                    <button type="button" onClick={() => setContinueFrame(null)} aria-label="Stop continuing the previous video">×</button>
                  </div>
                )}
                {stillRisk && (
                  <div className="notice notice-warn"><span><b>No action yet.</b> This says how @{stillRisk.handle} looks but not what happens, so the video can come back as a still image. Add an action or a line, for example <i>@{stillRisk.handle} looks into the lens and says “…”</i>. Keep the appearance in the character itself.</span></div>
                )}
                {!heroFrame && mode === "factory" && referencedElements.filter((element) => !parkedHandles.has(element.id)).length >= 2 && (
                  <div className="notice notice-info">
                    <span>A person and a product are both in this shot. Combining them as references can show up as a split screen in the video. Create a start frame instead: one picture of them together that the video then animates.
                      <span className="notice-actions"><button type="button" className="btn btn-secondary btn-sm" onClick={() => void handleCreateHeroFrame()} disabled={isBusy}>Create start frame</button></span></span>
                  </div>
                )}
                {referenceFrameCandidate && (
                  <div className="notice notice-info">
                    <span>Your prompt says the shot opens “as in the reference”. Use @{referenceFrameCandidate.handle}&apos;s image as the exact first frame?
                      <span className="notice-actions"><button type="button" className="btn btn-secondary btn-sm" onClick={() => applyExactStartFrame(referenceFrameCandidate)}>Use as first frame</button></span></span>
                  </div>
                )}
                {parkedElements.length > 0 && (
                  <div className="notice notice-warn">
                    <span>{parkedElements.map((element) => `@${element.handle}`).join(", ")} {parkedElements.length === 1 ? "is" : "are"} only tagged after the last sentence, so {parkedElements.length === 1 ? "its" : "their"} face stays out of the shot to keep your main character consistent.
                      <span className="notice-actions">{parkedElements.map((element) => (<button key={element.id} type="button" className="btn btn-secondary btn-sm" onClick={() => setElementKeepInShot((current) => ({ ...current, [element.id]: true }))}>Keep @{element.handle} in the shot</button>))}</span></span>
                  </div>
                )}
              </div>
            </div>

            {mode === "factory" && (
              <div className="block">
                <div className="block-head"><h3>Start frame</h3><span>{heroFrame ? "Ready" : "Recommended with products"}</span></div>
                {heroFrame ? (
                  <div className="hero-card">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={heroFrame.url} alt="Start frame" />
                    <div>
                      <b>Video starts from this exact frame</b>
                      <span>Your saved photos are not re-applied, so the face and product stay as shown.</span>
                      <span className="row" style={{ marginTop: "0.4rem" }}>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void handleCreateHeroFrame()} disabled={isBusy}>{heroBusy ? <span className="spinner" /> : null}Redo</button>
                        <label className="btn btn-ghost btn-sm">Upload other<input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" disabled={isBusy} onChange={(e) => { void handleUploadHeroFrame(e.target.files); e.target.value = ""; }} /></label>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setHeroFrame(null)} disabled={isBusy}>Remove</button>
                      </span>
                    </div>
                  </div>
                ) : (
                  <>
                    <button type="button" className="btn btn-secondary btn-block" onClick={() => void handleCreateHeroFrame()} disabled={isBusy || referencedElements.length === 0}>{heroBusy ? <span className="spinner" /> : null}{heroBusy ? "Creating start frame…" : "Create start frame"}</button>
                    <label className="btn btn-ghost btn-sm btn-block">Or upload your own start frame<input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" disabled={isBusy} onChange={(e) => { void handleUploadHeroFrame(e.target.files); e.target.value = ""; }} /></label>
                    <p className="help">Builds one picture of your cast already in position, for example holding the product. You approve it, then it is animated. No Gemini billing? Make the picture in the Gemini app, then upload it here.</p>
                  </>
                )}
              </div>
            )}

            <div className="block">
              <div className="block-head"><h3>Format</h3></div>
              <div className="settings-grid">
                <div className="span-2">
                  <span className="label">Quality</span>
                  <div className="segmented" role="group" aria-label="Quality">
                    {QUALITY_OPTIONS.map((item) => (
                      <button key={item.value} type="button" aria-pressed={quality === item.value} onClick={() => handleQualityChange(item.value)}>{item.label}<small>{item.sub}</small></button>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="label">Shape</span>
                  <div className="segmented" role="group" aria-label="Aspect ratio">
                    {RATIO_OPTIONS.map((item) => (
                      <button key={item.value} type="button" aria-pressed={aspectRatio === item.value} title={item.title} onClick={() => { setAspectRatio(item.value); invalidateRenderedMedia(); }}>{item.value}</button>
                    ))}
                  </div>
                </div>
                <div>
                  {mode === "factory" ? (
                    <><label className="label" htmlFor="length">Video length</label>
                      <select id="length" className="field" value={factoryTargetSeconds} onChange={(e) => handleFactoryTargetChange(Number(e.target.value))}>{FACTORY_TARGETS.map((value) => <option key={value} value={value}>{value < 60 ? `${value} seconds` : `${value / 60} minute${value === 60 ? "" : "s"}`}</option>)}</select></>
                  ) : mode === "storyboard" ? (
                    <><label className="label" htmlFor="scenes">Scenes</label>
                      <select id="scenes" className="field" value={sceneCount} onChange={(e) => setSceneCount(Number(e.target.value))}>{[2, 3, 4, 6, 8, 10, 12, 16, 20].map((value) => <option key={value} value={value}>{value} scenes</option>)}</select></>
                  ) : (
                    <><label className="label" htmlFor="length">Clip length</label>
                      <select id="length" className="field" value={durationSeconds} onChange={(e) => setDurationSeconds(Number(e.target.value))}>{durationOptions.map((value) => <option key={value} value={value}>{value} seconds</option>)}</select></>
                  )}
                </div>
              </div>
            </div>

            <details className="acc">
              <summary><span>Camera &amp; look<small>Shot size, movement, lens, mood</small></span></summary>
              <div className="acc-body">
                <div className="settings-grid">
                  <div><label className="label" htmlFor="shot">Shot size</label><select id="shot" className="field" value={shotSize} onChange={(e) => setShotSize(e.target.value as ShotSize)}>{SHOT_SIZES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></div>
                  <div><label className="label" htmlFor="move">Camera move</label><select id="move" className="field" value={cameraMove} onChange={(e) => setCameraMove(e.target.value as CameraMove)}>{CAMERA_MOVES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></div>
                  <div><label className="label" htmlFor="lens">Lens</label><select id="lens" className="field" value={lensPreset} onChange={(e) => setLensPreset(e.target.value as LensPreset)}>{LENS_PRESETS.map((value) => <option key={value} value={value}>{value === "auto" ? "Auto" : value}</option>)}</select></div>
                  <div><label className="label" htmlFor="genre">Genre</label><select id="genre" className="field" value={genrePreset} onChange={(e) => setGenrePreset(e.target.value as GenrePreset)}>{GENRE_PRESETS.map((value) => <option key={value} value={value}>{value === "auto" ? "Auto" : value}</option>)}</select></div>
                  <div><label className="label" htmlFor="color">Colour</label><select id="color" className="field" value={colorPreset} onChange={(e) => setColorPreset(e.target.value as ColorPreset)}>{COLOR_PRESETS.map((value) => <option key={value} value={value}>{value === "auto" ? "Auto" : value.replaceAll("-", " ")}</option>)}</select></div>
                  <div><label className="label" htmlFor="tempo">Pace</label><select id="tempo" className="field" value={tempoPreset} onChange={(e) => setTempoPreset(e.target.value as TempoPreset)}>{TEMPO_PRESETS.map((value) => <option key={value} value={value}>{value === "auto" ? "Auto" : value}</option>)}</select></div>
                </div>
                <p className="help">&ldquo;Auto&rdquo; leaves your wording exactly as written.</p>
              </div>
            </details>

            <details className="acc">
              <summary><span>Voice &amp; sound<small>Audio mode and sound direction</small></span></summary>
              <div className="acc-body">
                <div><label className="label" htmlFor="audio">Audio</label><select id="audio" className="field" value={audioMode} onChange={(e) => setAudioMode(e.target.value as AudioMode)}><option value="mastered">Generated and loudness-mastered</option><option value="native">Generated, untouched</option><option value="mute">No audio</option></select></div>
                <div><label className="label" htmlFor="sound">Sound direction</label><textarea id="sound" className="field" rows={3} value={audioDirection} onChange={(e) => setAudioDirection(e.target.value)} placeholder="Ambience, dialogue, Foley, music…" /></div>
              </div>
            </details>

            <details className="acc">
              <summary><span>Consistency &amp; realism<small>Keep faces the same, skin detail, seed</small></span></summary>
              <div className="acc-body">
                {mode === "factory" && (
                  <div className="row-between">
                    <span><b style={{ fontSize: "0.875rem" }}>Presenter preset</b><span className="help" style={{ display: "block", margin: 0 }}>1080p, strict consistency and face lock for a talking presenter. Your length stays as chosen.</span></span>
                    <button type="button" onClick={applyCreatorGradePreset} className="btn btn-secondary btn-sm">Apply</button>
                  </div>
                )}
                <div><label className="label" htmlFor="continuity">Keep characters consistent</label><select id="continuity" className="field" value={continuityMode} onChange={(e) => setContinuityMode(e.target.value as ContinuityMode)}><option value="strict">Strict · match face and last frame</option><option value="balanced">Balanced · match face</option><option value="off">Off</option></select></div>
                <div><label className="label" htmlFor="realism">Skin and detail</label><select id="realism" className="field" value={realismProfile} onChange={(e) => setRealismProfile(e.target.value as RealismProfile)}><option value="standard">Standard · fastest</option><option value="real_skin">Real Skin · more detail, about 6× slower</option><option value="identity_max">Identity Max · locks the face, slowest</option></select>
                  <p className="help">{realismProfile === "standard" ? "Best for drafts and quick checks." : realismProfile === "identity_max" ? "Keeps the character reference active through every stage and checks frames for drift. Needs a Character in the shot." : "Adds a second detail pass for natural skin texture on final renders."}</p></div>
                {realismProfile === "identity_max" && referencedElements.filter((element) => element.type === "character").length > 1 && (
                  <div className="notice notice-warn"><span>More than one character is active. For a solo presenter keep exactly one; extra faces can blend.</span></div>
                )}
                <label className="check"><input type="checkbox" checked={enhancePrompt} onChange={(e) => setEnhancePrompt(e.target.checked)} /><span>AI Director<small>Lets AI rewrite and expand your prompt. Off keeps your exact words.</small></span></label>
                {mode === "factory" && (
                  <div><label className="label" htmlFor="shotlen">Shot length</label><select id="shotlen" className="field" value={factorySceneSeconds} onChange={(e) => handleFactorySceneDurationChange(Number(e.target.value))}>{factoryDurationOptions.map((value) => <option key={value} value={value}>{value} seconds per shot</option>)}</select><p className="help">Longer videos are built from several shots that continue from each other.</p></div>
                )}
                <div className="settings-grid">
                  <div><label className="label" htmlFor="seed">Seed</label><input id="seed" className="field" type="number" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value) || 0)} /></div>
                  <div><label className="label" htmlFor="decoder">Draft decoder</label><select id="decoder" className="field" disabled={quality !== "preview"} value={quality === "preview" ? decoder : "diffusion"} onChange={(e) => setDecoder(e.target.value as DecoderName)}><option value="conv">Fast</option><option value="diffusion">Detailed</option></select></div>
                </div>
              </div>
            </details>

            {mode === "factory" && youtube?.enabled && (
              <details className="acc">
                <summary><span>Publish to YouTube<small>{youtube.connected ? youtube.channel_title || "Connected channel" : "Connect a channel in your account menu first"}</small></span></summary>
                <div className="acc-body">
                  <label className="check"><input type="checkbox" disabled={!youtube.connected} checked={publishToYouTube} onChange={(e) => setPublishToYouTube(e.target.checked)} /><span>Upload when the video is ready<small>Videos that fail a quality check are never published automatically.</small></span></label>
                  {publishToYouTube && (
                    <>
                      <input className="field" value={youtubeTitle} onChange={(e) => setYoutubeTitle(e.target.value)} placeholder="YouTube title" aria-label="YouTube title" />
                      <select className="field" value={youtubePrivacy} onChange={(e) => setYoutubePrivacy(e.target.value as YouTubePrivacy)} aria-label="Visibility"><option value="private">Private</option><option value="unlisted" disabled={!youtube.public_uploads_allowed}>Unlisted</option><option value="public" disabled={!youtube.public_uploads_allowed}>Public</option></select>
                      <textarea className="field" rows={3} value={youtubeDescription} onChange={(e) => setYoutubeDescription(e.target.value)} placeholder="Description" aria-label="Description" />
                    </>
                  )}
                </div>
              </details>
            )}
          </div>

          <div className="panel-foot">
            {error && <div className="notice notice-error" role="alert"><span>{error}</span><button type="button" onClick={() => setError("")} aria-label="Dismiss">×</button></div>}
            {notice && <div className="notice notice-success" role="status"><span>{notice}</span><button type="button" onClick={() => setNotice("")} aria-label="Dismiss">×</button></div>}
            <div className="estimate" data-slow={renderEstimate.slow}>
              <span><b>{renderEstimate.label}</b></span>
              {renderEstimate.slow && (quality !== "preview" || realismProfile !== "standard") ? <button type="button" onClick={switchToDraft}>Switch to Draft</button> : null}
            </div>
            <button type="submit" disabled={isBusy} className="btn btn-primary btn-lg btn-block">{isBusy ? <span className="spinner" /> : <PlayIcon />}{isBusy ? "Working…" : generateLabel}</button>
          </div>
        </form>
      </div>

      {showElementsLibrary && (
        <div className="overlay overlay-right" role="dialog" aria-modal="true" aria-label="Characters and elements" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowElementsLibrary(false); }}>
          <aside className="drawer">
            {detailElement && elementDetailOpen ? (
              <>
                <div className="sheet-head">
                  <div className="row"><button type="button" className="icon-btn" onClick={() => setElementDetailOpen(false)} aria-label="Back to all elements">←</button><div><h2>@{detailElement.handle}</h2><p className={elementTone(detailElement.type)} style={{ textTransform: "capitalize" }}>{detailElement.type} · version {detailElement.current_version}</p></div></div>
                  <button type="button" className="icon-btn" onClick={() => setShowElementsLibrary(false)} aria-label="Close">×</button>
                </div>
                <div className="sheet-body stack">
                  <div className="detail-hero">
                    {detailAsset ? <img src={absoluteApiUrl(detailAsset.asset_url)} alt={detailElement.name} /> : <div className="ph" />}
                    <div className="stack" style={{ gap: "0.6rem" }}>
                      <strong style={{ fontSize: "1.0625rem" }}>{detailElement.name}</strong>
                      {detailElement.description ? <p className="help" style={{ margin: 0 }}>{detailElement.description}</p> : null}
                      {detailActive
                        ? <button type="button" className="btn btn-secondary btn-sm" onClick={() => removeElementFromScene(detailElement)}>Remove from this shot</button>
                        : <button type="button" className="btn btn-primary btn-sm" onClick={() => { insertElementMention(detailElement); setShowElementsLibrary(false); }}>Add to this shot</button>}
                    </div>
                  </div>

                  <div>
                    <label className="label" htmlFor="el-mode">How to use it</label>
                    <select id="el-mode" className="field" value={elementModes[detailElement.id] || "identity"} onChange={(e) => setElementModes((current) => ({ ...current, [detailElement.id]: e.target.value as ElementReferenceMode }))}>
                      <option value="identity">Keep this look (recommended)</option>
                      <option value="start_frame">Open the shot on this exact image</option>
                    </select>
                  </div>
                  {detailElement.type === "character" && (elementModes[detailElement.id] || "identity") === "identity" && (
                    <div>
                      <label className="label" htmlFor="el-ward">Clothing</label>
                      <select id="el-ward" className="field" value={elementWardrobePolicies[detailElement.id] || "prompt"} onChange={(e) => setElementWardrobePolicies((current) => ({ ...current, [detailElement.id]: e.target.value as ElementWardrobePolicy }))}>
                        <option value="prompt">Follow my prompt (recommended)</option>
                        <option value="reference">Keep the outfit in the photo</option>
                      </select>
                    </div>
                  )}
                  <div>
                    <label className="label" htmlFor="el-str">How strictly to match: {Math.min(1, elementStrengths[detailElement.id] ?? 1).toFixed(2)}</label>
                    <input id="el-str" type="range" min="0.55" max="1" step="0.05" value={Math.min(1, elementStrengths[detailElement.id] ?? 1)} onChange={(e) => setElementStrengths((current) => ({ ...current, [detailElement.id]: Number(e.target.value) }))} />
                    <p className="help">Lower it a little if the video looks stiff or frozen.</p>
                  </div>
                  <label className="check"><input type="checkbox" checked={Boolean(elementApplyAll[detailElement.id])} onChange={(e) => setElementApplyAll((current) => ({ ...current, [detailElement.id]: e.target.checked }))} /><span>Keep in every scene of a long video<small>It must still be @mentioned in the prompt.</small></span></label>

                  <div>
                    <div className="block-head" style={{ marginBottom: "0.5rem" }}><h3>Photos</h3><span>{detailElement.assets.length}/{capabilities?.elements?.max_assets_per_element ?? 8} · tap one to make it the main photo</span></div>
                    <div className="thumbs">
                      {detailElement.assets.map((reference) => (
                        <button key={reference.id} type="button" className="thumb" data-active={reference.id === detailElement.primary_asset_id} onClick={() => void handleSetPrimaryElementAsset(detailElement, reference.id)} title={`${elementRoleLabel(reference.role)} · set as main photo`}>
                          <img src={absoluteApiUrl(reference.asset_url)} alt="" /><span>{elementRoleLabel(reference.role)}</span>
                        </button>
                      ))}
                      <label className="thumb" title="Add photos">+<input type="file" multiple accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => void handleAddElementReferences(detailElement, e.target.files)} /></label>
                    </div>
                    {detailElement.type === "character" && <p className="help">Best results: a sharp, front-facing face photo first, then a profile and a full-body photo.</p>}
                  </div>

                  <div className="row-between" style={{ borderTop: "1px solid var(--line)", paddingTop: "0.9rem" }}>
                    <span className="help" style={{ margin: 0 }}>Archiving hides it from new shots. Past videos keep their version.</span>
                    <button type="button" className="btn btn-danger-ghost btn-sm" onClick={() => void handleArchiveElement(detailElement)}>Archive</button>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="sheet-head">
                  <div><h2>Characters &amp; elements</h2><p>Save a face, prop or place once, then use it anywhere with @name.</p></div>
                  <button type="button" className="icon-btn" onClick={() => setShowElementsLibrary(false)} aria-label="Close">×</button>
                </div>
                <div className="sheet-body">
                  <div className="row">
                    <input value={elementSearch} onChange={(e) => setElementSearch(e.target.value)} className="field grow" placeholder="Search by name or @handle" aria-label="Search elements" />
                    <button type="button" onClick={() => { setShowElementsLibrary(false); setShowElementCreator(true); }} className="btn btn-primary"><PlusIcon />New</button>
                  </div>
                  <div className="filter-row">
                    {(["all", "character", "prop", "location", "style"] as const).map((value) => (
                      <button key={value} type="button" aria-pressed={elementFilter === value} onClick={() => setElementFilter(value)}>{value === "all" ? "All" : `${value}s`}</button>
                    ))}
                  </div>
                  <div className="el-grid">
                    {elementsLoading && elements.length === 0 ? <div className="el-empty">Loading…</div> : null}
                    {!elementsLoading && filteredElements.length === 0 ? <div className="el-empty">{elements.length === 0 ? "No characters yet. Upload a clear face photo to create your first one." : "Nothing matches this filter."}</div> : null}
                    {filteredElements.map((element) => {
                      const asset = primaryElementAsset(element);
                      const active = hasElementMention(prompt, element.handle);
                      return (
                        <div key={element.id} className="el-card" data-active={active}>
                          <button type="button" className="el-thumb" style={{ width: "100%", border: 0, padding: 0 }} onClick={() => { setSelectedElementId(element.id); setElementDetailOpen(true); }} aria-label={`Open @${element.handle}`}>
                            {asset ? <img src={absoluteApiUrl(asset.asset_url)} alt={element.name} /> : element.name.slice(0, 1)}
                            <span className={`chip ${elementTone(element.type)}`}>{element.type}</span>
                            {active ? <span className="check-mark">✓</span> : null}
                          </button>
                          <div className="el-meta">
                            <b>{element.name}</b>
                            <small>@{element.handle}</small>
                            <button type="button" className={`btn btn-sm btn-block ${active ? "btn-secondary" : "btn-primary"}`} style={{ marginTop: "0.5rem" }} onClick={() => { if (active) { removeElementFromScene(element); } else { insertElementMention(element); setShowElementsLibrary(false); } }}>{active ? "Remove" : "Add to shot"}</button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            )}
          </aside>
        </div>
      )}

      {showElementCreator && (
        <div className="overlay overlay-center" role="dialog" aria-modal="true" aria-label="Create element">
          <div className="modal">
            <div className="sheet-head">
              <div><h2>New {elementType}</h2><p>Upload clear photos once. Then type @{elementHandle || "name"} in any prompt.</p></div>
              <button type="button" className="icon-btn" onClick={closeElementCreator} aria-label="Close">×</button>
            </div>
            <div className="sheet-body stack">
              <div className="type-picker" role="group" aria-label="Type">
                {(["character", "prop", "location", "style"] as ElementType[]).map((type) => (
                  <button key={type} type="button" aria-pressed={elementType === type} onClick={() => setElementType(type)}>{type}<small>{type === "character" ? "a person" : type === "prop" ? "an object" : type === "location" ? "a place" : "a look"}</small></button>
                ))}
              </div>
              <div className="settings-grid">
                <div><label className="label" htmlFor="el-name">Name</label><input id="el-name" className="field" value={elementName} onChange={(e) => { setElementName(e.target.value); if (!elementHandle) setElementHandle(e.target.value.replace(/[^A-Za-z0-9_-]/g, "")); }} placeholder="Maya" /></div>
                <div><label className="label" htmlFor="el-handle">Handle for prompts</label><input id="el-handle" className="field" value={elementHandle} onChange={(e) => setElementHandle(e.target.value.replace(/^@/, "").replace(/[^A-Za-z0-9_-]/g, ""))} placeholder="Maya" /></div>
              </div>
              <div><label className="label" htmlFor="el-desc">Describe the {elementType} (optional)</label><textarea id="el-desc" className="field" rows={3} value={elementDescription} onChange={(e) => setElementDescription(e.target.value)} placeholder={elementType === "character" ? "Age, hair, skin, distinctive features that must never change." : "Materials, colours, landmarks that must stay stable."} /></div>
              <label className="dropzone">
                <strong>{elementFiles.length ? "Replace photos" : "Choose photos"}</strong>
                <small>{elementType === "character" ? "Order matters: 1 face close-up, 2 full body, 3 profile, 4 outfit. PNG, JPEG or WEBP." : `PNG, JPEG or WEBP · up to ${capabilities?.elements?.max_assets_per_element ?? 8} photos`}</small>
                <input type="file" multiple accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => chooseCreatorFiles(Array.from(e.target.files || []))} />
              </label>
              {elementFiles.length > 0 && (
                <div className="previews">
                  {elementFiles.map((file, index) => (
                    <figure key={`${file.name}-${file.size}`}>
                      {elementFilePreviews[index] ? <img src={elementFilePreviews[index]} alt={file.name} /> : null}
                      <figcaption>{elementRoleLabel(suggestedElementRoles(elementType, elementFiles.length)[index])}</figcaption>
                    </figure>
                  ))}
                </div>
              )}
              {error && <div className="notice notice-error" role="alert"><span>{error}</span></div>}
            </div>
            <div className="sheet-foot">
              <button type="button" onClick={closeElementCreator} className="btn btn-secondary">Cancel</button>
              <button type="button" onClick={() => void handleCreateElement()} disabled={elementBusy} className="btn btn-primary">{elementBusy ? <span className="spinner" /> : null}{elementBusy ? "Saving…" : `Save @${elementHandle || "name"}`}</button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

