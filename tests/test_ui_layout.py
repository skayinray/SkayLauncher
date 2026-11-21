"""Offline layout checks for the frameless launcher window."""

from __future__ import annotations

try:
    from PySide6.QtWidgets import QApplication
except ImportError as error:  # pragma: no cover - depends on host Qt libraries
    import pytest

    pytest.skip(f"PySide6 is unavailable: {error}", allow_module_level=True)

from skaylauncher.api.cache import ResponseCache
from skaylauncher.api.github import GitHubClient
from skaylauncher.core.apps import InstallRegistry
from skaylauncher.core.config import SettingsStore
from skaylauncher.core.i18n import Translator
from skaylauncher.core.models import PlatformInfo, Repository, Release, ReleaseAsset, InstalledApp
from skaylauncher.core.paths import PathManager
from skaylauncher.installer.downloader import DownloadManager
from skaylauncher.installer.manager import AppInstaller
from skaylauncher.installer.verifier import ReleaseVerifier
from skaylauncher.ui.cards import CARD_MIN_HEIGHT, AppCard
from skaylauncher.ui.main_window import MainWindow, grid_columns
from skaylauncher.updater.updater import SelfUpdater


def test_grid_columns_scale_with_width() -> None:
    assert grid_columns(200) == 1
    assert grid_columns(494) == 2
    assert grid_columns(700) == 2
    assert grid_columns(1000) == 3


def test_window_fits_small_screen_and_fullscreen(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKAYLAUNCHER_HOME", str(tmp_path))
    monkeypatch.setattr(MainWindow, "refresh_repositories", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_self_update", lambda self: None)

    app = QApplication.instance() or QApplication([])
    paths = PathManager()
    client = GitHubClient(ResponseCache(paths.api_cache_file))
    registry = InstallRegistry(paths.apps_file)
    platform = PlatformInfo("linux", "x86_64")
    installer = AppInstaller(paths, registry, DownloadManager(client, paths, ReleaseVerifier()), platform)
    updater = SelfUpdater(client, paths, "1.0.0", platform)
    window = MainWindow(
        SettingsStore(paths.settings_file), paths, client, registry, installer, updater,
        Translator("en"), platform,
    )

    assert window.minimumWidth() <= 700
    assert window.minimumHeight() <= 500

    window.resize(680, 480)
    window.show()
    app.processEvents()
    assert window._columns == 1
    assert window._scroll_area.viewport().width() > 240
    assert window._sidebar.width() <= 200

    window.resize(1024, 720)
    app.processEvents()
    assert window._columns >= 2

    window.showFullScreen()
    app.processEvents()
    assert window.isFullScreen()
    assert window._root_layout.contentsMargins().left() == 0

    window.toggle_fullscreen()
    app.processEvents()
    assert not window.isFullScreen()
    assert window._root_layout.contentsMargins().left() == 8
    window.close()


def test_cards_keep_minimum_height_and_scroll_on_small_window(tmp_path, monkeypatch) -> None:
    """Cards must not be squeezed below readable height; the view scrolls instead."""

    monkeypatch.setenv("SKAYLAUNCHER_HOME", str(tmp_path))
    monkeypatch.setattr(MainWindow, "refresh_repositories", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_self_update", lambda self: None)

    app = QApplication.instance() or QApplication([])
    paths = PathManager()
    client = GitHubClient(ResponseCache(paths.api_cache_file))
    registry = InstallRegistry(paths.apps_file)
    platform = PlatformInfo("linux", "x86_64")
    installer = AppInstaller(paths, registry, DownloadManager(client, paths, ReleaseVerifier()), platform)
    updater = SelfUpdater(client, paths, "1.0.0", platform)
    window = MainWindow(
        SettingsStore(paths.settings_file), paths, client, registry, installer, updater,
        Translator("en"), platform,
    )

    asset = ReleaseAsset("app.AppImage", "https://example.invalid/app.AppImage")
    release = Release("v1.0.0", "v1.0.0", "notes", "2026-01-01T00:00:00Z", (asset,))
    repos = [
        Repository(index, f"App{index}", f"skayinray/App{index}", "", "A short description", (), "", False, False, release)
        for index in range(1, 5)
    ]
    window.show()
    window._apply_repositories(repos)
    window.resize(680, 480)
    app.processEvents()

    assert window._columns == 1
    for card in window._cards.values():
        assert card.minimumHeight() >= CARD_MIN_HEIGHT
        assert card.height() >= CARD_MIN_HEIGHT
    assert window._grid_page.height() > window._scroll_area.viewport().height()
    assert window._scroll_area.verticalScrollBar().isVisible()
    window.close()


def test_description_elides_to_two_lines() -> None:
    """Long descriptions are elided instead of overflowing the card."""

    card = AppCard(Translator("en"))
    card.resize(240, 210)
    text = "A very long description that should be elided because it cannot fit inside two short lines at this card width"
    card._description_text = text
    card._elide_text()
    shown = card._description_label.text()
    assert "\n" in shown
    assert shown.count("\n") <= 1
    assert "\u2026" in shown
    assert shown != text
    card.close()
