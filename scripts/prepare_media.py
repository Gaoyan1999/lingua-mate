#!/usr/bin/env python3
"""Prepare a local media file for a Lingua Mate Library item."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}
SENTENCE_BOUNDARY_RE = re.compile(r"[^.!?]+[.!?]+(?:['\"])?|[^.!?]+$")
SENTENCE_DOT_PLACEHOLDER = "<prd>"
SENTENCE_ABBREVIATIONS = (
    "Mr.",
    "Mrs.",
    "Ms.",
    "Dr.",
    "Prof.",
    "Sr.",
    "Jr.",
    "St.",
    "vs.",
    "etc.",
    "e.g.",
    "i.e.",
    "a.m.",
    "p.m.",
    "U.S.",
    "U.K.",
)


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Silence:
    start: float
    end: float


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True)


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required command: {name}")


def media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    return "video"


def probe_duration(media_path: Path) -> float:
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(media_path),
        ]
    )
    payload = json.loads(result.stdout)
    return round(float(payload["format"]["duration"]), 3)


def extract_audio(media_path: Path, audio_path: Path) -> None:
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(media_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(audio_path),
        ]
    )


def detect_silences(audio_path: Path, min_silence: float, noise: str) -> list[Silence]:
    result = subprocess.run(
        [
            "ffmpeg",
            "-i",
            str(audio_path),
            "-af",
            f"silencedetect=n={noise}:d={min_silence}",
            "-f",
            "null",
            "-",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    starts: list[float] = []
    silences: list[Silence] = []
    for line in result.stderr.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            starts.append(float(start_match.group(1)))
            continue
        end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end_match and starts:
            end = float(end_match.group(1))
            silences.append(Silence(start=starts.pop(0), end=end))
    return silences


def run_whisper(
    audio_path: Path,
    output_dir: Path,
    model: str,
    source_language: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    whisper_command = ["whisper"] if shutil.which("whisper") else [sys.executable, "-m", "whisper"]
    cmd = [
        *whisper_command,
        str(audio_path),
        "--model",
        model,
        "--output_format",
        "json",
        "--output_dir",
        str(output_dir),
    ]
    if source_language.lower() != "auto":
        cmd.extend(["--language", source_language])
    run_command(cmd)
    transcript = output_dir / f"{audio_path.stem}.json"
    if not transcript.exists():
        candidates = sorted(output_dir.glob("*.json"))
        if not candidates:
            raise SystemExit("Whisper completed but no JSON transcript was produced.")
        return candidates[0]
    return transcript


def load_whisper_segments(transcript_path: Path) -> tuple[str, list[Segment]]:
    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    language = str(payload.get("language") or "auto")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        raise SystemExit("Whisper JSON must contain a 'segments' list.")
    segments: list[Segment] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        text = normalize_text(str(item.get("text") or ""))
        if not text:
            continue
        segments.append(
            Segment(
                start=float(item["start"]),
                end=float(item["end"]),
                text=text,
            )
        )
    if not segments:
        raise SystemExit("No usable transcript segments found.")
    return language, segments


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def split_text_sentences(text: str) -> list[str]:
    protected = text
    for abbreviation in SENTENCE_ABBREVIATIONS:
        protected = re.sub(
            re.escape(abbreviation),
            lambda match: match.group(0).replace(".", SENTENCE_DOT_PLACEHOLDER),
            protected,
            flags=re.IGNORECASE,
        )
    sentences = [
        normalize_text(match.group(0).replace(SENTENCE_DOT_PLACEHOLDER, "."))
        for match in SENTENCE_BOUNDARY_RE.finditer(protected)
    ]
    return [sentence for sentence in sentences if sentence]


def distribute_text_segments(texts: list[str], start: float, end: float) -> list[Segment]:
    duration = max(0.0, end - start)
    total_chars = sum(len(text) for text in texts)
    if duration <= 0 or total_chars <= 0:
        return [Segment(start=start, end=end, text=text) for text in texts]

    fragments: list[Segment] = []
    cursor = start
    consumed_chars = 0
    for index, text in enumerate(texts):
        if index == len(texts) - 1:
            text_end = end
        else:
            consumed_chars += len(text)
            text_end = start + duration * consumed_chars / total_chars
        fragments.append(Segment(start=cursor, end=text_end, text=text))
        cursor = text_end
    return fragments


def split_long_segment(segment: Segment, max_fragment_duration: float) -> list[Segment]:
    duration = max(0.0, segment.end - segment.start)
    if max_fragment_duration <= 0 or duration <= max_fragment_duration:
        return [segment]

    words = segment.text.split()
    if len(words) <= 1:
        return [segment]

    part_count = min(len(words), math.ceil(duration / max_fragment_duration))
    parts: list[str] = []
    cursor = 0
    for index in range(part_count):
        remaining_words = len(words) - cursor
        remaining_parts = part_count - index
        take = math.ceil(remaining_words / remaining_parts)
        parts.append(" ".join(words[cursor : cursor + take]))
        cursor += take

    part_duration = duration / part_count
    return [
        Segment(
            start=segment.start + index * part_duration,
            end=segment.end if index == part_count - 1 else segment.start + (index + 1) * part_duration,
            text=part,
        )
        for index, part in enumerate(parts)
    ]


def split_segment_sentences(segment: Segment, max_fragment_duration: float = 0.0) -> list[Segment]:
    sentences = split_text_sentences(segment.text)
    if len(sentences) <= 1:
        return split_long_segment(segment, max_fragment_duration)

    sentence_segments = distribute_text_segments(sentences, segment.start, segment.end)
    fragments: list[Segment] = []
    for sentence_segment in sentence_segments:
        fragments.extend(split_long_segment(sentence_segment, max_fragment_duration))
    return fragments


def split_segments_into_sentences(segments: list[Segment], max_fragment_duration: float = 0.0) -> list[Segment]:
    sentence_segments: list[Segment] = []
    for segment in segments:
        sentence_segments.extend(split_segment_sentences(segment, max_fragment_duration))
    return sentence_segments


def sentence_count(text: str) -> int:
    count = len(split_text_sentences(text))
    return max(1, count)


def has_detected_pause(prev_end: float, next_start: float, silences: Iterable[Silence], min_silence: float) -> bool:
    for silence in silences:
        if silence.end < prev_end:
            continue
        if silence.start > next_start:
            break
        overlap_start = max(prev_end, silence.start)
        overlap_end = min(next_start, silence.end)
        if overlap_end - overlap_start >= min_silence * 0.5:
            return True
    return False


def chunk_segments(
    segments: list[Segment],
    silences: list[Silence] | None = None,
    min_pause: float = 0.7,
    min_chunk_duration: float = 1.0,
    max_chunk_duration: float = 18.0,
    max_sentences_per_chunk: int = 2,
) -> list[dict[str, Any]]:
    if not segments:
        return []
    segments = split_segments_into_sentences(segments, max_chunk_duration)
    silences = sorted(silences or [], key=lambda item: item.start)
    chunks: list[dict[str, Any]] = []
    current: list[Segment] = [segments[0]]

    def flush() -> None:
        nonlocal current
        if not current:
            return
        start = current[0].start
        end = current[-1].end
        chunks.append(
            {
                "id": f"chunk-{len(chunks) + 1:04d}",
                "start": round(start, 3),
                "end": round(end, 3),
                "sourceText": normalize_text(" ".join(segment.text for segment in current)),
                "translation": "",
                "readThrough": [],
                "vocabulary": [],
            }
        )
        current = []

    for segment in segments[1:]:
        previous = current[-1]
        gap = max(0.0, segment.start - previous.end)
        duration_if_added = segment.end - current[0].start
        current_duration = previous.end - current[0].start
        pause_boundary = gap >= min_pause or has_detected_pause(previous.end, segment.start, silences, min_pause)
        split_for_pause = pause_boundary and current_duration >= min_chunk_duration
        split_for_length = duration_if_added > max_chunk_duration
        current_sentences = sum(sentence_count(item.text) for item in current)
        split_for_sentences = (
            max_sentences_per_chunk > 0
            and current_sentences >= max_sentences_per_chunk
            and current_duration >= min_chunk_duration
        )

        if split_for_pause or split_for_length or split_for_sentences:
            flush()
        current.append(segment)

    flush()
    return chunks


def write_ai_batches(lesson: dict[str, Any], output_dir: Path, batch_size: int) -> None:
    batches_dir = output_dir / "ai_batches"
    batches_dir.mkdir(parents=True, exist_ok=True)
    chunks = lesson["chunks"]
    for index in range(0, len(chunks), batch_size):
        batch_chunks = chunks[index : index + batch_size]
        batch = {
            "instructions": (
                "Fill translation, readThrough, and vocabulary for each chunk. "
                "Preserve ids, timestamps, and sourceText exactly. readThrough is an array "
                "of connected-speech and spoken-listening notes, including linking and common "
                "everyday spoken habits/fillers that can make audio hard to parse. vocabulary "
                "is an array of concise word and phrase notes. Each note needs original and explanation."
            ),
            "languages": lesson["languages"],
            "chunks": batch_chunks,
        }
        batch_path = batches_dir / f"batch-{index // batch_size + 1:03d}.json"
        batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_lesson(
    media_path: Path,
    public_media_path: str,
    duration: float,
    source_language: str,
    target_language: str,
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "media": {
            "type": media_type(media_path),
            "path": public_media_path,
            "duration": duration,
            "title": media_path.stem,
        },
        "languages": {
            "source": source_language,
            "target": target_language,
        },
        "chunks": chunks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a local video or podcast for a Lingua Mate Vite Library item.")
    parser.add_argument("media", type=Path, help="Path to the source video or audio file.")
    parser.add_argument("--out", type=Path, required=True, help="Output directory for Library artifacts.")
    parser.add_argument("--source-language", default="en", help="Source language for Whisper. Default: en.")
    parser.add_argument("--target-language", default="Chinese", help="Target language for translations/explanations.")
    parser.add_argument("--whisper-model", default="base", help="Local Whisper model name.")
    parser.add_argument("--transcript-json", type=Path, help="Use an existing Whisper JSON transcript instead of running Whisper.")
    parser.add_argument("--min-pause", type=float, default=0.7, help="Pause length in seconds that can split chunks.")
    parser.add_argument("--min-chunk-duration", type=float, default=1.0, help="Avoid pause splits below this duration.")
    parser.add_argument("--max-chunk-duration", type=float, default=18.0, help="Force splits above this duration.")
    parser.add_argument("--max-sentences-per-chunk", type=int, default=2, help="Split chunks after this many sentence-ending punctuation marks. Use 0 to disable the sentence-count cap.")
    parser.add_argument("--silence-noise", default="-35dB", help="FFmpeg silencedetect noise threshold.")
    parser.add_argument("--batch-size", type=int, default=25, help="Chunks per AI batch file.")
    parser.add_argument("--media-public-path", help="Media path used by the Vite app, for example /media/source.mp4.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    media_path = args.media.expanduser().resolve()
    if not media_path.exists():
        raise SystemExit(f"Media file not found: {media_path}")

    require_command("ffmpeg")
    require_command("ffprobe")

    output_dir = args.out
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / "audio.wav"
    extract_audio(media_path, audio_path)

    transcript_path = args.transcript_json
    if transcript_path is None:
        transcript_path = run_whisper(audio_path, output_dir / "whisper", args.whisper_model, args.source_language)
    else:
        transcript_path = transcript_path.expanduser().resolve()

    detected_language, segments = load_whisper_segments(transcript_path)
    source_language = args.source_language if args.source_language.lower() != "auto" else detected_language
    silences = detect_silences(audio_path, args.min_pause, args.silence_noise)
    chunks = chunk_segments(
        segments,
        silences=silences,
        min_pause=args.min_pause,
        min_chunk_duration=args.min_chunk_duration,
        max_chunk_duration=args.max_chunk_duration,
        max_sentences_per_chunk=args.max_sentences_per_chunk,
    )
    duration = probe_duration(media_path)
    public_media_path = args.media_public_path or f"/media/{media_path.name}"
    lesson = build_lesson(media_path, public_media_path, duration, source_language, args.target_language, chunks)

    (output_dir / "lesson.draft.json").write_text(
        json.dumps(lesson, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_ai_batches(lesson, output_dir, args.batch_size)
    print(f"Wrote {output_dir / 'lesson.draft.json'}")
    print(f"Wrote AI batches to {output_dir / 'ai_batches'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
