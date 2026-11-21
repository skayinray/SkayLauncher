"""Background task plumbing for network, install and update operations."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal


class WorkerSignals(QObject):
    """Signals emitted by a :class:`Worker` from the pool thread."""

    started = Signal()
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)


class Worker(QRunnable):
    """Run one callable in a :class:`QThreadPool` and expose Qt signals."""

    def __init__(
        self,
        function: Callable[..., Any],
        *args: Any,
        with_progress: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.function = function
        self.args = tuple(args)
        self.kwargs = dict(kwargs)
        self.signals = WorkerSignals()
        self.setAutoDelete(False)
        if with_progress:
            self.kwargs["progress"] = self.signals.progress.emit

        self.started = self.signals.started
        self.finished = self.signals.finished
        self.error = self.signals.error
        self.progress = self.signals.progress

    def run(self) -> None:
        self.signals.started.emit()
        try:
            result = self.function(*self.args, **self.kwargs)
        except Exception as error:  # noqa: BLE001
            message = str(error) or type(error).__name__
            self.signals.error.emit(message)
        else:
            self.signals.finished.emit(result)


class TaskRunner(QObject):
    """Submit callables to the thread pool and route results back to the GUI thread."""

    def __init__(self, parent: QObject | None = None, pool: QThreadPool | None = None) -> None:
        super().__init__(parent)
        self._pool = pool or QThreadPool.globalInstance()
        self._workers: set[Worker] = set()

    def submit(
        self,
        function: Callable[..., Any],
        *args: Any,
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_started: Callable[[], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        with_progress: bool = False,
        **kwargs: Any,
    ) -> Worker:
        worker = Worker(function, *args, with_progress=with_progress, **kwargs)
        if on_started is not None:
            worker.started.connect(on_started, Qt.QueuedConnection)
        if on_progress is not None:
            worker.progress.connect(on_progress, Qt.QueuedConnection)
        if on_result is not None:
            worker.finished.connect(on_result, Qt.QueuedConnection)
        if on_error is not None:
            worker.error.connect(on_error, Qt.QueuedConnection)

        worker.finished.connect(lambda _result=None, item=worker: self._release(item), Qt.QueuedConnection)
        worker.error.connect(lambda _message=None, item=worker: self._release(item), Qt.QueuedConnection)
        self._workers.add(worker)
        self._pool.start(worker)
        return worker

    def run(
        self,
        function: Callable[..., Any],
        *args: Any,
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_started: Callable[[], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        with_progress: bool = False,
        **kwargs: Any,
    ) -> Worker:
        """Alias for :meth:`submit`."""

        return self.submit(
            function,
            *args,
            on_result=on_result,
            on_error=on_error,
            on_started=on_started,
            on_progress=on_progress,
            with_progress=with_progress,
            **kwargs,
        )

    def _release(self, worker: Worker) -> None:
        self._workers.discard(worker)
