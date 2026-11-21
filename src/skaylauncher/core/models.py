"""Small immutable data objects shared by the API, installer and UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlatformInfo:
    """Target platform used for asset selection."""

    system: str
    machine: str

    @property
    def is_windows(self) -> bool:
        return self.system == "windows"

    @property
    def is_linux(self) -> bool:
        return self.system == "linux"

    @property
    def is_x86_64(self) -> bool:
        return self.machine in {"x86_64", "amd64", "AMD64"}

    def label(self) -> str:
        return f"{self.system}-{self.machine}"


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int = 0
    content_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReleaseAsset:
        return cls(
            name=str(data.get("name", "")),
            url=str(data.get("browser_download_url", data.get("url", ""))),
            size=int(data.get("size") or 0),
            content_type=str(data.get("content_type") or ""),
        )


@dataclass(frozen=True)
class Release:
    tag: str
    name: str
    body: str
    published_at: str
    assets: tuple[ReleaseAsset, ...] = field(default_factory=tuple)
    html_url: str = ""

    @property
    def version(self) -> str:
        return self.tag[1:] if self.tag.startswith(("v", "V")) else self.tag

    def is_newer_than(self, version: str) -> bool:
        return compare_versions(self.version, version) > 0


@dataclass(frozen=True)
class Repository:
    id: int
    name: str
    full_name: str
    html_url: str
    description: str
    topics: tuple[str, ...]
    updated_at: str
    fork: bool
    archived: bool
    release: Release | None = None

    @property
    def latest_version(self) -> str:
        return self.release.version if self.release else ""


@dataclass
class InstalledApp:
    repo: str
    version: str
    tag: str
    executable: str
    directory: str
    asset: str
    installed_at: str
    discovered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstalledApp:
        return cls(
            repo=str(data.get("repo", "")),
            version=str(data.get("version", "")),
            tag=str(data.get("tag", "")),
            executable=str(data.get("executable", "")),
            directory=str(data.get("directory", "")),
            asset=str(data.get("asset", "")),
            installed_at=str(data.get("installed_at", "")),
            discovered=bool(data.get("discovered", False)),
        )


def parse_version(value: str) -> tuple[int, ...]:
    """Return numeric parts from a version string, ignoring suffixes."""

    parts: list[int] = []
    current = ""
    for char in value.strip().lstrip("vV"):
        if char.isdigit():
            current += char
        elif char in ".-+_":
            if current:
                parts.append(int(current))
                current = ""
        else:
            break
    if current:
        parts.append(int(current))
    return tuple(parts) or (0,)


def compare_versions(left: str, right: str) -> int:
    """Compare two human version strings by their numeric prefix."""

    a = parse_version(left)
    b = parse_version(right)
    length = max(len(a), len(b))
    a += (0,) * (length - len(a))
    b += (0,) * (length - len(b))
    return (a > b) - (a < b)
