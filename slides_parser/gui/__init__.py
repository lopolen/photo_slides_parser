from __future__ import annotations

import faulthandler
import gc
import sys
import traceback
from pathlib import Path

from ..ocr import OcrSettings

CRASH_LOG = Path.home() / ".photo_slides_parser" / "crash.log"


def _install_error_reporting() -> None:
    """Make failures visible instead of the window silently disappearing.

    - Python exceptions inside Qt slots: printed and shown in a dialog.
    - Native crashes (access violations): traceback written to stderr and CRASH_LOG.
    """
    CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
    log = open(CRASH_LOG, "a", encoding="utf-8")  # kept open for the process lifetime
    faulthandler.enable(file=log, all_threads=True)

    def excepthook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        sys.__stderr__.write(text)
        log.write(text)
        log.flush()
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is not None:
            QMessageBox.critical(None, "Неочікувана помилка", text)

    sys.excepthook = excepthook


def run_gui(input_dir: Path = Path("input"), output: Path = Path("output.txt"),
            settings: OcrSettings | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    _install_error_reporting()
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(input_dir, output, settings or OcrSettings())
    window.show()
    code = app.exec()
    # Destroy the window (and its graphics items) before QApplication goes away.
    window.canvas.clear_image()
    window.deleteLater()
    del window
    gc.collect()
    app.processEvents()
    return code


__all__ = ["run_gui"]
