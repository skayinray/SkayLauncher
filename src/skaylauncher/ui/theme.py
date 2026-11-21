"""Embedded dark themes. No image files or external stylesheets are used."""

from __future__ import annotations

from string import Template

THEMES: dict[str, dict[str, str]] = {
    "midnight": {
        "window": "#0a0e1c",
        "window_alt": "#111936",
        "panel": "#141d3b",
        "panel_alt": "#1b2650",
        "card": "#151e3d",
        "card_alt": "#1b2751",
        "border": "#2b3a70",
        "border_soft": "#222f5c",
        "accent": "#8b7bff",
        "accent_alt": "#4f7dff",
        "accent_text": "#0a0e1c",
        "text": "#eef1ff",
        "muted": "#9aa7d0",
        "success": "#4ade80",
        "warning": "#fbbf24",
        "danger": "#fb7185",
        "scroll": "#334474",
        "shadow": "rgba(0, 0, 0, 180)",
        "nav": "#141d3b",
        "nav_active": "#283670",
    },
    "graphite": {
        "window": "#111315",
        "window_alt": "#191c1f",
        "panel": "#202327",
        "panel_alt": "#282c31",
        "card": "#22262a",
        "card_alt": "#2b3036",
        "border": "#3d434b",
        "border_soft": "#33383f",
        "accent": "#c9d1d9",
        "accent_alt": "#8b949e",
        "accent_text": "#111315",
        "text": "#e6edf3",
        "muted": "#9ba4ae",
        "success": "#5ac37e",
        "warning": "#d9a441",
        "danger": "#e06c75",
        "scroll": "#464d56",
        "shadow": "rgba(0, 0, 0, 170)",
        "nav": "#202327",
        "nav_active": "#383e46",
    },
    "aurora": {
        "window": "#071516",
        "window_alt": "#0b2224",
        "panel": "#0e2a2c",
        "panel_alt": "#12383a",
        "card": "#0f2b2d",
        "card_alt": "#14393a",
        "border": "#1d5555",
        "border_soft": "#174546",
        "accent": "#35e0c8",
        "accent_alt": "#49c98a",
        "accent_text": "#05201f",
        "text": "#e6fff8",
        "muted": "#94c4bd",
        "success": "#5ef2a0",
        "warning": "#f4d35e",
        "danger": "#ff7d8a",
        "scroll": "#25605c",
        "shadow": "rgba(0, 0, 0, 170)",
        "nav": "#0e2a2c",
        "nav_active": "#17504b",
    },
}

