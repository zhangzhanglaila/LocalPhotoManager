"""Timeline slider widget for date range filtering."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class TimelineSlider(QWidget):
    """A slider widget for selecting a date range and granularity.

    Signals
    -------
    rangeChanged(datetime, datetime)
        Emitted when the selected date range changes.
    granularityChanged(str)
        Emitted when the granularity changes ("day", "week", "month").
    """

    rangeChanged = Signal(datetime, datetime)
    granularityChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._start_date = datetime(2000, 1, 1)
        self._end_date = datetime.now()
        self._current_start = self._start_date
        self._current_end = self._end_date
        self._granularity = "day"
        self._updating = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Start date label
        self._start_label = QLabel(self._fmt(self._current_start))
        self._start_label.setFixedWidth(80)
        layout.addWidget(self._start_label)

        # Start slider
        self._slider_start = QSlider(Qt.Horizontal)
        self._slider_start.setMinimum(0)
        self._slider_start.setMaximum(1000)
        self._slider_start.setValue(0)
        self._slider_start.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self._slider_start, 1)

        # End slider
        self._slider_end = QSlider(Qt.Horizontal)
        self._slider_end.setMinimum(0)
        self._slider_end.setMaximum(1000)
        self._slider_end.setValue(1000)
        self._slider_end.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self._slider_end, 1)

        # End date label
        self._end_label = QLabel(self._fmt(self._current_end))
        self._end_label.setFixedWidth(80)
        layout.addWidget(self._end_label)

        # Granularity buttons
        self._btn_day = QPushButton("日")
        self._btn_week = QPushButton("周")
        self._btn_month = QPushButton("月")
        for btn in (self._btn_day, self._btn_week, self._btn_month):
            btn.setCheckable(True)
            btn.setFixedWidth(32)
            btn.clicked.connect(self._on_granularity_clicked)
        self._btn_day.setChecked(True)
        layout.addWidget(self._btn_day)
        layout.addWidget(self._btn_week)
        layout.addWidget(self._btn_month)

    def set_date_range(self, start: datetime, end: datetime) -> None:
        """Set the available date range."""
        self._updating = True
        self._start_date = start
        self._end_date = end
        self._current_start = start
        self._current_end = end
        self._start_label.setText(self._fmt(start))
        self._end_label.setText(self._fmt(end))
        self._slider_start.setValue(0)
        self._slider_end.setValue(1000)
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

    def _on_slider_changed(self, _value: int) -> None:
        if self._updating:
            return

        low = min(self._slider_start.value(), self._slider_end.value())
        high = max(self._slider_start.value(), self._slider_end.value())

        total_seconds = (self._end_date - self._start_date).total_seconds()
        if total_seconds <= 0:
            return

        self._current_start = self._start_date + (
            self._end_date - self._start_date
        ) * (low / 1000)
        self._current_end = self._start_date + (
            self._end_date - self._start_date
        ) * (high / 1000)

        self._start_label.setText(self._fmt(self._current_start))
        self._end_label.setText(self._fmt(self._current_end))

        self.rangeChanged.emit(self._current_start, self._current_end)

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

    @staticmethod
    def _fmt(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d")
