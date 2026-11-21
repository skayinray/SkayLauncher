from skaylauncher.core.models import (
    InstalledApp,
    Release,
    ReleaseAsset,
    compare_versions,
    parse_version,
)


def test_parse_version_ignores_suffixes():
    assert parse_version("v1.5.3.2") == (1, 5, 3, 2)
    assert parse_version("2.0-beta") == (2, 0)
    assert parse_version("nonsense") == (0,)


def test_compare_versions():
    assert compare_versions("1.2.0", "1.1.9") > 0
    assert compare_versions("v1.0.0", "1.0.0") == 0
    assert compare_versions("0.9", "1.0") < 0
    assert compare_versions("1.10", "1.9") > 0


def test_release_version_and_release_parser():
    assets = (ReleaseAsset(name="app.AppImage", url="https://example.invalid/app.AppImage"),)
    release = Release(tag="v2.1.0", name="Release", body="notes", published_at="2026-01-01", assets=assets)
    assert release.version == "2.1.0"
    assert release.is_newer_than("2.0.9")
    assert not release.is_newer_than("2.1.0")


def test_installed_app_roundtrip():
    record = InstalledApp(
        repo="chess.skay",
        version="1.0.0",
        tag="v1.0.0",
        executable="/tmp/chess/app.AppImage",
        directory="/tmp/chess",
        asset="chess.AppImage",
        installed_at="2026-01-01T00:00:00Z",
    )
    assert InstalledApp.from_dict(record.to_dict()) == record
