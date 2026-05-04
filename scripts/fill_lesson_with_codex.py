#!/usr/bin/env python3
"""Fill Lingua Mate lesson translations and study notes with Codex CLI."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from validate_lesson import validate_lesson


SCHEMA = {
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
                    "translation": {"type": "string"},
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
                "required": ["id", "translation", "readThrough", "vocabulary"],
            },
        }
    },
    "required": ["chunks"],
}

REASONING_EFFORTS = ("low", "medium", "high", "xhigh")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Codex output must be a JSON object.")
    return value


def is_note_list(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for note in value:
        if not isinstance(note, dict):
            return False
        if not isinstance(note.get("original"), str) or not note["original"].strip():
            return False
        if not isinstance(note.get("explanation"), str) or not note["explanation"].strip():
            return False
    return True


def chunk_needs_work(chunk: dict[str, Any], overwrite: bool) -> bool:
    if overwrite:
        return True
    return (
        not isinstance(chunk.get("translation"), str)
        or not chunk["translation"].strip()
        or not is_note_list(chunk.get("readThrough"))
        or not is_note_list(chunk.get("vocabulary"))
    )


def pending_chunks(lesson: dict[str, Any], overwrite: bool, limit: int | None) -> list[dict[str, Any]]:
    raw_chunks = lesson.get("chunks")
    if not isinstance(raw_chunks, list):
        raise SystemExit("Lesson must contain a chunks array.")
    chunks = [chunk for chunk in raw_chunks if isinstance(chunk, dict) and chunk_needs_work(chunk, overwrite)]
    return chunks[:limit] if limit is not None else chunks


def build_prompt(batch: list[dict[str, Any]], learner_level: str) -> str:
    payload = {
        "learnerLevel": learner_level,
        "chunks": [
            {
                "id": chunk["id"],
                "sourceText": chunk["sourceText"],
            }
            for chunk in batch
        ],
    }
    return (
        "You are creating Lingua Mate lesson data for Chinese-speaking English learners.\n"
        "Return JSON matching the provided schema exactly. Do not add commentary.\n"
        "For each input chunk, preserve the id and produce:\n"
        "1. translation: natural Simplified Chinese translation of sourceText.\n"
        "2. readThrough: 0-3 connected-speech and spoken-listening notes, such as linking, reductions, "
        "weak forms, dropped sounds, stress, contractions, fast-speech phrasing, or high-frequency spoken "
        "habits/fillers/discourse markers that are common in everyday English and can make audio hard to parse.\n"
        "3. vocabulary: 0-3 concise word or phrase notes, such as idioms, phrasal verbs, collocations, "
        "advanced words, implied meaning, register, cultural references, or easily confused lexical phrases. "
        "Do not put connected-speech/linking explanations in vocabulary unless the item is primarily a lexical phrase.\n"
        "Each note must use an exact short phrase from sourceText as original, and a concise Simplified "
        "Chinese explanation. Match note density and difficulty to the learner level. Avoid filler notes.\n\n"
        f"Input JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def fill_batch(
    batch: list[dict[str, Any]],
    learner_level: str,
    model: str,
    cwd: Path,
    skip_git_repo_check: bool,
    model_reasoning_effort: str | None,
) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        schema_path = temp_path / "schema.json"
        output_path = temp_path / "output.json"
        write_json(schema_path, SCHEMA)
        cmd = build_codex_command(
            cwd=cwd,
            model=model,
            schema_path=schema_path,
            output_path=output_path,
            prompt=build_prompt(batch, learner_level),
            skip_git_repo_check=skip_git_repo_check,
            model_reasoning_effort=model_reasoning_effort,
        )
        result = subprocess.run(cmd, check=False, text=True, capture_output=True)
        if result.returncode != 0:
            sys.stderr.write(result.stdout)
            sys.stderr.write(result.stderr)
            raise subprocess.CalledProcessError(result.returncode, cmd)
        payload = extract_json_object(output_path.read_text(encoding="utf-8"))
    chunks = payload.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("Codex output missing chunks array.")
    return chunks


def build_codex_command(
    cwd: Path,
    model: str,
    schema_path: Path,
    output_path: Path,
    prompt: str,
    skip_git_repo_check: bool,
    model_reasoning_effort: str | None,
) -> list[str]:
    cmd = ["codex", "exec"]
    if model_reasoning_effort:
        cmd.extend(["-c", f'model_reasoning_effort="{model_reasoning_effort}"'])
    cmd.extend(
        [
            "-C",
            str(cwd),
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--model",
            model,
        ]
    )
    if skip_git_repo_check:
        cmd.append("--skip-git-repo-check")
    cmd.extend(
        [
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            prompt,
        ]
    )
    return cmd


def normalize_note_list(value: Any, field: str, chunk_id: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError(f"{chunk_id}.{field} must be an array.")
    normalized: list[dict[str, str]] = []
    for index, note in enumerate(value):
        if not isinstance(note, dict):
            raise ValueError(f"{chunk_id}.{field}[{index}] must be an object.")
        original = note.get("original")
        explanation = note.get("explanation")
        if not isinstance(original, str) or not original.strip():
            raise ValueError(f"{chunk_id}.{field}[{index}].original must be a non-empty string.")
        if not isinstance(explanation, str) or not explanation.strip():
            raise ValueError(f"{chunk_id}.{field}[{index}].explanation must be a non-empty string.")
        normalized.append({"original": original.strip(), "explanation": explanation.strip()})
    return normalized


def apply_filled(lesson: dict[str, Any], filled: list[dict[str, Any]]) -> int:
    by_id = {item.get("id"): item for item in filled if isinstance(item, dict)}
    updated = 0
    for chunk in lesson.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        chunk_id = chunk.get("id")
        if not isinstance(chunk_id, str) or chunk_id not in by_id:
            continue
        item = by_id[chunk_id]
        translation = item.get("translation")
        if not isinstance(translation, str) or not translation.strip():
            raise ValueError(f"{chunk_id}.translation must be a non-empty string.")
        chunk["translation"] = translation.strip()
        chunk["readThrough"] = normalize_note_list(item.get("readThrough"), "readThrough", chunk_id)
        chunk["vocabulary"] = normalize_note_list(item.get("vocabulary"), "vocabulary", chunk_id)
        updated += 1
    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill a Lingua Mate lesson draft with Chinese output.")
    parser.add_argument("--draft", type=Path, required=True, help="Draft lesson JSON from prepare_media.py.")
    parser.add_argument("--out", type=Path, required=True, help="Final lesson JSON output path.")
    parser.add_argument(
        "--learner-level",
        required=True,
        help="Required learner level, for example beginner, intermediate, advanced, IELTS 6.5, or B2.",
    )
    parser.add_argument("--model", default="gpt-5.4-mini", help="Codex model used for generation.")
    parser.add_argument(
        "--model-reasoning-effort",
        choices=REASONING_EFFORTS,
        help="Codex reasoning effort for generation batches. Use 'low' for faster translation/note generation.",
    )
    parser.add_argument("--batch-size", type=int, default=8, help="Chunks per Codex batch.")
    parser.add_argument("--parallel", type=int, default=1, help="Number of Codex batches to run concurrently.")
    parser.add_argument("--limit", type=int, help="Fill at most this many pending chunks.")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate completed chunks.")
    parser.add_argument(
        "--no-skip-git-repo-check",
        action="store_true",
        help="Require Codex's normal git repository trust check.",
    )
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    if not str(args.learner_level).strip():
        raise SystemExit("--learner-level is required.")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be at least 1.")
    if args.parallel < 1:
        raise SystemExit("--parallel must be at least 1.")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1.")

    draft_path = args.draft.expanduser().resolve()
    out_path = args.out.expanduser().resolve()
    source_path = out_path if out_path.exists() else draft_path
    if not draft_path.exists():
        raise SystemExit(f"Draft lesson file not found: {draft_path}")

    lesson = read_json(source_path)
    errors = validate_lesson(lesson, allow_draft=True)
    if errors:
        for error in errors:
            print(error)
        return 1

    pending = pending_chunks(lesson, args.overwrite, args.limit)
    if not pending:
        print("No chunks need work.")
        write_json(out_path, lesson)
        return 0

    cwd = Path.cwd()
    total = 0
    skip_git_repo_check = not args.no_skip_git_repo_check
    batches = [
        (offset // args.batch_size + 1, pending[offset : offset + args.batch_size])
        for offset in range(0, len(pending), args.batch_size)
    ]
    if args.parallel == 1:
        for batch_number, batch in batches:
            print(f"Filling batch {batch_number}: {batch[0]['id']}-{batch[-1]['id']}", flush=True)
            filled = fill_batch(
                batch,
                args.learner_level.strip(),
                args.model,
                cwd,
                skip_git_repo_check,
                args.model_reasoning_effort,
            )
            total += apply_filled(lesson, filled)
            write_json(out_path, lesson)
            print(f"Updated {total} chunks so far.", flush=True)
    else:
        executor = ThreadPoolExecutor(max_workers=args.parallel)
        futures = {}
        try:
            for batch_number, batch in batches:
                print(f"Queueing batch {batch_number}: {batch[0]['id']}-{batch[-1]['id']}", flush=True)
                future = executor.submit(
                    fill_batch,
                    batch,
                    args.learner_level.strip(),
                    args.model,
                    cwd,
                    skip_git_repo_check,
                    args.model_reasoning_effort,
                )
                futures[future] = batch_number
            for future in as_completed(futures):
                batch_number = futures[future]
                filled = future.result()
                total += apply_filled(lesson, filled)
                write_json(out_path, lesson)
                print(f"Updated {total} chunks so far after batch {batch_number}.", flush=True)
        except Exception:
            for future in futures:
                future.cancel()
            raise
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    errors = validate_lesson(lesson)
    if errors:
        for error in errors:
            print(error)
        return 1

    print(f"Updated {total} chunks in {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
