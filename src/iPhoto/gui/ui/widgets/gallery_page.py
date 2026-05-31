"""Gallery page embedding the grid view inside a simple layout."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from ..icon import load_icon
from .gallery_grid_view import GalleryGridView
from .main_window_metrics import HEADER_BUTTON_SIZE, HEADER_ICON_GLYPH_SIZE


class GalleryPageWidget(QWidget):
    """Thin wrapper that exposes the gallery grid view as a self-contained page."""

    backRequested = Signal()
    """Signal emitted when the back button is clicked in cluster gallery mode."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("galleryPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with optional back button for cluster gallery mode
        self._header = QWidget()
        self._header.setObjectName("galleryHeader")
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(8, 8, 8, 8)
        header_layout.setSpacing(8)

        self.back_button = QToolButton()
        self.back_button.setObjectName("galleryBackButton")
        self.back_button.setIcon(load_icon("chevron.left.svg"))
        self.back_button.setIconSize(HEADER_ICON_GLYPH_SIZE)
        self.back_button.setFixedSize(HEADER_BUTTON_SIZE)
        self.back_button.setAutoRaise(True)
        self.back_button.setToolTip("Return to Map")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(self.backRequested.emit)
        header_layout.addWidget(self.back_button)
        header_layout.addStretch()

        # Hide header by default; shown only in cluster gallery mode
        self._header.hide()
        layout.addWidget(self._header)

        # Create a stacked widget to switch between grid view and loading message
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Grid view (index 0)
        self.grid_view = GalleryGridView()
        self.grid_view.setObjectName("galleryGridView")
        self._stack.addWidget(self.grid_view)

        # Loading message widget (index 1)
        self._loading_widget = QWidget()
        loading_layout = QVBoxLayout(self._loading_widget)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._loading_icon = QLabel("🔍")
        self._loading_icon.setStyleSheet("font-size: 48px;")
        self._loading_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(self._loading_icon)

        self._loading_label = QLabel("")
        self._loading_label.setStyleSheet("font-size: 16px; color: palette(text);")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(self._loading_label)

        self._loading_sublabel = QLabel("正在使用 AI 搜索照片...")
        self._loading_sublabel.setStyleSheet("font-size: 12px; color: palette(mid);")
        self._loading_sublabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(self._loading_sublabel)

        self._stack.addWidget(self._loading_widget)

        # Show grid view by default
        self._stack.setCurrentWidget(self.grid_view)

    def show_loading_message(self, message: str) -> None:
        """Show a loading message in the gallery area.

        Args:
            message: The message to display.
        """
        self._loading_label.setText(message)
        self._stack.setCurrentWidget(self._loading_widget)

    def hide_loading_message(self) -> None:
        """Hide the loading message and show the grid view."""
        self._stack.setCurrentWidget(self.grid_view)

    def set_cluster_gallery_mode(self, enabled: bool, back_tooltip: str = "Return") -> None:
        """Show or hide the header with back button for cluster gallery mode.

        Args:
            enabled: True to show the back button header (cluster gallery mode),
                     False to hide it (normal gallery mode).
        """
        self.back_button.setToolTip(back_tooltip)
        self._header.setVisible(enabled)


__all__ = ["GalleryPageWidget"]
