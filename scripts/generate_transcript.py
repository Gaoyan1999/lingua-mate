#!/usr/bin/env python3
"""Generate transcript files from Lingua Mate transcription chunks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_chunks(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{path} must contain an array.")
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise SystemExit(f"Chunk {index} must be an object.")
        for field in ("timeStart", "timeEnd", "origin", "translated"):
            if field not in item:
                raise SystemExit(f"Chunk {index} missing {field}.")
    return data


def timestamp_text(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{remaining:02d}"


def timestamp_subtitle(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole_seconds = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis == 1000:
        whole_seconds += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{millis:03d}"


def timestamp_vtt(seconds: float) -> str:
    return timestamp_subtitle(seconds).replace(",", ".")


def chunk_lines(chunk: dict[str, Any]) -> list[str]:
    lines = [str(chunk["origin"]).strip()]
    translated = str(chunk.get("translated") or "").strip()
    if translated:
        lines.append(translated)
    return [line for line in lines if line]


def write_txt(chunks: list[dict[str, Any]], path: Path) -> None:
    parts: list[str] = []
    for chunk in chunks:
        start = timestamp_text(float(chunk["timeStart"]))
        end = timestamp_text(float(chunk["timeEnd"]))
        parts.append(f"[{start} - {end}]")
        parts.extend(chunk_lines(chunk))
        parts.append("")
    path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def write_srt(chunks: list[dict[str, Any]], path: Path) -> None:
    parts: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        start = timestamp_subtitle(float(chunk["timeStart"]))
        end = timestamp_subtitle(float(chunk["timeEnd"]))
        parts.append(str(index))
        parts.append(f"{start} --> {end}")
        parts.extend(chunk_lines(chunk))
        parts.append("")
    path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def write_vtt(chunks: list[dict[str, Any]], path: Path) -> None:
    parts = ["WEBVTT", ""]
    for chunk in chunks:
        start = timestamp_vtt(float(chunk["timeStart"]))
        end = timestamp_vtt(float(chunk["timeEnd"]))
        parts.append(f"{start} --> {end}")
        parts.extend(chunk_lines(chunk))
        parts.append("")
    path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TXT, SRT, and VTT transcript files from chunks JSON.")
    parser.add_argument("--chunks", type=Path, default=Path("transcription_chunks.json"))
    parser.add_argument("--prefix", type=Path, default=Path("S10E01_transcript"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chunks = load_chunks(args.chunks)
    prefix = args.prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)

    txt_path = prefix.with_suffix(".txt")
    srt_path = prefix.with_suffix(".srt")
    vtt_path = prefix.with_suffix(".vtt")

    write_txt(chunks, txt_path)
    write_srt(chunks, srt_path)
    write_vtt(chunks, vtt_path)

    print(f"Wrote {txt_path.resolve()}")
    print(f"Wrote {srt_path.resolve()}")
    print(f"Wrote {vtt_path.resolve()}")
    print(f"Chunks: {len(chunks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

