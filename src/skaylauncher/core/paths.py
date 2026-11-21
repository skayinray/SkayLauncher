"""Cross-platform paths for configuration, data, caches and installs."""

from __future__ import annotations

import os
from pathlib import Path


class PathManager:
    def __init__(self, app_name: str = "SkayLauncher", base_dir: str | Path | None = None) -> None:
        self.app_name = app_name
        override = os.environ.get("SKAYLAUNCHER_HOME")
        self.base_dir = Path(override) if override else Path(base_dir) if base_dir else self._default_base()
        self.ensure_dirs()

    def _default_base(self) -> Path:
        if os.name == "nt":
            root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
            return root / self.app_name
        xdg_data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return Path(xdg_data) / self.app_name

    @property
    def config_dir(self) -> Path:
        if os.name == "nt":
            return self.base_dir / "Config"
        return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / self.app_name

    @property
    def cache_dir(self) -> Path:
        if os.name == "nt":
            return self.base_dir / "Cache"
        return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / self.app_name

    @property
    def data_dir(self) -> Path:
        return self.base_dir

    @property
    def apps_dir(self) -> Path:
        return self.data_dir / "apps"

    @property
    def downloads_dir(self) -> Path:
        return self.cache_dir / "downloads"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.cache_dir / "logs"

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def apps_file(self) -> Path:
        return self.data_dir / "apps.json"

    @property
    def api_cache_file(self) -> Path:
        return self.cache_dir / "github-cache.json"

    @property
    def known_repos_file(self) -> Path:
        return self.data_dir / "known-repos.json"

    @property
    def ignored_apps_file(self) -> Path:
        return self.data_dir / "ignored-apps.json"

    def ensure_dirs(self) -> None:
        for directory in (
            self.config_dir,
            self.data_dir,
            self.cache_dir,
            self.apps_dir,
            self.downloads_dir,
            self.backups_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def app_install_dir(self, repo: str, version: str) -> Path:
        return self.apps_dir / slugify(repo) / slugify(version)

    def app_staging_dir(self, repo: str, version: str) -> Path:
        return self.downloads_dir / f"stage-{slugify(repo)}-{slugify(version)}"


def slugify(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_." else "-" for char in value)
    return cleaned.strip("-.") or "unknown"
