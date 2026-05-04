---
name: lingua-mate
description: Generate a local Vite language-learning webpage from an English video or podcast. Use when the user wants local English media processed into pause-based English subtitles, Chinese translation, read-through notes, and advanced vocabulary explanations.
---

# Lingua Mate

Turn a local English video or podcast into a Vite study player with Chinese subtitles, read-through explanations, and advanced vocabulary notes.

## When to Use

Use this skill when the user provides or references a local English media file and wants a Chinese-output webpage for language learning. V1 is designed for 5-30 minute videos or podcasts.

If the user provides a Bilibili URL instead of a local file, first confirm it is a concrete `/video/BV...` or `/video/av...` link, then ask for the learner's English level before downloading. Do not start the Bilibili download until the level is known.

If the user provides a YouTube URL instead of a local file, first confirm it is a concrete watch, `youtu.be`, Shorts, embed, or live video link, then ask for the learner's English level before downloading. Do not start the YouTube download until the level is known.

## Requirements

Check these before processing:

- `ffmpeg` and `ffprobe` are installed.
- A local `whisper` CLI is installed and available on `PATH`.
- Node.js and `pnpm` are available for the Vite template.
- The user has permission to process the media.
- For private or high-quality Bilibili videos, the user may need to provide a `SESSDATA` value or set `BILIBILI_SESSDATA`.
- YouTube download uses the reference `youtube-dl` checkout at `/Users/daniel/Workspace/youtube-dl` by default. For another checkout, set `YOUTUBE_DL_ROOT` or pass `--youtube-dl-root`. For restricted videos, the user may need a Netscape cookies file and set `YOUTUBE_COOKIES` or pass `--cookies`.

Do not require cloud transcription or runtime AI calls from the generated webpage. Codex/cc should generate translation and learning content into JSON files before the page runs.

## Workflow

This skill should run as an automatic local pipeline. Given an English video or podcast, the agent should:

1. Determine whether the source material is a local file, a concrete Bilibili video link, or a concrete YouTube video link.
2. Ask the user for the learner's English level if it was not already provided. Keep the question simple: "What's your English level? You can answer beginner, intermediate, advanced, or tell me your test/school level." Also accept CEFR labels such as `A2`, `B1`, `B2`, or `C1` if the user provides them. Stop and wait for the user's answer before any download, transcription, translation, `readThrough`, or `vocabulary` work; do not infer a default level.
3. If it is a Bilibili or YouTube link, download it into a local folder named after the video after the learner level is confirmed.
4. Extract and split the transcript locally.
5. Fill English-to-Chinese translations and learning notes with `scripts/fill_lesson_with_codex.py`, passing the confirmed learner level with `--learner-level`.
6. Save the translated result as JSON in the generated material folder.
7. Clean up intermediate generation files unless the user explicitly asks to keep them.

Do not stop after transcription unless the user explicitly asks for transcript-only output.

## Preferred Material Layout

Prefer a separate working folder for user media and generated Library data. For local testing in this checkout, use `/Users/daniel/tools/test-lingua-mate` as the working folder. Each resource should have its own folder named after the source media, and the working folder should have one registry file:

```text
test-lingua-mate/
  registry.json
  materials/
    S10E01/
      S10E01.mp4
      chunks.json
      lesson.json
```

The resource folder should contain the original video or podcast file plus final generated JSON. Use a stable resource name derived from the media filename, such as `S10E01` for `S10E01.mp4`. Avoid leaving intermediate transcription files in the final folder unless the user asks to keep them.

## Steps

1. Ask for the learner's English level if not already known, and wait for the user's answer before generation. Do not choose a default level. Use this simple question: "What's your English level? You can answer beginner, intermediate, advanced, or tell me your test/school level." Use the answer for study-note difficulty and density:
   - beginner: explain common reductions, basic phrases, and high-frequency vocabulary in simple Chinese.
   - intermediate: focus on natural connected speech, phrasal verbs, idioms, collocations, and implied meaning.
   - advanced: avoid obvious vocabulary; focus on subtle register, cultural references, discourse markers, pronunciation reductions, and nuanced usage.
   - If the user gives a CEFR label, map `A1-A2` to beginner, `B1-B2` to intermediate, and `C1-C2` to advanced.
