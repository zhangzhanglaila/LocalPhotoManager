"""LLM configuration management."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_LOGGER = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""

    name: str
    """Display name for this configuration."""

    provider: str
    """Provider identifier (deepseek, qwen, zhipu, moonshot, openai, custom)."""

    base_url: str
    """API base URL."""

    model: str
    """Model name."""

    api_key: str
    """API key."""

    enabled: bool = True
    """Whether this configuration is enabled."""

    is_default: bool = False
    """Whether this is the default configuration."""

    extra_headers: Dict[str, str] = field(default_factory=dict)
    """Extra headers to send with requests."""

    max_tokens: int = 4096
    """Maximum tokens for responses."""

    temperature: float = 0.7
    """Default temperature."""


# Default configurations for common providers
DEFAULT_CONFIGS = {
    "deepseek": LLMConfig(
        name="DeepSeek",
        provider="deepseek",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key="",
    ),
    "qwen": LLMConfig(
        name="通义千问",
        provider="qwen",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-turbo",
        api_key="",
    ),
    "zhipu": LLMConfig(
        name="智谱",
        provider="zhipu",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-4-flash",
        api_key="",
    ),
    "moonshot": LLMConfig(
        name="Moonshot",
        provider="moonshot",
        base_url="https://api.moonshot.cn/v1",
        model="moonshot-v1-8k",
        api_key="",
    ),
    "openai": LLMConfig(
        name="OpenAI",
        provider="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        api_key="",
    ),
}


class LLMConfigManager:
    """Manager for LLM configurations.

    Handles loading, saving, and managing multiple LLM configurations.
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize the LLM config manager.

        Parameters
        ----------
        config_dir : Optional[Path]
            Directory to store configuration files.
            If None, uses ~/.iPhoto/agent/
        """
        if config_dir is None:
            config_dir = Path.home() / ".iPhoto" / "agent"

        self._config_dir = Path(config_dir)
        self._config_file = self._config_dir / "llm_configs.json"
        self._configs: Dict[str, LLMConfig] = {}
        self._active_config_id: Optional[str] = None

        # Load existing configs
        self._load_configs()

    def _load_configs(self) -> None:
        """Load configurations from file."""
        if not self._config_file.exists():
            # Initialize with default configs
            self._configs = dict(DEFAULT_CONFIGS)
            self._active_config_id = "deepseek" if "deepseek" in self._configs else None
            self._save_configs()
            return

        try:
            with open(self._config_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Load configs
            self._configs = {}
            for config_id, config_data in data.get("configs", {}).items():
                self._configs[config_id] = LLMConfig(**config_data)

            # Load active config
            self._active_config_id = data.get("active_config")

            _LOGGER.info("Loaded %d LLM configurations", len(self._configs))

        except Exception as e:
            _LOGGER.error("Failed to load LLM configs: %s", e)
            self._configs = dict(DEFAULT_CONFIGS)
            self._active_config_id = None

    def _save_configs(self) -> None:
        """Save configurations to file."""
        try:
            # Ensure directory exists
            self._config_dir.mkdir(parents=True, exist_ok=True)

            # Prepare data
            data = {
                "configs": {
                    config_id: asdict(config)
                    for config_id, config in self._configs.items()
                },
                "active_config": self._active_config_id,
            }

            # Write to file
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            _LOGGER.info("Saved %d LLM configurations", len(self._configs))

        except Exception as e:
            _LOGGER.error("Failed to save LLM configs: %s", e)

    def get_config(self, config_id: str) -> Optional[LLMConfig]:
        """Get a configuration by ID.

        Parameters
        ----------
        config_id : str
            Configuration ID.

        Returns
        -------
        Optional[LLMConfig]
            The configuration, or None if not found.
        """
        return self._configs.get(config_id)

    def get_active_config(self) -> Optional[LLMConfig]:
        """Get the active configuration.

        Returns
        -------
        Optional[LLMConfig]
            The active configuration, or None if not set.
        """
        if self._active_config_id:
            return self._configs.get(self._active_config_id)
        return None

    def get_active_config_id(self) -> Optional[str]:
        """Get the active configuration ID.

        Returns
        -------
        Optional[str]
            The active configuration ID.
        """
        return self._active_config_id

    def set_active_config(self, config_id: str) -> bool:
        """Set the active configuration.

        Parameters
        ----------
        config_id : str
            Configuration ID to activate.

        Returns
        -------
        bool
            True if successful.
        """
        if config_id not in self._configs:
            return False

        self._active_config_id = config_id
        self._save_configs()
        return True

    def add_config(self, config_id: str, config: LLMConfig) -> bool:
        """Add a new configuration.

        Parameters
        ----------
        config_id : str
            Configuration ID.
        config : LLMConfig
            Configuration to add.

        Returns
        -------
        bool
            True if successful.
        """
        self._configs[config_id] = config
        self._save_configs()
        return True

    def update_config(self, config_id: str, config: LLMConfig) -> bool:
        """Update an existing configuration.

        Parameters
        ----------
        config_id : str
            Configuration ID.
        config : LLMConfig
            New configuration.

        Returns
        -------
        bool
            True if successful.
        """
        if config_id not in self._configs:
            return False

        self._configs[config_id] = config
        self._save_configs()
        return True

    def delete_config(self, config_id: str) -> bool:
        """Delete a configuration.

        Parameters
        ----------
        config_id : str
            Configuration ID to delete.

        Returns
        -------
        bool
            True if successful.
        """
        if config_id not in self._configs:
            return False

        # Don't allow deleting the active config
        if config_id == self._active_config_id:
            return False

        del self._configs[config_id]
        self._save_configs()
        return True

    def list_configs(self) -> List[dict]:
        """List all configurations.

        Returns
        -------
        List[dict]
            List of configuration summaries.
        """
        configs = []
        for config_id, config in self._configs.items():
            configs.append({
                "id": config_id,
                "name": config.name,
                "provider": config.provider,
                "model": config.model,
                "enabled": config.enabled,
                "is_active": config_id == self._active_config_id,
                "has_api_key": bool(config.api_key),
            })
        return configs

    def get_enabled_configs(self) -> List[dict]:
        """Get all enabled configurations with API keys.

        Returns
        -------
        List[dict]
            List of enabled configuration summaries.
        """
        return [
            c for c in self.list_configs()
            if c["enabled"] and c["has_api_key"]
        ]

    def reset_to_defaults(self) -> None:
        """Reset all configurations to defaults."""
        self._configs = dict(DEFAULT_CONFIGS)
        self._active_config_id = "deepseek" if "deepseek" in self._configs else None
        self._save_configs()
