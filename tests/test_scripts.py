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


class PrepareMediaTests(unittest.TestCase):
    def test_chunk_segments_splits_on_pause(self):
        _, segments = prepare_media.load_whisper_segments(ROOT / "tests" / "fixtures" / "whisper_sample.json")
        chunks = prepare_media.chunk_segments(segments, min_pause=0.7)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["id"], "chunk-0001")
        self.assertIn("Hello everyone", chunks[0]["sourceText"])
        self.assertEqual(chunks[1]["start"], 6.2)

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
                    "readThrough": "",
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

    def test_draft_allows_empty_translation_fields(self):
        data = json.loads((ROOT / "tests" / "fixtures" / "lesson.invalid.json").read_text())
        errors = validate_lesson.validate_lesson(data, allow_draft=True)

        self.assertFalse(any("translation must not be empty" in error for error in errors))
        self.assertFalse(any("readThrough must not be empty" in error for error in errors))


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
                    "readThrough": "",
                    "vocabulary": [],
                }
            ]
        }
        filled = {
            "chunks": [
                {
                    "id": "chunk-0001",
                    "translation": "Hello.",
                    "readThrough": "A greeting.",
                    "vocabulary": [
                        {
                            "term": "Hola",
                            "meaning": "Hello",
                            "nuance": "Common greeting.",
                            "example": "Hola, Maria.",
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
        self.assertEqual(merged["chunks"][0]["vocabulary"][0]["term"], "Hola")


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


if __name__ == "__main__":
    unittest.main()
