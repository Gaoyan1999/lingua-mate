import { ChangeEvent, KeyboardEvent, PointerEvent as ReactPointerEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Clock,
  EyeOff,
  Film,
  Gauge,
  Headphones,
  ListRestart,
  LocateFixed,
  PanelRightClose,
  PanelRightOpen,
  Play,
  Search,
  Settings,
  X,
} from "lucide-react";
import type { Lesson, LessonChunk, LessonIndex, LessonIndexEntry, MediaType } from "./types";

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];
const INDEX_URL = "/data/lessons.json";
const LEGACY_LESSON_URL = "/data/lesson.json";
const DEFAULT_LESSON_ID = "template";
const DEFAULT_SUBTITLE_MASK = { x: 8, y: 78, width: 84, height: 12 };
const MIN_MASK_HEIGHT = 5;
const MIN_MASK_WIDTH = 8;
const PLAYER_CONFIG_STORAGE_KEY = "lingua-mate:player-config:v1";
const PLAY_PROGRESS_STORAGE_KEY = "lingua-mate:play-progress:v1";
const PROGRESS_SAVE_SECONDS = 2;
const PROGRESS_SAVE_MS = 5000;
const MAX_STORED_PROGRESS_ITEMS = 100;

type SubtitleMask = typeof DEFAULT_SUBTITLE_MASK;
type PlayerConfig = {
  speed: number;
  seekStep: number;
  isSubtitleMaskEnabled: boolean;
  subtitleMask: SubtitleMask;
  maskShortcut: string;
  isStudyOpen: boolean;
};
type PlaybackProgress = {
  time: number;
  duration?: number;
  updatedAt: number;
};
type PlaybackProgressMap = Record<string, PlaybackProgress>;
type MaskDragMode = "move" | "nw" | "ne" | "sw" | "se";
type MaskDragState = {
  mode: MaskDragMode;
  startX: number;
  startY: number;
  startMask: SubtitleMask;
  frameWidth: number;
  frameHeight: number;
};

const DEFAULT_LESSON: Lesson = {
  media: {
    type: "audio",
    path: "",
    duration: 8,
    title: "Lingua Mate Library",
  },
  languages: {
    source: "English",
    target: "Chinese",
  },
  chunks: [
    {
      id: "chunk-0001",
      start: 0,
      end: 8,
      sourceText: "Generate or link a media JSON file to start studying.",
      translation: "生成或链接媒体 JSON 文件后即可开始学习。",
      readThrough: [
        {
          original: "Generate or link",
          explanation: "Generate or 的尾音会和 link 前面的辅音快速接上，听起来不像三个清晰分开的词。",
        },
      ],
      vocabulary: [
        {
          original: "link",
          explanation: "这里不是网页链接，而是把生成的 JSON 或媒体文件连接到模板能读取的位置。",
        },
      ],
    },
  ],
};

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.floor(seconds % 60);
  return `${minutes}:${remaining.toString().padStart(2, "0")}`;
}

