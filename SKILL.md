---
name: lingua-mate
description: Generate a local Vite language-learning webpage from an English video or podcast. Use when the user wants local English media processed into pause-based English subtitles, Chinese translation, read-through notes, and advanced vocabulary explanations.
---

# Lingua Mate

Turn a local English video or podcast into a Vite study player with Chinese subtitles, read-through explanations, and advanced vocabulary notes.

## When to Use

Use this skill when the user provides or references a local English media file and wants a Chinese-output webpage for language learning. V1 is designed for 5-30 minute videos or podcasts.

## Requirements

Check these before processing:

- `ffmpeg` and `ffprobe` are installed.
- A local `whisper` CLI is installed and available on `PATH`.
- Node.js and `pnpm` are available for the Vite template.
- The user has permission to process the media.

Do not require cloud transcription or runtime AI calls from the generated webpage. Codex/cc should generate translation and learning content into JSON files before the page runs.

## Workflow

1. Create a generated material directory outside the reusable skill/template source, for example `materials/<slug>/`.
2. Run media preparation:

   ```bash
   python3 scripts/prepare_media.py /path/to/media.mp4 --out materials/my-lesson --source-language en --target-language Chinese
   ```

   This extracts audio, runs local Whisper, detects pauses, and writes `lesson.draft.json` plus `ai_batches/*.json`.

   For a translation-ready chunk list only, run:

   ```bash
   python3 scripts/split_transcription.py /path/to/media.mp4
   ```

   This writes `materials/<media-name>/chunks.json` with `{ "timeStart", "timeEnd", "origin", "translated" }[]`. Leave `translated` empty for Codex/cc to fill with Chinese later.

3. For translation work, create a focused subagent and assign it a lite model such as `gpt-5.4-mini`, because English-to-Chinese chunk translation is straightforward and benefits from parallel, low-cost batching. Ask the subagent to preserve every chunk `id`; add `translation`, `readThrough`, and `vocabulary`.
4. Merge filled batches:

   ```bash
   python3 scripts/merge_batches.py materials/my-lesson/lesson.draft.json materials/my-lesson/ai_filled/*.json --out materials/my-lesson/lesson.json
   ```

5. Validate:

   ```bash
   python3 scripts/validate_lesson.py materials/my-lesson/lesson.json
   ```

6. Keep generated lesson files under `materials/<slug>/`. Symlink or copy the active material lesson into `assets/vite-template/data/lesson.json`, and copy or symlink the media into `assets/vite-template/public/media/`. Keep the lesson media path relative to the Vite public root, such as `/media/source.mp4`.
7. Run the generated page:

   ```bash
   pnpm install
   pnpm dev
   ```

For previewing this skill package's bundled template from the repo root, run `pnpm template:install` once and then `pnpm dev`.

## Lesson JSON Shape

The final `lesson.json` must have:

- `media`: `{ "type": "video" | "audio", "path": string, "duration": number, "title": string }`
- `languages`: `{ "source": string, "target": string }`
- `chunks`: ordered items with `id`, `start`, `end`, `sourceText`, `translation`, `readThrough`, and `vocabulary`

Each vocabulary item should explain one English word or phrase for a Chinese-speaking learner:

- `term`
- `meaning`
- `nuance`
- `example`

## Content Guidance

- Keep translations natural rather than word-for-word when needed.
- Use `readThrough` to explain what the source chunk means in context.
- Choose vocabulary that helps comprehension: idioms, collocations, grammar patterns, advanced words, cultural references, or easily confused phrases.
- Keep vocabulary concise. Prefer 1-5 entries per chunk.
- If source and target language are the same, still provide read-through and vocabulary notes.

## Quality Checks

- Verify the media file loads in the generated Vite app.
- Confirm subtitle highlighting follows playback time.
- Confirm every chunk has monotonic timestamps and non-empty source text.
- Confirm generated JSON passes `scripts/validate_lesson.py`.
- For long lessons, generate and merge AI batches instead of placing all content inline in app code.
