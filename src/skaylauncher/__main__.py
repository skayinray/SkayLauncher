"""Application entry point with single-instance enforcement."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import sys

from PySide6.QtCore import Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .api.cache import ResponseCache
from .api.github import GitHubClient
from .core.apps import InstallRegistry
from .core.config import SettingsStore
from .core.i18n import Translator
from .core.logging import setup_logging
from .core.paths import PathManager
from .core.platform import current_platform
from .installer.downloader import DownloadManager
from .installer.manager import AppInstaller
from .installer.verifier import ReleaseVerifier
from .updater.updater import SelfUpdater
from .version import __version__


def socket_name() -> str:
    identity = hashlib.sha256(f"{getpass.getuser()}:{sys.platform}".encode()).hexdigest()[:12]
    return f"skaylauncher-{identity}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="skaylauncher")
    parser.add_argument("--version", action="version", version=f"SkayLauncher {__version__}")
    parser.add_argument("--no-self-update", action="store_true", help="Skip the startup launcher update check")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication.instance() or QApplication(sys.argv or ["skaylauncher"])
    app.setApplicationName("SkayLauncher")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("skayinray")

    name = socket_name()
    server = QLocalServer()
    if not server.listen(name):
        client = QLocalSocket()
        client.connectToServer(name)
        if client.waitForConnected(500):
            client.write(b"show")
            client.flush()
            client.waitForBytesWritten(500)
            client.disconnectFromServer()
            return 0
        QLocalServer.removeServer(name)
        if not server.listen(name):
            return 1

    paths = PathManager()
    setup_logging(paths.logs_dir)
    settings_store = SettingsStore(paths.settings_file)
    settings = settings_store.load()
    if args.no_self_update:
        settings.check_updates_on_start = False

    translator = Translator(settings.language)
    platform_info = current_platform()
    client = GitHubClient(ResponseCache(paths.api_cache_file), token=settings.github_token)
    registry = InstallRegistry(paths.apps_file)
    downloader = DownloadManager(client, paths, ReleaseVerifier())
    installer = AppInstaller(paths, registry, downloader, platform_info)
    updater = SelfUpdater(client, paths, __version__, platform_info)

    from .ui.main_window import MainWindow

    window = MainWindow(
        settings_store=settings_store,
        paths=paths,
        client=client,
        registry=registry,
        installer=installer,
        updater=updater,
        translator=translator,
        platform_info=platform_info,
    )
    server.newConnection.connect(window.activate_from_single_instance)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
