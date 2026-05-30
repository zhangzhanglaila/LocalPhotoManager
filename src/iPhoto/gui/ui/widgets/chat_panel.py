"""Chat panel for conversational photo management."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ....i18n import tr

_LOGGER = logging.getLogger(__name__)


class ChatMessageWidget(QWidget):
    """Widget displaying a single chat message."""

    def __init__(
        self,
        text: str,
        is_user: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the chat message widget.

        Parameters
        ----------
        text : str
            The message text.
        is_user : bool
            Whether this is a user message (True) or AI message (False).
        parent : QWidget | None
            Parent widget.
        """
        super().__init__(parent)
        self._is_user = is_user

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # Create message bubble
        self._bubble = QLabel(text)
        self._bubble.setWordWrap(True)
        self._bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # Style based on sender
        if is_user:
            self._bubble.setStyleSheet(
                "QLabel { background-color: palette(highlight); color: palette(highlighted-text); "
                "border-radius: 12px; padding: 8px 12px; }"
            )
            layout.addStretch()
            layout.addWidget(self._bubble, 0, Qt.AlignmentFlag.AlignRight)
        else:
            self._bubble.setStyleSheet(
                "QLabel { background-color: palette(base); color: palette(text); "
                "border: 1px solid palette(mid); border-radius: 12px; padding: 8px 12px; }"
            )
            layout.addWidget(self._bubble, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addStretch()


class ChatPanel(QWidget):
    """Panel for conversational interaction with the photo library.

    This panel provides a chat-like interface where users can ask questions
    and give commands in natural language.
    """

    # Signal emitted when user sends a message
    message_sent = Signal(str)

    # Signal emitted when user wants to search
    search_requested = Signal(str)

    # Signal emitted when user wants to perform an action
    action_requested = Signal(str, dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the chat panel.

        Parameters
        ----------
        parent : QWidget | None
            Parent widget.
        """
        super().__init__(parent)
        self.setObjectName("chatPanel")
        self.setMinimumWidth(300)
        self.setMaximumWidth(400)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background-color: palette(window);")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel(tr("chat.title", default="AI Assistant"))
        title.setFont(QFont("", 14, QFont.Weight.Bold))
        header_layout.addWidget(title)

        self._close_button = QPushButton("×")
        self._close_button.setFixedSize(24, 24)
        self._close_button.setStyleSheet(
            "QPushButton { border: none; font-size: 16px; }"
            "QPushButton:hover { background-color: palette(mid); border-radius: 12px; }"
        )
        self._close_button.clicked.connect(self.close)
        header_layout.addWidget(self._close_button)

        layout.addWidget(header)

        # Chat area
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._chat_container = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(8, 8, 8, 8)
        self._chat_layout.setSpacing(8)
        self._chat_layout.addStretch()

        self._scroll_area.setWidget(self._chat_container)
        layout.addWidget(self._scroll_area, 1)

        # Input area
        input_container = QWidget()
        input_container.setStyleSheet("background-color: palette(window);")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText(tr("chat.placeholder", default="Ask about your photos..."))
        self._input.returnPressed.connect(self._on_send)
        input_layout.addWidget(self._input, 1)

        self._send_button = QPushButton(tr("chat.send", default="Send"))
        self._send_button.clicked.connect(self._on_send)
        input_layout.addWidget(self._send_button)

        layout.addWidget(input_container)

        # Add welcome message
        self.add_message(
            tr("chat.welcome", default="Hello! I can help you find and organize your photos. Try asking me something!"),
            is_user=False,
        )

    def _on_send(self) -> None:
        """Handle send button click."""
        text = self._input.text().strip()
        if not text:
            return

        # Add user message
        self.add_message(text, is_user=True)
        self._input.clear()

        # Emit signal
        self.message_sent.emit(text)

    def add_message(self, text: str, is_user: bool = True) -> None:
        """Add a message to the chat.

        Parameters
        ----------
        text : str
            The message text.
        is_user : bool
            Whether this is a user message.
        """
        message = ChatMessageWidget(text, is_user, self._chat_container)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, message)

        # Scroll to bottom
        self._scroll_area.verticalScrollBar().setValue(
            self._scroll_area.verticalScrollBar().maximum()
        )

    def add_typing_indicator(self) -> None:
        """Add a typing indicator."""
        self.add_message(tr("chat.thinking", default="Thinking..."), is_user=False)

    def remove_last_message(self) -> None:
        """Remove the last message (used to remove typing indicator)."""
        count = self._chat_layout.count()
        if count > 1:
            item = self._chat_layout.itemAt(count - 2)
            if item and item.widget():
                item.widget().deleteLater()

    def clear(self) -> None:
        """Clear all messages."""
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Handle show event."""
        super().showEvent(event)
        self._input.setFocus()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Handle close event."""
        super().closeEvent(event)