2. Create the generated material directory outside the reusable skill/template source, for example `/Users/daniel/tools/test-lingua-mate/materials/<resource-name>/`. Put or copy the original media file in that folder when practical, so the original material and generated JSON stay together.
3. If the source is a Bilibili or YouTube video link, download it after the learner level is confirmed.

   For Bilibili:

   ```bash
   pnpm bilibili -- "https://www.bilibili.com/video/BV..." --output-root /Users/daniel/tools/test-lingua-mate/materials
   ```

   The downloader supports concrete `/video/BV...` and `/video/av...` links. It rejects search, channel, list, and bangumi pages in v1. If the link has `?p=N`, that part is downloaded; otherwise page 1 is used. For higher-quality restricted videos, pass `--sessdata "$BILIBILI_SESSDATA"` or set the environment variable.

   For YouTube:

   ```bash
   pnpm youtube -- "https://www.youtube.com/watch?v=..." --output-root /Users/daniel/tools/test-lingua-mate/materials
   ```

   The downloader supports concrete watch, `youtu.be`, Shorts, embed, and live video links. It rejects search, channel, and playlist-only pages in v1. It uses the reference `youtube-dl` checkout at `/Users/daniel/Workspace/youtube-dl` by default; pass `--youtube-dl-root` or set `YOUTUBE_DL_ROOT` to use another checkout. For restricted videos, pass `--cookies /path/to/cookies.txt` or set `YOUTUBE_COOKIES`.

4. Run media preparation:

   ```bash
   python3 scripts/prepare_media.py /Users/daniel/tools/test-lingua-mate/materials/S10E01/S10E01.mp4 --out /Users/daniel/tools/test-lingua-mate/materials/S10E01 --source-language en --target-language Chinese
   ```

   This extracts audio, runs local Whisper, detects pauses, and writes `lesson.draft.json` plus `ai_batches/*.json`.

   For a translation-ready chunk list only, run:

   ```bash
   python3 scripts/split_transcription.py /Users/daniel/tools/test-lingua-mate/materials/S10E01/S10E01.mp4
   ```

   This writes `/Users/daniel/tools/test-lingua-mate/materials/<media-name>/chunks.json` with `{ "timeStart", "timeEnd", "origin", "translated" }[]`. Leave `translated` empty for Codex/cc to fill with Chinese later.

5. Fill the draft lesson with Chinese translations plus level-matched `readThrough` and `vocabulary` notes. Pass the user's learner level explicitly:

   ```bash
   pnpm fill -- --draft /Users/daniel/tools/test-lingua-mate/materials/S10E01/lesson.draft.json --out /Users/daniel/tools/test-lingua-mate/materials/S10E01/lesson.json --learner-level intermediate
   ```

   This uses `scripts/fill_lesson_with_codex.py`, runs Codex in small batches with `gpt-5.4-mini` by default, writes progress after every batch, and resumes from `--out` if it already exists. Adjust `--batch-size`, `--model`, `--model-reasoning-effort`, `--parallel`, or `--limit` when useful. Use `--overwrite` only when intentionally regenerating completed chunks. For long lessons where translation quality can trade off against speed, prefer a low-reasoning parallel run:

   ```bash
   pnpm fill -- --draft /Users/daniel/tools/test-lingua-mate/materials/S10E01/lesson.draft.json --out /Users/daniel/tools/test-lingua-mate/materials/S10E01/lesson.json --learner-level intermediate --model gpt-5.4-mini --model-reasoning-effort low --batch-size 20 --parallel 4
   ```

6. If using manually filled `ai_batches/` instead of the `pnpm fill` path, merge filled batches:

   ```bash
   python3 scripts/merge_batches.py /Users/daniel/tools/test-lingua-mate/materials/S10E01/lesson.draft.json /Users/daniel/tools/test-lingua-mate/materials/S10E01/ai_filled/*.json --out /Users/daniel/tools/test-lingua-mate/materials/S10E01/lesson.json
   ```

7. Validate:

   ```bash
   python3 scripts/validate_lesson.py /Users/daniel/tools/test-lingua-mate/materials/S10E01/lesson.json
   ```

8. Enrich a specific finished lesson with connected-speech and vocabulary notes:

   ```bash
   pnpm enrich -- --lesson /Users/daniel/tools/test-lingua-mate/materials/S10E01/lesson.json --learner-level intermediate
   ```

   This step is explicit and targeted. It only updates the named lesson file. Use `--overwrite` only when regenerating existing notes intentionally. Pass the confirmed learner level so connected-speech and vocabulary notes are selected for that level.

