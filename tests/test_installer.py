import os
import stat
import zipfile
from pathlib import Path

import pytest

from skaylauncher.core.apps import InstallRegistry
from skaylauncher.core.models import PlatformInfo, Release, ReleaseAsset
from skaylauncher.core.paths import PathManager
from skaylauncher.installer.downloader import DownloadResult
from skaylauncher.installer.manager import AppInstaller, InstallationError
from skaylauncher.installer.verifier import VerificationResult


class FakeDownloader:
    def __init__(self, paths, content: bytes, name: str) -> None:
        self.paths = paths
        self.content = content
        self.name = name

    def download(self, repo, release, asset, progress=None, extra_assets=None):
        folder = self.paths.downloads_dir / "fake"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / self.name
        path.write_bytes(self.content)
        return DownloadResult(
            path=path,
            asset=asset,
            release=release,
            verification=VerificationResult(path.name, True, False, "test"),
        )


def make_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("SKAYLAUNCHER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return PathManager()


def linux_release():
    asset = ReleaseAsset("app-x86_64.AppImage", "https://example.invalid/app.AppImage")
    return Release("v1.2.3", "v1.2.3", "", "2026-01-01", (asset,))


def build_installer(monkeypatch, tmp_path, content=b"app", name="app-x86_64.AppImage", platform=None):
    paths = make_paths(monkeypatch, tmp_path)
    registry = InstallRegistry(paths.apps_file)
    installer = AppInstaller(
        paths,
        registry,
        FakeDownloader(paths, content, name),
        platform or PlatformInfo("linux", "x86_64"),
    )
    return paths, registry, installer


def test_install_appimage_sets_executable_and_registers(monkeypatch, tmp_path):
    _paths, registry, installer = build_installer(monkeypatch, tmp_path)
    record = installer.install("app", linux_release())
    assert record.version == "1.2.3"
    assert Path(record.executable).is_file()
    assert Path(record.executable).stat().st_mode & stat.S_IXUSR
    assert registry.get("app") == record


def test_launch_detaches_process(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("skaylauncher.installer.manager.subprocess.Popen", lambda *a, **k: calls.append((a, k)))
    _paths, _registry, installer = build_installer(monkeypatch, tmp_path)
    installer.install("app", linux_release())
    assert installer.launch("app") is True
    args, kwargs = calls[0]
    assert args[0][0].endswith("app-x86_64.AppImage")
    assert kwargs["start_new_session"] is True
    assert kwargs["stdout"] is not None


def test_uninstall_removes_directory_and_record(monkeypatch, tmp_path):
    paths, registry, installer = build_installer(monkeypatch, tmp_path)
    record = installer.install("app", linux_release())
    directory = Path(record.directory)
    assert directory.is_dir()
    installer.uninstall("app")
    assert not directory.exists()
    assert registry.get("app") is None


def test_windows_zip_install_extracts_executable(monkeypatch, tmp_path):
    archive = tmp_path / "app-windows.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("app.exe", b"binary")
    paths = make_paths(monkeypatch, tmp_path)
    registry = InstallRegistry(paths.apps_file)
    installer = AppInstaller(
        paths,
        registry,
        FakeDownloader(paths, archive.read_bytes(), "app-windows.zip"),
        PlatformInfo("windows", "x86_64"),
    )
    release = Release(
        "v2.0.0", "v2.0.0", "", "2026-01-01",
        (ReleaseAsset("app-windows.zip", "https://example.invalid/app.zip"),),
    )
    record = installer.install("app", release)
    assert Path(record.executable).name == "app.exe"
    assert Path(record.executable).read_bytes() == b"binary"


def test_safe_extract_rejects_traversal(monkeypatch, tmp_path):
    _paths, _registry, installer = build_installer(monkeypatch, tmp_path)
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", b"bad")
    with pytest.raises(InstallationError, match="Unsafe path"):
        installer._safe_extract(archive, tmp_path / "out")


def test_install_without_asset_raises(monkeypatch, tmp_path):
    _paths, _registry, installer = build_installer(monkeypatch, tmp_path)
    with pytest.raises(InstallationError, match="No installable asset"):
        installer.install("app", Release("v1", "v1", "", "", ()))