_QSS_TEMPLATE = Template(
    """
QWidget { color: $text; font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif; font-size: 13px; }
QWidget#windowContainer {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 $window, stop:0.55 $window_alt, stop:1 $window);
    border: 1px solid $border;
    border-radius: 16px;
}
QWidget#bodyHost { background: transparent; }
QFrame#sidebar, QFrame#sidePanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $panel, stop:1 $window_alt);
    border: 1px solid $border_soft;
    border-radius: 14px;
}
QFrame#cardFrame, QFrame#appCard, QFrame#dialogCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $card, stop:1 $card_alt);
    border: 1px solid $border_soft;
    border-radius: 14px;
}
QFrame#separator { background: $border_soft; border: none; height: 1px; }

QLabel { color: $text; background: transparent; }
QLabel#titleLabel { font-size: 14px; font-weight: 700; letter-spacing: 0.4px; }
QLabel#brandLabel { font-size: 19px; font-weight: 800; color: $accent; }
QLabel#sectionLabel { font-size: 12px; font-weight: 700; color: $muted; letter-spacing: 1px; }
QLabel#cardTitle { font-size: 16px; font-weight: 700; }
QLabel#description, QLabel#topics, QLabel#versionLabel, QLabel#speedLabel,
QLabel#statusLabel, QLabel#countLabel { color: $muted; }
QLabel#description { font-size: 12px; }
QLabel#topics { font-size: 11px; color: $accent; }
QLabel#versionLabel { font-size: 11px; }
QLabel#speedLabel { font-size: 11px; color: $muted; }
QLabel#statusLabel { font-size: 11px; }
QLabel#badge {
    color: $accent_text; background: $accent; border-radius: 7px;
    padding: 3px 8px; font-size: 10px; font-weight: 800; letter-spacing: 0.6px;
}
QLabel#badgeNeutral { color: $muted; background: $panel_alt; border-radius: 7px; padding: 3px 8px; font-size: 10px; }
QLabel#emptyLabel { color: $muted; font-size: 14px; }

QPushButton {
    background: $panel_alt; color: $text; border: 1px solid $border;
    border-radius: 10px; padding: 8px 14px; min-height: 18px;
}
QPushButton:hover { background: $card_alt; border-color: $accent; }
QPushButton:pressed { background: $panel; }
QPushButton:disabled { color: $muted; background: $panel; border-color: $border_soft; }
QPushButton#primaryButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_alt);
    color: $accent_text; border: none; border-radius: 10px; font-weight: 700; padding: 9px 16px;
}
QPushButton#primaryButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent_alt, stop:1 $accent); }
QPushButton#primaryButton:disabled { background: $panel_alt; color: $muted; border: 1px solid $border_soft; }
QPushButton#navButton {
    background: transparent; border: 1px solid transparent; border-radius: 10px;
    padding: 10px 14px; text-align: left; color: $muted;
}
QPushButton#navButton:hover { background: $panel_alt; color: $text; }
QPushButton#navButton:checked { background: $nav_active; color: $text; border-color: $border; font-weight: 700; }

QToolButton { background: transparent; border: none; color: $muted; padding: 5px; border-radius: 8px; }
QToolButton:hover { background: $panel_alt; color: $text; }
QToolButton#windowButton { font-size: 16px; min-width: 28px; min-height: 28px; }
QToolButton#windowButton:hover { background: $border; }
QToolButton#menuButton { font-size: 18px; min-width: 32px; min-height: 30px; border: 1px solid $border; }

QLineEdit, QSpinBox, QComboBox {
    background: $window_alt; color: $text; border: 1px solid $border;
    border-radius: 10px; padding: 8px 10px; selection-background-color: $accent;
    selection-color: $accent_text;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: $accent; }
QLineEdit#searchEdit { padding-left: 14px; }
QLineEdit::placeholder { color: $muted; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: $panel; color: $text; border: 1px solid $border;
    border-radius: 8px; selection-background-color: $accent;
    selection-color: $accent_text;
}
QCheckBox { color: $text; spacing: 9px; padding: 3px 0; }
QCheckBox::indicator {
    width: 17px; height: 17px; border: 1px solid $border;
    border-radius: 5px; background: $window_alt;
}
QCheckBox::indicator:checked { background: $accent; border-color: $accent; }

QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 11px; margin: 8px 1px 8px 0; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 5px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: $accent; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 0 8px 1px 8px; }
QScrollBar::handle:horizontal { background: $scroll; border-radius: 5px; min-width: 36px; }
QScrollBar::handle:horizontal:hover { background: $accent; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

QProgressBar {
    background: $panel_alt; border: 1px solid $border; border-radius: 8px;
    height: 12px; text-align: center; color: $text; font-size: 10px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_alt);
    border-radius: 6px;
}

QMenu { background: $panel; border: 1px solid $border; border-radius: 10px; padding: 5px; }
QMenu::item { padding: 8px 24px 8px 12px; border-radius: 6px; }
QMenu::item:selected { background: $nav_active; }
QMenu::separator { height: 1px; background: $border; margin: 4px 6px; }
QTextBrowser {
    background: $window_alt; color: $text; border: 1px solid $border;
    border-radius: 10px; padding: 10px;
}
QTextBrowser a { color: $accent; }
QToolTip { background: $panel; color: $text; border: 1px solid $border; border-radius: 6px; padding: 5px; }
QMessageBox { background: $window_alt; }
QDialog { background: $window_alt; }
QStackedWidget { background: transparent; }
"""
)


def theme_palette(theme_name: str) -> dict[str, str]:
    """Return the palette for a theme, falling back to midnight."""

    return THEMES.get(theme_name, THEMES["midnight"])


def build_stylesheet(theme_name: str) -> str:
    """Build the full QSS stylesheet for a theme."""

    return _QSS_TEMPLATE.safe_substitute(theme_palette(theme_name))


def theme_names() -> list[str]:
    """Return theme names in a stable order."""

    return list(THEMES)
