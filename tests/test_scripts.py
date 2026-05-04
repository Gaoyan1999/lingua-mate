import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_media
import validate_lesson
import merge_batches
import split_transcription
import generate_transcript
import translate_chunks_with_codex
import apply_chunks_to_template
import enrich_lesson_with_codex
import fill_lesson_with_codex
import download_bilibili
import download_youtube


class PrepareMediaTests(unittest.TestCase):
    def test_chunk_segments_splits_on_pause(self):
        _, segments = prepare_media.load_whisper_segments(ROOT / "tests" / "fixtures" / "whisper_sample.json")
        chunks = prepare_media.chunk_segments(segments, min_pause=0.7)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["id"], "chunk-0001")
        self.assertIn("Hello everyone", chunks[0]["sourceText"])
        self.assertEqual(chunks[0]["readThrough"], [])
        self.assertEqual(chunks[0]["vocabulary"], [])
        self.assertEqual(chunks[1]["start"], 6.2)

    def test_chunk_segments_caps_sentences_in_long_segment(self):
        segments = [prepare_media.Segment(start=0.0, end=9.0, text="One. Two. Three.")]

        chunks = prepare_media.chunk_segments(segments, max_sentences_per_chunk=2)

        self.assertEqual([chunk["sourceText"] for chunk in chunks], ["One. Two.", "Three."])
        self.assertLessEqual(chunks[0]["end"], chunks[1]["start"])

    def test_chunk_segments_force_splits_inside_long_single_segment(self):
        segments = [
            prepare_media.Segment(
                start=0.0,
                end=25.0,
                text="This is one long transcript segment without sentence punctuation and it should still split",
            )
        ]

        chunks = prepare_media.chunk_segments(segments, max_chunk_duration=10.0)

        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(chunk["end"] - chunk["start"] <= 10.001 for chunk in chunks))

    def test_sentence_splitter_preserves_common_abbreviations(self):
        self.assertEqual(
            prepare_media.split_text_sentences("Mr. Smith leaves at 8 a.m. Sharp. Okay."),
            ["Mr. Smith leaves at 8 a.m. Sharp.", "Okay."],
        )
        self.assertEqual(prepare_media.sentence_count("Mr. Smith leaves at 8 a.m. Sharp. Okay."), 2)

    def test_build_lesson_uses_media_type(self):
        lesson = prepare_media.build_lesson(
            ROOT / "sample.mp3",
            "/media/sample.mp3",
            10.0,
            "English",
            "Chinese",
            [],
        )

        self.assertEqual(lesson["media"]["type"], "audio")
        self.assertEqual(lesson["languages"]["target"], "Chinese")

    def test_translation_queue_shape(self):
        queue = split_transcription.to_translation_queue(
            [
                {
                    "start": 1.25,
                    "end": 3.5,
                    "sourceText": "Hello there.",
                    "translation": "",
                    "readThrough": [],
                    "vocabulary": [],
                }
            ]
        )

        self.assertEqual(
            queue,
            [
                {
                    "timeStart": 1.25,
                    "timeEnd": 3.5,
                    "origin": "Hello there.",
                    "translated": "",
                }
            ],
        )


class ValidateLessonTests(unittest.TestCase):
    def test_valid_lesson_passes(self):
        data = json.loads((ROOT / "tests" / "fixtures" / "lesson.valid.json").read_text())
        self.assertEqual(validate_lesson.validate_lesson(data), [])

    def test_invalid_lesson_fails(self):
        data = json.loads((ROOT / "tests" / "fixtures" / "lesson.invalid.json").read_text())
        errors = validate_lesson.validate_lesson(data)

        self.assertTrue(any("end must be greater" in error for error in errors))
        self.assertTrue(any("sourceText must not be empty" in error for error in errors))

    def test_draft_allows_empty_translation_field(self):
        data = json.loads((ROOT / "tests" / "fixtures" / "lesson.valid.json").read_text())
        data["chunks"][0]["translation"] = ""
        errors = validate_lesson.validate_lesson(data, allow_draft=True)

        self.assertFalse(any("translation must not be empty" in error for error in errors))

    def test_old_note_shapes_fail(self):
        data = json.loads((ROOT / "tests" / "fixtures" / "lesson.valid.json").read_text())
        data["chunks"][0]["readThrough"] = "old read-through"
        data["chunks"][0]["vocabulary"] = [
            {
                "term": "going to",
                "meaning": "将要",
                "nuance": "口语表达",
                "example": "We are going to talk.",
            }
        ]
        errors = validate_lesson.validate_lesson(data, allow_draft=True)

        self.assertTrue(any("$.chunks[0].readThrough must be an array" in error for error in errors))
        self.assertTrue(any("$.chunks[0].vocabulary[0].original must be a string" in error for error in errors))


