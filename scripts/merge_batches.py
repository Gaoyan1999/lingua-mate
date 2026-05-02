#!/usr/bin/env python3
"""Merge filled Lingua Mate AI batch files into a final lesson JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_chunks(payload: Any, path: Path) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("chunks"), list):
        chunks = payload["chunks"]
    elif isinstance(payload, list):
        chunks = payload
    else:
        raise SystemExit(f"{path} must be an array or an object with a chunks array.")
    if not all(isinstance(item, dict) for item in chunks):
        raise SystemExit(f"{path} contains non-object chunks.")
    return chunks


def merge_batches(draft: dict[str, Any], batch_paths: list[Path]) -> dict[str, Any]:
    by_id: dict[str, dict[str, Any]] = {}
    for path in batch_paths:
        payload = load_json(path)
        for chunk in extract_chunks(payload, path):
            chunk_id = chunk.get("id")
            if not isinstance(chunk_id, str):
                raise SystemExit(f"{path} contains a chunk without a string id.")
            if chunk_id in by_id:
                raise SystemExit(f"Duplicate filled chunk id: {chunk_id}")
            by_id[chunk_id] = chunk

    missing: list[str] = []
    for chunk in draft.get("chunks", []):
        chunk_id = chunk.get("id")
        filled = by_id.get(chunk_id)
        if filled is None:
            missing.append(str(chunk_id))
            continue
        for field in ("translation", "readThrough", "vocabulary"):
            if field not in filled:
                raise SystemExit(f"Filled chunk {chunk_id} is missing {field}.")
            chunk[field] = filled[field]

    if missing:
        raise SystemExit(f"Missing filled chunks: {', '.join(missing)}")
    return draft


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge filled AI batches into a final lesson JSON.")
    parser.add_argument("draft", type=Path, help="Path to lesson.draft.json.")
    parser.add_argument("batches", nargs="+", type=Path, help="Filled batch JSON files.")
    parser.add_argument("--out", type=Path, required=True, help="Output lesson.json path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    draft = load_json(args.draft)
    merged = merge_batches(draft, args.batches)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

