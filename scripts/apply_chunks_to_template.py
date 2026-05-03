#!/usr/bin/env python3
"""Apply translation-ready chunks to the bundled Vite template."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from prepare_media import media_type, probe_duration


def slugify(value: str, fallback: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in value.strip())
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug or fallback


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


def build_lesson(chunks: list[dict[str, Any]], media_path: Path, public_media_path: str, title: str) -> dict[str, Any]:
    return {
        "media": {
            "type": media_type(media_path),
            "path": public_media_path,
            "duration": probe_duration(media_path),
            "title": title,
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
                "readThrough": [],
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


def link_file(source_path: Path, link_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.resolve() == source_path.resolve():
        return
    if link_path.exists() or link_path.is_symlink():
        if link_path.is_symlink() and link_path.resolve() == source_path.resolve():
            return
        if link_path.is_dir():
            raise SystemExit(f"Template Library path is a directory: {link_path}")
        link_path.unlink()
    relative_target = os.path.relpath(source_path.resolve(), link_path.parent.resolve())
    link_path.symlink_to(relative_target)


def load_lesson_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_lessons = data if isinstance(data, list) else data.get("lessons", []) if isinstance(data, dict) else []
    if not isinstance(raw_lessons, list):
        return []
    return [item for item in raw_lessons if isinstance(item, dict)]


def update_lesson_registry(registry_path: Path, entry: dict[str, Any], seed_path: Path | None = None) -> None:
    lessons: list[dict[str, Any]] = []
    if registry_path.exists():
        lessons = load_lesson_entries(registry_path)
    elif seed_path is not None:
        lessons = load_lesson_entries(seed_path)
    lessons = [item for item in lessons if item.get("id") != entry["id"]]

    lessons.append(entry)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({"lessons": lessons}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_lesson_index(index_path: Path, entry: dict[str, Any]) -> None:
    update_lesson_registry(index_path, entry)


def default_registry_path(lesson_path: Path) -> Path:
    if lesson_path.parent.parent.name == "materials":
        return lesson_path.parent.parent.parent / "registry.json"
    return lesson_path.parent.parent / "registry.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply transcription_chunks.json to the Vite Library template.")
    parser.add_argument("--chunks", type=Path, default=Path("transcription_chunks.json"))
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=Path("assets/vite-template"))
    parser.add_argument("--lesson-out", type=Path, help="Canonical Library JSON output path.")
    parser.add_argument("--lesson-id", help="Stable id used in the template Library list. Defaults to the Library title slug.")
    parser.add_argument("--lesson-title", help="Display title used in the Library item and template Library list.")
    parser.add_argument("--registry", type=Path, help="Canonical Library registry JSON path. Defaults beside the working folder.")
    parser.add_argument("--link-template", action="store_true", help="Register the Library item in the Vite template public data.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chunks_path = args.chunks.expanduser().resolve()
    media_path = args.media.expanduser().resolve()
    template_dir = args.template
    lesson_title = args.lesson_title or media_path.stem
    lesson_id = slugify(args.lesson_id or lesson_title, media_path.stem)
    template_data_dir = template_dir / "public" / "data"
    template_lesson_path = template_dir / "public" / "data" / "lesson.json"
    template_catalog_lesson_path = template_dir / "public" / "data" / "lessons" / f"{lesson_id}.json"
    template_index_path = template_dir / "public" / "data" / "lessons.json"
    template_registry_path = template_data_dir / "registry.json"
    lesson_path = args.lesson_out or (template_catalog_lesson_path if args.link_template else template_lesson_path)
    registry_path = args.registry or default_registry_path(lesson_path)
    media_dir = template_dir / "public" / "media"

    if not chunks_path.exists():
        raise SystemExit(f"Chunks file not found: {chunks_path}")
    if not media_path.exists():
        raise SystemExit(f"Media file not found: {media_path}")
    lesson_path.parent.mkdir(parents=True, exist_ok=True)

    public_media_path = link_media(media_path, media_dir)
    lesson = build_lesson(load_chunks(chunks_path), media_path, public_media_path, lesson_title)
    lesson_path.write_text(json.dumps(lesson, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.link_template:
        entry = {
            "id": lesson_id,
            "title": lesson["media"]["title"],
            "lessonPath": f"/data/lessons/{lesson_id}.json",
            "mediaType": lesson["media"]["type"],
            "duration": lesson["media"]["duration"],
            "source": lesson["languages"]["source"],
            "target": lesson["languages"]["target"],
        }
        update_lesson_registry(registry_path, entry, seed_path=template_index_path)
        link_file(lesson_path, template_lesson_path)
        link_file(lesson_path, template_catalog_lesson_path)
        link_file(registry_path, template_registry_path)
        link_file(registry_path, template_index_path)
    print(f"Wrote {lesson_path.resolve()}")
    print(f"Media path: {public_media_path}")
    if args.link_template:
        print(f"Registry: {registry_path.resolve()}")
        print(f"Registered Library item: {lesson_id}")
    print(f"Chunks: {len(lesson['chunks'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
