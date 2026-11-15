# Spch2Txt

Spch2Txt records from your microphone, saves each recording and its transcript in both browser IndexedDB and the local `recordings/` folder, and uses Cartesia for speech-to-text. The paired files share a name, such as `speech-<id>.webm` and `speech-<id>.txt`. Recordings can be played, downloaded, copied, or deleted. Saved recordings with empty transcripts can be transcribed again from the library.

## Run locally

Microphone access requires localhost or HTTPS. From the repository root, start a static server:

```sh
python3 -m venv .venv
source .venv/bin/activate
export CARTESIA_API_KEY="your-cartesia-api-key"
export TAVILY_API_KEY="your-tavily-api-key"
export EXA_API_KEY="your-exa-api-key"
python server.py
```

Set `CARTESIA_API_KEY` in the environment before starting the server. The server uses only Python's standard library; no Python packages need to be installed. Keep the API key on the server and do not put it in browser code. `.env` files are ignored by Git if you choose to load the key through a local environment tool.

Open <http://localhost:8000> in Chrome or Edge, allow microphone access, choose a language, and press **Start recording**. Press **Stop & save** when you finish. The audio is saved locally, sent to Cartesia, and the returned transcript is saved alongside it. `.gitignore` excludes recording files and both agents' search data because they can contain personal speech and transcript content.

Cartesia's `ink-whisper` batch API accepts audio recordings including WebM and returns the complete transcript. The local server keeps the API key out of the browser.

## Search agents

Choose either **Explore with WST** or **Explore with WSex** on a saved transcript. Both agents run in parallel from the same `.txt` file and show provider results side by side: WST uses Tavily; WSex uses Exa. Each result set is saved under its provider's `data/searches/` folder, with a shared comparison ID. Their `context.json` files retain the latest 100 queries, transcript references, summaries, source links, and active search; context restores when the app or server restarts.

The transcript text is sent to both Tavily and Exa only when you click either search button. Audio is sent to Cartesia after each recording to transcribe it.

## Test

```sh
npm test
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```
