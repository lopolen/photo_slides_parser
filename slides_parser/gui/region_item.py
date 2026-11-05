from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QStyleOptionGraphicsItem, QWidget

from ..models import Region

HANDLE_PX = 8       # grab distance for resize, in screen pixels
MIN_SIZE = 8        # minimal region side, in image pixels

LEFT, TOP, RIGHT, BOTTOM = 1, 2, 4, 8

_CURSORS = {
    LEFT: Qt.SizeHorCursor, RIGHT: Qt.SizeHorCursor,
    TOP: Qt.SizeVerCursor, BOTTOM: Qt.SizeVerCursor,
    LEFT | TOP: Qt.SizeFDiagCursor, RIGHT | BOTTOM: Qt.SizeFDiagCursor,
    RIGHT | TOP: Qt.SizeBDiagCursor, LEFT | BOTTOM: Qt.SizeBDiagCursor,
}


def color_for(number: int) -> QColor:
    """Distinct, stable hue per region number."""
    hue = int((number - 1) * 137.508) % 360
    return QColor.fromHsv(hue, 200, 230)


class BadgeItem(QGraphicsItem):
    """Region number drawn at a constant on-screen size, regardless of zoom."""

    SIZE = 26

    def __init__(self, parent: RegionItem):
        super().__init__(parent)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setAcceptHoverEvents(False)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None):
        parent: RegionItem = self.parentItem()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.setBrush(color_for(parent.number).darker(140))
        painter.drawEllipse(self.boundingRect().adjusted(2, 2, -2, -2))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.drawText(self.boundingRect(), Qt.AlignCenter, str(parent.number))


class RegionItem(QGraphicsRectItem):
    """Semi-transparent, numbered, movable and resizable rectangle.

    Geometry convention: pos() is the top-left corner in scene (= image pixel)
    coordinates and rect() is always QRectF(0, 0, w, h).
    """

    def __init__(self, rect: QRectF, bounds: QRectF, number: int, on_changed: Callable[[], None]):
        super().__init__(0, 0, rect.width(), rect.height())
        self.number = number
        self._bounds = bounds
        self._on_changed = on_changed
        self._resize_edges = 0
        self._moved = False
        self.setPos(rect.topLeft())
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsFocusable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.badge = BadgeItem(self)

    # --- model conversion -------------------------------------------------
    def scene_rect(self) -> QRectF:
        return QRectF(self.pos(), self.rect().size())

    def to_region(self) -> Region:
        r = self.scene_rect()
        return Region(round(r.x()), round(r.y()), round(r.width()), round(r.height()))

    def set_number(self, number: int) -> None:
        self.number = number
        self.update()
        self.badge.update()

    # --- painting -----------------------------------------------------------
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None):
        color = color_for(self.number)
        fill = QColor(color)
        fill.setAlpha(110 if self.isSelected() else 70)
        pen = QPen(color.darker(120) if not self.isSelected() else QColor(255, 255, 255), 2)
        pen.setCosmetic(True)
        if self.isSelected():
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        painter.drawRect(self.rect())

    # --- helpers --------------------------------------------------------------
    def _view_scale(self) -> float:
        scene = self.scene()
        if scene and scene.views():
            return scene.views()[0].transform().m11() or 1.0
        return 1.0

    def _edges_at(self, local: QPointF) -> int:
        tol = HANDLE_PX / self._view_scale()
        r = self.rect()
        edges = 0
        if abs(local.x() - r.left()) <= tol:
            edges |= LEFT
        elif abs(local.x() - r.right()) <= tol:
            edges |= RIGHT
        if abs(local.y() - r.top()) <= tol:
            edges |= TOP
        elif abs(local.y() - r.bottom()) <= tol:
            edges |= BOTTOM
        return edges

    # --- geometry constraints -------------------------------------------------
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            pos: QPointF = value
            r = self.rect()
            x = min(max(pos.x(), self._bounds.left()), self._bounds.right() - r.width())
            y = min(max(pos.y(), self._bounds.top()), self._bounds.bottom() - r.height())
            return QPointF(round(x), round(y))
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._moved = True
        return super().itemChange(change, value)

    # --- mouse handling ---------------------------------------------------
    def hoverMoveEvent(self, event):
        edges = self._edges_at(event.pos())
        self.setCursor(_CURSORS.get(edges, Qt.SizeAllCursor))
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._resize_edges = self._edges_at(event.pos())
            self._moved = False
            if self._resize_edges:
                if not (event.modifiers() & Qt.ControlModifier):
                    self.scene().clearSelection()
                self.setSelected(True)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._resize_edges:
            super().mouseMoveEvent(event)
            return
        p = event.scenePos()
        b = self._bounds
        r = self.scene_rect()
        left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
        if self._resize_edges & LEFT:
            left = min(max(p.x(), b.left()), right - MIN_SIZE)
        if self._resize_edges & RIGHT:
            right = max(min(p.x(), b.right()), left + MIN_SIZE)
        if self._resize_edges & TOP:
            top = min(max(p.y(), b.top()), bottom - MIN_SIZE)
        if self._resize_edges & BOTTOM:
            bottom = max(min(p.y(), b.bottom()), top + MIN_SIZE)
        left, top, right, bottom = (round(v) for v in (left, top, right, bottom))
        self.prepareGeometryChange()
        self.setRect(0, 0, right - left, bottom - top)
        self.setPos(left, top)
        self._moved = True
        event.accept()

    def mouseReleaseEvent(self, event):
        was_resizing = bool(self._resize_edges)
        self._resize_edges = 0
        if not was_resizing:
            super().mouseReleaseEvent(event)
        if self._moved:
            self._moved = False
            self._on_changed()
