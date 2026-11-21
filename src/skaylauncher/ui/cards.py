"""Application cards with smart actions and animated hover borders."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.i18n import Translator
from ..core.models import InstalledApp, Release, Repository, ReleaseAsset
from ..core.platform import choose_asset, current_platform
from .theme import theme_palette

AssetCheck = Callable[[Release | None], ReleaseAsset | None]


class AppCard(QFrame):
    """One repository entry with install, launch, update and menu actions."""

    install_requested = Signal(str)
    launch_requested = Signal(str)
    update_requested = Signal(str)
    notes_requested = Signal(str)
    folder_requested = Signal(str)
    reinstall_requested = Signal(str)
    uninstall_requested = Signal(str)
    github_requested = Signal(str)

    def __init__(
        self,
        translator: Translator,
        parent: QWidget | None = None,
        asset_check: AssetCheck | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("appCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumWidth(240)
        self._translator = translator
        self._asset_check: AssetCheck = asset_check or self._default_asset_check

        palette = theme_palette("midnight")
        self._normal_border = QColor(palette["border"])
        self._hover_border = QColor(palette["accent"])
        self._border_color = QColor(self._normal_border)
        self._border_animation = QPropertyAnimation(self, b"borderColor", self)
        self._border_animation.setDuration(170)
        self._border_animation.setEasingCurve(QEasingCurve.OutCubic)

        self._repo: Repository | None = None
        self._installed: InstalledApp | None = None
        self._update_available = False
        self._new = False
        self._asset_available = False
        self._busy = False
        self._action = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(9)

        top = QHBoxLayout()
        top.setSpacing(10)
        self._name_label = QLabel("", self)
        self._name_label.setObjectName("cardTitle")
        self._name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._badge_label = QLabel("", self)
        self._badge_label.setObjectName("badge")
        self._badge_label.hide()
        top.addWidget(self._name_label, 1)
        top.addWidget(self._badge_label, 0, Qt.AlignTop)
        layout.addLayout(top)

        self._description_label = QLabel("", self)
        self._description_label.setObjectName("description")
        self._description_label.setWordWrap(True)
        self._description_label.setMaximumHeight(36)
        layout.addWidget(self._description_label)

        self._topics_label = QLabel("", self)
        self._topics_label.setObjectName("topics")
        self._topics_label.setWordWrap(True)
        layout.addWidget(self._topics_label)

        versions = QHBoxLayout()
        versions.setSpacing(14)
        self._installed_label = QLabel("", self)
        self._installed_label.setObjectName("versionLabel")
        self._latest_label = QLabel("", self)
        self._latest_label.setObjectName("versionLabel")
        versions.addWidget(self._installed_label)
        versions.addWidget(self._latest_label, 1, Qt.AlignRight)
        layout.addLayout(versions)

        self._progress = QProgressBar(self)
        self._progress.setObjectName("cardProgress")
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.hide()
        layout.addWidget(self._progress)

        self._speed_label = QLabel("", self)
        self._speed_label.setObjectName("speedLabel")
        self._speed_label.hide()
        layout.addWidget(self._speed_label)

        layout.addStretch(1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self._primary_button = QPushButton("", self)
        self._primary_button.setObjectName("primaryButton")
        self._primary_button.setMinimumHeight(38)
        self._primary_button.clicked.connect(self._on_primary_clicked)
        self._menu_button = QToolButton(self)
        self._menu_button.setObjectName("menuButton")
        self._menu_button.setText("\u2026")
        self._menu_button.setPopupMode(QToolButton.InstantPopup)
        bottom.addWidget(self._primary_button, 1)
        bottom.addWidget(self._menu_button, 0)
        layout.addLayout(bottom)

    def get_border_color(self) -> QColor:
        return QColor(self._border_color)

    def set_border_color(self, color: QColor) -> None:
        self._border_color = QColor(color)
        self.update()

    borderColor = Property(QColor, get_border_color, set_border_color)

    def set_border_colors(self, normal: QColor, hover: QColor) -> None:
        self._normal_border = QColor(normal)
        self._hover_border = QColor(hover)
        self._border_animation.stop()
        self._border_color = QColor(self._normal_border)
        self.update()

    def set_repo(
        self,
        repo: Repository,
        installed: InstalledApp | None,
        update_available: bool,
        new: bool = False,
    ) -> None:
        self._repo = repo
        self._installed = installed
        self._update_available = bool(update_available)
        self._new = bool(new)
        self._asset_available = repo.release is not None and self._asset_check(repo.release) is not None

        self._name_label.setText(repo.name)
        self._name_label.setToolTip(repo.full_name or repo.name)
        description = repo.description or ""
        self._description_label.setText(description)
        self._description_label.setToolTip(description)
        self._description_label.setVisible(bool(description))

        topics = "  ".join(f"#{topic}" for topic in repo.topics[:6])
        self._topics_label.setText(topics)
        self._topics_label.setVisible(bool(topics))

        if installed is not None:
            self._installed_label.setText(self._translator.tr("version.installed", version=installed.version))
        else:
            self._installed_label.setText("")
        if repo.release is not None:
            self._latest_label.setText(self._translator.tr("version.latest", version=repo.release.version))
        else:
            self._latest_label.setText(self._translator.tr("version.none"))

        self._update_badges()
        self._build_menu()
        self._update_primary_button()

    def set_asset_check(self, check: AssetCheck) -> None:
        """Set the function used to decide whether a release asset is installable."""

        self._asset_check = check

    @staticmethod
    def _default_asset_check(release: Release | None) -> ReleaseAsset | None:
        try:
            return choose_asset(release, current_platform())
        except RuntimeError:
            return release.assets[0] if release is not None and release.assets else None

    def set_progress(self, downloaded: int, total: int, elapsed: float) -> None:
        downloaded = max(0, int(downloaded))
        total = max(0, int(total))
        percent = 0 if total == 0 else min(100, int(downloaded * 100 / total))
        self._progress.setValue(percent)
        self._progress.setVisible(True)

        rate = downloaded / elapsed if elapsed > 0 else 0.0
        remaining = int((total - downloaded) / rate) if rate > 0 and total > 0 else 0
        self._speed_label.setText(
            self._translator.tr("speed", speed=f"{rate / 1_000_000:.2f}", remaining=max(0, remaining))
        )
        self._speed_label.setVisible(True)

    def reset_progress(self) -> None:
        self._progress.setValue(0)
        self._progress.hide()
        self._speed_label.clear()
        self._speed_label.hide()

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self._menu_button.setEnabled(not self._busy)
        self._update_primary_button()
        if not self._busy:
            self.reset_progress()

    def retranslate(self) -> None:
        """Refresh translated labels after a language change."""

        if self._repo is None:
            return
        self.set_repo(self._repo, self._installed, self._update_available, self._new)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self._border_color)
        pen.setWidthF(1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 13, 13)

    def enterEvent(self, event) -> None:
        self._animate_border(self._hover_border)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate_border(self._normal_border)
        super().leaveEvent(event)

    def _animate_border(self, target: QColor) -> None:
        self._border_animation.stop()
        self._border_animation.setStartValue(QColor(self._border_color))
        self._border_animation.setEndValue(QColor(target))
        self._border_animation.start()

    def _update_badges(self) -> None:
        labels: list[str] = []
        if self._update_available and self._asset_available:
            labels.append(self._translator.tr("badge.update"))
        elif self._installed is not None:
            labels.append(
                self._translator.tr("badge.discovered" if self._installed.discovered else "badge.installed")
            )
        if self._new:
            labels.append(self._translator.tr("badge.new"))
        self._badge_label.setText("  ".join(labels))
        self._badge_label.setVisible(bool(labels))

    def _update_primary_button(self) -> None:
        if self._repo is None:
            self._primary_button.setEnabled(False)
            return
        if self._busy:
            self._primary_button.setText(self._translator.tr("button.installing"))
            self._primary_button.setEnabled(False)
            self._action = ""
            return

        repo = self._repo
        can_update = self._update_available and self._asset_available and self._installed is not None
        if can_update:
            assert self._installed is not None and repo.release is not None
            self._action = "update"
            self._primary_button.setText(
                f"{self._translator.tr('button.update')} "
                f"(v{self._installed.version} -> v{repo.release.version})"
            )
            self._primary_button.setEnabled(True)
        elif self._installed is not None:
            self._action = "launch"
            self._primary_button.setText(self._translator.tr("button.launch"))
            self._primary_button.setEnabled(True)
        elif self._asset_available:
            self._action = "install"
            self._primary_button.setText(self._translator.tr("button.install"))
            self._primary_button.setEnabled(True)
        else:
            self._action = ""
            self._primary_button.setText(self._translator.tr("button.unavailable"))
            self._primary_button.setEnabled(False)

    def _build_menu(self) -> None:
        previous = self._menu_button.menu()
        if previous is not None:
            previous.deleteLater()
        repo = self._repo
        menu = QMenu(self)
        self._add_menu_action(menu, self._translator.tr("menu.notes"), self.notes_requested)
        self._add_menu_action(menu, self._translator.tr("menu.github"), self.github_requested)
        if repo is None:
            self._menu_button.setMenu(menu)
            return

        menu.addSeparator()
        if self._installed is not None:
            self._add_menu_action(menu, self._translator.tr("menu.open_folder"), self.folder_requested)
            reinstall = self._add_menu_action(menu, self._translator.tr("menu.reinstall"), self.reinstall_requested)
            reinstall.setEnabled(self._asset_available)
            action_key = "menu.forget" if self._installed.discovered else "menu.uninstall"
            self._add_menu_action(menu, self._translator.tr(action_key), self.uninstall_requested)
        self._menu_button.setMenu(menu)

    def _add_menu_action(self, menu: QMenu, text: str, signal: Signal) -> QAction:
        action = menu.addAction(text)
        repo_name = self._repo.name if self._repo is not None else ""
        action.triggered.connect(lambda _checked=False, name=repo_name: signal.emit(name))
        return action

    def _on_primary_clicked(self) -> None:
        if self._repo is None or not self._action:
            return
        name = self._repo.name
        if self._action == "install":
            self.install_requested.emit(name)
        elif self._action == "launch":
            self.launch_requested.emit(name)
        elif self._action == "update":
            self.update_requested.emit(name)
