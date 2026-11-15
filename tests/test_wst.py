import json
import os
import uuid
import unittest
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from wst.agent import WSTAgent


class WSTAgentTests(unittest.TestCase):
    def test_reads_transcript_searches_web_and_images_and_persists_context(self):
        recording_id = str(uuid.uuid4())
        comparison_id = str(uuid.uuid4())
        api_response = {
            "request_id": "request-1",
            "answer": "A concise research summary.",
            "results": [{"title": "A source", "url": "https://example.com", "content": "Useful details", "score": 0.9}],
            "images": [{"url": "https://example.com/image.jpg", "description": "An image result"}],
        }
        with TemporaryDirectory() as directory:
            recordings = os.path.join(directory, "recordings")
            state = os.path.join(directory, "wst")
            os.makedirs(recordings)
            transcript_path = os.path.join(recordings, f"speech-{recording_id}.txt")
            with open(transcript_path, "w", encoding="utf-8") as transcript_file:
                transcript_file.write("Explain how city gardens help pollinators.")
            agent = WSTAgent(recordings_dir=recordings, state_dir=state)

            with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}), patch(
                "wst.agent.urllib.request.urlopen", return_value=BytesIO(json.dumps(api_response).encode("utf-8"))
            ) as mocked_request:
                search = agent.search_recording(recording_id, comparison_id)

            request = mocked_request.call_args.args[0]
            request_body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(request_body["query"], "Explain how city gardens help pollinators.")
            self.assertTrue(request_body["include_images"])
            self.assertEqual(search["transcript_file"], f"speech-{recording_id}.txt")
            self.assertEqual(search["id"], comparison_id)
            self.assertEqual(len(search["images"]), 1)
            self.assertEqual(len(search["results"]), 1)

            restored = WSTAgent(recordings_dir=recordings, state_dir=state)
            context = restored.get_context()
            self.assertEqual(context["active_search_id"], search["id"])
            self.assertEqual(context["searches"][0]["query"], request_body["query"])
            self.assertEqual(restored.get_search(search["id"])["answer"], "A concise research summary.")


if __name__ == "__main__":
    unittest.main()
