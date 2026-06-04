"""Timeline range slider widget for date range filtering."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import (
    QDate,
    QPoint,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _DateLabel(QLabel):
    """Clickable date label that opens a calendar popup for manual editing."""

    dateChanged = Signal(datetime)

    def __init__(self, dt: datetime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dt = dt
        self._update_text()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QLabel { font-size: 11px; color: #356CB4; padding: 2px 6px; "
            "border: 1px solid transparent; border-radius: 4px; }"
            "QLabel:hover { border-color: #356CB4; background: rgba(53,108,180,0.06); }"
        )
        self.setFixedWidth(88)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_date(self, dt: datetime) -> None:
        self._dt = dt
        self._update_text()

    def date(self) -> datetime:
        return self._dt

    def _update_text(self) -> None:
        self.setText(self._dt.strftime("%Y-%m-%d"))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._show_calendar()
        super().mousePressEvent(event)

    def _show_calendar(self) -> None:
        dialog = QDialog(self.window())
        dialog.setWindowTitle("Select Date")
        dialog.setMinimumSize(320, 280)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        cal = QCalendarWidget()
        cal.setSelectedDate(QDate(self._dt.year, self._dt.month, self._dt.day))
        cal.setGridVisible(True)
        cal.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        layout.addWidget(cal)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        # Position the popup near the label.
        pos = self.mapToGlobal(QPoint(0, self.height()))
        dialog.move(pos)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            qd = cal.selectedDate()
            new_dt = datetime(qd.year(), qd.month(), qd.day())
            if new_dt != self._dt:
                self._dt = new_dt
                self._update_text()
                self.dateChanged.emit(new_dt)


class TimelineSlider(QWidget):
    """Range slider for selecting a date range on the photo trail.

    Shows a visual track with two draggable handles representing the
    start (left) and end (right) dates.  The highlighted area between
    the handles is the active date range.  Date labels are clickable
    to open a calendar picker for manual entry.

    Signals
    -------
    rangeChanged(datetime, datetime)
        Emitted when the selected date range changes.
    granularityChanged(str)
        Emitted when the granularity changes ("day", "week", "month").
    """

    rangeChanged = Signal(datetime, datetime)
    granularityChanged = Signal(str)

    HANDLE_RADIUS = 8
    TRACK_HEIGHT = 6
    HANDLE_HIT_PADDING = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._start_date = datetime(2000, 1, 1)
        self._end_date = datetime.now()
        self._current_start = self._start_date
        self._current_end = self._end_date
        self._granularity = "day"
        self._updating = False
        self._dragging: Optional[str] = None  # "start" | "end" | None

        self.setMinimumHeight(44)
        self.setMouseTracking(True)

        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 2, 8, 4)
        root.setSpacing(4)

        # --- Track area (custom painted) ---
        self._track = QWidget()
        self._track.setFixedHeight(self.HANDLE_RADIUS * 2 + self.TRACK_HEIGHT + 4)
        self._track.setMouseTracking(True)
        self._track.mousePressEvent = self._track_mouse_press
        self._track.mouseMoveEvent = self._track_mouse_move
        self._track.mouseReleaseEvent = self._track_mouse_release
        self._track.paintEvent = self._paint_track
        root.addWidget(self._track)

        # --- Bottom row: date labels + granularity buttons ---
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(6)

        self._start_label = _DateLabel(self._current_start)
        self._start_label.dateChanged.connect(self._on_start_label_changed)
        bottom.addWidget(self._start_label)

        bottom.addStretch(1)

        self._btn_day = QPushButton("Day")
        self._btn_week = QPushButton("Week")
        self._btn_month = QPushButton("Month")
        for btn in (self._btn_day, self._btn_week, self._btn_month):
            btn.setCheckable(True)
            btn.setFixedWidth(46)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                "QPushButton { font-size: 11px; border: 1px solid #ccc; "
                "border-radius: 4px; padding: 2px 6px; }"
                "QPushButton:checked { background: #356CB4; color: white; "
                "border-color: #356CB4; }"
            )
            btn.clicked.connect(self._on_granularity_clicked)
        self._btn_day.setChecked(True)
        bottom.addWidget(self._btn_day)
        bottom.addWidget(self._btn_week)
        bottom.addWidget(self._btn_month)

        bottom.addStretch(1)

        self._end_label = _DateLabel(self._current_end)
        self._end_label.dateChanged.connect(self._on_end_label_changed)
        bottom.addWidget(self._end_label)

        root.addLayout(bottom)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_date_range(self, start: datetime, end: datetime) -> None:
        """Set the available date range."""
        self._updating = True
        self._start_date = start
        self._end_date = end
        self._current_start = start
        self._current_end = end
        self._start_label.set_date(start)
        self._end_label.set_date(end)
        self._track.update()
        self._updating = False

    @property
    def current_start(self) -> datetime:
        return self._current_start

    @property
    def current_end(self) -> datetime:
        return self._current_end

    @property
    def granularity(self) -> str:
        return self._granularity

    # ------------------------------------------------------------------
    # Track geometry
    # ------------------------------------------------------------------
    def _track_rect(self) -> QRect:
        """Return the rectangle where the track bar is drawn."""
        w = self._track.width()
        h = self._track.height()
        margin = self.HANDLE_RADIUS + 4
        return QRect(
            margin, h // 2 - self.TRACK_HEIGHT // 2,
            max(w - 2 * margin, 0), self.TRACK_HEIGHT,
        )

    def _value_to_x(self, dt: datetime) -> int:
        total = (self._end_date - self._start_date).total_seconds()
        if total <= 0:
            return self._track_rect().left()
        frac = (dt - self._start_date).total_seconds() / total
        tr = self._track_rect()
        return int(tr.left() + frac * tr.width())

    def _x_to_value(self, x: int) -> datetime:
        tr = self._track_rect()
        if tr.width() <= 0:
            return self._start_date
        frac = max(0.0, min(1.0, (x - tr.left()) / tr.width()))
        total = (self._end_date - self._start_date).total_seconds()
        return self._start_date + timedelta(seconds=total * frac)

    def _handle_rect(self, which: str) -> QRect:
        dt = self._current_start if which == "start" else self._current_end
        cx = self._value_to_x(dt)
        r = self.HANDLE_RADIUS
        cy = self._track.height() // 2
        return QRect(cx - r, cy - r, r * 2, r * 2)

    # ------------------------------------------------------------------
    # Track painting
    # ------------------------------------------------------------------
    def _paint_track(self, event) -> None:
        painter = QPainter(self._track)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tr = self._track_rect()

        # Background track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#DDE1E6"))
        painter.drawRoundedRect(
            tr, self.TRACK_HEIGHT // 2, self.TRACK_HEIGHT // 2,
        )

        # Active range (between handles)
        sx = self._value_to_x(self._current_start)
        ex = self._value_to_x(self._current_end)
        active = QRect(sx, tr.top(), max(ex - sx, 0), tr.height())
        painter.setBrush(QColor("#356CB4"))
        painter.drawRoundedRect(
            active, self.TRACK_HEIGHT // 2, self.TRACK_HEIGHT // 2,
        )

        # Handles
        for which in ("start", "end"):
            hr = self._handle_rect(which)
            painter.setPen(QPen(QColor("#356CB4"), 2))
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(hr.adjusted(1, 1, -1, -1))

        painter.end()

    # ------------------------------------------------------------------
    # Mouse interaction for handle dragging
    # ------------------------------------------------------------------
    def _hit_handle(self, pos: QPoint) -> Optional[str]:
        for which in ("start", "end"):
            hr = self._handle_rect(which).adjusted(
                -self.HANDLE_HIT_PADDING, -self.HANDLE_HIT_PADDING,
                self.HANDLE_HIT_PADDING, self.HANDLE_HIT_PADDING,
            )
            if hr.contains(pos):
                return which
        return None

    def _track_mouse_press(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hit = self._hit_handle(event.pos())
        if hit:
            self._dragging = hit
            self._track.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            # Click on track body: move nearest handle
            click_dt = self._x_to_value(event.pos().x())
            dist_start = abs((click_dt - self._current_start).total_seconds())
            dist_end = abs((click_dt - self._current_end).total_seconds())
            self._dragging = "start" if dist_start <= dist_end else "end"
            self._apply_drag(event.pos().x())

    def _track_mouse_move(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._apply_drag(event.pos().x())
        else:
            hit = self._hit_handle(event.pos())
            self._track.setCursor(
                Qt.CursorShape.OpenHandCursor if hit else Qt.CursorShape.ArrowCursor,
            )

    def _track_mouse_release(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._apply_drag(event.pos().x())
            self._dragging = None
            self._track.setCursor(Qt.CursorShape.ArrowCursor)
            self.rangeChanged.emit(self._current_start, self._current_end)

    def _apply_drag(self, x: int) -> None:
        new_dt = self._x_to_value(x)
        if self._dragging == "start":
            if new_dt >= self._current_end:
                new_dt = self._current_end - timedelta(seconds=1)
            if new_dt < self._start_date:
                new_dt = self._start_date
            if new_dt != self._current_start:
                self._current_start = new_dt
                self._start_label.set_date(new_dt)
                self._track.update()
        else:
            if new_dt <= self._current_start:
                new_dt = self._current_start + timedelta(seconds=1)
            if new_dt > self._end_date:
                new_dt = self._end_date
            if new_dt != self._current_end:
                self._current_end = new_dt
                self._end_label.set_date(new_dt)
                self._track.update()

    # ------------------------------------------------------------------
    # Date label calendar callbacks
    # ------------------------------------------------------------------
    def _on_start_label_changed(self, dt: datetime) -> None:
        if dt >= self._current_end:
            dt = self._current_end - timedelta(days=1)
        if dt < self._start_date:
            dt = self._start_date
        self._current_start = dt
        self._start_label.set_date(dt)
        self._track.update()
        self.rangeChanged.emit(self._current_start, self._current_end)

    def _on_end_label_changed(self, dt: datetime) -> None:
        if dt <= self._current_start:
            dt = self._current_start + timedelta(days=1)
        if dt > self._end_date:
            dt = self._end_date
        self._current_end = dt
        self._end_label.set_date(dt)
        self._track.update()
        self.rangeChanged.emit(self._current_start, self._current_end)

    # ------------------------------------------------------------------
    # Granularity
    # ------------------------------------------------------------------
    def _on_granularity_clicked(self) -> None:
        sender = self.sender()
        if sender is self._btn_day:
            g = "day"
        elif sender is self._btn_week:
            g = "week"
        else:
            g = "month"

        if g == self._granularity:
            return

        self._granularity = g
        self._btn_day.setChecked(g == "day")
        self._btn_week.setChecked(g == "week")
        self._btn_month.setChecked(g == "month")
        self.granularityChanged.emit(g)
