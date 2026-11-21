import io
import json
import re
import time
import urllib.error
import urllib.request

import pytest

from skaylauncher.api.cache import ResponseCache
from skaylauncher.api.github import GitHubApiError, GitHubClient


class FakeResponse:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.stream = io.BytesIO(body)
        self.headers = FakeHeaders(headers or {})

    def read(self, size=-1):
        return self.stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeHeaders:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get(self, name: str, default=""):
        return self.values.get(name, default)


class FakeOpener:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = list(responses)
        self.requests: list[urllib.request.Request] = []

    def open(self, request, timeout=...):
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_cache_roundtrip_and_freshness(tmp_path):
    cache = ResponseCache(tmp_path / "cache.json", max_age=60)
    assert cache.fresh("url") is None
    cache.put("url", {"ok": True}, "etag-1")
    cached = cache.fresh("url")
    assert cached is not None and cached.body == {"ok": True}
    cache.max_age = -1
    assert cache.fresh("url") is None
    assert json.loads((tmp_path / "cache.json").read_text())["entries"]["url"]["etag"] == "etag-1"


def test_client_uses_etag_and_handles_304(tmp_path):
    cache = ResponseCache(tmp_path / "cache.json", max_age=-1)
    cache.put("https://api.github.com/users/skayinray/repos", [{"id": 1}], "etag-1")
    opener = FakeOpener([urllib.error.HTTPError("url", 304, "not modified", {}, io.BytesIO(b""))])
    client = GitHubClient(cache, opener=opener)
    result, from_cache = client._request("/users/skayinray/repos")
    assert result == [{"id": 1}] and from_cache is True
    assert opener.requests[0].headers["If-none-match"] == "etag-1"


def test_client_returns_cached_data_on_rate_limit(tmp_path):
    cache = ResponseCache(tmp_path / "cache.json", max_age=-1)
    cache.put("https://api.github.com/users/skayinray/repos", [{"id": 7}], "")
    opener = FakeOpener([urllib.error.HTTPError("url", 403, "rate limit", {}, io.BytesIO(b""))])
    client = GitHubClient(cache, opener=opener)
    result, from_cache = client._request("/users/skayinray/repos")
    assert result == [{"id": 7}] and from_cache is True


def test_client_raises_without_cached_data(tmp_path):
    opener = FakeOpener([urllib.error.HTTPError("url", 500, "server error", {}, io.BytesIO(b"boom"))])
    client = GitHubClient(ResponseCache(tmp_path / "cache.json"), opener=opener)
    with pytest.raises(GitHubApiError) as error:
        client._request("/user")
    assert error.value.status == 500


def test_download_asset_streams_and_calls_progress(tmp_path):
    opener = FakeOpener(
        [
            FakeResponse(b""),
            FakeResponse(b"abcdefghij", {"Content-Length": "10"}),
        ]
    )
    client = GitHubClient(ResponseCache(tmp_path / "cache.json"), opener=opener)
    seen = []
    target = client.download_asset(
        "https://example.invalid/app.AppImage",
        tmp_path / "app.AppImage",
        lambda done, total: seen.append((done, total)),
    )
    assert target.read_bytes() == b"abcdefghij"
    assert seen[-1] == (10, 10)
    assert not target.with_name(target.name + ".part").exists()


def test_download_asset_rejects_http(tmp_path):
    client = GitHubClient(ResponseCache(tmp_path / "cache.json"), opener=FakeOpener([]))
    with pytest.raises(GitHubApiError):
        client.download_asset("http://example.invalid/app", tmp_path / "app")


class RangeResponse(FakeResponse):
    def __init__(self, body: bytes, content_range: str) -> None:
        super().__init__(body, {"Content-Range": content_range, "Content-Length": str(len(body))})
        self.status = 206


class RangeOpener:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.requests: list[urllib.request.Request] = []

    def open(self, request, timeout=...):
        self.requests.append(request)
        header = request.get_header("Range") or ""
        match = re.fullmatch(r"bytes=(\d+)-(\d+)", header)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            return RangeResponse(
                self.data[start : end + 1], f"bytes {start}-{end}/{len(self.data)}"
            )
        return FakeResponse(self.data, {"Content-Length": str(len(self.data))})


def test_download_asset_uses_parallel_ranges_for_large_files(tmp_path):
    payload = bytes(range(256)) * (9 * 1024 * 1024 // 256)
    opener = RangeOpener(payload)
    client = GitHubClient(ResponseCache(tmp_path / "cache.json"), opener=opener)
    seen: list[tuple[int, int]] = []
    target = client.download_asset(
        "https://example.invalid/app.AppImage",
        tmp_path / "app.AppImage",
        lambda done, total: seen.append((done, total)),
    )
    assert target.read_bytes() == payload
    range_requests = [request.get_header("Range") for request in opener.requests if request.get_header("Range")]
    assert range_requests[0] == "bytes=0-0"
    assert len(range_requests) > 2
    assert seen[-1] == (len(payload), len(payload))
    assert not list(tmp_path.glob("*.part.*"))


class FlakyRangeOpener:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def open(self, request, timeout=...):
        header = request.get_header("Range") or ""
        if header == "bytes=0-0":
            return RangeResponse(b"x", f"bytes 0-0/{len(self.data)}")
        if header.startswith("bytes=0-"):
            return RangeResponse(b"x" * 1024, f"bytes 0-1023/{len(self.data)}")
        if header:
            raise urllib.error.HTTPError("url", 500, "range failed", {}, io.BytesIO(b""))
        return FakeResponse(self.data, {"Content-Length": str(len(self.data))})


def test_download_fallback_keeps_progress_monotonic(tmp_path):
    payload = bytes(range(256)) * (9 * 1024 * 1024 // 256)
    client = GitHubClient(ResponseCache(tmp_path / "cache.json"), opener=FlakyRangeOpener(payload))
    seen: list[int] = []
    target = client.download_asset(
        "https://example.invalid/app.AppImage",
        tmp_path / "app.AppImage",
        lambda done, _total: seen.append(done),
    )
    assert target.read_bytes() == payload
    assert seen and all(later >= earlier for earlier, later in zip(seen, seen[1:]))
    assert seen[-1] == len(payload)
    assert not list(tmp_path.glob("*.part*"))

