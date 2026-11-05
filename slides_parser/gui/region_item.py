from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QStyleOptionGraphicsItem, QWidget

from ..models import Region

HANDLE_PX = 8       # grab distance for resize, in screen pixels
MIN_SIZE = 8        # minimal region side, in image pixels
BADGE_PX = 26       # number badge diameter, in screen pixels

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


class RegionItem(QGraphicsRectItem):
    """Semi-transparent, numbered, movable and resizable rectangle.

    Geometry convention: pos() is the top-left corner in scene (= image pixel)
    coordinates and rect() is always QRectF(0, 0, w, h).
    """

    def __init__(self, rect: QRectF, bounds: QRectF, number: int):
        super().__init__(0, 0, rect.width(), rect.height())
        self.number = number
        self._bounds = bounds
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

    # --- model conversion -------------------------------------------------
    def scene_rect(self) -> QRectF:
        return QRectF(self.pos(), self.rect().size())

    def to_region(self) -> Region:
        r = self.scene_rect()
        return Region(round(r.x()), round(r.y()), round(r.width()), round(r.height()))

    def set_number(self, number: int) -> None:
        self.number = number
        self.update()

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
        self._paint_badge(painter, color)

    def _badge_rect(self) -> QRectF:
        size = BADGE_PX / self._view_scale()
        return QRectF(0, 0, size, size)

    def boundingRect(self) -> QRectF:
        # Include the number badge, which keeps a constant on-screen size.
        return super().boundingRect().united(self._badge_rect())

    def _paint_badge(self, painter: QPainter, color: QColor) -> None:
        scale = self._view_scale()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(1 / scale, 1 / scale)   # draw in screen pixels
        box = QRectF(0, 0, BADGE_PX, BADGE_PX)
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.setBrush(color.darker(140))
        painter.drawEllipse(box.adjusted(2, 2, -2, -2))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.drawText(box, Qt.AlignCenter, str(self.number))
        painter.restore()

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
            # Notify through the scene instead of storing a callback: a reference back to
            # the canvas creates a Python<->Qt cycle that crashes when collected at exit.
            if self.scene() is not None:
                for view in self.scene().views():
                    notify = getattr(view, "region_edited", None)
                    if notify is not None:
                        notify()
