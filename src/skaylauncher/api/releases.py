"""Parsers for GitHub REST payloads and release asset selection."""

from __future__ import annotations

from typing import Any, Iterable

from ..core.models import PlatformInfo, Release, ReleaseAsset, Repository
from ..core.platform import choose_asset


def parse_release(payload: dict[str, Any] | None) -> Release | None:
    if not isinstance(payload, dict):
        return None
    assets: list[ReleaseAsset] = []
    raw_assets = payload.get("assets")
    if isinstance(raw_assets, list):
        for item in raw_assets:
            if isinstance(item, dict) and item.get("name"):
                assets.append(ReleaseAsset.from_dict(item))
    return Release(
        tag=str(payload.get("tag_name") or ""),
        name=str(payload.get("name") or payload.get("tag_name") or ""),
        body=str(payload.get("body") or ""),
        published_at=str(payload.get("published_at") or ""),
        assets=tuple(assets),
        html_url=str(payload.get("html_url") or ""),
    )


def parse_repository(payload: dict[str, Any], release: Release | None = None) -> Repository:
    topics = payload.get("topics")
    if not isinstance(topics, list):
        topics = []
    return Repository(
        id=int(payload.get("id") or 0),
        name=str(payload.get("name") or ""),
        full_name=str(payload.get("full_name") or ""),
        html_url=str(payload.get("html_url") or ""),
        description=str(payload.get("description") or ""),
        topics=tuple(str(topic) for topic in topics),
        updated_at=str(payload.get("pushed_at") or payload.get("updated_at") or ""),
        fork=bool(payload.get("fork")),
        archived=bool(payload.get("archived")),
        release=release,
    )


def parse_repositories(
    payloads: Iterable[dict[str, Any]],
    releases: dict[str, dict[str, Any] | None],
    include_forks: bool = False,
    excluded: Iterable[str] = ("SkayLauncher",),
) -> list[Repository]:
    ignored = {name.lower() for name in excluded}
    result: list[Repository] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("name") or "")
        if name.lower() in ignored or payload.get("archived"):
            continue
        if payload.get("fork") and not include_forks:
            continue
        result.append(parse_repository(payload, parse_release(releases.get(name))))
    result.sort(key=lambda repo: (repo.release is None, repo.updated_at), reverse=True)
    return result


def latest_asset(release: Release | None, info: PlatformInfo) -> ReleaseAsset | None:
    return choose_asset(release, info)


def release_summary(release: Release | None) -> str:
    if release is None:
        return "No release"
    return f"{release.tag} ({len(release.assets)} assets)"
