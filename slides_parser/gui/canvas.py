from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView, QMenu,
)

from ..models import Region
from .region_item import MIN_SIZE, RegionItem

ZOOM_STEP = 1.15


class SlideCanvas(QGraphicsView):
    """Shows a slide image and lets the user draw, move, resize, delete and reorder regions.

    - Drag on empty space: create a region.
    - Drag a region / its edges: move / resize.
    - Del: delete selected. Right click: context menu (reorder / delete).
    - Ctrl+wheel: zoom. Middle button drag: pan.
    """

    regionsChanged = Signal()          # geometry, count or order changed
    selectedIndexChanged = Signal(int)  # -1 when nothing is selected

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setFrameShape(QFrame.NoFrame)
        self.setBackgroundBrush(QColor(45, 45, 48))
        self.setFocusPolicy(Qt.StrongFocus)

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._bounds = QRectF()
        self._items: list[RegionItem] = []
        self._auto_fit = True
        self._draw_origin: QPointF | None = None
        self._draw_preview: QGraphicsRectItem | None = None
        self._pan_start = None

        self.scene().selectionChanged.connect(self._on_selection_changed)

    # --- public API -----------------------------------------------------------
    def has_image(self) -> bool:
        return self._pixmap_item is not None

    def set_image(self, pixmap: QPixmap, regions: list[Region]) -> None:
        self.scene().blockSignals(True)
        self.scene().clear()
        self.scene().blockSignals(False)
        self._items = []
        self._pixmap_item = self.scene().addPixmap(pixmap)
        self._pixmap_item.setZValue(-1)
        self._bounds = QRectF(pixmap.rect())
        self.scene().setSceneRect(self._bounds)
        for region in regions:
            self._add_item(QRectF(region.x, region.y, region.w, region.h))
        self.fit()
        self.selectedIndexChanged.emit(-1)

    def clear_image(self) -> None:
        self.scene().clear()
        self._items = []
        self._pixmap_item = None

    def regions(self) -> list[Region]:
        return [item.to_region() for item in self._items]

    def set_regions(self, regions: list[Region]) -> None:
        for item in self._items:
            self.scene().removeItem(item)
        self._items = []
        for region in regions:
            self._add_item(QRectF(region.x, region.y, region.w, region.h))
        self.regionsChanged.emit()

    def selected_index(self) -> int:
        for i, item in enumerate(self._items):
            if item.isSelected():
                return i
        return -1

    def select_index(self, index: int) -> None:
        self.scene().clearSelection()
        if 0 <= index < len(self._items):
            item = self._items[index]
            item.setSelected(True)
            self.ensureVisible(item, 20, 20)

    def delete_selected(self) -> None:
        selected = [item for item in self._items if item.isSelected()]
        if not selected:
            return
        for item in selected:
            self._items.remove(item)
            self.scene().removeItem(item)
        self._renumber()
        self.regionsChanged.emit()

    def move_region(self, src: int, dst: int) -> None:
        if not (0 <= src < len(self._items)):
            return
        dst = max(0, min(dst, len(self._items) - 1))
        if src == dst:
            return
        item = self._items.pop(src)
        self._items.insert(dst, item)
        self._renumber()
        self.regionsChanged.emit()

    def reorder(self, order: list[int]) -> None:
        """Apply a permutation: `order[k]` is the old index of the region that becomes k-th."""
        if sorted(order) != list(range(len(self._items))):
            return
        self._items = [self._items[i] for i in order]
        self._renumber()
        self.regionsChanged.emit()

    def fit(self) -> None:
        self._auto_fit = True
        if self._pixmap_item:
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def zoom(self, factor: float) -> None:
        self._auto_fit = False
        self.scale(factor, factor)

    # --- internals ------------------------------------------------------------
    def _add_item(self, rect: QRectF) -> RegionItem:
        item = RegionItem(rect, self._bounds, len(self._items) + 1, self.regionsChanged.emit)
        self.scene().addItem(item)
        self._items.append(item)
        return item

    def _renumber(self) -> None:
        for number, item in enumerate(self._items, start=1):
            item.set_number(number)
            item.setZValue(number)

    def _region_at(self, view_pos) -> RegionItem | None:
        for item in self.items(view_pos):
            while item is not None and not isinstance(item, RegionItem):
                item = item.parentItem()
            if isinstance(item, RegionItem):
                return item
        return None

    def _clamp(self, p: QPointF) -> QPointF:
        b = self._bounds
        return QPointF(min(max(p.x(), b.left()), b.right()), min(max(p.y(), b.top()), b.bottom()))

    def _on_selection_changed(self) -> None:
        self.selectedIndexChanged.emit(self.selected_index())

    # --- events ---------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_fit:
            self.fit()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.zoom(ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan_start = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if (event.button() == Qt.LeftButton and self.has_image()
                and self._region_at(event.position().toPoint()) is None):
            self.scene().clearSelection()
            self._draw_origin = self._clamp(self.mapToScene(event.position().toPoint()))
            pen = QPen(QColor(255, 255, 255), 1.5, Qt.DashLine)
            pen.setCosmetic(True)
            self._draw_preview = self.scene().addRect(QRectF(self._draw_origin, self._draw_origin), pen,
                                                      QColor(255, 255, 255, 40))
            self._draw_preview.setZValue(10_000)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_start is not None:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        if self._draw_origin is not None and self._draw_preview is not None:
            current = self._clamp(self.mapToScene(event.position().toPoint()))
            self._draw_preview.setRect(QRectF(self._draw_origin, current).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._pan_start is not None:
            self._pan_start = None
            self.unsetCursor()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._draw_origin is not None:
            rect = self._draw_preview.rect() if self._draw_preview else QRectF()
            if self._draw_preview is not None:
                self.scene().removeItem(self._draw_preview)
            self._draw_preview = None
            self._draw_origin = None
            if rect.width() >= MIN_SIZE and rect.height() >= MIN_SIZE:
                rect = QRectF(round(rect.x()), round(rect.y()), round(rect.width()), round(rect.height()))
                item = self._add_item(rect)
                self._renumber()
                item.setSelected(True)
                self.regionsChanged.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        item = self._region_at(event.pos())
        if item is None:
            return
        self.scene().clearSelection()
        item.setSelected(True)
        index = self._items.index(item)
        last = len(self._items) - 1

        menu = QMenu(self)
        first_a = menu.addAction("Зробити першим")
        up_a = menu.addAction("Перемістити раніше")
        down_a = menu.addAction("Перемістити пізніше")
        last_a = menu.addAction("Зробити останнім")
        menu.addSeparator()
        del_a = menu.addAction("Видалити")
        first_a.setEnabled(index > 0)
        up_a.setEnabled(index > 0)
        down_a.setEnabled(index < last)
        last_a.setEnabled(index < last)

        chosen = menu.exec(event.globalPos())
        if chosen is first_a:
            self.move_region(index, 0)
        elif chosen is up_a:
            self.move_region(index, index - 1)
        elif chosen is down_a:
            self.move_region(index, index + 1)
        elif chosen is last_a:
            self.move_region(index, last)
        elif chosen is del_a:
            self.delete_selected()
