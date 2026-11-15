"""WSex: Exa search over a saved transcript with durable local context."""

import json
import os
import re
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_json(path, value, keep_backup=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if keep_backup and path.is_file():
        path.with_suffix(path.suffix + ".bak").write_bytes(path.read_bytes())
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


class WSexAgent:
    """Search Exa from the matching transcript text file and save its context."""

    def __init__(self, recordings_dir=None, state_dir=None):
        self.recordings_dir = Path(recordings_dir or ROOT / "recordings")
        self.state_dir = Path(state_dir or ROOT / "wsex" / "data")
        self.searches_dir = self.state_dir / "searches"
        self.context_path = self.state_dir / "context.json"
        self._lock = threading.RLock()

    @staticmethod
    def _valid_id(value):
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, AttributeError, TypeError) as error:
            raise ValueError("Invalid recording or comparison ID.") from error

    def _empty_context(self):
        return {"agent": "WSex", "version": 1, "updated_at": _now(), "active_search_id": None, "searches": []}

    def _load_context(self):
        for candidate in (self.context_path, self.context_path.with_suffix(self.context_path.suffix + ".bak")):
            try:
                context = json.loads(candidate.read_text(encoding="utf-8"))
                if context.get("agent") == "WSex" and isinstance(context.get("searches"), list):
                    return context
            except (OSError, json.JSONDecodeError, AttributeError):
                continue
        return self._empty_context()

    def get_context(self):
        with self._lock:
            return self._load_context()

    def get_search(self, comparison_id):
        safe_id = self._valid_id(comparison_id)
        path = self.searches_dir / f"{safe_id}.json"
        if not path.is_file():
            raise FileNotFoundError("Saved WSex search was not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def search_recording(self, recording_id, comparison_id=None):
        safe_recording_id = self._valid_id(recording_id)
        transcript_path = self.recordings_dir / f"speech-{safe_recording_id}.txt"
        if not transcript_path.is_file():
            raise FileNotFoundError("Save the recording transcript to recordings/ before searching with WSex.")
        transcript = re.sub(r"\s+", " ", transcript_path.read_text(encoding="utf-8")).strip()
        if not transcript:
            raise ValueError("The transcript file is empty. Transcribe the recording before searching.")

        query = transcript[:390].strip()
        api_key = os.environ.get("EXA_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("EXA_API_KEY is not set in the server environment.")
        payload = json.dumps({
            "query": query,
            "type": "auto",
            "numResults": 8,
            "contents": {"highlights": True},
        }).encode("utf-8")
        request = urllib.request.Request(
            "https://api.exa.ai/search",
            data=payload,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Exa returned HTTP {error.code}: {detail[:500]}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Could not reach Exa: {error.reason}") from error

        search_id = self._valid_id(comparison_id) if comparison_id else str(uuid.uuid4())
        results = []
        images = []
        for item in response_data.get("results", [])[:8]:
            highlights = item.get("highlights") or []
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": "\n".join(highlights) if highlights else item.get("summary", "") or item.get("text", "")[:900],
                "score": item.get("score"),
                "published_date": item.get("publishedDate"),
                "favicon": item.get("favicon"),
                "author": item.get("author"),
            })
            if item.get("image"):
                images.append({"url": item["image"], "description": item.get("title", "")})

        result = {
            "id": search_id,
            "comparison_id": search_id,
            "agent": "WSex",
            "recording_id": safe_recording_id,
            "transcript_file": transcript_path.name,
            "query": query,
            "created_at": _now(),
            "request_id": response_data.get("requestId"),
            "answer": response_data.get("output", {}).get("content", "") if isinstance(response_data.get("output"), dict) else "",
            "results": results,
            "images": images,
        }
        with self._lock:
            self.searches_dir.mkdir(parents=True, exist_ok=True)
            _atomic_json(self.searches_dir / f"{search_id}.json", result)
            context = self._load_context()
            history = [item for item in context["searches"] if item.get("id") != search_id]
            history.append({
                "id": search_id,
                "comparison_id": search_id,
                "recording_id": safe_recording_id,
                "transcript_file": transcript_path.name,
                "transcript": transcript[:2000],
                "query": query,
                "created_at": result["created_at"],
                "answer": result["answer"],
                "result_count": len(results),
                "image_count": len(images),
                "source_urls": [item["url"] for item in results if item.get("url")],
            })
            context.update({"agent": "WSex", "version": 1, "updated_at": _now(), "active_search_id": search_id, "searches": history[-100:]})
            _atomic_json(self.context_path, context, keep_backup=True)
        return result


agent = WSexAgent()
