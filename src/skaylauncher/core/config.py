"""Application settings with a small, explicit JSON schema."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .atomic import atomic_write_json


@dataclass
class Settings:
    language: str = "en"
    theme: str = "midnight"
    include_forks: bool = False
    check_updates_on_start: bool = True
    refresh_minutes: int = 15
    minimize_to_tray: bool = True
    show_notifications: bool = True
    github_token: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Settings:
        known = {field: value for field, value in cls().to_dict().items()}
        known.update({key: value for key, value in data.items() if key in known})
        known["refresh_minutes"] = max(1, min(1440, int(known["refresh_minutes"] or 15)))
        if known["language"] not in {"en", "ru"}:
            known["language"] = "en"
        if known["theme"] not in {"midnight", "graphite", "aurora"}:
            known["theme"] = "midnight"
        return cls(**known)


class SettingsStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return Settings()
        return Settings.from_dict(data if isinstance(data, dict) else {})

    def save(self, settings: Settings) -> None:
        atomic_write_json(self.path, settings.to_dict())

    def update(self, **changes) -> Settings:
        settings = replace(self.load(), **changes)
        self.save(settings)
        return settings
