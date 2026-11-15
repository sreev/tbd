"""WSex: Exa search over a saved transcript with durable local context."""

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from exa_py import Exa


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
        try:
            exa = Exa()
            response_data = exa.search(query, contents={"highlights": True})
        except Exception as error:
            detail = str(error)
            if "NO_MORE_CREDITS" in detail or "status code 402" in detail:
                raise RuntimeError("Exa has no remaining API credits. Add credits to the Exa account, then retry the search.") from error
            raise RuntimeError(f"Exa search failed: {detail}") from error

        search_id = self._valid_id(comparison_id) if comparison_id else str(uuid.uuid4())
        results = []
        images = []
        for item in getattr(response_data, "results", []) or []:
            highlights = getattr(item, "highlights", None) or []
            if isinstance(highlights, str):
                highlights = [highlights]
            title = getattr(item, "title", "") or ""
            url = getattr(item, "url", "") or ""
            summary = getattr(item, "summary", "") or ""
            text_content = getattr(item, "text", "") or ""
            results.append({
                "title": title,
                "url": url,
                "content": "\n".join(str(value) for value in highlights) if highlights else (summary or text_content[:900]),
                "score": getattr(item, "score", None),
                "published_date": getattr(item, "published_date", None),
                "favicon": getattr(item, "favicon", None),
                "author": getattr(item, "author", None),
            })
            image = getattr(item, "image", None)
            if image:
                images.append({"url": image, "description": title})

        result = {
            "id": search_id,
            "comparison_id": search_id,
            "agent": "WSex",
            "recording_id": safe_recording_id,
            "transcript_file": transcript_path.name,
            "query": query,
            "created_at": _now(),
            "request_id": getattr(response_data, "request_id", None),
            "answer": getattr(response_data, "answer", "") or "",
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
