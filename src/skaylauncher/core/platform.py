"""Platform detection and release asset selection."""

from __future__ import annotations

import platform as _platform
import re

from .models import PlatformInfo, Release, ReleaseAsset

IGNORED_SUFFIXES = (
    ".sig",
    ".sha256",
    ".sha256sum",
    ".md5",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    ".deb",
    ".rpm",
)


def current_platform() -> PlatformInfo:
    system = _platform.system().lower()
    if system not in {"linux", "windows"}:
        raise RuntimeError(f"Unsupported operating system: {system}")
    machine = _platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        machine = "x86_64"
    return PlatformInfo(system=system, machine=machine)


def _score_linux(asset: ReleaseAsset, info: PlatformInfo) -> int:
    name = asset.name.lower()
    if not name.endswith(".appimage"):
        return 0
    score = 100
    if "x86_64" in name or "amd64" in name:
        score += 20
    elif "aarch64" in name or "arm64" in name:
        return 0 if info.is_x86_64 else score
    elif info.is_x86_64:
        score += 5
    if "update" in name or "latest" in name:
        score -= 10
    return score


def _score_windows(asset: ReleaseAsset, info: PlatformInfo) -> int:
    name = asset.name.lower()
    if not (name.endswith(".exe") or name.endswith(".zip")):
        return 0
    if any(word in name for word in ("source", "sha256sums", "checksums")):
        return 0
    score = 100
    if "win" in name or "windows" in name:
        score += 20
    if "x86_64" in name or "amd64" in name or "64bit" in name:
        score += 20
    if "arm64" in name or "aarch64" in name:
        return 0 if info.is_x86_64 else score
    if name.endswith(".exe"):
        score += 5
    if info.is_x86_64:
        score += 5
    return score


def score_asset(asset: ReleaseAsset, info: PlatformInfo) -> int:
    if asset.name.lower().endswith(IGNORED_SUFFIXES):
        return 0
    if info.is_linux:
        return _score_linux(asset, info)
    if info.is_windows:
        return _score_windows(asset, info)
    return 0


def choose_asset(release: Release | None, info: PlatformInfo) -> ReleaseAsset | None:
    """Return the best installable asset for the current platform."""

    if release is None:
        return None
    ranked = sorted(
        ((score_asset(asset, info), index, asset)
         for index, asset in enumerate(release.assets)),
        key=lambda item: (-item[0], item[1]),
    )
    for score, _index, asset in ranked:
        if score > 0:
            return asset
    return None


def is_version_compatible(name: str, info: PlatformInfo) -> bool:
    lowered = name.lower()
    if info.is_linux and ("arm64" in lowered or "aarch64" in lowered):
        return False
    if info.is_windows and ("arm64" in lowered or "aarch64" in lowered):
        return False
    return True


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return slug or "app"
