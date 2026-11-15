import os
import uuid
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from wsex.agent import WSexAgent


class WSexAgentTests(unittest.TestCase):
    def test_reads_transcript_searches_exa_and_saves_context(self):
        recording_id = str(uuid.uuid4())
        comparison_id = str(uuid.uuid4())
        api_response = SimpleNamespace(
            request_id="exa-request-1",
            results=[SimpleNamespace(
                title="A source",
                url="https://example.com",
                highlights=["Relevant excerpt."],
                image="https://example.com/image.jpg",
                published_date="2026-01-01T00:00:00Z",
                score=0.9,
            )],
        )
        query = "companies selling AI voice agents to dental practices"
        with TemporaryDirectory() as directory:
            recordings = os.path.join(directory, "recordings")
            state = os.path.join(directory, "wsex")
            os.makedirs(recordings)
            with open(os.path.join(recordings, f"speech-{recording_id}.txt"), "w", encoding="utf-8") as transcript:
                transcript.write(query)
            agent = WSexAgent(recordings_dir=recordings, state_dir=state)

            with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), patch("wsex.agent.Exa") as mocked_exa:
                mocked_exa.return_value.search.return_value = api_response
                search = agent.search_recording(recording_id, comparison_id)

            mocked_exa.assert_called_once_with()
            mocked_exa.return_value.search.assert_called_once_with(query, contents={"highlights": True})
            self.assertEqual(search["id"], comparison_id)
            self.assertEqual(search["query"], query)
            self.assertEqual(search["results"][0]["content"], "Relevant excerpt.")
            self.assertEqual(search["results"][0]["title"], "A source")
            self.assertEqual(search["results"][0]["url"], "https://example.com")
            self.assertEqual(search["images"][0]["url"], "https://example.com/image.jpg")

            restored = WSexAgent(recordings_dir=recordings, state_dir=state)
            context = restored.get_context()
            self.assertEqual(context["active_search_id"], comparison_id)
            self.assertEqual(restored.get_search(comparison_id)["request_id"], "exa-request-1")

    def test_reports_exa_credit_limit_clearly(self):
        recording_id = str(uuid.uuid4())
        with TemporaryDirectory() as directory:
            recordings = os.path.join(directory, "recordings")
            os.makedirs(recordings)
            with open(os.path.join(recordings, f"speech-{recording_id}.txt"), "w", encoding="utf-8") as transcript:
                transcript.write("A harmless test query")
            agent = WSexAgent(recordings_dir=recordings, state_dir=os.path.join(directory, "wsex"))
            with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), patch(
                "wsex.agent.Exa"
            ) as mocked_exa:
                mocked_exa.return_value.search.side_effect = ValueError(
                    'Request failed with status code 402: {"error":"credit limit","tag":"NO_MORE_CREDITS"}'
                )
                with self.assertRaisesRegex(RuntimeError, "no remaining API credits"):
                    agent.search_recording(recording_id)


if __name__ == "__main__":
    unittest.main()
