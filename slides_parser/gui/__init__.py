from __future__ import annotations

import sys
from pathlib import Path

from ..ocr import OcrSettings


def run_gui(input_dir: Path = Path("input"), output: Path = Path("output.txt"),
            settings: OcrSettings | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(input_dir, output, settings or OcrSettings())
    window.show()
    return app.exec()


__all__ = ["run_gui"]
