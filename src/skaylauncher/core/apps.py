"""Local registry of installed applications."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

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

    def sync_discovered(self, found: Iterable[InstalledApp]) -> None:
        """Merge freshly discovered external installs, preserving managed ones.

        Records marked as ``discovered`` are owned by the discovery scanner. They
        are replaced when found again and dropped when the executable disappears.
        Applications installed by the launcher always take precedence.
        """

        previous = self.load()
        apps = dict(previous)
        found_by_repo = {record.repo.lower(): record for record in found if record.repo}
        for key, record in list(apps.items()):
            if record.discovered and key not in found_by_repo:
                apps.pop(key, None)
        for key, record in found_by_repo.items():
            if key not in apps or apps[key].discovered:
                apps[key] = record
        if apps != previous:
            self.save(apps)
