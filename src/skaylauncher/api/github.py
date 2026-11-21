"""Synchronous GitHub REST client. Callers run it in background workers."""

from __future__ import annotations

import json
import os
import shutil
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Protocol

from .cache import ResponseCache

CHUNK_SIZE = 1024 * 1024
SEGMENT_SIZE = 4 * 1024 * 1024
MIN_SEGMENTED_SIZE = 8 * 1024 * 1024
MAX_SEGMENTS = 8


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
        download_timeout: float = 60.0,
        max_segments: int | None = None,
    ) -> None:
        self.cache = cache
        self.token = token.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.download_timeout = download_timeout
        configured = max_segments if max_segments is not None else int(
            os.environ.get("SKAYLAUNCHER_DOWNLOAD_SEGMENTS", str(MAX_SEGMENTS))
        )
        self.max_segments = max(1, configured)
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

    def _download_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = self._headers(extra)
        headers["Accept-Encoding"] = "identity"
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

    def _probe_ranges(self, url: str) -> int:
        """Return the asset size when the server supports byte ranges."""

        request = urllib.request.Request(
            url, headers=self._download_headers({"Range": "bytes=0-0"}), method="GET"
        )
        with self._opener.open(request, timeout=self.download_timeout) as response:
            if getattr(response, "status", None) != 206:
                return 0
            content_range = response.headers.get("Content-Range", "")
        if "/" not in content_range:
            return 0
        try:
            return int(content_range.rsplit("/", 1)[1].strip())
        except ValueError:
            return 0

    def _stream(
        self,
        url: str,
        part: Path,
        progress: Callable[[int, int], None] | None,
    ) -> None:
        request = urllib.request.Request(
            url, headers=self._download_headers({"Accept": "application/octet-stream"}), method="GET"
        )
        downloaded = 0
        total = 0
        with self._opener.open(request, timeout=self.download_timeout) as response, part.open("wb") as handle:
            total = int(response.headers.get("Content-Length") or 0)
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)
        if progress:
            progress(downloaded, total or downloaded)

    def _download_segmented(
        self,
        url: str,
        part: Path,
        total: int,
        progress: Callable[[int, int], None] | None,
    ) -> bool:
        """Download the asset in parallel byte ranges. Return False to fall back."""

        count = min(self.max_segments, max(1, (total + SEGMENT_SIZE - 1) // SEGMENT_SIZE))
        segment_size = (total + count - 1) // count
        ranges = [
            (offset, min(total - 1, offset + segment_size - 1))
            for offset in range(0, total, segment_size)
        ]
        segments = [part.with_name(f"{part.name}.{index}") for index in range(len(ranges))]
        state = {"done": 0}
        lock = threading.Lock()

        def fetch(start: int, end: int, destination: Path) -> None:
            request = urllib.request.Request(
                url,
                headers=self._download_headers(
                    {"Accept": "application/octet-stream", "Range": f"bytes={start}-{end}"}
                ),
                method="GET",
            )
            with self._opener.open(request, timeout=self.download_timeout) as response:
                if getattr(response, "status", 200) not in (206, 200):
                    raise GitHubApiError("Byte range was not honoured by the server")
                with destination.open("wb") as handle:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        handle.write(chunk)
                        with lock:
                            state["done"] += len(chunk)
                            if progress:
                                progress(state["done"], total)

        executor = ThreadPoolExecutor(max_workers=len(ranges))
        futures: list[Any] = []
        try:
            futures = [executor.submit(fetch, start, end, path) for (start, end), path in zip(ranges, segments)]
            for future in futures:
                future.result()
            for index, (start, end) in enumerate(ranges):
                expected = end - start + 1
                if not segments[index].is_file() or segments[index].stat().st_size != expected:
                    raise GitHubApiError("Incomplete segmented download")
            with part.open("wb") as output:
                for segment in segments:
                    with segment.open("rb") as source:
                        shutil.copyfileobj(source, output, CHUNK_SIZE)
            return True
        except Exception:  # noqa: BLE001 - fall back to a single connection
            for future in futures:
                future.cancel()
            for segment in segments:
                segment.unlink(missing_ok=True)
            return False
        finally:
            executor.shutdown(wait=True)

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
        part.unlink(missing_ok=True)
        try:
            total = self._probe_ranges(url) if self.max_segments > 1 else 0
            if total >= MIN_SEGMENTED_SIZE and not self._download_segmented(url, part, total, progress):
                self._stream(url, part, progress)
            else:
                self._stream(url, part, progress)
            if progress:
                size = part.stat().st_size
                progress(size, size)
            part.replace(target)
            return target
        except urllib.error.HTTPError as error:
            raise GitHubApiError(f"Asset download failed with {error.code}", error.code) from error
        except urllib.error.URLError as error:
            raise GitHubApiError(f"Asset download failed: {error.reason}") from error
        finally:
            part.unlink(missing_ok=True)
