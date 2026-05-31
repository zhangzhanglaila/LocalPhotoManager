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
        loading_content_layout.setSpacing(20)
        loading_content_layout.setContentsMargins(40, 40, 40, 40)

        # Step indicators
        self._step_container = QWidget()
        step_layout = QHBoxLayout(self._step_container)
        step_layout.setSpacing(24)

        self._step1_widget = self._create_step_widget("1", "加载 AI 模型")
        self._step2_widget = self._create_step_widget("2", "生成照片索引")
        step_layout.addWidget(self._step1_widget)
        step_layout.addWidget(self._step2_widget)
        loading_content_layout.addWidget(self._step_container, 0, Qt.AlignmentFlag.AlignCenter)

        # Status icon with animation
        self._loading_icon = QLabel("⏳")
        self._loading_icon.setStyleSheet("font-size: 48px;")
        self._loading_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_content_layout.addWidget(self._loading_icon)

        # Main status text
        self._loading_label = QLabel("")
        self._loading_label.setStyleSheet("font-size: 16px; font-weight: bold; color: palette(text);")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_content_layout.addWidget(self._loading_label)

        # Sub status text
        self._loading_sublabel = QLabel("")
        self._loading_sublabel.setStyleSheet("font-size: 13px; color: palette(mid);")
        self._loading_sublabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_content_layout.addWidget(self._loading_sublabel)

        # Progress bar (only for step 2)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setMinimumWidth(350)
        self._progress_bar.setMaximumWidth(500)
        self._progress_bar.setFixedHeight(20)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        self._progress_bar.hide()
        loading_content_layout.addWidget(self._progress_bar, 0, Qt.AlignmentFlag.AlignCenter)

        # Progress detail text
        self._progress_detail = QLabel("")
        self._progress_detail.setStyleSheet("font-size: 12px; color: palette(mid);")
        self._progress_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_detail.hide()
        loading_content_layout.addWidget(self._progress_detail)

        # Elapsed time
        self._elapsed_label = QLabel("")
        self._elapsed_label.setStyleSheet("font-size: 12px; color: palette(mid);")
        self._elapsed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_content_layout.addWidget(self._elapsed_label)

        # Continue browsing button
        self._continue_button = QToolButton()
        self._continue_button.setText("先去看照片，后台继续")
        self._continue_button.setStyleSheet(
            "QToolButton { font-size: 13px; padding: 10px 24px; "
            "background-color: palette(highlight); color: palette(highlighted-text); "
            "border-radius: 8px; font-weight: bold; }"
            "QToolButton:hover { opacity: 0.85; }"
        )
        self._continue_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._continue_button.clicked.connect(self._on_continue_browsing)
        loading_content_layout.addWidget(self._continue_button, 0, Qt.AlignmentFlag.AlignCenter)

        # Hint text
        self._hint_label = QLabel("💡 之后搜索只需 0.1 秒")
        self._hint_label.setStyleSheet("font-size: 12px; color: palette(mid);")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

        # Only show progress bar when show_progress is True (embedding phase)
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

    def show_model_loading(self) -> None:
        """Show model loading phase (no progress bar, just spinner + time)."""
        self.show_loading_message(
            "正在加载 AI 模型（约350MB）...",
            "这是首次使用，需要加载 AI 模型，之后会很快",
            show_progress=False,
            show_continue=True
        )

    def show_embedding_progress(self, current: int, total: int) -> None:
        """Show embedding generation phase (with progress bar)."""
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        progress_pct = int(current / total * 100) if total > 0 else 0
        self._loading_label.setText(f"正在为照片生成索引... {progress_pct}%")
        self._loading_sublabel.setText(f"已处理 {current}/{total} 张照片")
        self._progress_bar.show()
        self._continue_button.show()
        self._hint_label.show()

    def _create_step_widget(self, number: str, label: str) -> QWidget:
        """Create a step indicator widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Circle with number
        circle = QLabel(number)
        circle.setFixedSize(32, 32)
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        circle.setStyleSheet(
            "QLabel { border-radius: 16px; background-color: palette(mid); "
            "color: palette(mid); font-weight: bold; font-size: 14px; }"
        )
        layout.addWidget(circle, 0, Qt.AlignmentFlag.AlignCenter)

        # Label
        text = QLabel(label)
        text.setStyleSheet("font-size: 11px; color: palette(mid);")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text)

        # Store references for updating
        widget._circle = circle
        widget._text = label
        return widget

    def _update_step_status(self, step: int, status: str) -> None:
        """Update step indicator status.

        Args:
            step: 1 or 2
            status: "pending", "active", "done"
        """
        widget = self._step1_widget if step == 1 else self._step2_widget
        circle = widget._circle

        if status == "active":
            circle.setStyleSheet(
                "QLabel { border-radius: 16px; background-color: palette(highlight); "
                "color: palette(highlighted-text); font-weight: bold; font-size: 14px; }"
            )
        elif status == "done":
            circle.setText("✓")
            circle.setStyleSheet(
                "QLabel { border-radius: 16px; background-color: #34C759; "
                "color: white; font-weight: bold; font-size: 14px; }"
            )
        else:  # pending
            circle.setStyleSheet(
                "QLabel { border-radius: 16px; background-color: palette(mid); "
                "color: palette(mid); font-weight: bold; font-size: 14px; }"
            )

    def show_model_loading(self) -> None:
        """Show model loading phase."""
        self._update_step_status(1, "active")
        self._update_step_status(2, "pending")
        self._loading_icon.setText("⏳")
        self._loading_label.setText("正在加载 AI 模型（约350MB）...")
        self._loading_sublabel.setText("首次使用需要加载模型，之后会很快")
        self._progress_bar.hide()
        self._progress_detail.hide()
        self._continue_button.show()
        self._hint_label.show()
        self._search_title_label.setText("初始化中")

        # Start elapsed timer
        self._loading_start_time = time.time()
        self._elapsed_label.show()
        self._elapsed_label.setText("已等待 0 秒...")
        self._elapsed_timer.start(1000)
        self._loading_dots = 0

        self._stack.setCurrentWidget(self._loading_widget)

    def show_embedding_progress(self, current: int, total: int) -> None:
        """Show embedding generation phase with progress bar."""
        self._update_step_status(1, "done")
        self._update_step_status(2, "active")
        self._loading_icon.setText("📸")
        progress_pct = int(current / total * 100) if total > 0 else 0
        self._loading_label.setText(f"正在为照片生成索引")
        self._loading_sublabel.setText(f"已处理 {current} / {total} 张照片")
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._progress_bar.show()
        self._progress_detail.setText(f"{progress_pct}% 完成")
        self._progress_detail.show()
        self._continue_button.show()
        self._hint_label.show()

    def show_loading_message(self, message: str, sub_message: str = "", show_progress: bool = False, show_continue: bool = True) -> None:
        """Show a generic loading message."""
        self._loading_label.setText(message)
        self._loading_sublabel.setText(sub_message)
        self._search_title_label.setText("搜索中")

        if show_progress:
            self._progress_bar.show()
        else:
            self._progress_bar.hide()

        self._progress_detail.hide()
        self._continue_button.setVisible(show_continue)
        self._hint_label.setVisible(show_continue)

        # Start elapsed timer
        if self._loading_start_time == 0:
            self._loading_start_time = time.time()
            self._elapsed_label.show()
            self._elapsed_label.setText("已等待 0 秒...")
            self._elapsed_timer.start(1000)
            self._loading_dots = 0

        self._stack.setCurrentWidget(self._loading_widget)

    def update_progress(self, current: int, total: int, message: str = None) -> None:
        """Update progress bar."""
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        if message:
            self._loading_label.setText(message)

    def _on_continue_browsing(self) -> None:
        """Handle continue browsing button click."""
        self.hide_loading_message()
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
        self._progress_detail.hide()
        self._elapsed_label.hide()
        self._elapsed_timer.stop()
        self._loading_start_time = 0
        # Reset step indicators
        self._update_step_status(1, "pending")
        self._update_step_status(2, "pending")
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