9. Keep generated Library files under the working folder's `materials/<slug>/`. Register each Library item in the working folder registry so the homepage can list multiple Library items:

   ```bash
   python3 scripts/apply_chunks_to_template.py --chunks /Users/daniel/tools/test-lingua-mate/materials/S10E01/chunks.json --media /Users/daniel/tools/test-lingua-mate/materials/S10E01/S10E01.mp4 --lesson-out /Users/daniel/tools/test-lingua-mate/materials/S10E01/lesson.json --lesson-id S10E01 --registry /Users/daniel/tools/test-lingua-mate/registry.json --link-template
   ```

   This updates `/Users/daniel/tools/test-lingua-mate/registry.json`, exposes it as `assets/vite-template/public/data/registry.json`, links the Library item under `assets/vite-template/public/data/lessons/<lesson-id>.json`, and keeps `assets/vite-template/public/data/lesson.json` as the latest Library fallback. `assets/vite-template/public/data/lessons.json` is only a compatibility link to the same registry. Copy or symlink media into `assets/vite-template/public/media/`. Keep media paths relative to the Vite public root, such as `/media/source.mp4`.
10. After final JSON is validated and linked, delete intermediate files unless the user asked to keep them. Remove generated working folders/files such as `ai_batches/`, `ai_filled/`, `.lingua-mate-work/`, extracted `audio.wav`, Whisper scratch output, Bilibili `.m4s` fragments, and youtube-dl partial files. Keep the original media file, final `lesson.json`, `chunks.json` when useful for reruns, transcript exports explicitly requested by the user, and linked template data.
11. Run the generated page:

   ```bash
   pnpm install
   pnpm dev
   ```

For previewing this skill package's bundled template from the repo root, run `pnpm template:install` once and then `pnpm dev`.

## Library JSON Shape

The final `lesson.json` must have:

- `media`: `{ "type": "video" | "audio", "path": string, "duration": number, "title": string }`
- `languages`: `{ "source": string, "target": string }`
- `chunks`: ordered items with `id`, `start`, `end`, `sourceText`, `translation`, `readThrough`, and `vocabulary`

`readThrough` is an array of connected-speech listening notes:

- `original`
- `explanation`

`vocabulary` is an array of concise word and phrase notes:

- `original`
- `explanation`

The working-folder `registry.json` Library index should be:

```json
{
  "lessons": [
    {
      "id": "my-lesson",
      "title": "My Library Item",
      "lessonPath": "/data/lessons/my-lesson.json",
      "mediaType": "video",
      "duration": 123,
      "source": "English",
      "target": "Chinese"
    }
  ]
}
```

## Content Guidance

- Keep translations natural rather than word-for-word when needed.
- Use `readThrough` for connected speech and spoken-listening issues: linking, reductions, weak forms, dropped sounds, stress, contractions, fast-speech phrasing, plus high-frequency spoken habits/fillers/discourse markers that are common in everyday English and can make audio hard to parse.
- Use `vocabulary` for words and phrases: idioms, phrasal verbs, collocations, grammar patterns, advanced words, cultural references, or easily confused phrases. Do not put connected-speech/linking explanations here unless the item is primarily a lexical phrase.
- Match `readThrough` and `vocabulary` note selection to the learner's English level. Beginner learners need more common phrase help; advanced learners need fewer obvious notes and more nuance.
- Keep notes concise and selective. Prefer 0-3 useful entries per section per chunk, with no filler.
- If source and target language are the same, still provide read-through and vocabulary notes.

## Quality Checks

- Confirm every chunk has monotonic timestamps and non-empty source text.
- Confirm generated JSON passes `scripts/validate_lesson.py`.
- For long Library items, generate and merge AI batches instead of placing all content inline in app code.
- Keep default verification fast for generated lessons: check output files exist, inspect/validate JSON, and avoid app-level verification.
- It is okay to run Vite build or start the local dev server when useful, especially after reusable source-code changes or when the user wants to try the generated page.
- Do not open the Codex internal browser after generating a lesson unless the user explicitly asks for browser verification. Browser verification is too time-costly for normal media generation.
- If source code did not change, do not spend time fixing frontend runtime warnings during media generation unless they block the requested lesson output.
