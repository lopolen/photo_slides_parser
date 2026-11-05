from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..models import Region
from ..ocr import OcrEngine, OcrSettings
from ..pipeline import extract_slide

Job = tuple[Path, list[Region]]


class OcrWorker(QObject):
    """Runs OCR for a list of (image, regions) jobs in a background thread."""

    progress = Signal(int, int, str)   # done, total, current file name
    finished = Signal(list)            # list[SlideText]
    failed = Signal(str)

    def __init__(self, settings: OcrSettings, jobs: list[Job]):
        super().__init__()
        self._settings = settings
        self._jobs = jobs

    @Slot()
    def run(self) -> None:
        try:
            engine = OcrEngine(self._settings)
            results = []
            total = len(self._jobs)
            for index, (path, regions) in enumerate(self._jobs):
                self.progress.emit(index, total, path.name)
                results.append(extract_slide(engine, path, regions))
            self.progress.emit(total, total, "")
            self.finished.emit(results)
        except Exception as exc:  # report any OCR/IO failure to the UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def start_worker(parent: QObject, worker: OcrWorker) -> QThread:
    """Move `worker` to a new thread, start it and clean both up when done."""
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread
