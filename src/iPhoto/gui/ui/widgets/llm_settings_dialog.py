"""Dialog for configuring LLM settings."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from ....agent.config.llm_config import LLMConfig, LLMConfigManager
from ....i18n import tr

_LOGGER = logging.getLogger(__name__)


class LLMSettingsDialog(QDialog):
    """Dialog for configuring LLM settings.

    Allows users to:
    - Add/edit/delete LLM configurations
    - Set active configuration
    - Configure API key, model, URL, etc.
    """

    # Signal emitted when settings change
    settings_changed = Signal()

    def __init__(
        self,
        config_manager: LLMConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the LLM settings dialog.

        Parameters
        ----------
        config_manager : LLMConfigManager
            Manager for LLM configurations.
        parent : QWidget | None
            Parent widget.
        """
        super().__init__(parent)
        self._config_manager = config_manager
        self._current_config_id: Optional[str] = None

        self.setWindowTitle(tr("llm_settings.title", default="LLM 设置"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self._setup_ui()
        self._load_configs()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(tr("llm_settings.header", default="配置 LLM 模型"))
        header.setFont(QFont("", 14, QFont.Weight.Bold))
        layout.addWidget(header)

        # Description
        desc = QLabel(tr(
            "llm_settings.description",
            default="配置用于 AI 助手的大语言模型。支持 OpenAI API 兼容的服务。"
        ))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Config selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel(tr("llm_settings.select_config", default="选择配置:")))

        self._config_combo = QComboBox()
        self._config_combo.currentIndexChanged.connect(self._on_config_selected)
        selector_layout.addWidget(self._config_combo, 1)

        self._set_active_button = QPushButton(tr("llm_settings.set_active", default="设为默认"))
        self._set_active_button.clicked.connect(self._on_set_active)
        selector_layout.addWidget(self._set_active_button)

        layout.addLayout(selector_layout)

        # Config editor
        editor_group = QGroupBox(tr("llm_settings.config_details", default="配置详情"))
        editor_layout = QFormLayout(editor_group)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(tr("llm_settings.name_placeholder", default="配置名称"))
        editor_layout.addRow(tr("llm_settings.name", default="名称:"), self._name_edit)

        self._provider_combo = QComboBox()
        self._provider_combo.addItems([
            "deepseek", "qwen", "zhipu", "moonshot", "openai", "custom"
        ])
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)
        editor_layout.addRow(tr("llm_settings.provider", default="提供商:"), self._provider_combo)

        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://api.example.com/v1")
        editor_layout.addRow(tr("llm_settings.url", default="API URL:"), self._url_edit)

        self._model_edit = QLineEdit()
        self._model_edit.setPlaceholderText("model-name")
        editor_layout.addRow(tr("llm_settings.model", default="模型:"), self._model_edit)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText(tr("llm_settings.api_key_placeholder", default="输入 API Key"))
        editor_layout.addRow(tr("llm_settings.api_key", default="API Key:"), self._api_key_edit)

        self._max_tokens_spin = QSpinBox()
        self._max_tokens_spin.setRange(256, 32768)
        self._max_tokens_spin.setValue(4096)
        editor_layout.addRow(tr("llm_settings.max_tokens", default="最大 Tokens:"), self._max_tokens_spin)

        self._temperature_spin = QDoubleSpinBox()
        self._temperature_spin.setRange(0.0, 2.0)
        self._temperature_spin.setSingleStep(0.1)
        self._temperature_spin.setValue(0.7)
        editor_layout.addRow(tr("llm_settings.temperature", default="Temperature:"), self._temperature_spin)

        layout.addWidget(editor_group)

        # Buttons
        button_layout = QHBoxLayout()

        self._add_button = QPushButton(tr("llm_settings.add", default="添加"))
        self._add_button.clicked.connect(self._on_add)
        button_layout.addWidget(self._add_button)

        self._save_button = QPushButton(tr("llm_settings.save", default="保存"))
        self._save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self._save_button)

        self._delete_button = QPushButton(tr("llm_settings.delete", default="删除"))
        self._delete_button.clicked.connect(self._on_delete)
        button_layout.addWidget(self._delete_button)

        button_layout.addStretch()

        self._test_button = QPushButton(tr("llm_settings.test", default="测试连接"))
        self._test_button.clicked.connect(self._on_test)
        button_layout.addWidget(self._test_button)

        self._close_button = QPushButton(tr("llm_settings.close", default="关闭"))
        self._close_button.clicked.connect(self.close)
        button_layout.addWidget(self._close_button)

        layout.addLayout(button_layout)

        # Status label
        self._status_label = QLabel()
        layout.addWidget(self._status_label)

    def _load_configs(self) -> None:
        """Load configurations into the combo box."""
        self._config_combo.blockSignals(True)
        self._config_combo.clear()

        configs = self._config_manager.list_configs()
        active_id = self._config_manager.get_active_config_id()

        for config in configs:
            display_text = f"{config['name']} ({config['model']})"
            if config["is_active"]:
                display_text += " ★"
            if not config["has_api_key"]:
                display_text += " (未配置Key)"

            self._config_combo.addItem(display_text, config["id"])

        # Select active config
        if active_id:
            for i in range(self._config_combo.count()):
                if self._config_combo.itemData(i) == active_id:
                    self._config_combo.setCurrentIndex(i)
                    break

        self._config_combo.blockSignals(False)

        # Load the selected config
        self._on_config_selected(self._config_combo.currentIndex())

    def _on_config_selected(self, index: int) -> None:
        """Handle config selection change."""
        config_id = self._config_combo.currentData()
        if not config_id:
            return

        self._current_config_id = config_id
        config = self._config_manager.get_config(config_id)

        if config:
            self._name_edit.setText(config.name)
            self._provider_combo.setCurrentText(config.provider)
            self._url_edit.setText(config.base_url)
            self._model_edit.setText(config.model)
            self._api_key_edit.setText(config.api_key)
            self._max_tokens_spin.setValue(config.max_tokens)
            self._temperature_spin.setValue(config.temperature)

    def _on_provider_changed(self, provider: str) -> None:
        """Handle provider change - update URL and model defaults."""
        defaults = {
            "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
            "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-turbo"),
            "zhipu": ("https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
            "moonshot": ("https://api.moonshot.cn/v1", "moonshot-v1-8k"),
            "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
        }

        if provider in defaults:
            url, model = defaults[provider]
            # Only update if fields are empty or match a known default
            if not self._url_edit.text() or self._url_edit.text() in [v[0] for v in defaults.values()]:
                self._url_edit.setText(url)
            if not self._model_edit.text() or self._model_edit.text() in [v[1] for v in defaults.values()]:
                self._model_edit.setText(model)

    def _on_add(self) -> None:
        """Add a new configuration."""
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入配置名称")
            return

        # Generate config ID from name
        config_id = name.lower().replace(" ", "_")

        # Check if already exists
        if self._config_manager.get_config(config_id):
            QMessageBox.warning(self, "错误", f"配置 '{name}' 已存在")
            return

        # Create config
        config = LLMConfig(
            name=name,
            provider=self._provider_combo.currentText(),
            base_url=self._url_edit.text().strip(),
            model=self._model_edit.text().strip(),
            api_key=self._api_key_edit.text().strip(),
            max_tokens=self._max_tokens_spin.value(),
            temperature=self._temperature_spin.value(),
        )

        if self._config_manager.add_config(config_id, config):
            self._load_configs()
            self._status_label.setText(f"已添加配置: {name}")
            self.settings_changed.emit()

    def _on_save(self) -> None:
        """Save the current configuration."""
        if not self._current_config_id:
            return

        config = LLMConfig(
            name=self._name_edit.text().strip(),
            provider=self._provider_combo.currentText(),
            base_url=self._url_edit.text().strip(),
            model=self._model_edit.text().strip(),
            api_key=self._api_key_edit.text().strip(),
            max_tokens=self._max_tokens_spin.value(),
            temperature=self._temperature_spin.value(),
        )

        if self._config_manager.update_config(self._current_config_id, config):
            self._load_configs()
            self._status_label.setText("配置已保存")
            self.settings_changed.emit()

    def _on_delete(self) -> None:
        """Delete the current configuration."""
        if not self._current_config_id:
            return

        config = self._config_manager.get_config(self._current_config_id)
        if not config:
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除配置 '{config.name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self._config_manager.delete_config(self._current_config_id):
                self._load_configs()
                self._status_label.setText(f"已删除配置: {config.name}")
                self.settings_changed.emit()
            else:
                QMessageBox.warning(self, "错误", "无法删除当前使用的配置")

    def _on_set_active(self) -> None:
        """Set the current configuration as active."""
        if not self._current_config_id:
            return

        if self._config_manager.set_active_config(self._current_config_id):
            self._load_configs()
            config = self._config_manager.get_config(self._current_config_id)
            self._status_label.setText(f"已设为默认: {config.name}")
            self.settings_changed.emit()

    def _on_test(self) -> None:
        """Test the connection to the LLM service."""
        url = self._url_edit.text().strip()
        api_key = self._api_key_edit.text().strip()
        model = self._model_edit.text().strip()

        if not url or not api_key:
            QMessageBox.warning(self, "错误", "请填写 API URL 和 API Key")
            return

        self._status_label.setText("正在测试连接...")
        self._test_button.setEnabled(False)

        # Test in background
        from PySide6.QtCore import QRunnable, Slot, QThreadPool

        class TestWorker(QRunnable):
            def __init__(self, callback):
                super().__init__()
                self.setAutoDelete(True)
                self._callback = callback

            @Slot()
            def run(self):
                try:
                    from ....agent.infrastructure.cloud_llm import CloudLLMService

                    llm = CloudLLMService(
                        api_key=api_key,
                        base_url=url,
                        model=model,
                    )

                    if llm.is_available():
                        self._callback(True, "连接成功!")
                    else:
                        self._callback(False, "连接失败，请检查配置")

                except Exception as e:
                    self._callback(False, f"连接错误: {str(e)}")

        def on_result(success, message):
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._on_test_result(success, message))

        worker = TestWorker(on_result)
        QThreadPool.globalInstance().start(worker)

    def _on_test_result(self, success: bool, message: str) -> None:
        """Handle test result."""
        self._test_button.setEnabled(True)
        self._status_label.setText(message)

        if success:
            QMessageBox.information(self, "测试结果", message)
        else:
            QMessageBox.warning(self, "测试结果", message)
