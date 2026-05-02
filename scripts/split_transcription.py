#!/usr/bin/env python3
"""Split a media transcription into Lingua Mate translation-ready chunks."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from prepare_media import (
    chunk_segments,
    detect_silences,
    extract_audio,
    load_whisper_segments,
    run_whisper,
)


def to_translation_queue(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "timeStart": chunk["start"],
            "timeEnd": chunk["end"],
            "origin": chunk["sourceText"],
            "translated": "",
        }
        for chunk in chunks
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Transcribe a local English video/audio file, split it by pauses, and write "
            "transcription_chunks.json in the running folder."
        )
    )
    parser.add_argument("media", type=Path, help="Path to video or audio file.")
    parser.add_argument("--out", type=Path, default=Path("transcription_chunks.json"), help="Output JSON path.")
    parser.add_argument("--work-dir", type=Path, default=Path(".lingua-mate-work"), help="Intermediate files directory.")
    parser.add_argument("--source-language", default="en", help="Whisper language code. Default: en.")
    parser.add_argument("--whisper-model", default="base", help="Local Whisper model. Default: base.")
    parser.add_argument("--transcript-json", type=Path, help="Reuse an existing Whisper JSON transcript.")
    parser.add_argument("--min-pause", type=float, default=0.7, help="Pause length in seconds that can split chunks.")
    parser.add_argument("--min-chunk-duration", type=float, default=1.0, help="Avoid pause splits below this duration.")
    parser.add_argument("--max-chunk-duration", type=float, default=18.0, help="Force splits above this duration.")
    parser.add_argument("--silence-noise", default="-35dB", help="FFmpeg silencedetect noise threshold.")
    parser.add_argument("--keep-work", action="store_true", help="Keep extracted audio and Whisper transcript.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    media_path = args.media.expanduser().resolve()
    if not media_path.exists():
        raise SystemExit(f"Media file not found: {media_path}")

    work_dir = args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    audio_path = work_dir / "audio.wav"

    print(f"Extracting audio from {media_path.name}...")
    extract_audio(media_path, audio_path)

    if args.transcript_json:
        transcript_path = args.transcript_json.expanduser().resolve()
    else:
        print(f"Running local Whisper model '{args.whisper_model}'...")
        transcript_path = run_whisper(audio_path, work_dir / "whisper", args.whisper_model, args.source_language)

    print("Loading transcript and detecting pauses...")
    _, segments = load_whisper_segments(transcript_path)
    silences = detect_silences(audio_path, args.min_pause, args.silence_noise)
    chunks = chunk_segments(
        segments,
        silences=silences,
        min_pause=args.min_pause,
        min_chunk_duration=args.min_chunk_duration,
        max_chunk_duration=args.max_chunk_duration,
    )

    queue = to_translation_queue(chunks)
    args.out.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(queue)} chunks to {args.out.resolve()}")

    if not args.keep_work and not args.transcript_json:
        shutil.rmtree(work_dir, ignore_errors=True)
    elif args.keep_work:
        print(f"Kept intermediate files in {work_dir.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