class MergeBatchTests(unittest.TestCase):
    def test_merge_batches_fills_generated_content(self):
        draft = {
            "chunks": [
                {
                    "id": "chunk-0001",
                    "start": 0,
                    "end": 1,
                    "sourceText": "Hola.",
                    "translation": "",
                    "readThrough": [],
                    "vocabulary": [],
                }
            ]
        }
        filled = {
            "chunks": [
                {
                    "id": "chunk-0001",
                    "translation": "Hello.",
                    "readThrough": [
                        {
                            "original": "Hola",
                            "explanation": "结尾元音在快语速里很短，容易被听轻。",
                        }
                    ],
                    "vocabulary": [
                        {
                            "original": "Hola",
                            "explanation": "常见问候语，相当于 hello。",
                        }
                    ],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            batch_path = Path(temp_dir) / "batch.json"
            batch_path.write_text(json.dumps(filled), encoding="utf-8")
            merged = merge_batches.merge_batches(draft, [batch_path])

        self.assertEqual(merged["chunks"][0]["translation"], "Hello.")
        self.assertEqual(merged["chunks"][0]["readThrough"][0]["original"], "Hola")
        self.assertEqual(merged["chunks"][0]["vocabulary"][0]["original"], "Hola")


class GenerateTranscriptTests(unittest.TestCase):
    def test_timestamp_formats(self):
        self.assertEqual(generate_transcript.timestamp_text(65.4), "00:01:05")
        self.assertEqual(generate_transcript.timestamp_subtitle(65.4), "00:01:05,400")
        self.assertEqual(generate_transcript.timestamp_vtt(65.4), "00:01:05.400")


class TranslateChunksTests(unittest.TestCase):
    def test_apply_translations(self):
        chunks = [{"translated": ""}, {"translated": ""}]
        updated = translate_chunks_with_codex.apply_translations(
            chunks,
            [{"index": 1, "translated": "你好"}],
        )

        self.assertEqual(updated, 1)
        self.assertEqual(chunks[1]["translated"], "你好")


class ApplyChunksToTemplateTests(unittest.TestCase):
    def test_slugify_normalizes_lesson_id(self):
        self.assertEqual(apply_chunks_to_template.slugify("My Library: 01", "fallback"), "my-library-01")
        self.assertEqual(apply_chunks_to_template.slugify("!!!", "fallback"), "fallback")

    def test_update_lesson_index_replaces_existing_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "lessons.json"
            index_path.write_text(
                json.dumps({"lessons": [{"id": "one", "title": "Old", "lessonPath": "/old.json"}]}),
                encoding="utf-8",
            )

            apply_chunks_to_template.update_lesson_index(
                index_path,
                {"id": "one", "title": "New", "lessonPath": "/data/lessons/one.json"},
            )

            data = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(data["lessons"], [{"id": "one", "title": "New", "lessonPath": "/data/lessons/one.json"}])

    def test_update_lesson_registry_seeds_from_existing_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            seed_path = temp_path / "lessons.json"
            registry_path = temp_path / "registry.json"
            seed_path.write_text(
                json.dumps({"lessons": [{"id": "old", "title": "Old", "lessonPath": "/old.json"}]}),
                encoding="utf-8",
            )

            apply_chunks_to_template.update_lesson_registry(
                registry_path,
                {"id": "new", "title": "New", "lessonPath": "/data/lessons/new.json"},
                seed_path=seed_path,
            )

            data = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in data["lessons"]], ["old", "new"])

    def test_default_registry_path_uses_working_folder_root(self):
        lesson_path = Path("/work/test-lingua-mate/materials/s10e01/lesson.json")

        self.assertEqual(
            apply_chunks_to_template.default_registry_path(lesson_path),
            Path("/work/test-lingua-mate/registry.json"),
        )


class EnrichLessonTests(unittest.TestCase):
    def test_build_prompt_includes_learner_level(self):
        prompt = enrich_lesson_with_codex.build_prompt(
            [{"id": "chunk-0001", "sourceText": "He's gonna figure it out.", "translation": "他会想办法。"}],
            {"languages": {"source": "English", "target": "Chinese"}},
            "C1",
        )

        self.assertIn('"learnerLevel": "C1"', prompt)
        self.assertIn("Match note density and difficulty to the learner level", prompt)

    def test_apply_enrichments_fills_missing_notes_and_preserves_existing(self):
        lesson = {
            "chunks": [
                {
                    "id": "chunk-0001",
                    "sourceText": "He's gonna have to figure it out.",
                    "translation": "他得自己想办法弄明白。",
                    "readThrough": [
                        {
                            "original": "He's gonna",
                            "explanation": "已有人工笔记应被保留。",
                        }
                    ],
                    "vocabulary": [],
                }
            ]
        }
        updated = enrich_lesson_with_codex.apply_enrichments(
            lesson,
            [
                {
                    "id": "chunk-0001",
                    "readThrough": [
                        {
                            "original": "have to",
                            "explanation": "模型返回的新连读笔记不应覆盖已有内容。",
                        }
                    ],
                    "vocabulary": [
                        {
                            "original": "figure it out",
                            "explanation": "靠思考或尝试把问题解决、弄懂。",
                        }
                    ],
                }
            ],
        )

        self.assertEqual(updated, 1)
        self.assertEqual(lesson["chunks"][0]["readThrough"][0]["original"], "He's gonna")
        self.assertEqual(lesson["chunks"][0]["vocabulary"][0]["original"], "figure it out")

    def test_apply_enrichments_overwrite_replaces_notes(self):
        lesson = {
            "chunks": [
                {
                    "id": "chunk-0001",
                    "readThrough": [{"original": "old", "explanation": "旧笔记"}],
                    "vocabulary": [{"original": "old vocab", "explanation": "旧词汇"}],
                }
            ]
        }
        updated = enrich_lesson_with_codex.apply_enrichments(
            lesson,
            [
                {
                    "id": "chunk-0001",
                    "readThrough": [{"original": "new", "explanation": "新笔记"}],
                    "vocabulary": [{"original": "new vocab", "explanation": "新词汇"}],
                }
            ],
            overwrite=True,
        )

        self.assertEqual(updated, 2)
        self.assertEqual(lesson["chunks"][0]["readThrough"][0]["original"], "new")
        self.assertEqual(lesson["chunks"][0]["vocabulary"][0]["original"], "new vocab")


class FillLessonTests(unittest.TestCase):
    def test_build_prompt_requires_learner_level_context(self):
        prompt = fill_lesson_with_codex.build_prompt(
            [{"id": "chunk-0001", "sourceText": "He's gonna figure it out."}],
            "B2",
        )

        self.assertIn('"learnerLevel": "B2"', prompt)
        self.assertIn("Match note density and difficulty to the learner level", prompt)
        self.assertIn("He's gonna figure it out.", prompt)

    def test_apply_filled_updates_translation_and_notes(self):
        lesson = {
            "chunks": [
                {
                    "id": "chunk-0001",
                    "sourceText": "He's gonna figure it out.",
                    "translation": "",
                    "readThrough": [],
                    "vocabulary": [],
                }
            ]
        }

        updated = fill_lesson_with_codex.apply_filled(
            lesson,
            [
                {
                    "id": "chunk-0001",
                    "translation": "他会想办法弄明白。",
                    "readThrough": [{"original": "He's gonna", "explanation": "口语里常读成很快的一组音。"}],
                    "vocabulary": [{"original": "figure it out", "explanation": "靠思考或尝试解决问题。"}],
                }
            ],
        )

        self.assertEqual(updated, 1)
        self.assertEqual(lesson["chunks"][0]["translation"], "他会想办法弄明白。")
        self.assertEqual(lesson["chunks"][0]["readThrough"][0]["original"], "He's gonna")
        self.assertEqual(lesson["chunks"][0]["vocabulary"][0]["original"], "figure it out")

    def test_pending_chunks_respects_completed_chunks(self):
        lesson = {
            "chunks": [
                {
                    "id": "chunk-0001",
                    "translation": "完成",
                    "readThrough": [],
                    "vocabulary": [],
                },
                {
                    "id": "chunk-0002",
                    "translation": "",
                    "readThrough": [],
                    "vocabulary": [],
                },
            ]
        }

        pending = fill_lesson_with_codex.pending_chunks(lesson, overwrite=False, limit=None)

        self.assertEqual([chunk["id"] for chunk in pending], ["chunk-0002"])


class DownloadBilibiliTests(unittest.TestCase):
    def test_classify_accepts_concrete_video_url(self):
        parsed = download_bilibili.classify_bilibili_url("https://www.bilibili.com/video/BV1abc12345?p=3")

        self.assertEqual(parsed.video_id, "BV1abc12345")
        self.assertEqual(parsed.page, 3)

    def test_classify_rejects_non_video_url(self):
        with self.assertRaises(ValueError):
            download_bilibili.classify_bilibili_url("https://search.bilibili.com/all?keyword=english")

    def test_extract_page_number_defaults_to_first_page(self):
        self.assertEqual(download_bilibili.extract_page_number("https://www.bilibili.com/video/av123"), 1)
        self.assertEqual(download_bilibili.extract_page_number("https://www.bilibili.com/video/av123?p=bad"), 1)

    def test_sanitize_title_removes_unsafe_characters(self):
        self.assertEqual(download_bilibili.sanitize_title(" Hello / Bili：Video? "), "HelloBiliVideo")
        self.assertEqual(download_bilibili.sanitize_title("???", "fallback"), "fallback")

    def test_select_streams_uses_requested_quality_when_available(self):
        selection = download_bilibili.select_streams(
            {
                "dash": {
                    "video": [
                        {"id": 64, "baseUrl": "https://video-720", "bandwidth": 1},
                        {"id": 80, "baseUrl": "https://video-1080", "bandwidth": 1},
                    ],
                    "audio": [
                        {"id": 30216, "baseUrl": "https://audio-low"},
                        {"id": 30280, "baseUrl": "https://audio-high"},
                    ],
                }
            },
            requested_quality=64,
        )

        self.assertEqual(selection.video_url, "https://video-720")
        self.assertEqual(selection.audio_url, "https://audio-high")
        self.assertEqual(selection.quality, 64)

    def test_select_streams_falls_back_to_best_quality(self):
        selection = download_bilibili.select_streams(
            {
                "dash": {
                    "video": [
                        {"id": 32, "baseUrl": "https://video-480", "bandwidth": 10},
                        {"id": 80, "baseUrl": "https://video-1080", "bandwidth": 1},
                    ],
                    "audio": [{"id": 30216, "baseUrl": "https://audio"}],
                }
            },
            requested_quality=120,
        )

        self.assertEqual(selection.video_url, "https://video-1080")
        self.assertEqual(selection.quality, 80)

    def test_build_ffmpeg_command(self):
        command = download_bilibili.build_ffmpeg_command(
            Path("video.m4s"),
            Path("audio.m4s"),
            Path("out.mp4"),
        )

        self.assertEqual(command, ["ffmpeg", "-y", "-i", "video.m4s", "-i", "audio.m4s", "-c", "copy", "out.mp4"])


class DownloadYouTubeTests(unittest.TestCase):
    def test_classify_accepts_watch_url(self):
        parsed = download_youtube.classify_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=abc")

        self.assertEqual(parsed.video_id, "dQw4w9WgXcQ")

    def test_classify_accepts_short_url(self):
        parsed = download_youtube.classify_youtube_url("https://youtu.be/dQw4w9WgXcQ?t=43")

        self.assertEqual(parsed.video_id, "dQw4w9WgXcQ")

    def test_classify_accepts_shorts_embed_and_live_urls(self):
        self.assertEqual(
            download_youtube.classify_youtube_url("https://www.youtube.com/shorts/dQw4w9WgXcQ").video_id,
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            download_youtube.classify_youtube_url("https://www.youtube.com/embed/dQw4w9WgXcQ").video_id,
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            download_youtube.classify_youtube_url("https://www.youtube.com/live/dQw4w9WgXcQ").video_id,
            "dQw4w9WgXcQ",
        )

    def test_classify_rejects_non_video_url(self):
        with self.assertRaises(ValueError):
            download_youtube.classify_youtube_url("https://www.youtube.com/results?search_query=english")

    def test_sanitize_title_removes_unsafe_characters(self):
        self.assertEqual(download_youtube.sanitize_title(" Hello / YouTube：Video? "), "HelloYouTubeVideo")
        self.assertEqual(download_youtube.sanitize_title("???", "fallback"), "fallback")

    def test_build_ydl_options_uses_single_video_mp4_defaults(self):
        options = download_youtube.build_ydl_options(
            Path("out/%(title)s.%(ext)s"),
            cookies=Path("/tmp/cookies.txt"),
            quiet=True,
            skip_download=True,
        )

        self.assertEqual(options["outtmpl"], "out/%(title)s.%(ext)s")
        self.assertEqual(options["format"], download_youtube.DEFAULT_FORMAT)
        self.assertEqual(options["cookiefile"], "/tmp/cookies.txt")
        self.assertTrue(options["noplaylist"])
        self.assertEqual(options["merge_output_format"], "mp4")
        self.assertTrue(options["quiet"])
        self.assertTrue(options["skip_download"])


if __name__ == "__main__":
    unittest.main()
