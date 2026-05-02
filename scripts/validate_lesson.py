#!/usr/bin/env python3
"""Validate a Lingua Mate lesson JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VALID_MEDIA_TYPES = {"video", "audio"}


def require_dict(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object.")
        return {}
    return value


def require_string(value: Any, path: str, errors: list[str], allow_empty: bool = False) -> None:
    if not isinstance(value, str):
        errors.append(f"{path} must be a string.")
    elif not allow_empty and not value.strip():
        errors.append(f"{path} must not be empty.")


def require_number(value: Any, path: str, errors: list[str]) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{path} must be a number.")
        return None
    return float(value)


def validate_lesson(data: Any, allow_draft: bool = False) -> list[str]:
    errors: list[str] = []
    lesson = require_dict(data, "$", errors)

    media = require_dict(lesson.get("media"), "$.media", errors)
    media_type = media.get("type")
    if media_type not in VALID_MEDIA_TYPES:
        errors.append("$.media.type must be 'video' or 'audio'.")
    require_string(media.get("path"), "$.media.path", errors)
    require_string(media.get("title"), "$.media.title", errors)
    duration = require_number(media.get("duration"), "$.media.duration", errors)
    if duration is not None and duration <= 0:
        errors.append("$.media.duration must be greater than 0.")

    languages = require_dict(lesson.get("languages"), "$.languages", errors)
    require_string(languages.get("source"), "$.languages.source", errors)
    require_string(languages.get("target"), "$.languages.target", errors)

    chunks = lesson.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        errors.append("$.chunks must be a non-empty array.")
        return errors

    previous_end = -1.0
    seen_ids: set[str] = set()
    for index, raw_chunk in enumerate(chunks):
        path = f"$.chunks[{index}]"
        chunk = require_dict(raw_chunk, path, errors)
        chunk_id = chunk.get("id")
        require_string(chunk_id, f"{path}.id", errors)
        if isinstance(chunk_id, str):
            if chunk_id in seen_ids:
                errors.append(f"{path}.id duplicates {chunk_id}.")
            seen_ids.add(chunk_id)

        start = require_number(chunk.get("start"), f"{path}.start", errors)
        end = require_number(chunk.get("end"), f"{path}.end", errors)
        if start is not None and end is not None:
            if start < 0:
                errors.append(f"{path}.start must be >= 0.")
            if end <= start:
                errors.append(f"{path}.end must be greater than start.")
            if start < previous_end:
                errors.append(f"{path}.start must be >= previous chunk end.")
            previous_end = end

        require_string(chunk.get("sourceText"), f"{path}.sourceText", errors)
        require_string(chunk.get("translation"), f"{path}.translation", errors, allow_empty=allow_draft)
        require_string(chunk.get("readThrough"), f"{path}.readThrough", errors, allow_empty=allow_draft)

        vocabulary = chunk.get("vocabulary")
        if not isinstance(vocabulary, list):
            errors.append(f"{path}.vocabulary must be an array.")
            continue
        for vocab_index, raw_vocab in enumerate(vocabulary):
            vocab_path = f"{path}.vocabulary[{vocab_index}]"
            vocab = require_dict(raw_vocab, vocab_path, errors)
            require_string(vocab.get("term"), f"{vocab_path}.term", errors)
            require_string(vocab.get("meaning"), f"{vocab_path}.meaning", errors)
            require_string(vocab.get("nuance"), f"{vocab_path}.nuance", errors)
            require_string(vocab.get("example"), f"{vocab_path}.example", errors)

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a Lingua Mate lesson JSON file.")
    parser.add_argument("lesson", type=Path)
    parser.add_argument("--allow-draft", action="store_true", help="Allow empty translation and readThrough fields.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = json.loads(args.lesson.read_text(encoding="utf-8"))
    errors = validate_lesson(data, allow_draft=args.allow_draft)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"Valid lesson: {args.lesson}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
