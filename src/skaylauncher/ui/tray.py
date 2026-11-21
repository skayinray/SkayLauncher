"""System tray integration with an installed applications submenu."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from ..core.i18n import Translator
from ..core.models import InstalledApp
from .theme import theme_palette


class TrayController(QSystemTrayIcon):
    """Tray icon whose actions are delivered as Qt signals."""

    open_requested = Signal()
    quit_requested = Signal()
    launched = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        translator: Translator | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator or Translator()

        self._open_action = QAction(self._translator.tr("tray.open"), self)
        self._quit_action = QAction(self._translator.tr("tray.quit"), self)
        self._open_action.triggered.connect(self.open_requested.emit)
        self._quit_action.triggered.connect(self.quit_requested.emit)

        menu = QMenu()
        menu.addAction(self._open_action)
        self._apps_menu = menu.addMenu(self._translator.tr("tray.installed"))
        menu.addSeparator()
        menu.addAction(self._quit_action)
        self.setContextMenu(menu)
        self.setIcon(QIcon(self._build_icon()))
        self.activated.connect(self._on_activated)

    def set_apps(
        self,
        installed_apps: Iterable[InstalledApp] | dict[str, InstalledApp],
        translator: Translator | None = None,
    ) -> None:
        """Rebuild the installed apps submenu."""

        if translator is not None:
            self._translator = translator
        self._open_action.setText(self._translator.tr("tray.open"))
        self._quit_action.setText(self._translator.tr("tray.quit"))
        self._apps_menu.setTitle(self._translator.tr("tray.installed"))
        self._apps_menu.clear()

        apps = list(installed_apps.values()) if isinstance(installed_apps, dict) else list(installed_apps)
        if not apps:
            empty = self._apps_menu.addAction(self._translator.tr("empty.installed"))
            empty.setEnabled(False)
            return
        for app in apps:
            action = self._apps_menu.addAction(f"{app.repo}  v{app.version}")
            action.triggered.connect(lambda _checked=False, repo=app.repo: self.launched.emit(repo))

    def notify(self, title: str, message: str) -> bool:
        if not self.isSystemTrayAvailable() or not self.supportsMessages():
            return False
        self.showMessage(title, message, QSystemTrayIcon.Information, 4500)
        return True

    def show_tray(self) -> bool:
        if not self.isSystemTrayAvailable():
            return False
        self.show()
        return True

    def hide_tray(self) -> None:
        self.hide()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.open_requested.emit()

    @staticmethod
    def _build_icon() -> QPixmap:
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        palette = theme_palette("midnight")
        gradient = QLinearGradient(0, 0, size, size)
        gradient.setColorAt(0.0, QColor(palette["accent"]))
        gradient.setColorAt(1.0, QColor(palette["accent_alt"]))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRect(2, 2, size - 4, size - 4), 15, 15)

        font = QFont()
        font.setBold(True)
        font.setPointSize(32)
        painter.setFont(font)
        painter.setPen(QColor(palette["accent_text"]))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "S")
        painter.end()
        return pixmap


__all__ = ["TrayController"]
