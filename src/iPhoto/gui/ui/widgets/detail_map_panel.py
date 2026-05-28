"""Map panel for the detail view showing the current photo's location."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .info_location_map import InfoLocationMapView


class DetailMapPanel(QWidget):
    """Side panel displaying a mini-map centred on the current photo's GPS location."""

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

        layout.addWidget(header)

        # GPS coordinates label
        self._coords_label = QLabel("", self)
        self._coords_label.setStyleSheet("color: #86868b; font-size: 11px;")
        self._coords_label.hide()
        layout.addWidget(self._coords_label)

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
        self._coords_label.setText(
            f"{latitude:.6f}, {longitude:.6f}"
        )
        self._coords_label.show()

    def clear_location(self) -> None:
        """Remove the pin and show the 'no location' message."""
        self._map_view.clear_location()
        self._map_view.hide()
        self._no_location_label.show()
        self._coords_label.hide()

    def current_location(self) -> tuple[float | None, float | None]:
        """Return the current pin location (latitude, longitude)."""
        return self._map_view.current_location()

    def set_map_runtime(self, map_runtime) -> None:
        self._map_view.set_map_runtime(map_runtime)

    def shutdown(self) -> None:
        self._map_view.shutdown()
