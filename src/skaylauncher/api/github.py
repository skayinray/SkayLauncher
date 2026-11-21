"""Synchronous GitHub REST client. Callers run it in background workers."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Protocol

from .cache import ResponseCache


class Opener(Protocol):
    def open(self, request: urllib.request.Request, timeout: float = ...): ...  # pragma: no cover


class GitHubApiError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GitHubClient:
    def __init__(
        self,
        cache: ResponseCache,
        token: str = "",
        base_url: str = "https://api.github.com",
        opener: Opener | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.cache = cache
        self.token = token.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = "SkayLauncher/1.0"
        self._opener = opener or urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context())
        )

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self.user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if extra:
            headers.update(extra)
        return headers

    def _request(self, path: str, params: dict[str, Any] | None = None, force: bool = False) -> tuple[Any, bool]:
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        cached = self.cache.get(url)
        if cached and not force and cached.is_fresh(self.cache.max_age):
            return cached.body, True
        headers = self._headers({"If-None-Match": cached.etag} if cached and cached.etag else None)
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                etag = response.headers.get("ETag", "")
                payload = json.loads(body) if body.strip() else None
                self.cache.put(url, payload, etag)
                return payload, False
        except urllib.error.HTTPError as error:
            if error.code == 304 and cached is not None:
                self.cache.put(url, cached.body, cached.etag)
                return cached.body, True
            if error.code == 404:
                self.cache.put(url, None, "")
                return None, False
            if error.code in (403, 429) and cached is not None:
                return cached.body, True
            detail = error.read().decode("utf-8", "replace")[:300]
            raise GitHubApiError(f"GitHub returned {error.code}: {detail}", error.code) from error
        except urllib.error.URLError as error:
            if cached is not None:
                return cached.body, True
            raise GitHubApiError(f"GitHub request failed: {error.reason}") from error
        except json.JSONDecodeError as error:
            raise GitHubApiError(f"Invalid JSON from GitHub: {error}") from error

    def list_repositories(self, include_forks: bool = False) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for page in range(1, 11):
            payload, _from_cache = self._request(
                "/users/skayinray/repos",
                {"per_page": 100, "page": page, "type": "owner", "sort": "pushed", "direction": "desc"},
            )
            if not isinstance(payload, list):
                break
            if not include_forks:
                payload = [item for item in payload if not item.get("fork")]
            result.extend(item for item in payload if isinstance(item, dict))
            if len(payload) < 100:
                break
        return result

    def get_latest_release(self, repo: str) -> dict[str, Any] | None:
        payload, _from_cache = self._request(f"/repos/skayinray/{repo}/releases/latest")
        return payload if isinstance(payload, dict) else None

    def get_release_by_tag(self, repo: str, tag: str) -> dict[str, Any] | None:
        payload, _from_cache = self._request(f"/repos/skayinray/{repo}/releases/tags/{tag}")
        return payload if isinstance(payload, dict) else None

    def user(self) -> dict[str, Any] | None:
        payload, _from_cache = self._request("/user")
        return payload if isinstance(payload, dict) else None

    def download_asset(
        self,
        url: str,
        destination: str | Path,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        if not url.startswith("https://"):
            raise GitHubApiError(f"Asset URL must use HTTPS: {url}")
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        headers = self._headers({"Accept": "application/octet-stream"})
        request = urllib.request.Request(url, headers=headers, method="GET")
        downloaded = 0
        total = 0
        try:
            with self._opener.open(request, timeout=self.timeout) as response, part.open("wb") as handle:
                total = int(response.headers.get("Content-Length") or 0)
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    handle.flush()
                    if progress:
                        progress(downloaded, total)
                handle.flush()
            if progress:
                progress(downloaded, total or downloaded)
            part.replace(target)
            return target
        except urllib.error.HTTPError as error:
            raise GitHubApiError(f"Asset download failed with {error.code}", error.code) from error
        except urllib.error.URLError as error:
            raise GitHubApiError(f"Asset download failed: {error.reason}") from error
        finally:
            if part.exists():
                part.unlink()
