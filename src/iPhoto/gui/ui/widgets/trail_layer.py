"""Trail rendering layer for the map widget."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

from ..models.trail_models import TrailData, TrailPoint, TrailSegment

if TYPE_CHECKING:
    pass


# Shared route key for overlap detection
_ROUTE_KEY = tuple[tuple[float, float], tuple[float, float]]


def _make_route_key(start: QPointF, end: QPointF) -> _ROUTE_KEY:
    """Coarse-grained route key for overlap grouping."""
    return (
        (round(start.x(), -1), round(start.y(), -1)),
        (round(end.x(), -1), round(end.y(), -1)),
    )


class TrailLayer:
    """Renders photo trail lines and arrows on the map.

    Features:
    - Thick lines (2-3px) with 1px white outline for contrast.
    - Time-gradient colors: early→orange, mid→blue, late→purple.
    - Large filled arrows at destination endpoint only.
    - Overlapping routes are offset to avoid blending.
    - Hover highlight: one segment brightens, others dim.
    """

    _ARROW_LEN = 11.0     # ~1.8× original 6.0
    _ARROW_WIDTH = 7.0    # ~1.8× original 4.0
    _OUTLINE_WIDTH = 1.0
    _OVERLAP_OFFSET = 6   # px offset between overlapping parallel routes

    def __init__(self) -> None:
        self._trail_data: Optional[TrailData] = None
        self._visible_segments: set[int] = set()
        self._highlighted_point: Optional[TrailPoint] = None
        self._opacity: float = 0.85
        self._hovered_segment: Optional[int] = None

    def set_trail(self, trail: TrailData) -> None:
        """Set the trail data to render."""
        self._trail_data = trail
        self._visible_segments = set(range(len(trail.segments)))
        self._hovered_segment = None

    def clear(self) -> None:
        """Clear all trail data."""
        self._trail_data = None
        self._visible_segments.clear()
        self._highlighted_point = None
        self._hovered_segment = None

    def set_opacity(self, opacity: float) -> None:
        """Set the trail opacity (0.0 to 1.0)."""
        self._opacity = max(0.0, min(1.0, opacity))

    def set_hovered_segment(self, segment_index: int | None) -> None:
        """Highlight one segment and dim the rest."""
        self._hovered_segment = segment_index

    def segment_at_point(
        self, screen_pos: QPointF, project_fn, threshold: float = 12.0,
    ) -> int | None:
        """Return the index of the segment nearest to *screen_pos*."""
        if self._trail_data is None:
            return None
        best_idx: int | None = None
        best_dist = threshold
        for idx in self._visible_segments:
            if idx >= len(self._trail_data.segments):
                continue
            seg = self._trail_data.segments[idx]
            for tp in seg.points:
                try:
                    pt = project_fn(tp.longitude, tp.latitude)
                except Exception:
                    continue
                if pt is None:
                    continue
                d = math.hypot(screen_pos.x() - pt.x(), screen_pos.y() - pt.y())
                if d < best_dist:
                    best_dist = d
                    best_idx = idx
        return best_idx

    # ------------------------------------------------------------------
    # Main paint entry
    # ------------------------------------------------------------------
    def paint(
        self,
        painter: QPainter,
        project_fn,
        viewport: QRectF,
    ) -> None:
        """Paint all trail segments on the map."""
        if self._trail_data is None or self._trail_data.is_empty:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Build screen-projected segments grouped by coarse route key
        from collections import defaultdict
        projected: list[tuple[int, TrailSegment, list[QPointF], _ROUTE_KEY]] = []
        for idx in self._visible_segments:
            if idx >= len(self._trail_data.segments):
                continue
            seg = self._trail_data.segments[idx]
            pts = self._project_points(seg, project_fn)
            if len(pts) < 2:
                continue
            key = _make_route_key(pts[0], pts[-1])
            projected.append((idx, seg, pts, key))

        # Group overlapping routes and compute offsets
        groups: dict[_ROUTE_KEY, list[int]] = defaultdict(list)
        for order, entry in enumerate(projected):
            groups[entry[3]].append(order)

        offsets: dict[int, float] = {}
        for _key, order_list in groups.items():
            if len(order_list) <= 1:
                for o in order_list:
                    offsets[o] = 0.0
                continue
            n = len(order_list)
            for j, o in enumerate(order_list):
                offsets[o] = (j - (n - 1) / 2.0) * self._OVERLAP_OFFSET

        # Determine per-segment opacity (hover effect)
        hover = self._hovered_segment
        for order, (idx, seg, pts, _key) in enumerate(projected):
            seg_opacity = self._opacity
            if hover is not None:
                seg_opacity = self._opacity if idx == hover else 0.18
            offset = offsets.get(order, 0.0)
            self._paint_segment(painter, seg, pts, seg_opacity, offset_x=offset)

        # Highlighted point
        if self._highlighted_point is not None:
            self._paint_highlight(painter, self._highlighted_point, project_fn)

        painter.restore()

    # ------------------------------------------------------------------
    # Segment painting
    # ------------------------------------------------------------------
    def _project_points(
        self, segment: TrailSegment, project_fn,
    ) -> list[QPointF]:
        """Project all trail points to screen coordinates."""
        pts: list[QPointF] = []
        for tp in segment.points:
            try:
                pt = project_fn(tp.longitude, tp.latitude)
                if pt is not None:
                    pts.append(pt)
            except Exception:
                continue
        return pts

    def _paint_segment(
        self,
        painter: QPainter,
        segment: TrailSegment,
        screen_points: list[QPointF],
        opacity: float,
        offset_x: float = 0.0,
    ) -> None:
        """Paint one trail segment with outline, line, and arrows."""
        if len(screen_points) < 2:
            return

        r, g, b = segment.color
        line_w = segment.line_width
        alpha = int(255 * opacity)
        color = QColor(r, g, b, alpha)

        # Apply horizontal offset for overlapping routes
        if offset_x != 0.0:
            pts = [QPointF(p.x() + offset_x, p.y()) for p in screen_points]
        else:
            pts = screen_points

        # --- White outline (drawn first, slightly wider) ---
        outline_color = QColor(255, 255, 255, alpha)
        outline_pen = QPen(outline_color, line_w + self._OUTLINE_WIDTH * 2,
                           Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(outline_pen)
        painter.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        painter.drawPath(path)

        # --- Main colored line ---
        line_pen = QPen(color, line_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(line_pen)
        painter.drawPath(path)

        # --- Arrow at destination endpoint only ---
        if len(pts) >= 2:
            self._paint_arrow_at_end(painter, pts, color, alpha)

    def _paint_arrow_at_end(
        self,
        painter: QPainter,
        pts: list[QPointF],
        color: QColor,
        alpha: int,
    ) -> None:
        """Draw a single large arrowhead at the destination (last point)."""
        p1 = pts[-2]
        p2 = pts[-1]
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length < 2:
            return
        nx, ny = dx / length, dy / length

        al = self._ARROW_LEN
        aw = self._ARROW_WIDTH
        tip = QPointF(p2.x(), p2.y())
        left = QPointF(
            tip.x() - al * nx + aw * ny,
            tip.y() - al * ny - aw * nx,
        )
        right = QPointF(
            tip.x() - al * nx - aw * ny,
            tip.y() - al * ny + aw * nx,
        )

        # White outline (slightly larger)
        outline_c = QColor(255, 255, 255, alpha)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(outline_c))
        ol_al = al + 2
        ol_aw = aw + 1.5
        outline_path = QPainterPath()
        outline_path.moveTo(tip)
        outline_path.lineTo(QPointF(
            tip.x() - ol_al * nx + ol_aw * ny,
            tip.y() - ol_al * ny - ol_aw * nx,
        ))
        outline_path.lineTo(QPointF(
            tip.x() - ol_al * nx - ol_aw * ny,
            tip.y() - ol_al * ny + ol_aw * nx,
        ))
        outline_path.closeSubpath()
        painter.drawPath(outline_path)

        # Filled arrow
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), alpha)))
        arrow_path = QPainterPath()
        arrow_path.moveTo(tip)
        arrow_path.lineTo(left)
        arrow_path.lineTo(right)
        arrow_path.closeSubpath()
        painter.drawPath(arrow_path)

    # ------------------------------------------------------------------
    # Highlight
    # ------------------------------------------------------------------
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
