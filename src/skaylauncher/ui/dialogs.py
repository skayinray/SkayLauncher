"""Settings, release notes and self-update dialogs."""

from __future__ import annotations

import html
import re
from dataclasses import replace
from urllib.parse import urlparse

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..core.config import Settings, SettingsStore
from ..core.i18n import SUPPORTED_LANGUAGES, SUPPORTED_THEMES, Translator
from ..updater.updater import UpdateCheck
from .widgets import SectionLabel

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_BULLET_RE = re.compile(r"^[-*+]\s+(.+)$")
_ORDERED_RE = re.compile(r"^\d+[.)]\s+(.+)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", re.IGNORECASE)
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")


def _inline_html(text: str) -> str:
    escaped = html.escape(text, quote=True)

    def link(match: re.Match[str]) -> str:
        label = match.group(1)
        url = match.group(2)
        parsed = urlparse(html.unescape(url))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return label
        return f'<a href="{url}">{label}</a>'

    escaped = _LINK_RE.sub(link, escaped)
    escaped = _CODE_RE.sub(r"<code>\1</code>", escaped)
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    return escaped


def render_release_notes(body: str) -> str:
    """Convert a markdown subset to escaped HTML suitable for QTextBrowser."""

    lines = (body or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parts: list[str] = []
    paragraph: list[str] = []
    code: list[str] = []
    list_type: str | None = None
    in_code = False

    def flush_paragraph() -> None:
        if paragraph:
            parts.append(f"<p>{'<br>'.join(_inline_html(line) for line in paragraph)}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_type
        if list_type is not None:
            parts.append(f"</{list_type}>")
            list_type = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                parts.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
                code.clear()
                in_code = False
            else:
                flush_paragraph()
                close_list()
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        if not stripped:
            flush_paragraph()
            close_list()
            continue

        heading = _HEADING_RE.match(stripped)
        if heading is not None:
            flush_paragraph()
            close_list()
            level = 2 if len(heading.group(1)) <= 2 else 3
            parts.append(f"<h{level}>{_inline_html(heading.group(2))}</h{level}>")
            continue

        bullet = _BULLET_RE.match(stripped)
        ordered = _ORDERED_RE.match(stripped)
        if bullet is not None or ordered is not None:
            flush_paragraph()
            kind = "ul" if bullet is not None else "ol"
            if list_type != kind:
                close_list()
                parts.append(f"<{kind}>")
                list_type = kind
            item = bullet if bullet is not None else ordered
            assert item is not None
            parts.append(f"<li>{_inline_html(item.group(1))}</li>")
            continue

        close_list()
        paragraph.append(stripped)

    if in_code:
        parts.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
    flush_paragraph()
    close_list()
    return "".join(parts)


render_markdown = render_release_notes


class SettingsDialog(QDialog):
    """Edit and persist application settings."""

    def __init__(
        self,
        settings_store: SettingsStore,
        translator: Translator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = settings_store
        self._translator = translator
        self._settings: Settings = settings_store.load()
        self.saved_settings: Settings | None = None

        self.setWindowTitle(translator.tr("settings.title"))
        self.setMinimumWidth(360)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 18)
        outer.setSpacing(14)
        outer.addWidget(SectionLabel(translator.tr("settings.title"), self))

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._language_combo = QComboBox(self)
        for code, label in SUPPORTED_LANGUAGES.items():
            self._language_combo.addItem(label, code)
        self._language_combo.setCurrentIndex(max(0, self._language_combo.findData(self._settings.language)))

        self._theme_combo = QComboBox(self)
        for name, label in SUPPORTED_THEMES.items():
            self._theme_combo.addItem(label, name)
        self._theme_combo.setCurrentIndex(max(0, self._theme_combo.findData(self._settings.theme)))

        self._forks_check = QCheckBox(translator.tr("settings.forks"), self)
        self._forks_check.setChecked(self._settings.include_forks)
        self._startup_check = QCheckBox(translator.tr("settings.startup_update"), self)
        self._startup_check.setChecked(self._settings.check_updates_on_start)
        self._tray_check = QCheckBox(translator.tr("settings.tray"), self)
        self._tray_check.setChecked(self._settings.minimize_to_tray)
        self._notifications_check = QCheckBox(translator.tr("settings.notifications"), self)
        self._notifications_check.setChecked(self._settings.show_notifications)

        self._refresh_spin = QSpinBox(self)
        self._refresh_spin.setRange(1, 1440)
        self._refresh_spin.setValue(self._settings.refresh_minutes)

        self._token_edit = QLineEdit(self._settings.github_token, self)
        self._token_edit.setEchoMode(QLineEdit.Password)

        form.addRow(translator.tr("settings.language"), self._language_combo)
        form.addRow(translator.tr("settings.theme"), self._theme_combo)
        form.addRow(self._forks_check)
        form.addRow(self._startup_check)
        form.addRow(self._tray_check)
        form.addRow(self._notifications_check)
        form.addRow(translator.tr("settings.refresh"), self._refresh_spin)
        form.addRow(translator.tr("settings.token"), self._token_edit)
        outer.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        save_button = buttons.button(QDialogButtonBox.Save)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if save_button is not None:
            save_button.setText(translator.tr("settings.save"))
        if cancel_button is not None:
            cancel_button.setText(translator.tr("settings.cancel"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _save(self) -> None:
        updated = replace(
            self._settings,
            language=str(self._language_combo.currentData() or "en"),
            theme=str(self._theme_combo.currentData() or "midnight"),
            include_forks=self._forks_check.isChecked(),
            check_updates_on_start=self._startup_check.isChecked(),
            minimize_to_tray=self._tray_check.isChecked(),
            show_notifications=self._notifications_check.isChecked(),
            refresh_minutes=int(self._refresh_spin.value()),
            github_token=self._token_edit.text().strip(),
        )
        self._store.save(updated)
        self.saved_settings = updated
        self.accept()


class ReleaseNotesDialog(QDialog):
    """Display a sanitized subset of release markdown."""

    def __init__(
        self,
        name: str,
        body: str,
        translator: Translator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(translator.tr("notes.title", name=name))
        self.resize(640, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        browser = QTextBrowser(self)
        browser.setHtml(render_release_notes(body))
        browser.setOpenExternalLinks(True)
        layout.addWidget(browser, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close_button = QPushButton(translator.tr("settings.cancel"), self)
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)


class UpdateDialog(QDialog):
    """Show launcher update details and download progress."""

    install_requested = Signal()

    def __init__(
        self,
        check: UpdateCheck,
        translator: Translator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setWindowTitle(translator.tr("app.title"))
        self.resize(620, 460)
        self._check = check

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self._message = QLabel(translator.tr("update.available", version=check.version), self)
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.hide()
        layout.addWidget(self._progress)

        browser = QTextBrowser(self)
        browser.setHtml(render_release_notes(check.release.body if check.release else ""))
        browser.setOpenExternalLinks(True)
        layout.addWidget(browser, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close_button = QPushButton(translator.tr("settings.cancel"), self)
        close_button.clicked.connect(self.reject)
        self._install_button = QPushButton(translator.tr("button.update"), self)
        self._install_button.setObjectName("primaryButton")
        self._install_button.clicked.connect(self.install_requested.emit)
        buttons.addWidget(close_button)
        buttons.addWidget(self._install_button)
        layout.addLayout(buttons)

    def set_progress(self, downloaded: int, total: int) -> None:
        self._progress.show()
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(max(0, min(total, int(downloaded))))
        else:
            self._progress.setRange(0, 0)

    def set_busy(self, busy: bool) -> None:
        self._install_button.setEnabled(not busy)
        self._install_button.setText(
            self._translator.tr("button.installing") if busy else self._translator.tr("button.update")
        )
        if busy:
            self._progress.show()
            self._progress.setRange(0, 0)

    def set_error(self, error: str) -> None:
        self._progress.setRange(0, 100)
        self._message.setText(self._translator.tr("update.failed", error=error))
        self.set_busy(False)

    def set_finished(self) -> None:
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self._message.setText(self._translator.tr("update.installed"))
        self._install_button.setEnabled(False)


__all__ = [
    "ReleaseNotesDialog",
    "SettingsDialog",
    "UpdateDialog",
    "render_markdown",
    "render_release_notes",
]
