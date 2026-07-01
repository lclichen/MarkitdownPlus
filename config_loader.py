"""
config_loader.py
================
Unified configuration loader for MarkItDown services.

Loads settings from:
  - config.json (main configuration)
"""

import json
import os
from pathlib import Path
from typing import Any

# Config file paths
CONFIG_FILE = Path(__file__).parent / "config.json"


class Config:
    """Configuration manager with lazy loading."""

    _instance: "Config | None" = None
    _data: dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._data:
            self._load_configs()

    def _load_configs(self):
        """Load configuration from JSON files."""
        # Load main config
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-separated key."""
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value

    @property
    def vlm_config(self) -> dict:
        """Get VLM configuration."""
        return self._data.get("vlm_config", {})

    @property
    def server_config(self) -> dict:
        """Get server configuration."""
        return self._data.get("server_config", {})

    @property
    def task_config(self) -> dict:
        """Get task management configuration."""
        return self._data.get("task_config", {})

    @property
    def directory_config(self) -> dict:
        """Get directory configuration."""
        return self._data.get("directory_config", {})

    @property
    def image_convert_modes(self) -> list:
        """Get supported image convert modes."""
        return self._data.get("image_convert_modes", ["OCR", "Caption", "Origin"])

    @property
    def response_formats(self) -> list:
        """Get supported response formats."""
        return self._data.get("response_formats", ["json", "zip"])

    @property
    def supported_formats(self) -> list:
        """Get supported file formats."""
        return self._data.get("supported_formats", [])


def get_config() -> Config:
    """Get singleton Config instance."""
    return Config()


# Convenience functions for direct access
def get_vlm_base_url() -> str:
    return os.getenv("VLM_BASE_URL", get_config().vlm_config.get("base_url", "http://172.18.34.89:8888/v1"))


def get_vlm_api_key() -> str:
    return os.getenv("VLM_API_KEY", get_config().vlm_config.get("api_key", "Empty"))


def get_vlm_model() -> str:
    return os.getenv("VLM_MODEL", get_config().vlm_config.get("model", "Qwen3.5-35B"))


def get_api_host() -> str:
    return os.getenv("API_HOST", get_config().server_config.get("api_host", "0.0.0.0"))


def get_api_port() -> int:
    return int(os.getenv("API_PORT", get_config().server_config.get("api_port", 38062)))


def get_webui_port() -> int:
    return int(os.getenv("WEBUI_PORT", get_config().server_config.get("webui_port", 38061)))


def get_task_retention_seconds() -> int:
    return int(os.getenv("TASK_RETENTION_SECONDS", get_config().task_config.get("retention_seconds", 3600)))


def get_task_cleanup_interval() -> int:
    return int(os.getenv("TASK_CLEANUP_INTERVAL_SECONDS", get_config().task_config.get("cleanup_interval_seconds", 300)))


def get_sync_timeout() -> int:
    return int(get_config().task_config.get("sync_timeout_seconds", 600))


def get_upload_dir() -> str:
    return os.getenv("UPLOAD_DIR", get_config().directory_config.get("upload_dir", "./uploads_api"))


def get_output_dir() -> str:
    return os.getenv("OUTPUT_DIR", get_config().directory_config.get("output_dir", "./outputs_api"))


def get_webui_output_dir() -> str:
    return get_config().directory_config.get("webui_output_dir", "./outputs")


def get_supported_formats() -> list:
    return get_config().supported_formats
