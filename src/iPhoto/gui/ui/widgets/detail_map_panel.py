"""Map panel for the detail view showing the current photo's location."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .info_location_map import InfoLocationMapView


class DetailMapPanel(QWidget):
    """Side panel displaying a map centred on the current photo's GPS location.

    Includes a toggle button to show / hide markers for all library photos.
    """

    showAllToggled = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        map_runtime=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("detailMapPanel")
        self.setMinimumWidth(260)
        self.setMaximumWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header row
        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        title = QLabel("Location", header)
        title.setStyleSheet("font-weight: 600; font-size: 13px;")
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        self._show_all_btn = QPushButton("Show All Photos", header)
        self._show_all_btn.setCheckable(True)
        self._show_all_btn.setChecked(False)
        self._show_all_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 8px; border-radius: 6px; "
            "border: 1px solid palette(mid); }"
            "QPushButton:checked { background-color: palette(highlight); color: palette(highlighted-text); }"
        )
        self._show_all_btn.toggled.connect(self.showAllToggled.emit)
        header_layout.addWidget(self._show_all_btn)

        layout.addWidget(header)

        # Map view
        self._map_view = InfoLocationMapView(self, map_runtime=map_runtime)
        layout.addWidget(self._map_view, 1)

        # Status label (shown when no GPS data)
        self._no_location_label = QLabel("No location data for this photo.", self)
        self._no_location_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_location_label.setStyleSheet("color: #86868b; font-size: 12px;")
        self._no_location_label.hide()
        layout.addWidget(self._no_location_label)

    # ---- Public API ----

    def set_location(self, latitude: float, longitude: float) -> None:
        """Centre the map on the given coordinates."""
        self._no_location_label.hide()
        self._map_view.show()
        self._map_view.set_location(latitude, longitude)

    def clear_location(self) -> None:
        """Remove the pin and show the 'no location' message."""
        self._map_view.clear_location()
        self._map_view.hide()
        self._no_location_label.show()

    def set_map_runtime(self, map_runtime) -> None:
        self._map_view.set_map_runtime(map_runtime)

    def shutdown(self) -> None:
        self._map_view.shutdown()
