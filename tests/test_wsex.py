import json
import os
import uuid
import unittest
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from wsex.agent import WSexAgent


class WSexAgentTests(unittest.TestCase):
    def test_reads_transcript_searches_exa_and_saves_context(self):
        recording_id = str(uuid.uuid4())
        comparison_id = str(uuid.uuid4())
        api_response = {
            "requestId": "exa-request-1",
            "results": [{
                "title": "A source",
                "url": "https://example.com",
                "highlights": ["Relevant excerpt."],
                "image": "https://example.com/image.jpg",
                "publishedDate": "2026-01-01T00:00:00Z",
            }],
        }
        with TemporaryDirectory() as directory:
            recordings = os.path.join(directory, "recordings")
            state = os.path.join(directory, "wsex")
            os.makedirs(recordings)
            with open(os.path.join(recordings, f"speech-{recording_id}.txt"), "w", encoding="utf-8") as transcript:
                transcript.write("Find reliable research on urban pollinator gardens.")
            agent = WSexAgent(recordings_dir=recordings, state_dir=state)

            with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), patch(
                "wsex.agent.urllib.request.urlopen", return_value=BytesIO(json.dumps(api_response).encode("utf-8"))
            ) as mocked_request:
                search = agent.search_recording(recording_id, comparison_id)

            request = mocked_request.call_args.args[0]
            request_body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(request.headers["X-api-key"], "test-key")
            self.assertEqual(request_body["query"], "Find reliable research on urban pollinator gardens.")
            self.assertTrue(request_body["contents"]["highlights"])
            self.assertEqual(search["id"], comparison_id)
            self.assertEqual(search["results"][0]["content"], "Relevant excerpt.")
            self.assertEqual(search["images"][0]["url"], "https://example.com/image.jpg")

            restored = WSexAgent(recordings_dir=recordings, state_dir=state)
            context = restored.get_context()
            self.assertEqual(context["active_search_id"], comparison_id)
            self.assertEqual(restored.get_search(comparison_id)["request_id"], "exa-request-1")


if __name__ == "__main__":
    unittest.main()
