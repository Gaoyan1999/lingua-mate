# Lingua Mate

Lingua Mate is a Codex skill package that turns an English video or podcast into a local language-learning web page. It creates transcript chunks, Chinese translations, connected-speech notes, and vocabulary notes, then shows them in a local Vite learner app.

Current input support:

- Local video or audio files
- Bilibili video URLs, only concrete `https://www.bilibili.com/video/BV...` or `/video/av...` links

## Recommended Workflow

The most important setup step is to create a separate folder for your learning material. Do not put your videos, generated JSON, or temporary files directly inside this skill project.

For example:

```text
lingua-mate-materials/
  registry.json
  materials/
    my-video/
      my-video.mp4
      chunks.json
      lesson.draft.json
      lesson.json
```

Each video or podcast should get its own folder under `materials/`. Keep the original media file and the generated `lesson.json` together so it is easy to rerun, validate, or add the lesson to the local app later.

## Use It With Codex

The easiest way to use Lingua Mate is to ask Codex to use the `lingua-mate` skill.

For a local file:

```text
Use the lingua-mate skill. I want to learn this local file:
/absolute/path/to/lingua-mate-materials/materials/my-video/my-video.mp4
My English level is intermediate.
```

For a Bilibili video:

```text
Use the lingua-mate skill. I want to learn this Bilibili video:
https://www.bilibili.com/video/BV...
My English level is B1.
Put the material in /absolute/path/to/lingua-mate-materials.
```

Codex will usually:

1. Check whether the source is a local file or a supported Bilibili video link.
2. Ask for your English level if you did not provide it.
3. Download the Bilibili video when needed.
4. Extract audio and transcribe it locally with Whisper.
5. Split the transcript into study chunks.
6. Generate Chinese translations, read-through listening notes, and vocabulary notes.
7. Validate the finished `lesson.json`.
8. Link the lesson into the local Vite app so you can study it in the browser.

Supported level descriptions include `beginner`, `intermediate`, `advanced`, CEFR levels such as `A2`, `B1`, `B2`, `C1`, or a short description like `IELTS 6.5`.

## Requirements

Install these before asking Codex to process media:

- Python 3
- FFmpeg and FFprobe
- A local `whisper` CLI available on `PATH`
- Node.js and pnpm
- Codex CLI

For private or higher-quality Bilibili videos, you may also need a Bilibili `SESSDATA` value. You can pass it in the request or set it in your shell:

```bash
export BILIBILI_SESSDATA="..."
```

Only process media that you have permission to use.

## Generated Files

Generated content is intentionally kept out of source control. A finished material folder should normally keep:

- The original media file
- `chunks.json`
- `lesson.json`

Temporary files such as extracted audio, Whisper scratch files, `ai_batches/`, `ai_filled/`, and Bilibili `.m4s` fragments can be removed after the final `lesson.json` is validated and linked.

The reusable source code for this skill lives in:

- `SKILL.md`
- `scripts/`
- `assets/vite-template/`
- `tests/`

## Development

Run tests:

```bash
pnpm test
```

Build the learner app:

```bash
pnpm build
```
