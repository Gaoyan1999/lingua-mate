#!/usr/bin/env python3
"""Generate concise study notes for one Lingua Mate lesson JSON file."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from validate_lesson import validate_lesson


NOTE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "chunks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "readThrough": {
                        "type": "array",
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "original": {"type": "string"},
                                "explanation": {"type": "string"},
                            },
                            "required": ["original", "explanation"],
                        },
                    },
                    "vocabulary": {
                        "type": "array",
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "original": {"type": "string"},
                                "explanation": {"type": "string"},
                            },
                            "required": ["original", "explanation"],
                        },
                    },
                },
                "required": ["id", "readThrough", "vocabulary"],
            },
        }
    },
    "required": ["chunks"],
}


NOTE_FIELDS = ("readThrough", "vocabulary")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("Enrichment output must be a JSON object.")
    return payload


def is_nonempty_note_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(
            isinstance(item, dict)
            and isinstance(item.get("original"), str)
            and item["original"].strip()
            and isinstance(item.get("explanation"), str)
            and item["explanation"].strip()
            for item in value
        )
    )


def normalize_note_list(value: Any, field: str, chunk_id: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError(f"Chunk {chunk_id} field {field} must be an array.")
    notes: list[dict[str, str]] = []
    for index, raw_note in enumerate(value):
        if not isinstance(raw_note, dict):
            raise ValueError(f"Chunk {chunk_id} field {field}[{index}] must be an object.")
        original = raw_note.get("original")
        explanation = raw_note.get("explanation")
        if not isinstance(original, str) or not original.strip():
            raise ValueError(f"Chunk {chunk_id} field {field}[{index}].original must be a non-empty string.")
        if not isinstance(explanation, str) or not explanation.strip():
            raise ValueError(f"Chunk {chunk_id} field {field}[{index}].explanation must be a non-empty string.")
        notes.append({"original": original.strip(), "explanation": explanation.strip()})
    return notes


def chunk_needs_enrichment(chunk: dict[str, Any], overwrite: bool) -> bool:
    return overwrite or any(not is_nonempty_note_list(chunk.get(field)) for field in NOTE_FIELDS)


def pending_chunks(lesson: dict[str, Any], overwrite: bool, limit: int | None) -> list[dict[str, Any]]:
    raw_chunks = lesson.get("chunks")
    if not isinstance(raw_chunks, list):
        raise SystemExit("Lesson must contain a chunks array.")
    chunks = [chunk for chunk in raw_chunks if isinstance(chunk, dict) and chunk_needs_enrichment(chunk, overwrite)]
    return chunks[:limit] if limit is not None else chunks


def build_prompt(batch: list[dict[str, Any]], lesson: dict[str, Any], learner_level: str) -> str:
    languages = lesson.get("languages", {})
    payload = {
        "languages": languages,
        "learnerLevel": learner_level,
        "chunks": [
            {
                "id": chunk["id"],
                "sourceText": chunk["sourceText"],
                "translation": chunk.get("translation", ""),
            }
            for chunk in batch
        ],
    }
    return (
        "Generate Lingua Mate study notes for Chinese-speaking learners.\n"
        "Return JSON matching the provided schema exactly. Do not add commentary.\n"
        "Use the same chunk ids. Do not alter sourceText or translation.\n"
        "For readThrough, generate 0-3 connected-speech listening notes per chunk: reductions, linking, weak forms, "
        "dropped sounds, stress, contractions, or fast-speech phrasing that could confuse listening.\n"
        "For vocabulary, generate 0-3 concise comprehension notes per chunk: idioms, phrasal verbs, collocations, "
        "implied meaning, cultural references, or easily confused phrases. Do not provide plain dictionary translation.\n"
        "Each note must have original and explanation. original should be an exact short phrase from sourceText. "
        "explanation should be concise Simplified Chinese. Match note density and difficulty to the learner level. "
        "If there is no genuinely useful note, return an empty array.\n\n"
        f"Input JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def enrich_batch(
    batch: list[dict[str, Any]],
    lesson: dict[str, Any],
    learner_level: str,
    model: str,
    cwd: Path,
) -> list[dict[str, Any]]:
    prompt = build_prompt(batch, lesson, learner_level)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        schema_path = temp_path / "schema.json"
        output_path = temp_path / "output.json"
        schema_path.write_text(json.dumps(NOTE_SCHEMA), encoding="utf-8")
        cmd = [
            "codex",
            "exec",
            "-C",
            str(cwd),
            "--sandbox",
            "read-only",
            "--model",
            model,
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            prompt,
        ]
        subprocess.run(cmd, check=True)
        payload = extract_json_object(output_path.read_text(encoding="utf-8"))

    chunks = payload.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("Enrichment output missing chunks array.")
    return chunks


def apply_enrichments(lesson: dict[str, Any], enrichments: list[dict[str, Any]], overwrite: bool = False) -> int:
    by_id: dict[str, dict[str, Any]] = {}
    for item in enrichments:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Each enrichment must contain a string id.")
        by_id[item["id"]] = item

    updated = 0
    for chunk in lesson.get("chunks", []):
        if not isinstance(chunk, dict) or not isinstance(chunk.get("id"), str):
            continue
        enrichment = by_id.get(chunk["id"])
        if enrichment is None:
            continue

        for field in NOTE_FIELDS:
            if not overwrite and is_nonempty_note_list(chunk.get(field)):
                continue
            next_notes = normalize_note_list(enrichment.get(field), field, chunk["id"])
            if chunk.get(field) != next_notes:
                chunk[field] = next_notes
                updated += 1
    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich one Lingua Mate lesson JSON with study notes.")
    parser.add_argument("--lesson", type=Path, required=True, help="Lesson JSON file to update.")
    parser.add_argument(
        "--learner-level",
        required=True,
        help="Required learner level, for example beginner, intermediate, advanced, IELTS 6.5, or B2.",
    )
    parser.add_argument("--model", default="gpt-5.4-mini", help="Codex model used for note generation.")
    parser.add_argument("--batch-size", type=int, default=10, help="Chunks per Codex enrichment batch.")
    parser.add_argument("--limit", type=int, help="Enrich at most this many pending chunks.")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate notes even when notes already exist.")
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    lesson_path = args.lesson.expanduser().resolve()
    if not lesson_path.exists():
        raise SystemExit(f"Lesson file not found: {lesson_path}")
    if not str(args.learner_level).strip():
        raise SystemExit("--learner-level is required.")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be at least 1.")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1.")

    lesson = load_json(lesson_path)
    errors = validate_lesson(lesson, allow_draft=True)
    if errors:
        for error in errors:
            print(error)
        return 1

    pending = pending_chunks(lesson, args.overwrite, args.limit)
    if not pending:
        print("No lesson chunks need enrichment.")
        return 0

    total_updates = 0
    cwd = Path.cwd()
    for offset in range(0, len(pending), args.batch_size):
        batch = pending[offset : offset + args.batch_size]
        print(f"Enriching batch {offset // args.batch_size + 1}: {batch[0]['id']}-{batch[-1]['id']}")
        enrichments = enrich_batch(batch, lesson, args.learner_level.strip(), args.model, cwd)
        total_updates += apply_enrichments(lesson, enrichments, overwrite=args.overwrite)
        write_json(lesson_path, lesson)

    errors = validate_lesson(lesson)
    if errors:
        for error in errors:
            print(error)
        return 1

    print(f"Updated {total_updates} note fields in {lesson_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