function findActiveChunk(chunks: LessonChunk[], time: number): number {
  const index = chunks.findIndex((chunk) => time >= chunk.start && time < chunk.end);
  if (index >= 0) return index;
  for (let i = chunks.length - 1; i >= 0; i -= 1) {
    if (time >= chunks[i].start) return i;
  }
  return 0;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

const DEFAULT_PLAYER_CONFIG: PlayerConfig = {
  speed: 1,
  seekStep: 5,
  isSubtitleMaskEnabled: false,
  subtitleMask: DEFAULT_SUBTITLE_MASK,
  maskShortcut: "M",
  isStudyOpen: false,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readStorageValue(key: string): unknown {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeStorageValue(key: string, value: unknown) {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage may be disabled or full. The app should still work without persistence.
  }
}

function normalizeShortcut(value: unknown, fallback: string): string {
  if (typeof value !== "string") return fallback;
  return value.trim().slice(-1).toUpperCase();
}

function normalizeSubtitleMask(value: unknown): SubtitleMask {
  if (!isRecord(value)) return DEFAULT_SUBTITLE_MASK;

  const rawWidth = typeof value.width === "number" ? value.width : DEFAULT_SUBTITLE_MASK.width;
  const rawHeight = typeof value.height === "number" ? value.height : DEFAULT_SUBTITLE_MASK.height;
  const width = clamp(rawWidth, MIN_MASK_WIDTH, 100);
  const height = clamp(rawHeight, MIN_MASK_HEIGHT, 100);
  return {
    x: clamp(typeof value.x === "number" ? value.x : DEFAULT_SUBTITLE_MASK.x, 0, 100 - width),
    y: clamp(typeof value.y === "number" ? value.y : DEFAULT_SUBTITLE_MASK.y, 0, 100 - height),
    width,
    height,
  };
}

function readPlayerConfig(): PlayerConfig {
  const stored = readStorageValue(PLAYER_CONFIG_STORAGE_KEY);
  if (!isRecord(stored)) return DEFAULT_PLAYER_CONFIG;

  return {
    speed: typeof stored.speed === "number" && SPEEDS.includes(stored.speed) ? stored.speed : DEFAULT_PLAYER_CONFIG.speed,
    seekStep:
      typeof stored.seekStep === "number" && Number.isFinite(stored.seekStep)
        ? clamp(Math.round(stored.seekStep), 1, 60)
        : DEFAULT_PLAYER_CONFIG.seekStep,
    isSubtitleMaskEnabled:
      typeof stored.isSubtitleMaskEnabled === "boolean"
        ? stored.isSubtitleMaskEnabled
        : DEFAULT_PLAYER_CONFIG.isSubtitleMaskEnabled,
    subtitleMask: normalizeSubtitleMask(stored.subtitleMask),
    maskShortcut: normalizeShortcut(stored.maskShortcut, DEFAULT_PLAYER_CONFIG.maskShortcut),
    isStudyOpen: typeof stored.isStudyOpen === "boolean" ? stored.isStudyOpen : DEFAULT_PLAYER_CONFIG.isStudyOpen,
  };
}

function readPlaybackProgress(): PlaybackProgressMap {
  const stored = readStorageValue(PLAY_PROGRESS_STORAGE_KEY);
  if (!isRecord(stored)) return {};

  return Object.fromEntries(
    Object.entries(stored).flatMap(([id, value]) => {
      if (!id || !isRecord(value) || typeof value.time !== "number" || typeof value.updatedAt !== "number") return [];
      return [
        [
          id,
          {
            time: Math.max(0, value.time),
            duration: typeof value.duration === "number" && value.duration > 0 ? value.duration : undefined,
            updatedAt: value.updatedAt,
          },
        ],
      ];
    }),
  );
}

function writePlaybackProgress(lessonId: string, progress: PlaybackProgress): PlaybackProgressMap {
  const nextProgress = {
    ...readPlaybackProgress(),
    [lessonId]: progress,
  };
  const prunedProgress = Object.fromEntries(
    Object.entries(nextProgress)
      .sort(([, a], [, b]) => b.updatedAt - a.updatedAt)
      .slice(0, MAX_STORED_PROGRESS_ITEMS),
  );
  writeStorageValue(PLAY_PROGRESS_STORAGE_KEY, prunedProgress);
  return prunedProgress;
}

function readResumeTime(lessonId: string, duration: number): number {
  const progress = readPlaybackProgress()[lessonId];
  if (!progress || !Number.isFinite(progress.time)) return 0;
  if (duration > 0 && progress.time >= duration - 1) return 0;
  return clamp(progress.time, 0, Math.max(0, duration));
}

function isLesson(value: unknown): value is Lesson {
  if (!value || typeof value !== "object") return false;
  const lesson = value as Lesson;
  return (
    typeof lesson.media?.title === "string" &&
    typeof lesson.media?.path === "string" &&
    typeof lesson.languages?.source === "string" &&
    typeof lesson.languages?.target === "string" &&
    Array.isArray(lesson.chunks) &&
    lesson.chunks.length > 0
  );
}

function isMediaType(value: unknown): value is MediaType {
  return value === "video" || value === "audio";
}

function slugify(value: string, fallback: string): string {
  const slug = value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || fallback;
}

function lessonToIndexEntry(lesson: Lesson, lessonPath: string, fallbackId: string): LessonIndexEntry {
  return {
    id: slugify(lesson.media.title, fallbackId),
    title: lesson.media.title,
    lessonPath,
    mediaType: lesson.media.type,
    duration: lesson.media.duration,
    source: lesson.languages.source,
    target: lesson.languages.target,
  };
}

function normalizeLessonIndex(value: unknown): LessonIndexEntry[] {
  const rawLessons = Array.isArray(value)
    ? value
    : Array.isArray((value as LessonIndex | null)?.lessons)
      ? (value as LessonIndex).lessons
      : [];

  return rawLessons.flatMap((raw, index) => {
    if (!raw || typeof raw !== "object") return [];
    const item = raw as Partial<LessonIndexEntry> & { lesson?: unknown; path?: unknown };
    const lessonPath = item.lessonPath ?? item.lesson ?? item.path;
    const title = item.title;
    if (typeof lessonPath !== "string" || typeof title !== "string" || !lessonPath.trim() || !title.trim()) {
      return [];
    }

    const id = typeof item.id === "string" && item.id.trim() ? item.id.trim() : slugify(title, `library-${index + 1}`);
    return [
      {
        id,
        title: title.trim(),
        lessonPath: lessonPath.trim(),
        mediaType: isMediaType(item.mediaType) ? item.mediaType : undefined,
        duration: typeof item.duration === "number" && item.duration > 0 ? item.duration : undefined,
        source: typeof item.source === "string" ? item.source : undefined,
        target: typeof item.target === "string" ? item.target : undefined,
        description: typeof item.description === "string" ? item.description : undefined,
      },
    ];
  });
}

function currentLibraryParam(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get("library") ?? params.get("lesson");
}

export default function App() {
  const mediaRef = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const mediaFrameRef = useRef<HTMLDivElement | null>(null);
  const lyricsListRef = useRef<HTMLDivElement | null>(null);
  const chunkRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const maskDragRef = useRef<MaskDragState | null>(null);
  const lastProgressSaveRef = useRef({ lessonId: "", time: 0, savedAt: 0 });
  const [initialPlayerConfig] = useState<PlayerConfig>(() => readPlayerConfig());
  const [lesson, setLesson] = useState<Lesson>(DEFAULT_LESSON);
  const [catalog, setCatalog] = useState<LessonIndexEntry[]>([]);
  const [catalogStatus, setCatalogStatus] = useState<"loading" | "ready">("loading");
  const [lessonStatus, setLessonStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [lessonError, setLessonError] = useState("");
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(() => currentLibraryParam());
  const [libraryQuery, setLibraryQuery] = useState("");
  const [currentTime, setCurrentTime] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [speed, setSpeed] = useState(initialPlayerConfig.speed);
  const [seekStep, setSeekStep] = useState(initialPlayerConfig.seekStep);
  const [isSubtitleMaskEnabled, setIsSubtitleMaskEnabled] = useState(initialPlayerConfig.isSubtitleMaskEnabled);
  const [subtitleMask, setSubtitleMask] = useState<SubtitleMask>(initialPlayerConfig.subtitleMask);
  const [maskShortcut, setMaskShortcut] = useState(initialPlayerConfig.maskShortcut);
  const [query, setQuery] = useState("");
  const [isStudyOpen, setIsStudyOpen] = useState(initialPlayerConfig.isStudyOpen);
  const [playProgress, setPlayProgress] = useState<PlaybackProgressMap>(() => readPlaybackProgress());
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const activeIndex = findActiveChunk(lesson.chunks, currentTime);
  const focusIndex = selectedIndex >= 0 ? selectedIndex : activeIndex;
  const activeChunk = lesson.chunks[activeIndex] ?? lesson.chunks[0];
  const focusChunk = lesson.chunks[focusIndex] ?? activeChunk;
  const selectedLesson = useMemo(() => {
    if (!selectedLessonId) return null;
    return (
      catalog.find((item) => item.id === selectedLessonId) ??
      (selectedLessonId.startsWith("/") ? { id: selectedLessonId, title: selectedLessonId, lessonPath: selectedLessonId } : null)
    );
  }, [catalog, selectedLessonId]);

  const filteredLessons = useMemo(() => {
    const needle = libraryQuery.trim().toLowerCase();
    if (!needle) return catalog;
    return catalog.filter((item) =>
      `${item.title} ${item.source ?? ""} ${item.target ?? ""} ${item.description ?? ""}`.toLowerCase().includes(needle),
    );
  }, [catalog, libraryQuery]);

  const filteredChunks = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return lesson.chunks;
    return lesson.chunks.filter((chunk) => {
      const readThrough = chunk.readThrough.map((item) => `${item.original} ${item.explanation}`).join(" ");
      const vocab = chunk.vocabulary.map((item) => `${item.original} ${item.explanation}`).join(" ");
      return `${chunk.sourceText} ${chunk.translation} ${readThrough} ${vocab}`.toLowerCase().includes(needle);
    });
  }, [lesson.chunks, query]);

  useEffect(() => {
    let cancelled = false;

    async function loadCatalog() {
      try {
        const response = await fetch(INDEX_URL, { cache: "no-store" });
        if (response.ok) {
          const nextIndex: unknown = await response.json();
          const nextCatalog = normalizeLessonIndex(nextIndex);
          if (!cancelled && nextCatalog.length > 0) {
            setCatalog(nextCatalog);
            setCatalogStatus("ready");
            return;
          }
        }
      } catch {
        // Clean checkouts do not include generated Library indexes.
      }

      try {
        const response = await fetch(LEGACY_LESSON_URL, { cache: "no-store" });
        if (response.ok) {
          const nextLesson: unknown = await response.json();
          if (!cancelled && isLesson(nextLesson)) {
            setCatalog([lessonToIndexEntry(nextLesson, LEGACY_LESSON_URL, DEFAULT_LESSON_ID)]);
            setCatalogStatus("ready");
            return;
          }
        }
      } catch {
        // Clean checkouts do not include generated Library material.
      }

      if (!cancelled) {
        setCatalog([{ ...lessonToIndexEntry(DEFAULT_LESSON, "", DEFAULT_LESSON_ID), id: DEFAULT_LESSON_ID }]);
        setCatalogStatus("ready");
      }
    }

    void loadCatalog();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    writeStorageValue(PLAYER_CONFIG_STORAGE_KEY, {
      speed,
      seekStep,
      isSubtitleMaskEnabled,
      subtitleMask,
      maskShortcut,
      isStudyOpen,
    });
  }, [speed, seekStep, isSubtitleMaskEnabled, subtitleMask, maskShortcut, isStudyOpen]);

  useEffect(() => {
    function onPopState() {
      setSelectedLessonId(currentLibraryParam());
    }

    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (!selectedLessonId) {
      setLessonStatus("idle");
      setLessonError("");
      mediaRef.current?.pause();
      return;
    }
    if (catalogStatus !== "ready") return;

    const activeLessonId = selectedLessonId;
    let cancelled = false;

    async function loadLesson() {
      setLessonStatus("loading");
      setLessonError("");
      setQuery("");

      if (!selectedLesson || !selectedLesson.lessonPath) {
        if (activeLessonId === DEFAULT_LESSON_ID) {
          const nextTime = readResumeTime(activeLessonId, DEFAULT_LESSON.media.duration);
          const nextIndex = findActiveChunk(DEFAULT_LESSON.chunks, nextTime);
          setLesson(DEFAULT_LESSON);
          setCurrentTime(nextTime);
          setSelectedIndex(nextIndex);
          setLessonStatus("ready");
          return;
        }
        setLessonError("Media not found.");
        setLessonStatus("error");
        return;
      }

      try {
        const response = await fetch(selectedLesson.lessonPath, { cache: "no-store" });
        if (!response.ok) throw new Error(`Media request failed: ${response.status}`);
        const nextLesson: unknown = await response.json();
        if (!isLesson(nextLesson)) throw new Error("Invalid media JSON.");
        if (!cancelled) {
          const nextTime = readResumeTime(activeLessonId, nextLesson.media.duration);
          const nextIndex = findActiveChunk(nextLesson.chunks, nextTime);
          setLesson(nextLesson);
          setCurrentTime(nextTime);
          setSelectedIndex(nextIndex);
          setLessonStatus("ready");
        }
      } catch (error) {
        if (!cancelled) {
          setLessonError(error instanceof Error ? error.message : "Could not load media.");
          setLessonStatus("error");
        }
      }
    }

    void loadLesson();
    return () => {
      cancelled = true;
    };
  }, [catalogStatus, selectedLesson, selectedLessonId]);

  useEffect(() => {
    if (query.trim()) return;
    scrollChunkIntoTranscript(activeIndex, "smooth");
  }, [activeIndex, query]);

  useEffect(() => {
    const media = mediaRef.current;
    if (!media || lessonStatus !== "ready") return;
    media.playbackRate = speed;
  }, [lesson.media.path, lessonStatus, speed]);

  useEffect(() => {
    const media = mediaRef.current;
    if (!media || lessonStatus !== "ready") return;
    const nextTime = clamp(currentTime, 0, media.duration || lesson.media.duration);
    if (Number.isFinite(nextTime) && Math.abs(media.currentTime - nextTime) > 0.5) {
      media.currentTime = nextTime;
    }
  }, [lesson.media.duration, lesson.media.path, lessonStatus]);


  useEffect(() => {
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.repeat) return;

      if (isSettingsOpen) {
        if (event.code === "Escape") {
          event.preventDefault();
          setIsSettingsOpen(false);
        }
        return;
      }

      const target = event.target as HTMLElement | null;
      const shouldIgnore =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.tagName === "SELECT" ||
        target?.tagName === "BUTTON" ||
        target?.isContentEditable;

      if (shouldIgnore) return;

      const isPlainKey = !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey;
      if (
        isPlainKey &&
        lesson.media.type === "video" &&
        maskShortcut &&
        event.key.toLowerCase() === maskShortcut.toLowerCase()
      ) {
        event.preventDefault();
        setIsSubtitleMaskEnabled((value) => !value);
        return;
      }

      const media = mediaRef.current;
      if (!media) return;

      if (event.code === "Space") {
        event.preventDefault();
        setCurrentTime(media.currentTime);

        if (media.paused) {
          void media.play();
        } else {
          media.pause();
        }
        return;
      }

      if (event.code !== "ArrowLeft" && event.code !== "ArrowRight") return;

      event.preventDefault();

      if (event.metaKey) {
        const direction = event.code === "ArrowRight" ? 1 : -1;
        const nextIndex = Math.min(Math.max(activeIndex + direction, 0), lesson.chunks.length - 1);
        seekTo(lesson.chunks[nextIndex], !media.paused);
        return;
      }

      const delta = event.code === "ArrowRight" ? seekStep : -seekStep;
      const nextTime = Math.min(Math.max(media.currentTime + delta, 0), media.duration || lesson.media.duration);
      media.currentTime = nextTime;
      setCurrentTime(nextTime);
    }

    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [activeIndex, isSettingsOpen, lesson.chunks, lesson.media.duration, lesson.media.type, maskShortcut, seekStep]);

  function seekTo(chunk: LessonChunk, shouldPlay = true) {
    const media = mediaRef.current;
    if (!media) return;
    media.currentTime = chunk.start;
    setCurrentTime(chunk.start);
    const nextIndex = lesson.chunks.findIndex((item) => item.id === chunk.id);
    setSelectedIndex(nextIndex >= 0 ? nextIndex : activeIndex);
    if (shouldPlay) {
      void media.play();
    }
  }

  function scrollChunkIntoTranscript(index: number, behavior: ScrollBehavior = "smooth") {
    const chunk = lesson.chunks[index];
    if (!chunk) return;
    const container = lyricsListRef.current;
    const row = chunkRefs.current[chunk.id];
    if (!container || !row) return;

    const containerRect = container.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    const nextTop =
      container.scrollTop +
      rowRect.top -
      containerRect.top -
      Math.max(0, (container.clientHeight - row.clientHeight) / 2);

    container.scrollTo({ top: Math.max(0, nextTop), behavior });
  }

  function scrollToActiveChunk() {
    if (query.trim()) {
      setQuery("");
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => scrollChunkIntoTranscript(activeIndex)));
      return;
    }

    scrollChunkIntoTranscript(activeIndex);
  }

  function openLesson(entry: LessonIndexEntry) {
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set("library", entry.id);
    nextUrl.searchParams.delete("lesson");
    window.history.pushState({}, "", nextUrl);
    setSelectedLessonId(entry.id);
  }

  function returnToLibrary() {
    mediaRef.current?.pause();
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.delete("library");
    nextUrl.searchParams.delete("lesson");
    window.history.pushState({}, "", nextUrl);
    setSelectedLessonId(null);
  }

  function changeSpeed(event: ChangeEvent<HTMLSelectElement>) {
    const nextSpeed = Number(event.target.value);
    setSpeed(nextSpeed);
    if (mediaRef.current) {
      mediaRef.current.playbackRate = nextSpeed;
    }
  }

  function changeSeekStep(event: ChangeEvent<HTMLInputElement>) {
    const value = Number(event.target.value);
    if (!Number.isFinite(value)) return;
    setSeekStep(Math.min(Math.max(Math.round(value), 1), 60));
  }

  function changeMaskShortcut(event: ChangeEvent<HTMLInputElement>) {
    const value = event.target.value.trim().slice(-1).toUpperCase();
    setMaskShortcut(value);
  }

  function startMaskDrag(event: ReactPointerEvent<HTMLDivElement>, mode: MaskDragMode) {
    const frame = mediaFrameRef.current;
    if (!frame || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const frameRect = frame.getBoundingClientRect();
    maskDragRef.current = {
      mode,
      startX: event.clientX,
      startY: event.clientY,
      startMask: subtitleMask,
      frameWidth: frameRect.width,
      frameHeight: frameRect.height,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function dragMask(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = maskDragRef.current;
    if (!drag) return;
    event.preventDefault();
    event.stopPropagation();

    const dx = ((event.clientX - drag.startX) / drag.frameWidth) * 100;
    const dy = ((event.clientY - drag.startY) / drag.frameHeight) * 100;
    const start = drag.startMask;

    if (drag.mode === "move") {
      setSubtitleMask({
        ...start,
        x: clamp(start.x + dx, 0, 100 - start.width),
        y: clamp(start.y + dy, 0, 100 - start.height),
      });
      return;
    }

    const right = start.x + start.width;
    const bottom = start.y + start.height;
    const next = { ...start };

    if (drag.mode.includes("w")) {
      next.x = clamp(start.x + dx, 0, right - MIN_MASK_WIDTH);
      next.width = right - next.x;
    }

    if (drag.mode.includes("e")) {
      next.width = clamp(start.width + dx, MIN_MASK_WIDTH, 100 - start.x);
    }

    if (drag.mode.includes("n")) {
      next.y = clamp(start.y + dy, 0, bottom - MIN_MASK_HEIGHT);
      next.height = bottom - next.y;
    }

    if (drag.mode.includes("s")) {
      next.height = clamp(start.height + dy, MIN_MASK_HEIGHT, 100 - start.y);
    }

    setSubtitleMask(next);
  }

  function stopMaskDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (!maskDragRef.current) return;
    event.preventDefault();
    event.stopPropagation();
    maskDragRef.current = null;
  }

  function saveCurrentPlaybackProgress(force = false) {
    const media = mediaRef.current;
    if (!media || !selectedLessonId) return;

    const duration =
      Number.isFinite(media.duration) && media.duration > 0
        ? media.duration
        : lesson.media.duration > 0
          ? lesson.media.duration
          : undefined;
    const current = duration ? clamp(media.currentTime, 0, duration) : Math.max(0, media.currentTime);
    const now = Date.now();
    const last = lastProgressSaveRef.current;
    if (
      !force &&
      last.lessonId === selectedLessonId &&
      Math.abs(current - last.time) < PROGRESS_SAVE_SECONDS &&
      now - last.savedAt < PROGRESS_SAVE_MS
    ) {
      return;
    }

    lastProgressSaveRef.current = { lessonId: selectedLessonId, time: current, savedAt: now };
    setPlayProgress(
      writePlaybackProgress(selectedLessonId, {
        time: current,
        duration,
        updatedAt: now,
      }),
    );
  }

  function getDisplayProgress(entry: LessonIndexEntry): PlaybackProgress | null {
    const progress = playProgress[entry.id];
    if (!progress || progress.time < 1) return null;
    const duration = entry.duration ?? progress.duration;
    if (duration && progress.time >= duration - 1) return null;
    return progress;
  }

  function onTimeUpdate() {
    const media = mediaRef.current;
    if (!media) return;
    setCurrentTime(media.currentTime);
    saveCurrentPlaybackProgress();
    const nextActive = findActiveChunk(lesson.chunks, media.currentTime);
    if (nextActive !== selectedIndex) {
      setSelectedIndex(nextActive);
    }
  }

  function focusTranscriptRow(index: number) {
    const chunk = lesson.chunks[index];
    if (!chunk) return;
    setSelectedIndex(index);
    window.requestAnimationFrame(() => {
      chunkRefs.current[chunk.id]?.focus();
      scrollChunkIntoTranscript(index);
    });
  }

  function onLyricsKeyDown(event: KeyboardEvent<HTMLDivElement>, chunk: LessonChunk) {
    if (event.key === "Enter") {
      seekTo(chunk);
      return;
    }

    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      const index = lesson.chunks.findIndex((item) => item.id === chunk.id);
      if (index < 0) return;
      const direction = event.key === "ArrowDown" ? 1 : -1;
      const nextIndex = Math.min(Math.max(index + direction, 0), lesson.chunks.length - 1);
      focusTranscriptRow(nextIndex);
    }
  }

  if (!selectedLessonId) {
    return (
      <main className="app-shell library-shell">
        <section className="library-stage" aria-label="Library">
          <div className="library-header">
            <div>
              <p className="eyebrow">Lingua Mate</p>
              <h1>Library</h1>
            </div>
            <label className="search-box">
              <Search size={18} />
              <input
                value={libraryQuery}
                onChange={(event) => setLibraryQuery(event.target.value)}
                placeholder="Search media"
              />
            </label>
          </div>

          <div className="lesson-grid" aria-live="polite">
            {catalogStatus === "loading" ? <p className="empty-note">Loading media...</p> : null}
            {catalogStatus === "ready" && filteredLessons.length === 0 ? (
              <p className="empty-note">No media match the search.</p>
            ) : null}
            {filteredLessons.map((item) => {
              const progress = getDisplayProgress(item);
              return (
                <button type="button" className="lesson-card" key={item.id} onClick={() => openLesson(item)}>
                  <span className="lesson-media-icon" aria-hidden="true">
                    {item.mediaType === "audio" ? <Headphones size={22} /> : <Film size={22} />}
                  </span>
                  <span className="lesson-card-body">
                    <span className="lesson-title">{item.title}</span>
                    <span className="lesson-meta">
                      {item.source && item.target ? `${item.source} to ${item.target}` : "Study media"}
                      {typeof item.duration === "number" ? (
                        <>
                          <span aria-hidden="true">/</span>
                          <Clock size={15} />
                          {formatTime(item.duration)}
                        </>
                      ) : null}
                      {progress ? (
                        <>
                          <span aria-hidden="true">/</span>
                          <Play size={15} />
                          Resume {formatTime(progress.time)}
                        </>
                      ) : null}
                    </span>
                    {item.description ? <span className="lesson-description">{item.description}</span> : null}
                  </span>
                  <Play size={18} className="lesson-open-icon" aria-hidden="true" />
                </button>
              );
            })}
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <section className={`lesson-stage${isStudyOpen ? "" : " study-collapsed"}`} aria-label="Media player">
        <div className="media-column">
          <div className="title-row">
            <div>
              <p className="eyebrow">{lesson.languages.source} to {lesson.languages.target}</p>
              <h1>{lesson.media.title}</h1>
            </div>
            <div className="title-actions">
              <button type="button" className="panel-toggle" onClick={returnToLibrary}>
                <ArrowLeft size={18} />
                <span>Library</span>
              </button>
              <button
                type="button"
                className={`icon-button${isSubtitleMaskEnabled ? " active" : ""}`}
                onClick={() => setIsSubtitleMaskEnabled((value) => !value)}
                disabled={lesson.media.type !== "video"}
                title="Toggle subtitle mask"
                aria-label="Toggle subtitle mask"
                aria-pressed={isSubtitleMaskEnabled}
              >
                <EyeOff size={18} />
              </button>
              <button
                type="button"
                className="icon-button"
                onClick={() => setIsSettingsOpen(true)}
                title="Settings"
                aria-label="Settings"
              >
                <Settings size={18} />
              </button>
              <label className="speed-control">
                <Gauge size={18} />
                <select value={speed} onChange={changeSpeed} aria-label="Playback speed">
                  {SPEEDS.map((item) => (
                    <option key={item} value={item}>{item}x</option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="panel-toggle"
                onClick={() => setIsStudyOpen((value) => !value)}
                aria-expanded={isStudyOpen}
                aria-controls="study-notes"
                title={isStudyOpen ? "Hide study notes" : "Show study notes"}
              >
                {isStudyOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
                <span>{isStudyOpen ? "Hide notes" : "Study notes"}</span>
              </button>
            </div>
          </div>

          <div className="media-frame" ref={mediaFrameRef}>
            {lessonStatus === "loading" ? (
              <p className="media-message">Loading media...</p>
            ) : lessonStatus === "error" ? (
              <p className="media-message">{lessonError}</p>
            ) : lesson.media.type === "audio" ? (
              <audio
                key={lesson.media.path}
                ref={mediaRef}
                controls
                src={lesson.media.path}
                onTimeUpdate={onTimeUpdate}
                onPause={() => saveCurrentPlaybackProgress(true)}
                onEnded={() => saveCurrentPlaybackProgress(true)}
              />
            ) : (
              <video
                key={lesson.media.path}
                ref={mediaRef}
                controls
                src={lesson.media.path}
                onTimeUpdate={onTimeUpdate}
                onPause={() => saveCurrentPlaybackProgress(true)}
                onEnded={() => saveCurrentPlaybackProgress(true)}
                playsInline
              />
            )}
            {lesson.media.type === "video" && isSubtitleMaskEnabled ? (
              <div
                className="subtitle-mask"
                style={{
                  left: `${subtitleMask.x}%`,
                  top: `${subtitleMask.y}%`,
                  width: `${subtitleMask.width}%`,
                  height: `${subtitleMask.height}%`,
                }}
                aria-hidden="true"
                onPointerDown={(event) => startMaskDrag(event, "move")}
                onPointerMove={dragMask}
                onPointerUp={stopMaskDrag}
                onPointerCancel={stopMaskDrag}
              >
                <div className="mask-handle nw" onPointerDown={(event) => startMaskDrag(event, "nw")} />
                <div className="mask-handle ne" onPointerDown={(event) => startMaskDrag(event, "ne")} />
                <div className="mask-handle sw" onPointerDown={(event) => startMaskDrag(event, "sw")} />
                <div className="mask-handle se" onPointerDown={(event) => startMaskDrag(event, "se")} />
              </div>
            ) : null}
          </div>

          <div className="lyrics-panel" aria-label="Transcript subtitles">
            <div className="lyrics-toolbar">
              <div>
                <p className="eyebrow">Transcript</p>
                <h2>Live subtitles</h2>
              </div>
              <div className="lyrics-actions">
                <button
                  type="button"
                  className="icon-button"
                  onClick={scrollToActiveChunk}
                  title="Go to current subtitle"
                  aria-label="Go to current subtitle"
                >
                  <LocateFixed size={18} />
                </button>
                <label className="search-box compact">
                  <Search size={18} />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search transcript, translation, notes"
                  />
                </label>
              </div>
            </div>

            <div className="lyrics-list" ref={lyricsListRef} aria-live="polite">
              {filteredChunks.map((chunk) => {
                const index = lesson.chunks.findIndex((item) => item.id === chunk.id);
                const isActive = index === activeIndex;
                const isSelected = index === focusIndex;
                return (
                  <div
                    key={chunk.id}
                    ref={(node) => {
                      chunkRefs.current[chunk.id] = node;
                    }}
                    role="button"
                    tabIndex={0}
                    className={`lyric-row${isActive ? " playing" : ""}${isSelected ? " selected" : ""}`}
                    onClick={() => seekTo(chunk)}
                    onKeyDown={(event) => onLyricsKeyDown(event, chunk)}
                  >
                    <span className="chunk-time">{formatTime(chunk.start)}-{formatTime(chunk.end)}</span>
                    <span className="lyric-text">
                      <strong>{chunk.sourceText}</strong>
                      <span>{chunk.translation || "待翻译"}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

        </div>

        {isStudyOpen ? (
          <aside className="study-column" id="study-notes" aria-label="Study notes">
            <div className="study-header">
              <div>
                <p className="eyebrow">Study</p>
                <h2>Notes</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => setIsStudyOpen(false)}
                title="Collapse study notes"
                aria-label="Collapse study notes"
              >
                <PanelRightClose size={18} />
              </button>
            </div>

            <div className="readthrough">
              <div className="section-heading">
                <Play size={18} />
                <h2>Connected speech</h2>
              </div>
              <div className="note-list">
                {focusChunk.readThrough.length > 0 ? (
                  focusChunk.readThrough.map((item) => (
                    <article className="note-card" key={`${item.original}-${item.explanation}`}>
                      <h3>{item.original}</h3>
                      <p>{item.explanation}</p>
                    </article>
                  ))
                ) : (
                  <span className="empty-note">No listening notes for this chunk.</span>
                )}
              </div>
            </div>

            <div className="vocabulary">
              <div className="section-heading">
                <ListRestart size={18} />
                <h2>Vocabulary notes</h2>
              </div>
              <div className="note-list">
                {focusChunk.vocabulary.length > 0 ? (
                  focusChunk.vocabulary.map((item) => (
                    <article className="note-card" key={`${item.original}-${item.explanation}`}>
                      <h3>{item.original}</h3>
                      <p>{item.explanation}</p>
                    </article>
                  ))
                ) : (
                  <span className="empty-note">No vocabulary notes for this chunk.</span>
                )}
              </div>
            </div>
          </aside>
        ) : null}
      </section>

      {isSettingsOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setIsSettingsOpen(false)}>
          <section
            className="settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="settings-header">
              <div>
                <p className="eyebrow">Player</p>
                <h2 id="settings-title">Settings</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => setIsSettingsOpen(false)}
                title="Close settings"
                aria-label="Close settings"
              >
                <X size={18} />
              </button>
            </div>

            <label className="setting-field">
              <span>Back / forward seconds</span>
              <input min={1} max={60} type="number" value={seekStep} onChange={changeSeekStep} />
            </label>
            <label className="setting-field">
              <span>Subtitle mask shortcut</span>
              <input
                maxLength={1}
                value={maskShortcut}
                onChange={changeMaskShortcut}
                placeholder="M"
                aria-label="Subtitle mask shortcut"
              />
            </label>

            <div className="shortcut-list" aria-label="Keyboard shortcuts">
              <div>
                <kbd>{maskShortcut || "Unset"}</kbd>
                <span>Show or hide subtitle mask</span>
              </div>
              <div>
                <kbd>Space</kbd>
                <span>Play or pause</span>
              </div>
              <div>
                <kbd>Left / Right</kbd>
                <span>Back or forward {seekStep} seconds</span>
              </div>
              <div>
                <kbd>Cmd + Left / Right</kbd>
                <span>Previous or next sentence</span>
              </div>
              <div>
                <kbd>Enter</kbd>
                <span>Play selected transcript row</span>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
