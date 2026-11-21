"""Local registry of installed applications."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .atomic import atomic_write_json
from .models import InstalledApp


class InstallRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, InstalledApp]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        records = raw.get("apps", raw) if isinstance(raw, dict) else {}
        result: dict[str, InstalledApp] = {}
        if isinstance(records, dict):
            for key, value in records.items():
                if isinstance(value, dict):
                    record = InstalledApp.from_dict(value)
                    if record.repo:
                        result[record.repo.lower()] = record
        return result

    def save(self, apps: dict[str, InstalledApp]) -> None:
        payload = {
            "schema": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "apps": {key: value.to_dict() for key, value in sorted(apps.items())},
        }
        atomic_write_json(self.path, payload)

    def get(self, repo: str) -> InstalledApp | None:
        return self.load().get(repo.lower())

    def upsert(self, record: InstalledApp) -> None:
        apps = self.load()
        apps[record.repo.lower()] = record
        self.save(apps)

    def remove(self, repo: str) -> None:
        apps = self.load()
        if apps.pop(repo.lower(), None) is not None:
            self.save(apps)
