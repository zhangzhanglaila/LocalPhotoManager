"""Helper for showing API configuration prompts."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtWidgets import QMessageBox, QWidget

from ....agent.config.llm_config import LLMConfigManager
from ....i18n import tr

_LOGGER = logging.getLogger(__name__)


def check_and_prompt_api_config(
    parent: QWidget,
    config_manager: LLMConfigManager,
    feature_name: str = "AI 助手",
) -> bool:
    """Check if API is configured, and prompt user to configure if not.

    Parameters
    ----------
    parent : QWidget
        Parent widget for the dialog.
    config_manager : LLMConfigManager
        The LLM configuration manager.
    feature_name : str
        Name of the feature requiring API.

    Returns
    -------
    bool
        True if API is configured (or user configured it), False otherwise.
    """
    # Check if there's an active config with API key
    active_config = config_manager.get_active_config()

    if active_config and active_config.api_key:
        return True

    # Show prompt dialog
    message = tr(
        "api_config.prompt",
        default=f"使用 {feature_name} 需要配置 LLM API。\n\n是否现在配置？"
    )

    reply = QMessageBox.question(
        parent,
        tr("api_config.title", default="需要配置 API"),
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )

    if reply == QMessageBox.StandardButton.Yes:
        # Open LLM settings dialog
        from .llm_settings_dialog import LLMSettingsDialog

        dialog = LLMSettingsDialog(config_manager, parent)

        # Connect to check if config was added
        config_added = [False]

        def on_settings_changed():
            config_added[0] = True

        dialog.settings_changed.connect(on_settings_changed)
        dialog.exec()

        # Check if config was added
        if config_added[0]:
            active_config = config_manager.get_active_config()
            if active_config and active_config.api_key:
                return True

    return False


def show_api_config_required(parent: QWidget, feature_name: str = "AI 助手") -> None:
    """Show a simple message that API configuration is required.

    Parameters
    ----------
    parent : QWidget
        Parent widget for the dialog.
    feature_name : str
        Name of the feature requiring API.
    """
    message = tr(
        "api_config.required",
        default=f"请先配置 LLM API 才能使用 {feature_name}。\n\n设置 → LLM 设置"
    )

    QMessageBox.information(
        parent,
        tr("api_config.title", default="需要配置 API"),
        message,
    )


def show_search_tips(parent: QWidget) -> None:
    """Show tips for better search results.

    Parameters
    ----------
    parent : QWidget
        Parent widget for the dialog.
    """
    tips = tr(
        "search.tips",
        default="搜索提示：\n\n"
        "1. 使用英文关键词效果更好（如 'yellow crane tower' 而非 '黄鹤楼'）\n"
        "2. 使用描述性词语（如 'Chinese tower', 'landmark', 'building'）\n"
        "3. 可以组合多个关键词（如 'sunset beach summer'）\n"
        "4. 支持场景、物体、活动等描述"
    )

    QMessageBox.information(
        parent,
        tr("search.tips_title", default="搜索技巧"),
        tips,
    )
