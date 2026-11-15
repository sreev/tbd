"""Local Spch2Txt server and Cartesia batch transcription proxy."""

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from wst.agent import agent as WST_AGENT
from wsex.agent import agent as WSEX_AGENT


ROOT = Path(__file__).resolve().parent
RECORDINGS_DIR = ROOT / "recordings"
CARTESIA_URL = "https://api.cartesia.ai/stt"
CARTESIA_VERSION = "2026-08-14"
MAX_AUDIO_BYTES = 24 * 1024 * 1024
LANGUAGES = {"en", "es", "fr", "de", "hi", "ja"}
RECORDING_EXTENSIONS = {"audio/webm": "webm", "audio/mp4": "mp4", "audio/ogg": "ogg", "audio/wav": "wav"}


def _safe_recording_id(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError("Invalid recording ID.") from error


def _write_atomically(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if isinstance(data, bytes):
        temporary.write_bytes(data)
    else:
        temporary.write_text(data, encoding="utf-8")
    os.replace(temporary, path)


def save_recording_pair(recording_id, audio, mime_type, transcript=""):
    safe_id = _safe_recording_id(recording_id)
    media_type = (mime_type or "").split(";", 1)[0].strip().lower()
    extension = RECORDING_EXTENSIONS.get(media_type, "audio")
    base_name = f"speech-{safe_id}"
    audio_path = RECORDINGS_DIR / f"{base_name}.{extension}"
    transcript_path = RECORDINGS_DIR / f"{base_name}.txt"
    _write_atomically(audio_path, audio)
    _write_atomically(transcript_path, transcript or "")
    return {"base_name": base_name, "audio_file": audio_path.name, "transcript_file": transcript_path.name}


def save_transcript_file(recording_id, transcript):
    safe_id = _safe_recording_id(recording_id)
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    audio_paths = [RECORDINGS_DIR / f"speech-{safe_id}.{extension}" for extension in (*RECORDING_EXTENSIONS.values(), "audio")]
    if not any(path.is_file() for path in audio_paths):
        raise FileNotFoundError("Save the audio recording to recordings/ before saving its transcript.")
    transcript_path = RECORDINGS_DIR / f"speech-{safe_id}.txt"
    _write_atomically(transcript_path, transcript or "")
    return transcript_path.name


def delete_recording_pair(recording_id):
    safe_id = _safe_recording_id(recording_id)
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    base = RECORDINGS_DIR / f"speech-{safe_id}"
    for extension in (*RECORDING_EXTENSIONS.values(), "audio", "txt"):
        path = base.with_suffix(f".{extension}")
        if path.is_file():
            path.unlink()


def build_multipart(audio, mime_type, language, boundary=None):
    """Build Cartesia's documented multipart batch STT request body."""
    boundary = boundary or uuid.uuid4().hex
    media_type = (mime_type or "").split(";", 1)[0].strip().lower()
    safe_mime = media_type if re.fullmatch(r"audio/[\w.+-]+", media_type) else "application/octet-stream"
    extension = {"audio/webm": "webm", "audio/mp4": "mp4", "audio/ogg": "ogg", "audio/wav": "wav"}.get(safe_mime, "audio")
    filename = f"speech.{extension}"
    marker = boundary.encode("ascii")
    chunks = [
        b"--" + marker + b"\r\n",
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {safe_mime}\r\n\r\n".encode(),
        audio,
        b"\r\n--" + marker + b"\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nink-whisper\r\n",
        b"--" + marker + b"\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\n" + language.encode("ascii") + b"\r\n",
        b"--" + marker + b"--\r\n",
    ]
    return marker, b"".join(chunks)


def transcribe_with_cartesia(audio, mime_type, language):
    api_key = os.environ.get("CARTESIA_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CARTESIA_API_KEY is not set. Add your Cartesia API key to the server environment and restart Spch2Txt.")

    boundary, body = build_multipart(audio, mime_type, language)
    request = urllib.request.Request(
        CARTESIA_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Cartesia-Version": CARTESIA_VERSION,
            "Content-Type": f"multipart/form-data; boundary={boundary.decode('ascii')}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cartesia returned HTTP {error.code}: {detail[:500]}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach Cartesia: {error.reason}") from error

    text = result.get("text")
    if not isinstance(text, str):
        raise RuntimeError("Cartesia returned a response without transcript text.")
    return text


class Spch2TxtHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        # Keep local request logs free of request headers and audio payloads.
        super().log_message(format, *args)

    def do_POST(self):
        if self.path not in {"/api/transcribe", "/api/recordings/save", "/api/recordings/transcript", "/api/wst/search", "/api/search/both"}:
            self.send_error(404)
            return

        try:
            payload = self._read_json(MAX_AUDIO_BYTES * 2 + 64_000)
            if self.path == "/api/search/both":
                recording_id = payload.get("recordingId", "")
                comparison_id = str(uuid.uuid4())

                def run(agent):
                    try:
                        return agent.search_recording(recording_id, comparison_id)
                    except Exception as error:
                        return {"error": str(error)}

                with ThreadPoolExecutor(max_workers=2) as pool:
                    wst_future = pool.submit(run, WST_AGENT)
                    wsex_future = pool.submit(run, WSEX_AGENT)
                    wst_result, wsex_result = wst_future.result(), wsex_future.result()
                if "error" in wst_result and "error" in wsex_result:
                    self._send_json(502, {"comparison_id": comparison_id, "wst": wst_result, "wsex": wsex_result})
                else:
                    self._send_json(200, {"comparison_id": comparison_id, "wst": wst_result, "wsex": wsex_result})
                return
            if self.path == "/api/wst/search":
                result = WST_AGENT.search_recording(payload.get("recordingId", ""))
                self._send_json(200, result)
                return
            if self.path == "/api/recordings/transcript":
                filename = save_transcript_file(payload.get("recordingId", ""), str(payload.get("transcript", "")))
                self._send_json(200, {"transcript_file": filename})
                return

            audio = base64.b64decode(payload.get("audioBase64", ""), validate=True)
            if not audio or len(audio) > MAX_AUDIO_BYTES:
                raise ValueError("Recording is empty or too large (maximum 24 MB).")
            mime_type = str(payload.get("mimeType", "audio/webm"))
            if self.path == "/api/recordings/save":
                files = save_recording_pair(payload.get("recordingId", ""), audio, mime_type, str(payload.get("transcript", "")))
                self._send_json(200, files)
                return
            language = str(payload.get("language", "en")).split("-")[0].lower()
            if language not in LANGUAGES:
                language = "en"
            transcript = transcribe_with_cartesia(audio, mime_type, language)
            self._send_json(200, {"text": transcript})
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": str(error)})
        except FileNotFoundError as error:
            self._send_json(404, {"error": str(error)})
        except RuntimeError as error:
            self._send_json(502, {"error": str(error)})
        except Exception:
            self._send_json(500, {"error": "Unexpected transcription server error."})

    def do_GET(self):
        if self.path == "/api/search/context":
            wst_context, wsex_context = WST_AGENT.get_context(), WSEX_AGENT.get_context()
            self._send_json(200, {
                "wst": wst_context,
                "wsex": wsex_context,
                "providers": {
                    "wst": bool(os.environ.get("TAVILY_API_KEY", "").strip()),
                    "wsex": bool(os.environ.get("EXA_API_KEY", "").strip()),
                },
            })
            return
        if self.path.startswith("/api/search/both/"):
            comparison_id = self.path.removeprefix("/api/search/both/").split("?", 1)[0]
            result = {"comparison_id": comparison_id}
            for name, agent in (("wst", WST_AGENT), ("wsex", WSEX_AGENT)):
                try:
                    result[name] = agent.get_search(comparison_id)
                except (ValueError, FileNotFoundError) as error:
                    result[f"{name}_error"] = str(error)
            self._send_json(200, result)
            return
        if self.path == "/api/wst/context":
            self._send_json(200, WST_AGENT.get_context())
            return
        if self.path.startswith("/api/wst/search/"):
            try:
                search_id = self.path.removeprefix("/api/wst/search/").split("?", 1)[0]
                self._send_json(200, WST_AGENT.get_search(search_id))
            except (ValueError, FileNotFoundError) as error:
                self._send_json(404, {"error": str(error)})
            except Exception:
                self._send_json(500, {"error": "Could not read saved WST search."})
            return
        super().do_GET()

    def do_DELETE(self):
        if not self.path.startswith("/api/recordings/"):
            self.send_error(404)
            return
        try:
            recording_id = self.path.removeprefix("/api/recordings/").split("?", 1)[0]
            delete_recording_pair(recording_id)
            self._send_json(200, {"deleted": True})
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
        except Exception:
            self._send_json(500, {"error": "Could not delete recording files."})

    def _read_json(self, maximum):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > maximum:
            raise ValueError("Request is empty or too large.")
        return json.loads(self.rfile.read(content_length))

    def _send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_head(self):
        path = self.translate_path(self.path)
        relative = Path(path).resolve().relative_to(ROOT)
        if any(part.startswith(".") or part in {"tests", "agent", "recordings", "wst", "wsex"} for part in relative.parts):
            self.send_error(404)
            return None
        if relative.suffix in {".py", ".toml"} or relative.name in {"README.md", "AGENTS.md", "WORK_LOG_2026-11-14.md", "package.json"}:
            self.send_error(404)
            return None
        return super().send_head()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Spch2TxtHandler)
    print("Spch2Txt listening on http://127.0.0.1:8000", flush=True)
    server.serve_forever()
