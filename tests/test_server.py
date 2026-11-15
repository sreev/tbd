import unittest
import uuid
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path

import server
from server import build_multipart


class MultipartRequestTests(unittest.TestCase):
    def test_builds_multipart_with_audio_model_and_language(self):
        audio = b"example webm bytes"
        boundary, body = build_multipart(audio, "audio/webm;codecs=opus", "en", "fixed-boundary")

        self.assertEqual(boundary, b"fixed-boundary")
        self.assertIn(b'name="file"; filename="speech.webm"', body)
        self.assertIn(b"Content-Type: audio/webm", body)
        self.assertIn(audio, body)
        self.assertIn(b'name="model"\r\n\r\nink-whisper', body)
        self.assertIn(b'name="language"\r\n\r\nen', body)
        self.assertTrue(body.endswith(b"--fixed-boundary--\r\n"))

    def test_saves_audio_and_transcript_with_matching_names(self):
        recording_id = str(uuid.uuid4())
        with TemporaryDirectory() as directory:
            with patch.object(server, "RECORDINGS_DIR", Path(directory)):
                files = server.save_recording_pair(recording_id, b"audio bytes", "audio/webm;codecs=opus", "A test transcript.")
                root = Path(directory)
                audio_path = root / files["audio_file"]
                transcript_path = root / files["transcript_file"]

                self.assertEqual(audio_path.stem, transcript_path.stem)
                self.assertEqual(audio_path.read_bytes(), b"audio bytes")
                self.assertEqual(transcript_path.read_text(encoding="utf-8"), "A test transcript.")

    def test_saves_transcript_against_existing_audio(self):
        recording_id = str(uuid.uuid4())
        with TemporaryDirectory() as directory:
            with patch.object(server, "RECORDINGS_DIR", Path(directory)):
                server.save_recording_pair(recording_id, b"audio bytes", "audio/webm", "")
                filename = server.save_transcript_file(recording_id, "Recovered transcript.")
                transcript_path = Path(directory) / filename
                self.assertEqual(transcript_path.read_text(encoding="utf-8"), "Recovered transcript.")


if __name__ == "__main__":
    unittest.main()
