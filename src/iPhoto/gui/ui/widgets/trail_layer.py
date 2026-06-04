"""Trail rendering layer for the map widget."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

from ..models.trail_models import TrailData, TrailPoint, TrailSegment

if TYPE_CHECKING:
    pass


class TrailLayer:
    """Renders photo trail lines and points on the map.

    This layer draws polyline trails connecting geotagged photos
    in chronological order, with colored segments per time period.
    """

    def __init__(self) -> None:
        self._trail_data: Optional[TrailData] = None
        self._visible_segments: set[int] = set()
        self._highlighted_point: Optional[TrailPoint] = None
        self._opacity: float = 0.8

    def set_trail(self, trail: TrailData) -> None:
        """Set the trail data to render."""
        self._trail_data = trail
        self._visible_segments = set(range(len(trail.segments)))

    def clear(self) -> None:
        """Clear all trail data."""
        self._trail_data = None
        self._visible_segments.clear()
        self._highlighted_point = None

    def set_opacity(self, opacity: float) -> None:
        """Set the trail opacity (0.0 to 1.0)."""
        self._opacity = max(0.0, min(1.0, opacity))

    def paint(
        self,
        painter: QPainter,
        project_fn,
        viewport: QRectF,
    ) -> None:
        """Paint the trail on the map.

        Parameters
        ----------
        painter : QPainter
            The painter to draw on.
        project_fn : callable
            Function to project (lon, lat) -> QPointF in screen coords.
        viewport : QRectF
            The visible viewport in screen coordinates.
        """
        if self._trail_data is None or self._trail_data.is_empty:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        for idx in self._visible_segments:
            if idx >= len(self._trail_data.segments):
                continue
            segment = self._trail_data.segments[idx]
            self._paint_segment(painter, segment, project_fn, viewport)

        # Paint highlighted point
        if self._highlighted_point is not None:
            self._paint_highlight(painter, self._highlighted_point, project_fn)

        painter.restore()

    def _paint_segment(
        self,
        painter: QPainter,
        segment: TrailSegment,
        project_fn,
        viewport: QRectF,
    ) -> None:
        """Paint a single trail segment as a line with direction arrows."""
        if len(segment.points) < 2:
            return

        # Project all points to screen coordinates
        screen_points: list[QPointF] = []
        for tp in segment.points:
            try:
                pt = project_fn(tp.longitude, tp.latitude)
                if pt is not None:
                    screen_points.append(pt)
            except Exception:
                continue

        if len(screen_points) < 2:
            return

        r, g, b = segment.color
        color = QColor(r, g, b, int(255 * self._opacity))
        pen = QPen(color, 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        # Draw the trail line
        path = QPainterPath()
        path.moveTo(screen_points[0])
        for pt in screen_points[1:]:
            path.lineTo(pt)
        painter.drawPath(path)

        # Draw filled direction arrows along the path
        if len(screen_points) >= 2:
            self._paint_arrows(painter, screen_points, color)

    def _paint_arrows(
        self,
        painter: QPainter,
        points: list[QPointF],
        color: QColor,
    ) -> None:
        """Paint filled direction arrowheads along the trail."""
        arrow_color = QColor(color.red(), color.green(), color.blue(),
                             int(255 * self._opacity))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(arrow_color))

        step = max(len(points) // 5, 2)
        for i in range(step, len(points), step):
            p1 = points[i - 1]
            p2 = points[i]
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length = math.sqrt(dx * dx + dy * dy)
            if length < 6:
                continue

            nx, ny = dx / length, dy / length
            arrow_len = 6.0
            arrow_width = 4.0
            tip = QPointF(p2.x(), p2.y())
            left = QPointF(
                tip.x() - arrow_len * nx + arrow_width * ny,
                tip.y() - arrow_len * ny - arrow_width * nx,
            )
            right = QPointF(
                tip.x() - arrow_len * nx - arrow_width * ny,
                tip.y() - arrow_len * ny + arrow_width * nx,
            )
            arrow_path = QPainterPath()
            arrow_path.moveTo(tip)
            arrow_path.lineTo(left)
            arrow_path.lineTo(right)
            arrow_path.closeSubpath()
            painter.drawPath(arrow_path)

    def _paint_highlight(
        self,
        painter: QPainter,
        point: TrailPoint,
        project_fn,
    ) -> None:
        """Paint a highlighted point (e.g., on hover)."""
        try:
            pt = project_fn(point.longitude, point.latitude)
        except Exception:
            return

        if pt is None:
            return

        painter.setPen(QPen(QColor(255, 255, 255, 200), 3))
        painter.setBrush(QBrush(QColor(255, 100, 0, 200)))
        painter.drawEllipse(pt, 10, 10)
