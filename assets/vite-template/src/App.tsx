import { ChangeEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { Gauge, ListRestart, PanelRightClose, PanelRightOpen, Play, RotateCcw, Search } from "lucide-react";
import type { Lesson, LessonChunk, VocabularyItem } from "./types";

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];
const LESSON_URL = "/data/lesson.json";

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
  const chunkRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [lesson, setLesson] = useState<Lesson>(DEFAULT_LESSON);
  const [currentTime, setCurrentTime] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [query, setQuery] = useState("");
  const [isStudyOpen, setIsStudyOpen] = useState(false);
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
    const activeId = lesson.chunks[activeIndex]?.id;
    if (!activeId || query.trim()) return;
    chunkRefs.current[activeId]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeIndex, lesson.chunks, query]);

  useEffect(() => {
    function onKeyDown(event: globalThis.KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const isTyping =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.tagName === "SELECT" ||
        target?.isContentEditable;

      if (event.code !== "Space" || isTyping) return;

      const media = mediaRef.current;
      if (!media) return;
      event.preventDefault();
      media.pause();
      setCurrentTime(media.currentTime);
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function seekTo(chunk: LessonChunk) {
    const media = mediaRef.current;
    if (!media) return;
    media.currentTime = chunk.start;
    setCurrentTime(chunk.start);
    const nextIndex = lesson.chunks.findIndex((item) => item.id === chunk.id);
    setSelectedIndex(nextIndex >= 0 ? nextIndex : activeIndex);
    setSelectedTerm(chunk.vocabulary[0] ?? null);
    void media.play();
  }

  function replayFocusChunk() {
    seekTo(focusChunk);
  }

  function changeSpeed(event: ChangeEvent<HTMLSelectElement>) {
    const nextSpeed = Number(event.target.value);
    setSpeed(nextSpeed);
    if (mediaRef.current) {
      mediaRef.current.playbackRate = nextSpeed;
    }
  }

  function onTimeUpdate() {
    const media = mediaRef.current;
    if (!media) return;
    setCurrentTime(media.currentTime);
    const nextActive = findActiveChunk(lesson.chunks, media.currentTime);
    if (nextActive !== activeIndex) {
      setSelectedIndex(nextActive);
      setSelectedTerm(lesson.chunks[nextActive]?.vocabulary[0] ?? null);
    }
  }

  function onLyricsKeyDown(event: KeyboardEvent<HTMLButtonElement>, chunk: LessonChunk) {
    if (event.key === "Enter") {
      seekTo(chunk);
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

          <div className="media-frame">
            {lesson.media.type === "audio" ? (
              <audio ref={mediaRef} controls src={lesson.media.path} onTimeUpdate={onTimeUpdate} />
            ) : (
              <video ref={mediaRef} controls src={lesson.media.path} onTimeUpdate={onTimeUpdate} playsInline />
            )}
          </div>

          <div className="lyrics-panel" aria-label="Transcript subtitles">
            <div className="lyrics-toolbar">
              <div>
                <p className="eyebrow">Transcript</p>
                <h2>Live subtitles</h2>
              </div>
              <label className="search-box compact">
                <Search size={18} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search transcript, translation, notes"
                />
              </label>
            </div>

            <div className="lyrics-list" aria-live="polite">
              {filteredChunks.map((chunk) => {
                const index = lesson.chunks.findIndex((item) => item.id === chunk.id);
                const isActive = index === activeIndex;
                const isSelected = index === focusIndex;
                return (
                  <button
                    type="button"
                    key={chunk.id}
                    ref={(node) => {
                      chunkRefs.current[chunk.id] = node;
                    }}
                    className={`lyric-row${isActive ? " playing" : ""}${isSelected ? " selected" : ""}`}
                    onClick={() => seekTo(chunk)}
                    onKeyDown={(event) => onLyricsKeyDown(event, chunk)}
                  >
                    <span className="chunk-time">{formatTime(chunk.start)}-{formatTime(chunk.end)}</span>
                    <span className="lyric-text">
                      <strong>{chunk.sourceText}</strong>
                      <span>{chunk.translation || "待翻译"}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="control-row">
            <button type="button" onClick={replayFocusChunk} title="Replay current chunk">
              <RotateCcw size={18} />
              Replay
            </button>
            <label className="speed-control">
              <Gauge size={18} />
              <select value={speed} onChange={changeSpeed} aria-label="Playback speed">
                {SPEEDS.map((item) => (
                  <option key={item} value={item}>{item}x</option>
                ))}
              </select>
            </label>
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
    </main>
  );
}
