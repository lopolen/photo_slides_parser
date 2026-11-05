from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDockWidget, QFileDialog, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QSplitter, QToolBar, QVBoxLayout, QWidget,
)

from ..images import IMAGE_EXTENSIONS, find_images, natural_key
from ..layout_store import LayoutStore
from ..models import SlideText
from ..ocr import OcrSettings
from ..pipeline import write_notes
from .canvas import SlideCanvas
from .region_item import color_for
from .worker import OcrWorker, start_worker

THUMB_SIZE = QSize(160, 90)


class MainWindow(QMainWindow):
    def __init__(self, input_dir: Path, output: Path, settings: OcrSettings):
        super().__init__()
        self.setWindowTitle("Photo Slides Parser")
        self.resize(1400, 850)

        self.settings = settings
        self.output = output
        self.input_dir: Path | None = None
        self.images: list[Path] = []
        self.store: LayoutStore | None = None
        self.current = -1
        self._thread: QThread | None = None
        self._worker: OcrWorker | None = None
        self._last_text = ""  # recognized text without block headers, for copying
        self._syncing = False

        self.canvas = SlideCanvas(self)
        self.setCentralWidget(self.canvas)
        self._build_slide_dock()
        self._build_region_dock()
        self._build_actions()
        self._build_status_bar()

        self.canvas.regionsChanged.connect(self._on_regions_changed)
        self.canvas.selectedIndexChanged.connect(self._on_canvas_selection)

        if input_dir.is_dir():
            self.open_folder(input_dir)
        elif input_dir.is_file():
            self.open_files([input_dir])
        self._update_actions()

    # --- UI construction --------------------------------------------------
    def _build_slide_dock(self) -> None:
        self.slide_list = QListWidget()
        self.slide_list.setIconSize(THUMB_SIZE)
        self.slide_list.setSpacing(2)
        self.slide_list.currentRowChanged.connect(self.show_slide)
        dock = QDockWidget("Слайди", self)
        dock.setObjectName("slides")
        dock.setWidget(self.slide_list)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _build_region_dock(self) -> None:
        self.region_list = QListWidget()
        self.region_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.region_list.setDefaultDropAction(Qt.MoveAction)
        self.region_list.currentRowChanged.connect(self._on_region_list_selection)
        self.region_list.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, self._apply_list_order))

        hint = QLabel(
            "Перетягніть мишею по слайду, щоб додати блок.\n"
            "Порядок блоків = порядок тексту в конспекті.\n"
            "Змінити порядок: перетягніть рядок у списку\n"
            "або ПКМ по блоку. Del — видалити.\n"
            "Без блоків слайд читається повністю."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Тут з'явиться результат розпізнавання (Ctrl+R)")

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(4, 4, 4, 4)
        top_layout.addWidget(QLabel("Блоки (у порядку читання):"))
        top_layout.addWidget(self.region_list)
        top_layout.addWidget(hint)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(self.preview)
        splitter.setSizes([350, 450])

        dock = QDockWidget("Блоки та текст", self)
        dock.setObjectName("regions")
        dock.setWidget(splitter)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.resizeDocks([dock], [360], Qt.Horizontal)

    def _action(self, text: str, slot, shortcut=None, tip: str = "") -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            tip = f"{tip or text} ({QKeySequence(shortcut).toString()})"
        action.setToolTip(tip or text)
        return action

    def _build_actions(self) -> None:
        self.a_open = self._action("Відкрити папку…", self.choose_folder, QKeySequence.Open)
        self.a_open_file = self._action("Відкрити файл…", self.choose_files, "Ctrl+Shift+O",
                                        "Відкрити одне або кілька зображень")
        self.a_copy_text = self._action("Копіювати текст", self.copy_text, "Ctrl+Shift+C",
                                        "Скопіювати розпізнаний текст у буфер обміну")
        self.a_prev = self._action("◀ Попередній", lambda: self._step(-1), Qt.Key_PageUp)
        self.a_next = self._action("Наступний ▶", lambda: self._step(1), Qt.Key_PageDown)
        self.a_fit = self._action("Вмістити", self.canvas.fit, "Ctrl+0", "Масштаб під розмір вікна")
        self.a_zoom_in = self._action("＋", lambda: self.canvas.zoom(1.25), QKeySequence.ZoomIn, "Збільшити")
        self.a_zoom_out = self._action("－", lambda: self.canvas.zoom(0.8), QKeySequence.ZoomOut, "Зменшити")
        self.a_copy_prev = self._action("Копіювати блоки з попереднього", self.copy_from_previous,
                                        "Ctrl+Shift+V", "Взяти розмітку попереднього слайда")
        self.a_clear = self._action("Очистити блоки", self.clear_regions, None, "Видалити всі блоки слайда")
        self.a_preview = self._action("Розпізнати слайд", self.preview_current, "Ctrl+R",
                                      "Показати текст поточного слайда")
        self.a_extract = self._action("Зберегти конспект…", self.extract_all, "Ctrl+E",
                                      "Розпізнати всі слайди та записати у файл")

        toolbar = QToolBar("Інструменти", self)
        toolbar.setObjectName("tools")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        for item in (self.a_open, self.a_open_file, None, self.a_prev, self.a_next, None,
                     self.a_zoom_out, self.a_fit, self.a_zoom_in, None, self.a_copy_prev, self.a_clear, None,
                     self.a_preview, self.a_copy_text, self.a_extract):
            toolbar.addSeparator() if item is None else toolbar.addAction(item)
        self.addToolBar(toolbar)

    def _build_status_bar(self) -> None:
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)

    # --- folder & slides ----------------------------------------------------
    def choose_folder(self) -> None:
        start = str(self.input_dir or Path.cwd())
        folder = QFileDialog.getExistingDirectory(self, "Папка зі слайдами", start)
        if folder:
            self.open_folder(Path(folder))

    def choose_files(self) -> None:
        start = str(self.input_dir or Path.cwd())
        patterns = " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS)
        files, _ = QFileDialog.getOpenFileNames(self, "Відкрити зображення", start,
                                                f"Зображення ({patterns});;Усі файли (*)")
        if files:
            self.open_files([Path(f) for f in files])

    def open_folder(self, folder: Path) -> None:
        self._load(folder, find_images(folder), str(folder))

    def open_files(self, files: list[Path]) -> None:
        """Open only the given images (all from one folder, as a file dialog returns them).

        Their regions are still stored in that folder's regions.json, so a layout drawn
        here is also used when the whole folder is processed later.
        """
        files = sorted(files, key=lambda p: natural_key(p.name))
        title = str(files[0]) if len(files) == 1 else f"{files[0].parent}  ({len(files)} файли)"
        self._load(files[0].parent, files, title)

    def _load(self, folder: Path, images: list[Path], title: str) -> None:
        try:
            store = LayoutStore.for_directory(folder)
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.critical(self, "Помилка", f"Не вдалося прочитати {folder / 'regions.json'}:\n{exc}")
            return
        self.input_dir = folder
        self.store = store
        self.images = images
        self.current = -1
        self.setWindowTitle(f"Photo Slides Parser — {title}")

        self.slide_list.blockSignals(True)
        self.slide_list.clear()
        for path in self.images:
            thumb = QPixmap(str(path)).scaled(THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.slide_list.addItem(QListWidgetItem(QIcon(thumb), ""))
        self.slide_list.blockSignals(False)
        self._refresh_slide_labels()

        if self.images:
            self.slide_list.setCurrentRow(0)
        else:
            self.canvas.clear_image()
            self._refresh_region_list()
            self.statusBar().showMessage(f"У папці {folder} немає зображень")
        self._update_actions()

    def show_slide(self, index: int) -> None:
        if not (0 <= index < len(self.images)) or self.store is None:
            return
        self.current = index
        path = self.images[index]
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            QMessageBox.warning(self, "Помилка", f"Не вдалося відкрити {path.name}")
            return
        self.canvas.set_image(pixmap, self.store.get(path.name))
        self._set_result("", "")
        self._refresh_region_list()
        self.statusBar().showMessage(f"{path.name}  —  {pixmap.width()}×{pixmap.height()}")
        self._update_actions()

    def _step(self, delta: int) -> None:
        target = self.current + delta
        if 0 <= target < len(self.images):
            self.slide_list.setCurrentRow(target)

    def _refresh_slide_labels(self) -> None:
        for i, path in enumerate(self.images):
            count = len(self.store.get(path.name)) if self.store else 0
            suffix = f"\n{count} бл." if count else "\nвесь слайд"
            self.slide_list.item(i).setText(path.name + suffix)

    # --- regions --------------------------------------------------------------
    def _on_regions_changed(self) -> None:
        if self.store is None or self.current < 0:
            return
        name = self.images[self.current].name
        self.store.set(name, self.canvas.regions())
        try:
            self.store.save()
        except OSError as exc:
            self.statusBar().showMessage(f"Не вдалося зберегти розмітку: {exc}")
        self._refresh_region_list()
        self._refresh_slide_labels()
        self._update_actions()

    def _refresh_region_list(self) -> None:
        self._syncing = True
        self.region_list.clear()
        for i, region in enumerate(self.canvas.regions()):
            item = QListWidgetItem(f"{i + 1}.   {region.w}×{region.h}  @ ({region.x}, {region.y})")
            item.setData(Qt.UserRole, i)
            item.setForeground(color_for(i + 1).darker(110))
            self.region_list.addItem(item)
        selected = self.canvas.selected_index()
        if selected >= 0:
            self.region_list.setCurrentRow(selected)
        self._syncing = False

    def _apply_list_order(self) -> None:
        order = [self.region_list.item(i).data(Qt.UserRole) for i in range(self.region_list.count())]
        self.canvas.reorder(order)

    def _on_region_list_selection(self, row: int) -> None:
        if not self._syncing:
            self._syncing = True
            self.canvas.select_index(row)
            self._syncing = False

    def _on_canvas_selection(self, index: int) -> None:
        if not self._syncing:
            self._syncing = True
            self.region_list.setCurrentRow(index)
            self._syncing = False

    def copy_from_previous(self) -> None:
        if self.store is None or self.current <= 0:
            return
        previous = self.store.get(self.images[self.current - 1].name)
        if not previous:
            self.statusBar().showMessage("На попередньому слайді немає блоків")
            return
        self.canvas.set_regions(previous)

    def clear_regions(self) -> None:
        if self.canvas.regions():
            self.canvas.set_regions([])

    # --- OCR ------------------------------------------------------------------
    def preview_current(self) -> None:
        if self.current < 0 or self._busy():
            return
        path = self.images[self.current]
        self._run([(path, self.canvas.regions())], self._show_preview)

    def _show_preview(self, results: list[SlideText]) -> None:
        if not results:
            return
        slide = results[0]
        if len(slide.blocks) == 1:
            shown = slide.blocks[0]
        else:
            shown = "\n\n".join(f"── Блок {i} ──\n{text}" for i, text in enumerate(slide.blocks, start=1))
        self._set_result(shown, slide.text)
        self.statusBar().showMessage("Готово. Ctrl+Shift+C — скопіювати текст")

    def _set_result(self, shown: str, clean: str) -> None:
        self.preview.setPlainText(shown)
        self._last_text = clean
        self._update_actions()

    def copy_text(self) -> None:
        if self._last_text:
            QGuiApplication.clipboard().setText(self._last_text)
            self.statusBar().showMessage("Текст скопійовано в буфер обміну")

    def extract_all(self) -> None:
        if not self.images or self._busy():
            return
        target, _ = QFileDialog.getSaveFileName(self, "Зберегти конспект", str(self.output.resolve()),
                                                "Text files (*.txt);;All files (*)")
        if not target:
            return
        self.output = Path(target)
        jobs = [(path, self.store.get(path.name)) for path in self.images]
        self._run(jobs, self._save_notes)

    def _save_notes(self, results: list[SlideText]) -> None:
        try:
            write_notes(self.output, results)
        except OSError as exc:
            QMessageBox.critical(self, "Помилка", f"Не вдалося записати {self.output}:\n{exc}")
            return
        combined = "\n\n".join(s.text for s in results)
        self._set_result(combined, combined)
        self.statusBar().showMessage(f"Конспект збережено: {self.output}")
        QMessageBox.information(self, "Готово", f"Текст {len(results)} слайдів збережено у\n{self.output}")

    def _run(self, jobs, on_done) -> None:
        worker = OcrWorker(self.settings, jobs)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(on_done)
        worker.finished.connect(self._on_worker_done)
        worker.failed.connect(self._on_worker_failed)
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        # Keep a Python reference: otherwise the worker is garbage-collected right after
        # this method returns and the thread runs nothing (progress stuck at 0%).
        self._worker = worker
        self._thread = start_worker(self, worker)
        self._thread.finished.connect(self._on_thread_finished)
        self._update_actions()

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setValue(done)
        if name:
            self.statusBar().showMessage(f"Розпізнавання {name} ({done + 1}/{total})…")

    def _on_worker_done(self, _results) -> None:
        self.progress.setVisible(False)

    def _on_worker_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Помилка розпізнавання", message)

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._update_actions()

    def _busy(self) -> bool:
        return self._thread is not None

    # --- misc -----------------------------------------------------------------
    def _update_actions(self) -> None:
        has_slide = self.current >= 0
        busy = self._busy()
        self.a_prev.setEnabled(has_slide and self.current > 0)
        self.a_next.setEnabled(has_slide and self.current < len(self.images) - 1)
        for a in (self.a_fit, self.a_zoom_in, self.a_zoom_out):
            a.setEnabled(has_slide)
        self.a_copy_prev.setEnabled(has_slide and self.current > 0)
        self.a_clear.setEnabled(has_slide and bool(self.canvas.regions()))
        self.a_preview.setEnabled(has_slide and not busy)
        self.a_extract.setEnabled(bool(self.images) and not busy)
        self.a_open.setEnabled(not busy)
        self.a_open_file.setEnabled(not busy)
        self.a_copy_text.setEnabled(bool(self._last_text))

    def closeEvent(self, event):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
        # Remove Python-subclassed graphics items while Qt is fully alive; leaving them
        # for interpreter shutdown randomly crashes with an access violation.
        self.canvas.clear_image()
        super().closeEvent(event)
