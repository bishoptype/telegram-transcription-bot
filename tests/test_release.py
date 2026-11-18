import html
import os
import re
import runpy
import unittest
from pathlib import Path
from unittest.mock import call, patch

from text_utils import create_transcription_txt, split_text_into_chunks


class ConfigTests(unittest.TestCase):
    def load_config(self, allowed_users):
        settings = {
            "BOT_TOKEN": "123456:example",
            "PYTHON_DOTENV_DISABLED": "1",
            "ALLOWED_USERS": allowed_users,
            "WHISPER_DEVICE": "cpu",
        }
        with patch.dict(os.environ, settings, clear=True):
            return runpy.run_path(str(Path(__file__).resolve().parents[1] / "config.py"))

    def test_cpu_uses_int8_by_default(self):
        self.assertEqual(self.load_config("")["WHISPER_COMPUTE_TYPE"], "int8")

    def test_allowlist_keeps_access_restricted(self):
        allowed = self.load_config("42, 73,")["is_user_allowed"]
        self.assertTrue(allowed(42))
        self.assertFalse(allowed(99))

    def test_invalid_allowlist_raises(self):
        for value in ("oops", "42,oops", ",,", "0"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "ALLOWED_USERS"):
                self.load_config(value)


class CudaFallbackTests(unittest.TestCase):
    def test_retries_on_cpu_after_lazy_cuda_library_error(self):
        settings = {
            "BOT_TOKEN": "123456:example",
            "PYTHON_DOTENV_DISABLED": "1",
            "WHISPER_DEVICE": "cpu",
        }
        with patch.dict(os.environ, settings):
            import transcriber

        gpu_model, cpu_model = object(), object()
        result = {"full_text": "Привет"}
        with (
            patch.object(transcriber.config, "WHISPER_DEVICE", "cuda"),
            patch.object(transcriber, "WhisperModel", side_effect=[gpu_model, cpu_model]) as load,
            patch.object(
                transcriber.WhisperService,
                "_transcribe",
                side_effect=[RuntimeError("Library cublas64_12.dll is not found"), result],
            ) as transcribe,
        ):
            service = transcriber.WhisperService()
            self.assertEqual(service.transcribe_sync("audio.wav"), result)
            self.assertEqual(service.device, "cpu")
            self.assertEqual(service.compute_type, "int8")
            self.assertEqual(load.call_count, 2)
            transcribe.assert_has_calls(
                [call(gpu_model, "audio.wav", None), call(cpu_model, "audio.wav", None)]
            )


class TextTests(unittest.TestCase):
    def test_preserves_paragraphs_and_escapes_html(self):
        text = "abc\ndef <x> ghi"
        chunks = split_text_into_chunks(text, max_chunk_size=8)
        self.assertEqual(chunks[0].split("<pre>")[1], "abc</pre>")
        self.assertIn("&lt;x&gt;", chunks[1])
        self.assertEqual(len(chunks), 3)

    def test_splits_long_unbroken_words(self):
        text = "я" * 8500
        chunks = split_text_into_chunks(text)
        pieces = [html.unescape(re.search(r"<pre>(.+)</pre>", chunk)[1]) for chunk in chunks]
        self.assertEqual([len(piece) for piece in pieces], [3800, 3800, 900])
        self.assertEqual("".join(pieces), text)

    def test_transcript_contains_timestamps_and_text(self):
        transcript = create_transcription_txt(
            "голос.ogg", 3.0, "ru", "Привет", [{"start": 1.0, "end": 2.0, "text": "Привет"}]
        )
        self.assertIn("голос.ogg", transcript)
        self.assertIn("[00:01 -> 00:02] Привет", transcript)
