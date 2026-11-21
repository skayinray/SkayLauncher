import hashlib
import os
from pathlib import Path

from skaylauncher.api.releases import parse_release
from skaylauncher.core.models import PlatformInfo
from skaylauncher.core.paths import PathManager
from skaylauncher.installer.verifier import VerificationResult
from skaylauncher.updater.updater import PreparedUpdate, SelfUpdater, UpdateNotApplicable


class FakeClient:
    def __init__(self, release_payload=None) -> None:
        self.release_payload = release_payload
        self.downloads = {}

    def get_latest_release(self, repo):
        return self.release_payload

    def download_asset(self, url, destination, progress=None):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = self.downloads.get(url, b"data")
        destination.write_bytes(content)
        if progress:
            progress(len(content), len(content))
        return destination


def make_updater(monkeypatch, tmp_path, payload=None, version="1.0.0", platform=None):
    monkeypatch.setenv("SKAYLAUNCHER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    paths = PathManager()
    client = FakeClient(payload)
    return paths, client, SelfUpdater(
        client,
        paths,
        version,
        platform_info=platform or PlatformInfo("linux", "x86_64"),
        frozen=True,
    )


def release_payload(version="v1.1.0", asset_name="SkayLauncher-x86_64.AppImage", url="https://example.invalid/app"):
    return {
        "tag_name": version,
        "name": version,
        "body": "Release notes.",
        "published_at": "2026-11-21T00:00:00Z",
        "assets": [{"name": asset_name, "browser_download_url": url, "size": 4}],
    }


def test_check_detects_newer_release(monkeypatch, tmp_path):
    _paths, _client, updater = make_updater(monkeypatch, tmp_path, release_payload())
    check = updater.check()
    assert check.available is True
    assert check.version == "1.1.0"
    assert check.asset is not None


def test_check_ignores_older_or_equal_version(monkeypatch, tmp_path):
    _paths, _client, updater = make_updater(monkeypatch, tmp_path, release_payload("v1.0.0"))
    assert updater.check().available is False
    _paths, _client, updater = make_updater(monkeypatch, tmp_path, release_payload("v0.9.0"))
    assert updater.check().available is False


def test_prepare_downloads_and_verifies(monkeypatch, tmp_path):
    payload = release_payload()
    payload["assets"].append({
        "name": "SHA256SUMS",
        "browser_download_url": "https://example.invalid/sums",
    })
    content = b"new launcher"
    digest = hashlib.sha256(content).hexdigest()
    paths, client, updater = make_updater(monkeypatch, tmp_path, payload)
    client.downloads["https://example.invalid/app"] = content
    client.downloads["https://example.invalid/sums"] = f"{digest}  SkayLauncher-x86_64.AppImage\n".encode()
    check = updater.check()
    prepared = updater.prepare(check)
    assert prepared.path.read_bytes() == content
    assert prepared.verification.checksum_verified is True


def test_apply_linux_replaces_appimage_and_keeps_backup(monkeypatch, tmp_path):
    paths, _client, updater = make_updater(monkeypatch, tmp_path)
    current = tmp_path / "SkayLauncher-x86_64.AppImage"
    current.write_bytes(b"old")
    monkeypatch.setattr(updater, "current_executable", lambda: current)
    prepared_path = tmp_path / "prepared.AppImage"
    prepared_path.write_bytes(b"new")
    result = updater.apply(PreparedUpdate(prepared_path, VerificationResult("x", True, False)))
    assert result == "applied"
    assert current.read_bytes() == b"new"
    assert any(path.name.startswith("SkayLauncher-x86_64.AppImage.") for path in paths.backups_dir.iterdir())


def test_apply_windows_starts_detached_powershell(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("skaylauncher.updater.updater.subprocess.Popen", lambda *a, **k: calls.append((a[0], k)))
    monkeypatch.setattr("skaylauncher.updater.updater.subprocess.DETACHED_PROCESS", 0x00000008, raising=False)
    monkeypatch.setattr("skaylauncher.updater.updater.subprocess.CREATE_NEW_PROCESS_GROUP", 0x00000200, raising=False)
    paths, _client, updater = make_updater(
        monkeypatch,
        tmp_path,
        platform=PlatformInfo("windows", "x86_64"),
    )
    current = tmp_path / "SkayLauncher.exe"
    current.write_bytes(b"old")
    monkeypatch.setattr(updater, "current_executable", lambda: current)
    prepared_path = tmp_path / "prepared.exe"
    prepared_path.write_bytes(b"new")
    result = updater.apply(PreparedUpdate(prepared_path, VerificationResult("x", True, False)))
    assert result == "pending_restart"
    args, kwargs = calls[0][0], calls[0][1]
    assert args[0] == "powershell.exe"
    assert "-LauncherPid" in args
    assert kwargs["creationflags"] != 0
    assert list(paths.cache_dir.glob("replace-*.ps1"))


def test_apply_from_source_is_not_applicable(monkeypatch, tmp_path):
    _paths, _client, updater = make_updater(monkeypatch, tmp_path)
    updater.frozen = False
    prepared_path = tmp_path / "prepared.AppImage"
    prepared_path.write_bytes(b"new")
    import pytest

    with pytest.raises(UpdateNotApplicable):
        updater.apply(PreparedUpdate(prepared_path, VerificationResult("x", True, False)))
