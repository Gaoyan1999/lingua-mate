#!/usr/bin/env python3
"""Apply translation-ready chunks to the bundled Vite template."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from prepare_media import media_type, probe_duration


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


def build_lesson(chunks: list[dict[str, Any]], media_path: Path, public_media_path: str) -> dict[str, Any]:
    return {
        "media": {
            "type": media_type(media_path),
            "path": public_media_path,
            "duration": probe_duration(media_path),
            "title": media_path.stem,
        },
        "languages": {
            "source": "English",
            "target": "Chinese",
        },
        "chunks": [
            {
                "id": f"chunk-{index + 1:04d}",
                "start": round(float(chunk["timeStart"]), 3),
                "end": round(float(chunk["timeEnd"]), 3),
                "sourceText": str(chunk["origin"]).strip(),
                "translation": str(chunk["translated"]).strip(),
                "readThrough": "",
                "vocabulary": [],
            }
            for index, chunk in enumerate(chunks)
        ],
    }


def link_media(media_path: Path, media_dir: Path) -> str:
    media_dir.mkdir(parents=True, exist_ok=True)
    link_path = media_dir / media_path.name
    if link_path.exists() or link_path.is_symlink():
        if link_path.is_symlink() and link_path.resolve() == media_path.resolve():
            return f"/media/{media_path.name}"
        raise SystemExit(f"Media target already exists and is not the expected symlink: {link_path}")
    relative_target = os.path.relpath(media_path.resolve(), link_path.parent.resolve())
    link_path.symlink_to(relative_target)
    return f"/media/{media_path.name}"


def link_lesson(lesson_path: Path, template_lesson_path: Path) -> None:
    template_lesson_path.parent.mkdir(parents=True, exist_ok=True)
    if template_lesson_path.exists() or template_lesson_path.is_symlink():
        if template_lesson_path.is_symlink() and template_lesson_path.resolve() == lesson_path.resolve():
            return
        if template_lesson_path.is_dir():
            raise SystemExit(f"Template lesson path is a directory: {template_lesson_path}")
        template_lesson_path.unlink()
    relative_target = os.path.relpath(lesson_path.resolve(), template_lesson_path.parent.resolve())
    template_lesson_path.symlink_to(relative_target)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply transcription_chunks.json to the Vite lesson template.")
    parser.add_argument("--chunks", type=Path, default=Path("transcription_chunks.json"))
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=Path("assets/vite-template"))
    parser.add_argument("--lesson-out", type=Path, help="Canonical lesson JSON output path.")
    parser.add_argument("--link-template", action="store_true", help="Symlink template data/lesson.json to --lesson-out.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chunks_path = args.chunks.expanduser().resolve()
    media_path = args.media.expanduser().resolve()
    template_dir = args.template
    template_lesson_path = template_dir / "data" / "lesson.json"
    lesson_path = args.lesson_out or template_lesson_path
    media_dir = template_dir / "public" / "media"

    if not chunks_path.exists():
        raise SystemExit(f"Chunks file not found: {chunks_path}")
    if not media_path.exists():
        raise SystemExit(f"Media file not found: {media_path}")
    lesson_path.parent.mkdir(parents=True, exist_ok=True)

    public_media_path = link_media(media_path, media_dir)
    lesson = build_lesson(load_chunks(chunks_path), media_path, public_media_path)
    lesson_path.write_text(json.dumps(lesson, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.link_template:
        link_lesson(lesson_path, template_lesson_path)
    print(f"Wrote {lesson_path.resolve()}")
    print(f"Media path: {public_media_path}")
    print(f"Chunks: {len(lesson['chunks'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
