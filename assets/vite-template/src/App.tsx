import { ChangeEvent, KeyboardEvent, PointerEvent as ReactPointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { EyeOff, Gauge, ListRestart, LocateFixed, PanelRightClose, PanelRightOpen, Play, Search, Settings, X } from "lucide-react";
import type { Lesson, LessonChunk, VocabularyItem } from "./types";

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];
const LESSON_URL = "/data/lesson.json";
const DEFAULT_SUBTITLE_MASK = { x: 8, y: 78, width: 84, height: 12 };
const MIN_MASK_HEIGHT = 5;
const MIN_MASK_WIDTH = 8;

type SubtitleMask = typeof DEFAULT_SUBTITLE_MASK;
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
    title: "Lingua Mate lesson",
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
      sourceText: "Generate or link a lesson JSON file to start studying.",
      translation: "生成或链接 lesson JSON 文件后即可开始学习。",
      readThrough: "This placeholder keeps the reusable template buildable before local generated lesson material is linked.",
      vocabulary: [
        {
          term: "link",
          meaning: "连接；在这里指把生成的 lesson.json 放到模板可读取的位置",
          nuance: "In developer tooling, link often means symlink or connect one file path to another.",
          example: "Link the generated lesson file before running the learner page.",
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

export default function App() {
  const mediaRef = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const mediaFrameRef = useRef<HTMLDivElement | null>(null);
  const lyricsListRef = useRef<HTMLDivElement | null>(null);
  const chunkRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const maskDragRef = useRef<MaskDragState | null>(null);
  const [lesson, setLesson] = useState<Lesson>(DEFAULT_LESSON);
  const [currentTime, setCurrentTime] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [seekStep, setSeekStep] = useState(5);
  const [isSubtitleMaskEnabled, setIsSubtitleMaskEnabled] = useState(false);
  const [subtitleMask, setSubtitleMask] = useState<SubtitleMask>(DEFAULT_SUBTITLE_MASK);
  const [maskShortcut, setMaskShortcut] = useState("M");
  const [query, setQuery] = useState("");
  const [isStudyOpen, setIsStudyOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [selectedTerm, setSelectedTerm] = useState<VocabularyItem | null>(
    DEFAULT_LESSON.chunks[0]?.vocabulary[0] ?? null,
  );

  const activeIndex = findActiveChunk(lesson.chunks, currentTime);
  const focusIndex = selectedIndex >= 0 ? selectedIndex : activeIndex;
  const activeChunk = lesson.chunks[activeIndex] ?? lesson.chunks[0];
  const focusChunk = lesson.chunks[focusIndex] ?? activeChunk;
  const focusReadThrough = focusChunk.readThrough || "待生成中文讲解";

  const filteredChunks = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return lesson.chunks;
    return lesson.chunks.filter((chunk) => {
      const vocab = chunk.vocabulary.map((item) => `${item.term} ${item.meaning}`).join(" ");
      return `${chunk.sourceText} ${chunk.translation} ${chunk.readThrough} ${vocab}`.toLowerCase().includes(needle);
    });
  }, [lesson.chunks, query]);

  useEffect(() => {
    let cancelled = false;

    async function loadLesson() {
      try {
        const response = await fetch(LESSON_URL, { cache: "no-store" });
        if (!response.ok) return;
        const nextLesson: unknown = await response.json();
        if (!cancelled && isLesson(nextLesson)) {
          setLesson(nextLesson);
          setCurrentTime(0);
          setSelectedIndex(0);
          setSelectedTerm(nextLesson.chunks[0]?.vocabulary[0] ?? null);
        }
      } catch {
        // Clean checkouts do not include generated lesson material.
      }
    }

    void loadLesson();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (query.trim()) return;
    scrollChunkIntoTranscript(activeIndex, "smooth");
  }, [activeIndex, query]);

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
    setSelectedTerm(chunk.vocabulary[0] ?? null);
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

  function onTimeUpdate() {
    const media = mediaRef.current;
    if (!media) return;
    setCurrentTime(media.currentTime);
    const nextActive = findActiveChunk(lesson.chunks, media.currentTime);
    if (nextActive !== selectedIndex) {
      setSelectedIndex(nextActive);
      setSelectedTerm(lesson.chunks[nextActive]?.vocabulary[0] ?? null);
    }
  }

  function focusTranscriptRow(index: number) {
    const chunk = lesson.chunks[index];
    if (!chunk) return;
    setSelectedIndex(index);
    setSelectedTerm(chunk.vocabulary[0] ?? null);
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

  return (
    <main className="app-shell">
      <section className={`lesson-stage${isStudyOpen ? "" : " study-collapsed"}`} aria-label="Lesson player">
        <div className="media-column">
          <div className="title-row">
            <div>
              <p className="eyebrow">{lesson.languages.source} to {lesson.languages.target}</p>
              <h1>{lesson.media.title}</h1>
            </div>
            <div className="title-actions">
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
              <div className="time-badge">{formatTime(currentTime)} / {formatTime(lesson.media.duration)}</div>
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
            {lesson.media.type === "audio" ? (
              <audio ref={mediaRef} controls src={lesson.media.path} onTimeUpdate={onTimeUpdate} />
            ) : (
              <video ref={mediaRef} controls src={lesson.media.path} onTimeUpdate={onTimeUpdate} playsInline />
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
                <h2>Read-through</h2>
              </div>
              <p>{focusReadThrough}</p>
            </div>

            <div className="vocabulary">
              <div className="section-heading">
                <ListRestart size={18} />
                <h2>Advanced words</h2>
              </div>
              <div className="term-list">
                {focusChunk.vocabulary.length > 0 ? (
                  focusChunk.vocabulary.map((item) => (
                    <button
                      type="button"
                      className={selectedTerm?.term === item.term ? "term active" : "term"}
                      key={item.term}
                      onClick={() => setSelectedTerm(item)}
                    >
                      {item.term}
                    </button>
                  ))
                ) : (
                  <span className="empty-note">No vocabulary notes for this chunk.</span>
                )}
              </div>
              {selectedTerm ? (
                <div className="term-detail">
                  <h3>{selectedTerm.term}</h3>
                  <p><strong>Meaning:</strong> {selectedTerm.meaning}</p>
                  <p><strong>Nuance:</strong> {selectedTerm.nuance}</p>
                  <p><strong>Example:</strong> {selectedTerm.example}</p>
                </div>
              ) : null}
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
