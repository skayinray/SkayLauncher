"""Reusable frameless window pieces, title bar, toasts and small labels."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .theme import theme_palette


def _local_pos(event: QEvent) -> QPoint:
    getter = getattr(event, "position", None)
    if getter is not None:
        point = getter()
        return point.toPoint() if hasattr(point, "toPoint") else QPoint(int(point.x()), int(point.y()))
    return event.pos()


def _global_pos(event: QEvent) -> QPoint:
    getter = getattr(event, "globalPosition", None)
    if getter is not None:
        point = getter()
        return point.toPoint() if hasattr(point, "toPoint") else QPoint(int(point.x()), int(point.y()))
    return event.globalPos()


class TitleBar(QWidget):
    """Title row that drives a frameless window."""

    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(46)
        self.setMouseTracking(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 8, 6)
        layout.setSpacing(6)

        self._title_label = QLabel(title, self)
        self._title_label.setObjectName("titleLabel")
        self._title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self._title_label)

        self._minimize_button = QToolButton(self)
        self._minimize_button.setObjectName("windowButton")
        self._minimize_button.setText("\u2212")
        self._minimize_button.clicked.connect(self.minimize_clicked.emit)

        self._maximize_button = QToolButton(self)
        self._maximize_button.setObjectName("windowButton")
        self._maximize_button.setText("\u25a1")
        self._maximize_button.clicked.connect(self.maximize_clicked.emit)

        self._close_button = QToolButton(self)
        self._close_button.setObjectName("windowButton")
        self._close_button.setText("\u00d7")
        self._close_button.clicked.connect(self.close_clicked.emit)

        for button in (self._minimize_button, self._maximize_button, self._close_button):
            button.setCursor(Qt.ArrowCursor)
            layout.addWidget(button)

        self._drag_origin: QPoint | None = None

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def set_maximized(self, maximized: bool) -> None:
        self._maximize_button.setText("\u25a0" if maximized else "\u25a1")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            handle = self.window().windowHandle() if self.window() else None
            if handle is not None:
                handle.startSystemMove()
            else:
                self._drag_origin = _global_pos(event) - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_origin is not None and self.window() is not None:
            self.window().move(_global_pos(event) - self._drag_origin)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.maximize_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class _CornerResizeFilter(QObject):
    """Resize the host window when the lower-right container corner is dragged."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self._window = window
        self._resizing = False
        self._origin: QPoint | None = None
        self._geometry: QRect | None = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        event_type = event.type()
        handled = (
            QEvent.MouseButtonPress,
            QEvent.MouseMove,
            QEvent.MouseButtonRelease,
            QEvent.Leave,
        )
        if event_type not in handled:
            return False
        window = self._window
        if window.isMaximized() or not isinstance(watched, QWidget):
            return False
        corner = QRect(watched.rect().right() - 18, watched.rect().bottom() - 18, 18, 18)
        position = QPoint() if event_type == QEvent.Leave else _local_pos(event)

        if event_type == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if corner.contains(position):
                self._resizing = True
                self._origin = _global_pos(event)
                self._geometry = window.geometry()
                return True
        elif event_type == QEvent.MouseMove:
            if self._resizing and self._origin is not None and self._geometry is not None:
                delta = _global_pos(event) - self._origin
                width = max(window.minimumWidth(), self._geometry.width() + delta.x())
                height = max(window.minimumHeight(), self._geometry.height() + delta.y())
                window.resize(width, height)
                return True
            watched.setCursor(Qt.SizeFDiagCursor if corner.contains(position) else Qt.ArrowCursor)
        elif event_type == QEvent.MouseButtonRelease:
            if self._resizing:
                self._resizing = False
                self._origin = None
                self._geometry = None
                return True
        elif event_type == QEvent.Leave:
            watched.unsetCursor()
        return False


