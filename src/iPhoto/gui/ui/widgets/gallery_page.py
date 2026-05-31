"""Gallery page embedding the grid view inside a simple layout."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from ..icon import load_icon
from .gallery_grid_view import GalleryGridView
from .main_window_metrics import HEADER_BUTTON_SIZE, HEADER_ICON_GLYPH_SIZE


class GalleryPageWidget(QWidget):
    """Thin wrapper that exposes the gallery grid view as a self-contained page."""

    backRequested = Signal()
    """Signal emitted when the back button is clicked in cluster gallery mode."""

    searchBackRequested = Signal()
    """Signal emitted when the back button is clicked during search."""

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
        loading_layout.setContentsMargins(0, 0, 0, 0)
        loading_layout.setSpacing(0)

        # Back button for search
        self._search_back_bar = QWidget()
        search_back_layout = QHBoxLayout(self._search_back_bar)
        search_back_layout.setContentsMargins(8, 8, 8, 8)

        self._search_back_button = QToolButton()
        self._search_back_button.setIcon(load_icon("chevron.left.svg"))
        self._search_back_button.setIconSize(HEADER_ICON_GLYPH_SIZE)
        self._search_back_button.setFixedSize(HEADER_BUTTON_SIZE)
        self._search_back_button.setAutoRaise(True)
        self._search_back_button.setToolTip("返回照片")
        self._search_back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._search_back_button.clicked.connect(self._on_search_back_clicked)
        search_back_layout.addWidget(self._search_back_button)

        self._search_title_label = QLabel("搜索中")
        self._search_title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        search_back_layout.addWidget(self._search_title_label)
        search_back_layout.addStretch()

        loading_layout.addWidget(self._search_back_bar)

        # Loading content
        loading_content = QWidget()
        loading_content_layout = QVBoxLayout(loading_content)
        loading_content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_content_layout.setSpacing(16)

        self._loading_icon = QLabel("🔍")
        self._loading_icon.setStyleSheet("font-size: 48px;")
        self._loading_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_content_layout.addWidget(self._loading_icon)

        self._loading_label = QLabel("")
        self._loading_label.setStyleSheet("font-size: 16px; color: palette(text);")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_content_layout.addWidget(self._loading_label)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setMinimumWidth(300)
        self._progress_bar.setMaximumWidth(500)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p% (%v/%m)")
        self._progress_bar.hide()
        loading_content_layout.addWidget(self._progress_bar, 0, Qt.AlignmentFlag.AlignCenter)

        self._loading_sublabel = QLabel("正在使用 AI 搜索照片...")
        self._loading_sublabel.setStyleSheet("font-size: 12px; color: palette(mid);")
        self._loading_sublabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_content_layout.addWidget(self._loading_sublabel)

        # Elapsed time label
        self._elapsed_label = QLabel("")
        self._elapsed_label.setStyleSheet("font-size: 11px; color: palette(mid);")
        self._elapsed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._elapsed_label.hide()
        loading_content_layout.addWidget(self._elapsed_label)

        # Continue browsing button
        self._continue_button = QToolButton()
        self._continue_button.setText("先去看照片 →")
        self._continue_button.setStyleSheet(
            "QToolButton { font-size: 13px; padding: 8px 16px; "
            "background-color: palette(highlight); color: palette(highlighted-text); "
            "border-radius: 6px; }"
            "QToolButton:hover { background-color: palette(highlight); opacity: 0.8; }"
        )
        self._continue_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._continue_button.clicked.connect(self._on_continue_browsing)
        self._continue_button.hide()
        loading_content_layout.addWidget(self._continue_button, 0, Qt.AlignmentFlag.AlignCenter)

        # Hint text
        self._hint_label = QLabel("AI 索引生成后，搜索会非常快（0.1秒）")
        self._hint_label.setStyleSheet("font-size: 11px; color: palette(mid); font-style: italic;")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.hide()
        loading_content_layout.addWidget(self._hint_label)

        loading_layout.addWidget(loading_content, 1)

        self._stack.addWidget(self._loading_widget)

        # Timer for elapsed time
        self._loading_start_time = 0
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._update_elapsed_time)
        self._loading_dots = 0

        # Show grid view by default
        self._stack.setCurrentWidget(self.grid_view)

    def show_loading_message(self, message: str, sub_message: str = "正在使用 AI 搜索照片...", show_progress: bool = False, show_continue: bool = False) -> None:
        """Show a loading message in the gallery area.

        Args:
            message: The main message to display.
            sub_message: The sub message to display.
            show_progress: Whether to show the progress bar.
            show_continue: Whether to show the continue browsing button.
        """
        self._loading_label.setText(message)
        self._loading_sublabel.setText(sub_message)
        self._search_title_label.setText("搜索中")
        if show_progress:
            self._progress_bar.show()
        else:
            self._progress_bar.hide()

        # Show/hide continue button
        self._continue_button.setVisible(show_continue)
        self._hint_label.setVisible(show_continue)

        # Start elapsed timer
        self._loading_start_time = time.time()
        self._elapsed_label.show()
        self._elapsed_label.setText("已等待 0 秒...")
        self._elapsed_timer.start(1000)  # Update every second
        self._loading_dots = 0

        self._stack.setCurrentWidget(self._loading_widget)

    def _on_continue_browsing(self) -> None:
        """Handle continue browsing button click."""
        # Hide the loading UI but keep the background task running
        self.hide_loading_message()
        # Emit signal to notify that user wants to continue browsing
        self.searchBackRequested.emit()

    def _update_elapsed_time(self) -> None:
        """Update the elapsed time display."""
        if self._loading_start_time > 0:
            elapsed = int(time.time() - self._loading_start_time)
            self._elapsed_label.setText(f"已等待 {elapsed} 秒...")

            # Animate dots in sublabel
            self._loading_dots = (self._loading_dots + 1) % 4
            dots = "." * self._loading_dots
            current_text = self._loading_sublabel.text()
            # Remove trailing dots and add new ones
            base_text = current_text.rstrip(".")
            self._loading_sublabel.setText(f"{base_text}{dots}")

    def update_progress(self, current: int, total: int, message: str = None) -> None:
        """Update the progress bar.

        Args:
            current: Current progress value.
            total: Total value.
            message: Optional message to display.
        """
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        if message:
            self._loading_label.setText(message)

    def show_search_results_mode(self, query: str) -> None:
        """Show search results mode with back button.

        Args:
            query: The search query.
        """
        self._search_title_label.setText(f"搜索: {query}")
        self._progress_bar.hide()
        self._stack.setCurrentWidget(self._loading_widget)

    def hide_loading_message(self) -> None:
        """Hide the loading message and show the grid view."""
        self._progress_bar.hide()
        self._elapsed_label.hide()
        self._elapsed_timer.stop()
        self._loading_start_time = 0
        self._stack.setCurrentWidget(self.grid_view)

    def _on_search_back_clicked(self) -> None:
        """Handle back button click during search."""
        # Emit a signal to go back to normal gallery view
        self.searchBackRequested.emit()
        self.hide_loading_message()

    def set_cluster_gallery_mode(self, enabled: bool, back_tooltip: str = "Return") -> None:
        """Show or hide the header with back button for cluster gallery mode.

        Args:
            enabled: True to show the back button header (cluster gallery mode),
                     False to hide it (normal gallery mode).
        """
        self.back_button.setToolTip(back_tooltip)
        self._header.setVisible(enabled)


__all__ = ["GalleryPageWidget"]
