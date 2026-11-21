"""Detection of applications installed outside the launcher's own registry.

The launcher can only manage what it knows about. Many users download release
assets manually (for example AppImageLauncher puts AppImages in ``~/Applications``),
so this scanner recognises those files, maps them to GitHub repositories and
registers them as discovered installs. Discovered records never delete external
files on uninstall.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .atomic import atomic_write_json
from .models import InstalledApp, PlatformInfo, Repository

_HASH_SUFFIX = re.compile(r"_([0-9a-fA-F]{16,64})$")
_ARCH_TOKEN = re.compile(
    r"[-_](?:x86_64|amd64|x64|aarch64|arm64|i686|linux|linux64|win64|win32|windows|macos|osx|universal)(?=[-_.]|$)",
    re.IGNORECASE,
)
_VERSION = re.compile(r"(?<!\d)(\d+(?:\.\d+){1,3})(?!\d)")
_SEPARATORS = re.compile(r"[-_.]+")
_NON_ALNUM = re.compile(r"[^a-z0-9]")

_EXCLUDED = {"skaylauncher", "launcher"}
_ALIASES = {
    "chess": "chess.skay",
    "chessskay": "chess.skay",
    "steamsnm": "SteamSNM",
    "skaycleartux": "SkayClearTux",
    "hackmeskay": "hackmeskay",
}

_LINUX_EXECUTABLE_SUFFIXES = {".appimage"}
_WINDOWS_EXECUTABLE_SUFFIXES = {".exe"}
_MACOS_BUNDLE_SUFFIXES = {".app"}


def normalize_name(value: str) -> str:
    """Return a comparison key that ignores case, punctuation and spaces."""

    return _NON_ALNUM.sub("", value.casefold())


def load_ignored(path: Path) -> set[str]:
    """Load repository names the user chose to forget in the launcher."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(payload, list):
        return set()
    return {str(item).lower() for item in payload}


def save_ignored(path: Path, names: Iterable[str]) -> None:
    atomic_write_json(path, sorted({name.lower() for name in names}))


def parse_asset_name(name: str) -> tuple[str, str]:
    """Extract a repository base name and version from a downloaded asset name.

    Handles plain names (``SteamSNM.exe``), AppImageLauncher names
    (``SkayClearTux-1.5.3.2-x86_64_<hash>.AppImage``) and generic release names.
    """

    stem = Path(name).stem
    stem = _HASH_SUFFIX.sub("", stem)
    version_match = _VERSION.search(stem)
    version = version_match.group(1) if version_match else ""
    if version_match is not None:
        stem = stem[: version_match.start()] + stem[version_match.end() :]
    stem = _ARCH_TOKEN.sub("", stem)
    stem = _SEPARATORS.sub("-", stem).strip("-_ ")
    return stem, version


def _iter_files(root: Path, max_depth: int) -> Iterator[Path]:
    """Yield files up to ``max_depth`` levels below ``root`` without deep walks."""

    for current, dirs, files in os.walk(root):
        depth = len(Path(current).relative_to(root).parts)
        if depth >= max_depth:
            dirs[:] = []
        for name in files:
            yield Path(current) / name


def _desktop_executable(path: Path) -> Path | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        if not line.startswith("Exec="):
            continue
        value = line[5:].strip()
        if not value:
            continue
        tokens = value.split()
        candidate_str = tokens[0].strip('"')
        if not candidate_str or candidate_str.startswith("%"):
            continue
        candidate = Path(candidate_str)
        if not candidate.is_absolute():
            candidate = Path("/usr/bin") / candidate.name
        if candidate.is_file():
            return candidate
    return None


