#!/usr/bin/env python3
"""Translate transcription_chunks.json to Simplified Chinese with Codex CLI batches."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer"},
                    "translated": {"type": "string"},
                },
                "required": ["index", "translated"],
            },
        }
    },
    "required": ["translations"],
}


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
        raise ValueError("Translator output must be a JSON object.")
    return payload


def translate_batch(batch: list[dict[str, Any]], model: str, cwd: Path) -> list[dict[str, Any]]:
    prompt = (
        "Translate each origin field from English into natural Simplified Chinese.\n"
        "Return JSON matching the provided schema exactly.\n"
        "Use the same index values. Do not include the English text. Do not add commentary.\n"
        "Preserve profanity, tone, speaker intent, and repeated phrases. If the English is garbled, "
        "translate the best apparent meaning literally.\n\n"
        f"Input JSON:\n{json.dumps(batch, ensure_ascii=False, indent=2)}"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        schema_path = temp_path / "schema.json"
        output_path = temp_path / "output.json"
        schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
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

    translations = payload.get("translations")
    if not isinstance(translations, list):
        raise ValueError("Translator output missing translations array.")
    return translations


def apply_translations(chunks: list[dict[str, Any]], translations: list[dict[str, Any]]) -> int:
    updated = 0
    for item in translations:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        translated = item.get("translated")
        if not isinstance(index, int) or not isinstance(translated, str):
            continue
        if index < 0 or index >= len(chunks):
            continue
        if translated.strip():
            chunks[index]["translated"] = translated.strip()
            updated += 1
    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Translate transcription chunks to Simplified Chinese with Codex CLI.")
    parser.add_argument("--chunks", type=Path, default=Path("transcription_chunks.json"))
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--limit", type=int, help="Translate at most this many untranslated chunks.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chunks_path = args.chunks
    chunks = load_chunks(chunks_path)
    pending = [index for index, chunk in enumerate(chunks) if not str(chunk.get("translated") or "").strip()]
    if args.limit is not None:
        pending = pending[: args.limit]
    if not pending:
        print("No untranslated chunks found.")
        return 0

    total_updated = 0
    cwd = Path.cwd()
    for offset in range(0, len(pending), args.batch_size):
        indexes = pending[offset : offset + args.batch_size]
        batch = [{"index": index, "origin": chunks[index]["origin"]} for index in indexes]
        print(f"Translating batch {offset // args.batch_size + 1}: chunks {indexes[0]}-{indexes[-1]}")
        translations = translate_batch(batch, args.model, cwd)
        updated = apply_translations(chunks, translations)
        total_updated += updated
        chunks_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {updated} chunks in this batch.")

    print(f"Updated {total_updated} chunks total in {chunks_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

