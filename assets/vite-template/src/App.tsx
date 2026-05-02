import { ChangeEvent, useMemo, useRef, useState } from "react";
import { Gauge, ListRestart, Play, RotateCcw, Search } from "lucide-react";
import lessonData from "../data/lesson.json";
import type { Lesson, LessonChunk, VocabularyItem } from "./types";

const lesson = lessonData as Lesson;
const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

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

export default function App() {
  const mediaRef = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [query, setQuery] = useState("");
  const [selectedTerm, setSelectedTerm] = useState<VocabularyItem | null>(lesson.chunks[0]?.vocabulary[0] ?? null);

  const activeIndex = findActiveChunk(lesson.chunks, currentTime);
  const focusIndex = selectedIndex >= 0 ? selectedIndex : activeIndex;
  const activeChunk = lesson.chunks[activeIndex] ?? lesson.chunks[0];
  const focusChunk = lesson.chunks[focusIndex] ?? activeChunk;
  const activeTranslation = activeChunk.translation || "待翻译";
  const focusReadThrough = focusChunk.readThrough || "待生成中文讲解";

  const filteredChunks = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return lesson.chunks;
    return lesson.chunks.filter((chunk) => {
      const vocab = chunk.vocabulary.map((item) => `${item.term} ${item.meaning}`).join(" ");
      return `${chunk.sourceText} ${chunk.translation} ${chunk.readThrough} ${vocab}`.toLowerCase().includes(needle);
    });
  }, [query]);

  function seekTo(chunk: LessonChunk) {
    const media = mediaRef.current;
    if (!media) return;
    media.currentTime = chunk.start;
    setCurrentTime(chunk.start);
    setSelectedIndex(lesson.chunks.findIndex((item) => item.id === chunk.id));
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

  return (
    <main className="app-shell">
      <section className="lesson-stage" aria-label="Lesson player">
        <div className="media-column">
          <div className="title-row">
            <div>
              <p className="eyebrow">{lesson.languages.source} to {lesson.languages.target}</p>
              <h1>{lesson.media.title}</h1>
            </div>
            <div className="time-badge">{formatTime(currentTime)} / {formatTime(lesson.media.duration)}</div>
          </div>

          <div className="media-frame">
            {lesson.media.type === "audio" ? (
              <audio ref={mediaRef} controls src={lesson.media.path} onTimeUpdate={onTimeUpdate} />
            ) : (
              <video ref={mediaRef} controls src={lesson.media.path} onTimeUpdate={onTimeUpdate} playsInline />
            )}
          </div>

          <div className="subtitle-panel" aria-live="polite">
            <p className="source-line">{activeChunk.sourceText}</p>
            <p className="translation-line">{activeTranslation}</p>
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

        <aside className="study-column" aria-label="Study notes">
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
      </section>

      <section className="transcript-area" aria-label="Transcript">
        <div className="transcript-toolbar">
          <div>
            <p className="eyebrow">Transcript</p>
            <h2>Pause-based chunks</h2>
          </div>
          <label className="search-box">
            <Search size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search transcript, translation, notes"
            />
          </label>
        </div>

        <div className="chunk-list">
          {filteredChunks.map((chunk) => {
            const index = lesson.chunks.findIndex((item) => item.id === chunk.id);
            const isActive = index === activeIndex;
            const isSelected = index === focusIndex;
            return (
              <button
                type="button"
                key={chunk.id}
                className={`chunk-row${isActive ? " playing" : ""}${isSelected ? " selected" : ""}`}
                onClick={() => seekTo(chunk)}
              >
                <span className="chunk-time">{formatTime(chunk.start)}-{formatTime(chunk.end)}</span>
                <span className="chunk-text">
                  <strong>{chunk.sourceText}</strong>
                  <span>{chunk.translation || "待翻译"}</span>
                </span>
              </button>
            );
          })}
        </div>
      </section>
    </main>
  );
}
