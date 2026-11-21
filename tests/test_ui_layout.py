"""Offline layout checks for the frameless launcher window."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from skaylauncher.api.cache import ResponseCache
from skaylauncher.api.github import GitHubClient
from skaylauncher.core.apps import InstallRegistry
from skaylauncher.core.config import SettingsStore
from skaylauncher.core.i18n import Translator
from skaylauncher.core.models import PlatformInfo
from skaylauncher.core.paths import PathManager
from skaylauncher.installer.downloader import DownloadManager
from skaylauncher.installer.manager import AppInstaller
from skaylauncher.installer.verifier import ReleaseVerifier
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
