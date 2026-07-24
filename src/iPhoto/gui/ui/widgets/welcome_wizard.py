"""初次启动引导对话框，帮助用户配置工作目录。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QWidget,
)


class WelcomeWizard(QDialog):
    """初次启动引导对话框。

    显示默认工作目录，允许用户点击按钮修改。
    """

    # 信号：完成配置，传递 (workspace_base: Optional[Path])
    finished = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._custom_path: Optional[Path] = None
        self._use_custom = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """设置用户界面。"""
        self.setWindowTitle("欢迎使用 iPhotron - 配置工作目录")
        self.setMinimumSize(550, 250)
        self.resize(550, 250)

        # 设置为模态对话框
        self.setModal(True)

        # 确保窗口在最前面
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        # 禁用整个对话框的文本选择
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # 标题
        title = QLabel("欢迎使用 iPhotron 📸")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #000;")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(title)

        # 说明
        description = QLabel(
            "iPhotron 需要存储索引、缩略图等工作文件。\n"
            "请选择这些文件的存储位置："
        )
        description.setStyleSheet("font-size: 14px; color: #333;")
        description.setWordWrap(True)
        description.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(description)

        layout.addSpacing(12)

        # 路径显示和选择区域
        path_container = QWidget()
        path_layout = QHBoxLayout(path_container)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(12)

        # 路径显示框
        self._path_display = QLineEdit()
        default_path = Path.home() / "iPhotronWorkspace"
        self._path_display.setText(str(default_path))
        self._path_display.setReadOnly(True)
        self._path_display.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                font-size: 13px;
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 6px;
            }
        """)
        path_layout.addWidget(self._path_display, 1)

        # 选择按钮
        self._browse_button = QPushButton("选择目录...")
        self._browse_button.setMinimumWidth(100)
        self._browse_button.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
                padding: 10px 16px;
            }
            QPushButton:hover {
                background-color: #0051D5;
            }
            QPushButton:pressed {
                background-color: #003F9D;
            }
        """)
        self._browse_button.clicked.connect(self._on_select_path)
        path_layout.addWidget(self._browse_button)

        layout.addWidget(path_container)

        layout.addSpacing(16)

        # 说明文字
        note = QLabel("提示：可以保留默认位置，或点击右侧按钮选择自定义目录")
        note.setStyleSheet("font-size: 12px; color: #888; font-style: italic;")
        note.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(note)

        # 弹簧
        layout.addStretch()

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._finish_button = QPushButton("开始使用")
        self._finish_button.setMinimumSize(120, 36)
        self._finish_button.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 24px;
            }
            QPushButton:hover {
                background-color: #0051D5;
            }
            QPushButton:pressed {
                background-color: #003F9D;
            }
        """)
        self._finish_button.clicked.connect(self._on_finish)
        button_layout.addWidget(self._finish_button)

        layout.addLayout(button_layout)

    def _on_select_path(self) -> None:
        """选择自定义路径。"""
        current = self._custom_path or (Path.home() / "iPhotronWorkspace")
        path = QFileDialog.getExistingDirectory(
            self,
            "选择工作目录的基础位置",
            str(current),
        )
        if path:
            base_path = Path(path)
            # 自动添加 iPhotronWorkspace 子目录
            self._custom_path = base_path / "iPhotronWorkspace"
            # 显示完整路径
            self._path_display.setText(str(self._custom_path))
            self._use_custom = True

    def _on_finish(self) -> None:
        """完成配置。"""
        # 获取选择的路径
        if self._use_custom and self._custom_path:
            workspace_base = self._custom_path
        else:
            # 使用显示框中的路径（可能是默认路径）
            workspace_base = Path(self._path_display.text())

        # 应用设置
        from ....utils.pathutils import set_custom_workspace_base
        set_custom_workspace_base(workspace_base)

        # 发射完成信号
        self.finished.emit(workspace_base)

        # 关闭对话框
        self.accept()

    def get_selected_workspace_base(self) -> Optional[Path]:
        """获取选择的工作目录基础路径。"""
        if self._use_custom and self._custom_path:
            return self._custom_path
        return Path(self._path_display.text())

    def show_and_wait(self) -> Optional[Path]:
        """显示对话框并等待用户选择，返回选择的工作目录基础路径。"""
        result = self.exec()
        if result == QDialog.DialogCode.Accepted:
            return self.get_selected_workspace_base()
        return None
