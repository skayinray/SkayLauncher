"""Tests for detection of apps installed outside the launcher registry."""

from __future__ import annotations

from pathlib import Path

from skaylauncher.core.apps import InstallRegistry
from skaylauncher.core.discovery import InstalledAppDiscovery, parse_asset_name
from skaylauncher.core.models import InstalledApp, PlatformInfo, Repository
from skaylauncher.installer.manager import AppInstaller


def repos() -> list[Repository]:
    return [
        Repository(1, "hackmeskay", "skayinray/hackmeskay", "", "", (), "", False, False),
        Repository(2, "SkayClearTux", "skayinray/SkayClearTux", "", "", (), "", False, False),
        Repository(3, "chess.skay", "skayinray/chess.skay", "", "", (), "", False, False),
        Repository(4, "SteamSNM", "skayinray/SteamSNM", "", "", (), "", False, False),
        Repository(5, "SkayLauncher", "skayinray/SkayLauncher", "", "", (), "", False, False),
    ]


def test_parse_asset_name_handles_appimage_launcher_names() -> None:
    assert parse_asset_name("SkayClearTux-1.5.3.2-x86_64_2ec5bcd431cc208839c7adee50736d65.AppImage") == (
        "SkayClearTux",
        "1.5.3.2",
    )
    assert parse_asset_name("SteamSNM-x86_64_6975c3285af3aaaa185fc79d63902431.AppImage") == (
        "SteamSNM",
        "",
    )
    assert parse_asset_name("hackmeskay.exe") == ("hackmeskay", "")


def test_discovery_matches_known_apps_and_ignores_launcher(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "SkayClearTux-1.5.3.2-x86_64_2ec5bcd431cc208839c7adee50736d65.AppImage").write_bytes(b"x")
    (tmp_path / "SteamSNM-x86_64_6975c3285af3aaaa185fc79d63902431.AppImage").write_bytes(b"x")
    (tmp_path / "SkayLauncher-x86_64_deadbeefdeadbeefdeadbeefdeadbeef.AppImage").write_bytes(b"x")
    (tmp_path / "unrelated.AppImage").write_bytes(b"x")

    discovery = InstalledAppDiscovery(PlatformInfo("linux", "x86_64"))
    monkeypatch.setattr(discovery, "scan_roots", lambda: [tmp_path])
    found = {record.repo: record for record in discovery.discover(repos())}

    assert set(found) == {"SkayClearTux", "SteamSNM"}
    assert found["SkayClearTux"].version == "1.5.3.2"
    assert found["SkayClearTux"].discovered is True
    assert found["SteamSNM"].executable.endswith(".AppImage")


def test_registry_sync_keeps_managed_apps_and_drops_missing_discovered(tmp_path: Path) -> None:
    registry = InstallRegistry(tmp_path / "apps.json")
    managed_record = InstalledApp("hackmeskay", "1.0", "v1.0", "/opt/hackmeskay/app", "/opt/hackmeskay", "", "now")
    registry.upsert(managed_record)
    discovered = InstalledApp(
        "SteamSNM", "1.2", "v1.2", "/home/u/Applications/SteamSNM.AppImage", "/home/u/Applications", "", "now", True
    )
    registry.sync_discovered([discovered])
    assert registry.get("hackmeskay") == managed_record
    assert registry.get("SteamSNM") == discovered

    registry.sync_discovered([])
    assert registry.get("hackmeskay") == managed_record
    assert registry.get("SteamSNM") is None


def test_uninstall_discovered_app_never_deletes_external_file(tmp_path: Path, monkeypatch) -> None:
    from skaylauncher.api.cache import ResponseCache
    from skaylauncher.api.github import GitHubClient
    from skaylauncher.core.paths import PathManager
    from skaylauncher.installer.downloader import DownloadManager
    from skaylauncher.installer.verifier import ReleaseVerifier

    monkeypatch.setenv("SKAYLAUNCHER_HOME", str(tmp_path / "home"))
    paths = PathManager()
    registry = InstallRegistry(paths.apps_file)
    external = tmp_path / "Applications"
    external.mkdir()
    executable = external / "SteamSNM-x86_64.AppImage"
    executable.write_bytes(b"keep me")
    record = InstalledApp(
        "SteamSNM", "1", "v1", str(executable), str(external), "", "now", True
    )
    registry.upsert(record)
    client = GitHubClient(ResponseCache(paths.api_cache_file))
    installer = AppInstaller(paths, registry, DownloadManager(client, paths, ReleaseVerifier()), PlatformInfo("linux", "x86_64"))

    installer.uninstall("SteamSNM")

    assert executable.is_file()
    assert registry.get("SteamSNM") is None
