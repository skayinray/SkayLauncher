"""Persistent HTTP cache with ETag support for GitHub responses."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.atomic import atomic_write_json


@dataclass
class CachedResponse:
    body: Any
    etag: str = ""
    stored_at: float = 0.0

    def is_fresh(self, max_age: float) -> bool:
        return time.time() - self.stored_at < max_age


class ResponseCache:
    def __init__(self, path: str | Path, max_age: float = 300.0) -> None:
        self.path = Path(path)
        self.max_age = max_age
        self._entries: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        entries = data.get("entries", {}) if isinstance(data, dict) else {}
        return entries if isinstance(entries, dict) else {}

    def flush(self) -> None:
        atomic_write_json(self.path, {"schema": 1, "entries": self._entries})

    def get(self, key: str) -> CachedResponse | None:
        entry = self._entries.get(key)
        if not isinstance(entry, dict) or "body" not in entry:
            return None
        return CachedResponse(
            body=entry["body"],
            etag=str(entry.get("etag") or ""),
            stored_at=float(entry.get("stored_at") or 0.0),
        )

    def put(self, key: str, body: Any, etag: str = "") -> CachedResponse:
        entry = {"body": body, "etag": etag, "stored_at": time.time()}
        self._entries[key] = entry
        self.flush()
        return CachedResponse(body=body, etag=etag, stored_at=entry["stored_at"])

    def fresh(self, key: str) -> CachedResponse | None:
        cached = self.get(key)
        return cached if cached and cached.is_fresh(self.max_age) else None
