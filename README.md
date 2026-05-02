# Lingua Mate

Lingua Mate is a Codex skill package for turning a local English video or podcast into a local Vite study page with English transcript chunks and Chinese translation.

## What It Does

- Extracts audio from local media with FFmpeg.
- Transcribes English speech with local Whisper.
- Splits transcript text into pause-based chunks.
- Translates chunk JSON into Simplified Chinese with Codex CLI batches.
- Applies translated material to a Vite learner page.
- Keeps generated lesson material out of source control.

## Requirements

- Python 3
- FFmpeg and FFprobe
- Local Whisper package or CLI
- Node.js and pnpm
- Codex CLI for translation batches

## Common Commands

```bash
pnpm test
pnpm build
```

Split a local video into translation-ready chunks:

```bash
pnpm split -- ./S10E01.mp4 --whisper-model tiny.en --keep-work
```

Translate the configured material chunks:

```bash
pnpm translate
```

Apply translated S10E01 material to the Vite template:

```bash
pnpm apply:s10e01
```

Run the local learner page:

```bash
pnpm template:install
pnpm dev
```

## Generated Material

Generated content is intentionally ignored by git. The canonical generated material path for the current sample is:

```text
materials/s10e01/
```

When applying a generated lesson to the reusable Vite template, link or copy the active lesson JSON to:

```text
assets/vite-template/public/data/lesson.json
```

The reusable source code lives in `scripts/`, `assets/vite-template/`, `tests/`, and `SKILL.md`.
