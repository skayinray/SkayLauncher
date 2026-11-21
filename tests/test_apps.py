from skaylauncher.core.apps import InstallRegistry
from skaylauncher.core.models import InstalledApp


def record(repo, version):
    return InstalledApp(
        repo=repo,
        version=version,
        tag=f"v{version}",
        executable=f"/tmp/{repo}/app",
        directory=f"/tmp/{repo}",
        asset="app.AppImage",
        installed_at="2026-01-01T00:00:00Z",
    )


def test_registry_upsert_get_remove(tmp_path):
    registry = InstallRegistry(tmp_path / "apps.json")
    assert registry.load() == {}
    registry.upsert(record("chess.skay", "1.0.0"))
    registry.upsert(record("SteamSNM", "2.0.0"))
    assert set(registry.load()) == {"chess.skay", "steamsnm"}
    assert registry.get("CHESS.SKAY").version == "1.0.0"
    registry.remove("chess.skay")
    assert registry.get("chess.skay") is None
    assert set(registry.load()) == {"steamsnm"}


def test_registry_survives_corrupt_file(tmp_path):
    path = tmp_path / "apps.json"
    path.write_text("not json")
    assert InstallRegistry(path).load() == {}


def test_registry_saves_versioned_payload(tmp_path):
    registry = InstallRegistry(tmp_path / "apps.json")
    registry.upsert(record("app", "3.1"))
    text = (tmp_path / "apps.json").read_text()
    assert '"schema": 1' in text
    assert '"version": "3.1"' in text