class FramelessWindow(QMainWindow):
    """Rounded, shadowed main window without native decorations."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._root = QWidget(self)
        self._root.setObjectName("windowRoot")
        self.setCentralWidget(self._root)
        self._root_layout = QVBoxLayout(self._root)
        self._root_layout.setContentsMargins(10, 10, 10, 10)
        self._root_layout.setSpacing(0)

        self._container = QFrame(self._root)
        self._container.setObjectName("windowContainer")
        self._container.setMouseTracking(True)
        shadow = QGraphicsDropShadowEffect(self._container)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 170))
        self._container.setGraphicsEffect(shadow)
        self._root_layout.addWidget(self._container)

        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self._title_bar = TitleBar(title, self._container)
        self._title_bar.minimize_clicked.connect(self.showMinimized)
        self._title_bar.maximize_clicked.connect(self.toggle_maximized)
        self._title_bar.close_clicked.connect(self.close)
        container_layout.addWidget(self._title_bar)

        self._body_host = QWidget(self._container)
        self._body_host.setObjectName("bodyHost")
        self._body_layout = QVBoxLayout(self._body_host)
        self._body_layout.setContentsMargins(16, 6, 16, 16)
        self._body_layout.setSpacing(14)
        container_layout.addWidget(self._body_host, 1)

        self._resize_filter = _CornerResizeFilter(self)
        self._container.installEventFilter(self._resize_filter)

    @property
    def title_bar(self) -> TitleBar:
        return self._title_bar

    @property
    def content_area(self) -> QWidget:
        return self._body_host

    def set_title(self, title: str) -> None:
        self._title_bar.set_title(title)
        self.setWindowTitle(title)

    def set_content(self, widget: QWidget) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            existing = item.widget()
            if existing is not None:
                existing.setParent(None)
        self._body_layout.addWidget(widget, 1)

    def toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self._title_bar.set_maximized(False)
        else:
            self.showMaximized()
            self._title_bar.set_maximized(True)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.WindowStateChange:
            margin = 0 if self.isMaximized() else 10
            self._root_layout.setContentsMargins(margin, margin, margin, margin)
        super().changeEvent(event)


class ToastWidget(QWidget):
    """Small translucent notification that fades and slides into place."""

    def __init__(self, text: str, ok: bool = True, duration: int = 2600, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(380, 60)
        self._ok = ok
        self._duration = max(600, duration)
        self._closing = False
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 10, 18, 10)
        label = QLabel(text, self)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.NoTextInteraction)
        layout.addWidget(label, 1)

    def paintEvent(self, event) -> None:
        palette = theme_palette("midnight")
        background = QColor(palette["panel"])
        background.setAlpha(238)
        accent = QColor(palette["success"] if self._ok else palette["danger"])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(background)
        painter.setPen(QPen(QColor(palette["border"]), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 13, 13)
        painter.setPen(Qt.NoPen)
        painter.fillRect(QRect(3, 15, 4, self.height() - 30), accent)
        super().paintEvent(event)

    def animate_in(self, target: QPoint) -> None:
        self.move(target + QPoint(0, 18))
        self.show()
        self.raise_()

        fade = QPropertyAnimation(self._effect, b"opacity", self)
        fade.setDuration(190)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutQuad)

        slide = QPropertyAnimation(self, b"pos", self)
        slide.setDuration(240)
        slide.setStartValue(self.pos())
        slide.setEndValue(target)
        slide.setEasingCurve(QEasingCurve.OutCubic)

        self._entrance = QParallelAnimationGroup(self)
        self._entrance.addAnimation(fade)
        self._entrance.addAnimation(slide)
        self._entrance.start()
        QTimer.singleShot(self._duration, self.begin_fade_out)

    def begin_fade_out(self) -> None:
        if self._closing:
            return
        self._closing = True
        entrance = getattr(self, "_entrance", None)
        if entrance is not None:
            entrance.stop()
        self._exit = QPropertyAnimation(self._effect, b"opacity", self)
        self._exit.setDuration(260)
        self._exit.setStartValue(self._effect.opacity())
        self._exit.setEndValue(0.0)
        self._exit.setEasingCurve(QEasingCurve.OutQuad)
        self._exit.finished.connect(self.deleteLater)
        self._exit.start()


class SectionLabel(QLabel):
    """Uppercase section caption used by dialogs and the sidebar."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("sectionLabel")
        self.setTextInteractionFlags(Qt.NoTextInteraction)


class EmptyState(QWidget):
    """Centered message shown when a view has no matching cards."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 40, 20, 40)
        layout.setAlignment(Qt.AlignCenter)
        self._label = QLabel(text, self)
        self._label.setObjectName("emptyLabel")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

    def set_text(self, text: str) -> None:
        self._label.setText(text)


def show_toast(parent: QWidget | None, text: str, ok: bool = True, duration: int = 2600) -> ToastWidget:
    """Create and display a toast anchored to the bottom-right of ``parent``."""

    toast = ToastWidget(text, ok, duration, parent)
    if parent is not None and parent.isVisible():
        corner = parent.mapToGlobal(QPoint(parent.width(), parent.height()))
    else:
        screen = QGuiApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 800)
        corner = QPoint(geometry.right(), geometry.bottom())
    target = corner - QPoint(toast.width() + 22, toast.height() + 22)
    toast.animate_in(target)
    return toast


__all__ = [
    "EmptyState",
    "FramelessWindow",
    "SectionLabel",
    "TitleBar",
    "ToastWidget",
    "show_toast",
]
