"""Main launcher window: repository browsing, actions and self-update."""

from __future__ import annotations

import json
import time
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from ..api.github import GitHubClient
from ..api.releases import parse_repositories
from ..core.apps import InstallRegistry
from ..core.atomic import atomic_write_json
from ..core.config import Settings, SettingsStore
from ..core.discovery import InstalledAppDiscovery, load_ignored, save_ignored
from ..core.i18n import Translator
from ..core.models import InstalledApp, PlatformInfo, Release, ReleaseAsset, Repository, compare_versions
from ..core.paths import PathManager
from ..core.platform import choose_asset
from ..installer.manager import AppInstaller
from ..updater.updater import SelfUpdater, UpdateCheck
from .cards import AppCard
from .dialogs import ReleaseNotesDialog, SettingsDialog, UpdateDialog
from .theme import build_stylesheet, theme_palette
from .tray import TrayController
from .widgets import EmptyState, FramelessWindow, show_toast
from .workers import TaskRunner

TABS = ("all", "installed", "updates")
CARD_MIN_WIDTH = 240
CARD_SPACING = 14
SIDEBAR_WIDE = 232
SIDEBAR_NARROW = 172


def grid_columns(width: int) -> int:
    """Number of card columns that fit in ``width`` pixels."""

    needed = CARD_MIN_WIDTH + CARD_SPACING
    return max(1, min(3, (max(0, width) + CARD_SPACING) // needed))


class MainWindow(FramelessWindow):
    """Primary launcher UI built on a frameless, shadowed container."""

    def __init__(
        self,
        settings_store: SettingsStore,
        paths: PathManager,
        client: GitHubClient,
        registry: InstallRegistry,
        installer: AppInstaller,
        updater: SelfUpdater,
        translator: Translator,
        platform_info: PlatformInfo,
        parent=None,
    ) -> None:
        super().__init__(translator.tr("app.title"), parent)
        self._settings_store = settings_store
        self._paths = paths
        self._client = client
        self._registry = registry
        self._installer = installer
        self._updater = updater
        self._translator = translator
        self._platform_info = platform_info

        self._settings: Settings = settings_store.load()
        if self._translator.language != self._settings.language:
            self._translator.set_language(self._settings.language)
        self._client.token = self._settings.github_token.strip()

        self._force_quit = False
        self._runner = TaskRunner(self)
        self._repos: list[Repository] = []
        self._cards: dict[str, AppCard] = {}
        self._states: dict[str, tuple[InstalledApp | None, ReleaseAsset | None, bool]] = {}
        self._new_names: set[str] = set()
        self._busy_repos: set[str] = set()
        self._active_tab = "all"
        self._visible_names: set[str] = set()
        self._columns = 0
        self._refresh_active = False
        self._update_checked = False
        self._update_check: UpdateCheck | None = None
        self._update_dialog: UpdateDialog | None = None
        self._status_key = "status.ready"
        self._status_values: dict[str, Any] = {}
        self._fade_token = 0
        self._fade_out: QPropertyAnimation | None = None
        self._fade_in: QPropertyAnimation | None = None

        self._known_initialized = self._paths.known_repos_file.exists()
        self._known_repo_ids = self._load_known_ids()
        self._known_releases = self._load_known_releases()
        self._discovery = InstalledAppDiscovery(platform_info)

        self.setMinimumSize(640, 460)
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        width = min(1160, available.width() - 48) if available else 1160
        height = min(780, available.height() - 48) if available else 780
        self.resize(max(640, width), max(460, height))
        self._build_interface()
        self._apply_stylesheet()

        self._tray = TrayController(self, self._translator)
        self._tray.set_apps(self._registry.load(), self._translator)
        self._tray.open_requested.connect(self.activate_from_single_instance)
        self._tray.quit_requested.connect(self.force_quit)
        self._tray.launched.connect(self._launch_app)
        self._tray.show_tray()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(max(1, self._settings.refresh_minutes) * 60_000)
        self._refresh_timer.timeout.connect(self.refresh_repositories)
        self._refresh_timer.start()

        self._set_status("status.ready")
        QTimer.singleShot(0, self.refresh_repositories)
        QTimer.singleShot(0, self.discover_installed)
        if self._settings.check_updates_on_start:
            QTimer.singleShot(0, self._check_self_update)

    def _tr(self, key: str, **values: Any) -> str:
        return self._translator.tr(key, **values)

    def _build_interface(self) -> None:
        main = QWidget(self)
        main.setObjectName("mainPanel")
        root = QHBoxLayout(main)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        sidebar = QFrame(main)
        self._sidebar = sidebar
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(SIDEBAR_NARROW)
        sidebar.setMaximumWidth(SIDEBAR_WIDE)
        sidebar.setFixedWidth(SIDEBAR_WIDE)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 18, 14, 16)
        sidebar_layout.setSpacing(12)

        brand = QLabel(self._tr("app.title"), sidebar)
        brand.setObjectName("brandLabel")
        sidebar_layout.addWidget(brand)
        separator = QFrame(sidebar)
        separator.setObjectName("separator")
        separator.setFixedHeight(1)
        sidebar_layout.addWidget(separator)

        self._nav_buttons: dict[str, QPushButton] = {}
        nav_group = QButtonGroup(sidebar)
        nav_group.setExclusive(True)
        for key, label_key in (("all", "tab.all"), ("installed", "tab.installed"), ("updates", "tab.updates")):
            button = QPushButton(self._tr(label_key), sidebar)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setChecked(key == "all")
            button.clicked.connect(lambda _checked=False, tab=key: self._select_tab(tab))
            nav_group.addButton(button)
            self._nav_buttons[key] = button
            sidebar_layout.addWidget(button)
        self._nav_group = nav_group

        sidebar_layout.addStretch(1)
        self._status_label = QLabel("", sidebar)
        self._status_label.setObjectName("statusLabel")
        self._status_label.setWordWrap(True)
        sidebar_layout.addWidget(self._status_label)

        self._refresh_button = QPushButton("\u21bb", sidebar)
        self._refresh_button.setObjectName("iconButton")
        self._refresh_button.setToolTip(self._tr("status.refreshing"))
        self._refresh_button.clicked.connect(self.refresh_repositories)
        self._settings_button = QPushButton(self._tr("settings.title"), sidebar)
        self._settings_button.clicked.connect(self._open_settings)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self._refresh_button)
        actions.addWidget(self._settings_button, 1)
        sidebar_layout.addLayout(actions)

        root.addWidget(sidebar)

        right = QWidget(main)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        self._search_edit = QLineEdit(right)
        self._search_edit.setObjectName("searchEdit")
        self._search_edit.setPlaceholderText(self._tr("search.placeholder"))
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search_changed)
        self._count_label = QLabel("", right)
        self._count_label.setObjectName("countLabel")
        self._count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        toolbar.addWidget(self._search_edit, 1)
        toolbar.addWidget(self._count_label, 0)
        right_layout.addLayout(toolbar)

        self._scroll_area = QScrollArea(right)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._view_stack = QStackedWidget(self._scroll_area)
        self._view_effect = QGraphicsOpacityEffect(self._view_stack)
        self._view_effect.setOpacity(1.0)
        self._view_stack.setGraphicsEffect(self._view_effect)

        grid_page = QWidget(self._view_stack)
        self._grid_layout = QGridLayout(grid_page)
        self._grid_layout.setContentsMargins(2, 2, 4, 2)
        self._grid_layout.setHorizontalSpacing(CARD_SPACING)
        self._grid_layout.setVerticalSpacing(CARD_SPACING)
        self._grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._empty_state = EmptyState(self._tr("empty.all"), self._view_stack)
        self._view_stack.addWidget(grid_page)
        self._view_stack.addWidget(self._empty_state)
        self._view_stack.setCurrentWidget(grid_page)
        self._grid_page = grid_page
        self._empty_page = self._empty_state

        self._scroll_area.setWidget(self._view_stack)
        right_layout.addWidget(self._scroll_area, 1)
        root.addWidget(right, 1)
        self.set_content(main)

    def _apply_stylesheet(self) -> None:
        application = QApplication.instance()
        if application is not None:
            application.setStyleSheet(build_stylesheet(self._settings.theme))

    def _card_border_colors(self) -> tuple[QColor, QColor]:
        palette = theme_palette(self._settings.theme)
        return QColor(palette["border"]), QColor(palette["accent"])

    def _set_status(self, key: str, **values: Any) -> None:
        self._status_key = key
        self._status_values = dict(values)
        self._status_label.setText(self._tr(key, **values))

    def _make_card(self, name: str) -> AppCard:
        card = AppCard(self._translator, self, asset_check=self._asset_check)
        card.install_requested.connect(self._install_app)
        card.update_requested.connect(self._update_app)
        card.launch_requested.connect(self._launch_app)
        card.notes_requested.connect(self._show_notes)
        card.folder_requested.connect(self._open_folder)
        card.reinstall_requested.connect(self._reinstall_app)
        card.uninstall_requested.connect(self._uninstall_app)
        card.github_requested.connect(self._open_github)
        normal, hover = self._card_border_colors()
        card.set_border_colors(normal, hover)
        return card

    def _asset_check(self, release: Release | None) -> ReleaseAsset | None:
        return choose_asset(release, self._platform_info)

    def _state_for(
        self,
        repo: Repository,
        installed_map: dict[str, InstalledApp],
    ) -> tuple[InstalledApp | None, ReleaseAsset | None, bool]:
        installed = installed_map.get(repo.name.lower())
        asset = choose_asset(repo.release, self._platform_info)
        update_available = bool(
            installed is not None
            and repo.release is not None
            and asset is not None
            and compare_versions(repo.release.version, installed.version) > 0
        )
        return installed, asset, update_available

    def _load_known_ids(self) -> set[str]:
        path = self._paths.known_repos_file
        if not path.exists():
            return set()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        if isinstance(payload, dict):
            payload = payload.get("repos", [])
        if not isinstance(payload, list):
            return set()
        return {str(item) for item in payload}

    def _load_known_releases(self) -> dict[str, str]:
        path = self._paths.data_dir / "known-releases.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items()}

    def _save_known(self) -> None:
        atomic_write_json(self._paths.known_repos_file, sorted(self._known_repo_ids))
        atomic_write_json(self._paths.data_dir / "known-releases.json", self._known_releases)

    def _compute_notifications(self, repos: list[Repository]) -> tuple[set[str], set[str]]:
        new_ids: set[str] = set()
        changed_names: set[str] = set()
        if not self._known_initialized:
            self._known_initialized = True
        else:
            new_ids = {str(repo.id) for repo in repos if str(repo.id) not in self._known_repo_ids}
            for repo in repos:
                current_tag = repo.release.tag if repo.release else ""
                previous_tag = self._known_releases.get(repo.name, "")
                if not current_tag or not previous_tag or current_tag == previous_tag:
                    continue
                previous_version = previous_tag[1:] if previous_tag[:1] in {"v", "V"} else previous_tag
                if repo.release is not None and compare_versions(repo.release.version, previous_version) > 0:
                    changed_names.add(repo.name)

        self._known_repo_ids.update(str(repo.id) for repo in repos)
        for repo in repos:
            if repo.release is not None:
                self._known_releases[repo.name] = repo.release.tag
        self._save_known()
        return new_ids, changed_names

    def _notify(self, message: str) -> None:
        show_toast(self, message)
        if self._settings.show_notifications:
            title = f"{self._tr('badge.new')} {self._tr('app.title')}"
            self._tray.notify(title, message)

    def refresh_repositories(self) -> None:
        if self._refresh_active:
            return
        self._refresh_active = True
        self._refresh_button.setEnabled(False)
        self._set_status("status.refreshing")

        def job() -> list[Repository]:
            include_forks = self._settings.include_forks
            payloads = self._client.list_repositories(include_forks=include_forks)
            releases: dict[str, dict[str, Any] | None] = {}
            for payload in payloads:
                name = str(payload.get("name") or "")
                if name:
                    releases[name] = self._client.get_latest_release(name)
            return parse_repositories(payloads, releases, include_forks=include_forks)

        self._runner.submit(
            job,
            on_result=self._on_refresh_done,
            on_error=self._on_refresh_error,
        )

    def _on_refresh_done(self, repos: list[Repository]) -> None:
        self._refresh_active = False
        self._refresh_button.setEnabled(True)
        new_ids, changed_names = self._compute_notifications(repos)
        self._apply_repositories(repos, new_ids, changed_names)
        self._set_status("status.updated")
        self._update_tray_apps()
        self.discover_installed()

    def discover_installed(self) -> None:
        """Find apps installed outside the launcher and refresh their state."""
        if not self._repos:
            return

        def job() -> None:
            ignored = load_ignored(self._paths.ignored_apps_file)
            found = [
                record
                for record in self._discovery.discover(self._repos)
                if record.repo.lower() not in ignored
            ]
            self._registry.sync_discovered(found)

        self._runner.submit(job, on_result=lambda _result: self._reload_states())

    def _on_refresh_error(self, message: str) -> None:
        self._refresh_active = False
        self._refresh_button.setEnabled(True)
        self._set_status("status.error", error=message)
        show_toast(self, self._tr("status.error", error=message), ok=False)

    def _apply_repositories(
        self,
        repos: list[Repository],
        new_ids: set[str] | None = None,
        changed_names: set[str] | None = None,
    ) -> None:
        self._repos = list(repos)
        if new_ids is not None or changed_names is not None:
            self._new_names = {
                repo.name for repo in repos if str(repo.id) in (new_ids or set())
            }
            for repo in repos:
                if repo.name in (changed_names or set()):
                    self._new_names.add(repo.name)

        installed_map = self._registry.load()
        self._states = {repo.name: self._state_for(repo, installed_map) for repo in repos}
        active_names = {repo.name for repo in repos}
        for name, card in list(self._cards.items()):
            if name not in active_names:
                self._grid_layout.removeWidget(card)
                card.setParent(None)
                card.deleteLater()
                self._cards.pop(name, None)

        normal, hover = self._card_border_colors()
        for repo in repos:
            card = self._cards.get(repo.name)
            if card is None:
                card = self._make_card(repo.name)
                self._cards[repo.name] = card
            installed, _asset, update_available = self._states[repo.name]
            card.set_repo(repo, installed, update_available, repo.name in self._new_names)
            card.set_border_colors(normal, hover)
        self._apply_filter(animate=False)

        for repo in repos:
            if str(repo.id) in (new_ids or set()):
                self._notify(self._tr("notify.new_repo", name=repo.name))
            if repo.name in (changed_names or set()) and repo.release is not None:
                self._notify(
                    self._tr("notify.new_release", name=repo.name, version=repo.release.version)
                )

    def _visible_repositories(self) -> list[Repository]:
        query = self._search_edit.text().strip().casefold()
        result: list[Repository] = []
        for repo in self._repos:
            installed, _asset, update_available = self._states.get(
                repo.name, (None, None, False)
            )
            if self._active_tab == "installed" and installed is None:
                continue
            if self._active_tab == "updates" and not update_available:
                continue
            if query:
                haystack = " ".join((repo.name, repo.full_name, repo.description, *repo.topics)).casefold()
                if query not in haystack:
                    continue
            result.append(repo)
        return result

    def _apply_filter(self, animate: bool = False) -> None:
        visible = self._visible_repositories()
        self._visible_names = {repo.name for repo in visible}
        self._relayout_grid()
        self._count_label.setText(f"{len(visible)} / {len(self._repos)}")
        target = self._grid_page if visible else self._empty_page
        if not visible:
            key = f"empty.{self._active_tab}"
            self._empty_state.set_text(self._tr(key))

        if animate and self._view_stack.currentWidget() is not target:
            self._fade_token += 1
            token = self._fade_token
            effect = self._view_effect
            if self._fade_out is not None:
                self._fade_out.stop()
            outgoing = QPropertyAnimation(effect, b"opacity", self)
            outgoing.setDuration(110)
            outgoing.setStartValue(effect.opacity())
            outgoing.setEndValue(0.0)
            outgoing.setEasingCurve(QEasingCurve.OutQuad)

            def finish_out() -> None:
                if token != self._fade_token:
                    return
                self._view_stack.setCurrentWidget(target)
                incoming = QPropertyAnimation(effect, b"opacity", self)
                incoming.setDuration(190)
                incoming.setStartValue(0.0)
                incoming.setEndValue(1.0)
                incoming.setEasingCurve(QEasingCurve.OutCubic)
                self._fade_in = incoming
                incoming.start()

            outgoing.finished.connect(finish_out)
            self._fade_out = outgoing
            outgoing.start()
        else:
            self._view_stack.setCurrentWidget(target)
            self._view_effect.setOpacity(1.0)

    def _relayout_grid(self) -> None:
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        visible = [repo for repo in self._repos if repo.name in self._visible_names]
        for index, repo in enumerate(visible):
            card = self._cards.get(repo.name)
            if card is None:
                continue
            row, column = divmod(index, self._columns)
            self._grid_layout.addWidget(card, row, column)
        for column in range(self._columns):
            self._grid_layout.setColumnStretch(column, 1)

    def _select_tab(self, key: str) -> None:
        if key not in TABS or key == self._active_tab:
            return
        self._active_tab = key
        for name, button in self._nav_buttons.items():
            button.setChecked(name == key)
        self._apply_filter(animate=True)

    def _on_search_changed(self, _text: str) -> None:
        self._apply_filter(animate=False)

    def _find_repo(self, name: str) -> Repository | None:
        for repo in self._repos:
            if repo.name == name:
                return repo
        return None

    def _update_tray_apps(self) -> None:
        self._tray.set_apps(self._registry.load(), self._translator)

    def _reload_states(self) -> None:
        installed_map = self._registry.load()
        self._states = {repo.name: self._state_for(repo, installed_map) for repo in self._repos}
        normal, hover = self._card_border_colors()
        for repo in self._repos:
            card = self._cards.get(repo.name)
            if card is None:
                continue
            installed, _asset, update_available = self._states[repo.name]
            card.set_repo(repo, installed, update_available, repo.name in self._new_names)
            card.set_border_colors(normal, hover)
        self._apply_filter(animate=False)
        self._update_tray_apps()

    def _install_app(self, name: str) -> None:
        self._start_install(name)

    def _update_app(self, name: str) -> None:
        self._start_install(name)

    def _reinstall_app(self, name: str) -> None:
        self._start_install(name)

    def _start_install(self, name: str) -> None:
        if name in self._busy_repos:
            return
        repo = self._find_repo(name)
        if repo is None:
            return
        _installed, asset, _update = self._states.get(name, (None, None, False))
        if repo.release is None or asset is None:
            show_toast(self, self._tr("button.unavailable"), ok=False)
            return

        card = self._cards.get(name)
        self._busy_repos.add(name)
        if card is not None:
            card.set_busy(True)
            card.set_progress(0, 0, 0.0)
        started = time.monotonic()
        release = repo.release
        companions = list(release.assets)

        def task(progress) -> InstalledApp:
            return self._installer.install(
                repo.name,
                release,
                asset=asset,
                progress=progress,
                extra_assets=companions,
            )

        def on_progress(downloaded: int, total: int) -> None:
            if card is not None:
                card.set_progress(downloaded, total, time.monotonic() - started)

        def on_done(_record: InstalledApp) -> None:
            self._busy_repos.discard(name)
            if card is not None:
                card.set_busy(False)
            self._set_status("status.updated")
            show_toast(self, f"{name}: {self._tr('status.updated')}")
            self._reload_states()

        def on_error(message: str) -> None:
            self._busy_repos.discard(name)
            if card is not None:
                card.set_busy(False)
            self._set_status("status.error", error=message)
            show_toast(self, self._tr("error.install", error=message), ok=False)

        self._runner.submit(
            task,
            with_progress=True,
            on_result=on_done,
            on_error=on_error,
            on_progress=on_progress,
        )

    def _launch_app(self, name: str) -> None:
        def task() -> bool:
            return self._installer.launch(name)

        def on_done(ok: bool) -> None:
            if not ok:
                self._set_status("status.error", error=name)
                show_toast(self, self._tr("version.none"), ok=False)
            else:
                self._set_status("status.updated")

        self._runner.submit(task, on_result=on_done, on_error=self._on_generic_error)

    def _uninstall_app(self, name: str) -> None:
        record = self._registry.get(name)
        key = "confirm.forget" if record is not None and record.discovered else "confirm.uninstall"
        answer = QMessageBox.question(
            self,
            self._tr("confirm.title"),
            self._tr(key, name=name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        def task() -> None:
            if record is not None and record.discovered:
                ignored = load_ignored(self._paths.ignored_apps_file)
                ignored.add(name.lower())
                save_ignored(self._paths.ignored_apps_file, ignored)
            self._installer.uninstall(name)

        def on_done(_result: None) -> None:
            self._set_status("status.updated")
            self._reload_states()

        self._runner.submit(task, on_result=on_done, on_error=self._on_generic_error)

    def _open_folder(self, name: str) -> None:
        def task() -> bool:
            return self._installer.open_folder(name)

        def on_done(ok: bool) -> None:
            if not ok:
                show_toast(self, self._tr("version.none"), ok=False)

        self._runner.submit(task, on_result=on_done, on_error=self._on_generic_error)

    def _show_notes(self, name: str) -> None:
        repo = self._find_repo(name)
        if repo is None:
            return
        body = repo.release.body if repo.release else self._tr("notes.no_release")
        dialog = ReleaseNotesDialog(name, body, self._translator, self)
        dialog.exec()

    def _open_github(self, name: str) -> None:
        repo = self._find_repo(name)
        if repo is not None and repo.html_url:
            QDesktopServices.openUrl(QUrl(repo.html_url))

    def _on_generic_error(self, message: str) -> None:
        self._set_status("status.error", error=message)
        show_toast(self, message, ok=False)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._settings_store, self._translator, self)
        if dialog.exec() != QDialog.Accepted or dialog.saved_settings is None:
            return
        self._apply_settings(dialog.saved_settings)

    def _apply_settings(self, settings: Settings) -> None:
        forks_changed = settings.include_forks != self._settings.include_forks
        self._settings = settings
        self._settings_store.save(settings)
        self._client.token = settings.github_token.strip()
        self._translator.set_language(settings.language)
        self._apply_stylesheet()
        self._refresh_timer.setInterval(max(1, settings.refresh_minutes) * 60_000)
        self._retranslate_static()
        normal, hover = self._card_border_colors()
        for card in self._cards.values():
            card.retranslate()
            card.set_border_colors(normal, hover)
        self._apply_filter(animate=False)
        if forks_changed:
            self.refresh_repositories()

    def _retranslate_static(self) -> None:
        self.set_title(self._tr("app.title"))
        labels = {
            "all": "tab.all",
            "installed": "tab.installed",
            "updates": "tab.updates",
        }
        for key, label_key in labels.items():
            self._nav_buttons[key].setText(self._tr(label_key))
        self._search_edit.setPlaceholderText(self._tr("search.placeholder"))
        self._refresh_button.setToolTip(self._tr("status.refreshing"))
        self._settings_button.setText(self._tr("settings.title"))
        self._set_status(self._status_key, **self._status_values)
        self._tray.set_apps(self._registry.load(), self._translator)

    def _check_self_update(self) -> None:
        self._runner.submit(
            self._updater.check,
            on_result=self._on_update_check,
            on_error=self._on_generic_error,
        )

    def _on_update_check(self, check: UpdateCheck) -> None:
        self._update_checked = True
        if not check.available:
            return
        self._update_check = check
        self._notify(self._tr("update.available", version=check.version))
        if self._update_dialog is not None:
            self._update_dialog.close()
        dialog = UpdateDialog(check, self._translator, self)
        dialog.install_requested.connect(lambda: self._install_self_update(dialog))
        dialog.show()
        self._update_dialog = dialog

    def _install_self_update(self, dialog: UpdateDialog) -> None:
        check = self._update_check
        if check is None:
            return
        dialog.set_busy(True)

        def task(progress) -> str:
            prepared = self._updater.prepare(check, progress)
            return self._updater.apply(prepared)

        def on_progress(downloaded: int, total: int) -> None:
            dialog.set_progress(downloaded, total)

        def on_done(_result: str) -> None:
            dialog.set_finished()
            self._notify(self._tr("update.installed"))

        def on_error(message: str) -> None:
            dialog.set_error(message)
            show_toast(self, self._tr("update.failed", error=message), ok=False)

        self._runner.submit(
            task,
            with_progress=True,
            on_result=on_done,
            on_error=on_error,
            on_progress=on_progress,
        )

    def activate_from_single_instance(self, *_args: Any) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def force_quit(self) -> None:
        self._force_quit = True
        self._tray.hide_tray()
        self.close()

    def closeEvent(self, event) -> None:
        if (
            not self._force_quit
            and self._settings.minimize_to_tray
            and QSystemTrayIcon.isSystemTrayAvailable()
        ):
            self.hide()
            event.ignore()
            return
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "_grid_page"):
            return
        width = self.width()
        sidebar_width = (
            SIDEBAR_WIDE if width >= 1100 else SIDEBAR_NARROW + 28 if width >= 820 else SIDEBAR_NARROW
        )
        if self._sidebar.width() != sidebar_width:
            self._sidebar.setFixedWidth(sidebar_width)
        self._count_label.setVisible(width >= 760)
        margins = self._root_layout.contentsMargins()
        body = self._body_layout.contentsMargins()
        chrome = margins.left() + margins.right() + 2 + body.left() + body.right() + 12 + 12
        available = max(0, width - chrome - sidebar_width)
        columns = grid_columns(available)
        if columns != self._columns:
            self._columns = columns
            self._relayout_grid()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)


__all__ = ["MainWindow"]