class InstalledAppDiscovery:
    """Scan conventional install locations and match files to repositories."""

    def __init__(self, platform_info: PlatformInfo) -> None:
        self.platform = platform_info

    def scan_roots(self) -> list[Path]:
        home = Path.home()
        roots: list[Path] = [home / "Applications"]

        if self.platform.is_windows:
            local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
            roots.extend(
                [
                    local / "Programs",
                    home / "Desktop",
                    Path(os.environ["ProgramFiles"]) if os.environ.get("ProgramFiles") else None,
                    Path(os.environ["ProgramFiles(x86)"]) if os.environ.get("ProgramFiles(x86)") else None,
                ]
            )
        elif self.platform.is_linux:
            data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
            roots.extend(
                [
                    data / "applications",
                    home / ".local" / "bin",
                    home / "bin",
                    Path("/usr/share/applications"),
                ]
            )
        else:
            roots.extend([Path("/Applications"), Path("/usr/share/applications")])

        extra = os.environ.get("SKAYLAUNCHER_DISCOVERY_DIRS", "")
        roots.extend(Path(item).expanduser() for item in extra.split(os.pathsep) if item.strip())
        unique: list[Path] = []
        for root in roots:
            if root.is_dir() and root not in unique:
                unique.append(root)
        return unique

    def discover(self, repositories: Iterable[Repository]) -> list[InstalledApp]:
        repos = list(repositories)
        repo_by_key: dict[str, Repository] = {}
        for repo in repos:
            key = normalize_name(repo.name)
            if key and key not in _EXCLUDED:
                repo_by_key[key] = repo

        found: dict[str, InstalledApp] = {}
        for root in self.scan_roots():
            for executable in self._candidates(root):
                record = self._match(executable, repo_by_key)
                if record is not None:
                    found.setdefault(record.repo.lower(), record)

        if self.platform.is_windows:
            for executable in self._registry_candidates(repo_by_key):
                record = self._match(executable, repo_by_key)
                if record is not None:
                    found.setdefault(record.repo.lower(), record)
        return list(found.values())

    def _candidates(self, root: Path) -> Iterator[Path]:
        if self.platform.is_windows:
            suffixes = _WINDOWS_EXECUTABLE_SUFFIXES
        elif self.platform.system == "darwin":
            suffixes = _MACOS_BUNDLE_SUFFIXES
        else:
            suffixes = _LINUX_EXECUTABLE_SUFFIXES

        for path in _iter_files(root, 2):
            if path.suffix.casefold() in suffixes:
                if self.platform.system == "darwin":
                    bundled = self._bundle_executable(path)
                    if bundled is not None:
                        yield bundled
                else:
                    yield path
            elif path.name.casefold().endswith(".desktop"):
                executable = _desktop_executable(path)
                if executable is not None:
                    yield executable
            elif self.platform.is_linux and not path.suffix and os.access(path, os.X_OK):
                yield path

    @staticmethod
    def _bundle_executable(bundle: Path) -> Path | None:
        info = bundle / "Contents" / "Info.plist"
        if not info.is_file():
            return None
        try:
            import plistlib

            with info.open("rb") as handle:
                name = str(plistlib.load(handle).get("CFBundleExecutable", ""))
        except (OSError, ValueError, ImportError):
            return None
        executable = bundle / "Contents" / "MacOS" / name
        return executable if executable.is_file() else None

    def _match(self, executable: Path, repo_by_key: dict[str, Repository]) -> InstalledApp | None:
        base, version = parse_asset_name(executable.name)
        key = normalize_name(base)
        if not key or key in _EXCLUDED:
            return None
        repo = repo_by_key.get(_ALIASES.get(key, key))
        if repo is None:
            for repo_key, candidate in repo_by_key.items():
                if len(key) >= 6 and len(repo_key) >= 6 and (
                    repo_key.startswith(key) or key.startswith(repo_key)
                ):
                    repo = candidate
                    break
        if repo is None:
            return None
        if not version and repo.release is not None:
            version = repo.release.version
        elif not version:
            version = "unknown"
        return InstalledApp(
            repo=repo.name,
            version=version,
            tag=repo.release.tag if repo.release is not None else f"v{version}",
            executable=str(executable),
            directory=str(executable.parent),
            asset="",
            installed_at=datetime.now(timezone.utc).isoformat(),
            discovered=True,
        )

    @staticmethod
    def _registry_candidates(repo_by_key: dict[str, Repository]) -> Iterator[Path]:
        try:
            import winreg
        except ImportError:
            return
        hives = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]
        subkey = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
        for hive in hives:
            try:
                with winreg.OpenKey(hive, subkey) as root:
                    index = 0
                    while True:
                        try:
                            name = winreg.EnumKey(root, index)
                        except OSError:
                            break
                        index += 1
                        try:
                            with winreg.OpenKey(root, name) as entry:
                                display = str(winreg.QueryValueEx(entry, "DisplayName")[0])
                                key = normalize_name(display)
                                if key not in repo_by_key and key not in _ALIASES:
                                    continue
                                raw_icon = str(winreg.QueryValueEx(entry, "DisplayIcon")[0])
                                icon = Path(raw_icon.split(",", 1)[0].strip('"'))
                                if icon.is_file():
                                    yield icon
                        except OSError:
                            continue
            except OSError:
                continue


__all__ = [
    "InstalledAppDiscovery",
    "load_ignored",
    "normalize_name",
    "parse_asset_name",
    "save_ignored",
]
