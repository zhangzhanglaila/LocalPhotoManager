"""CLIP model downloader with manual download support."""

from __future__ import annotations

import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Callable, Optional

_LOGGER = logging.getLogger(__name__)

# CLIP model ID
_TRANSFORMERS_MODEL_ID = "openai/clip-vit-base-patch32"

# Model directory name
_MODEL_NAME = "clip-vit-base-patch32"


def get_model_dir(library_root: Path) -> Path:
    """Get the model directory for CLIP."""
    return library_root.parent / "extension" / "models"


def get_model_path(library_root: Path) -> Path:
    """Get the full path to the CLIP model."""
    return get_model_dir(library_root) / _MODEL_NAME


def is_model_available(model_dir: Path) -> bool:
    """Check if CLIP model is available."""
    model_path = model_dir / _MODEL_NAME

    # Check for config.json (indicates model is downloaded)
    config_file = model_path / "config.json"
    if config_file.exists():
        return True

    # Check for ONNX files
    onnx_dir = model_path / "onnx"
    if onnx_dir.exists():
        return True

    return False


def get_download_instructions(model_dir: Path) -> str:
    """Get instructions for manually downloading the model.

    Parameters
    ----------
    model_dir : Path
        Directory where model should be saved.

    Returns
    -------
    str
        Download instructions.
    """
    model_path = model_dir / _MODEL_NAME

    return f"""手动下载 CLIP 模型：

方法1：使用 HuggingFace 镜像（推荐）
========================================
pip install huggingface_hub
export HF_ENDPOINT=https://hf-mirror.com
python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/clip-vit-base-patch32', local_dir='{model_path}')"

方法2：手动下载
========================================
1. 访问 https://huggingface.co/openai/clip-vit-base-patch32
2. 或使用镜像 https://hf-mirror.com/openai/clip-vit-base-patch32
3. 下载所有文件到: {model_path}

方法3：使用 ModelScope（国内镜像）
========================================
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('AI-ModelScope/clip-vit-base-patch32', cache_dir='{model_dir}')"

下载完成后重启应用即可使用语义搜索功能。
"""


def download_model(
    model_dir: Path,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """Try to download CLIP model automatically.

    Parameters
    ----------
    model_dir : Path
        Directory to save the model.
    progress_callback : Optional[Callable]
        Callback for progress updates.

    Returns
    -------
    bool
        True if download was successful.
    """
    model_path = model_dir / _MODEL_NAME
    model_path.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(0, 100, "尝试下载 CLIP 模型...")

    # Try using huggingface_hub with mirror
    try:
        return _download_with_huggingface_hub(model_path, progress_callback)
    except Exception as e:
        _LOGGER.warning("HuggingFace download failed: %s", e)

    # Try using modelscope
    try:
        return _download_with_modelscope(model_dir, progress_callback)
    except Exception as e:
        _LOGGER.warning("ModelScope download failed: %s", e)

    return False


def _download_with_huggingface_hub(
    model_path: Path,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """Download using huggingface_hub with mirror support."""
    try:
        from huggingface_hub import snapshot_download

        # Try mirror first
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

        if progress_callback:
            progress_callback(10, 100, "正在从镜像下载...")

        snapshot_download(
            repo_id=_TRANSFORMERS_MODEL_ID,
            local_dir=str(model_path),
            local_dir_use_symlinks=False,
        )

        if progress_callback:
            progress_callback(100, 100, "下载完成！")

        return True

    except Exception as e:
        _LOGGER.error("HuggingFace download failed: %s", e)
        raise


def _download_with_modelscope(
    model_dir: Path,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """Download using ModelScope (Chinese mirror)."""
    try:
        from modelscope import snapshot_download

        if progress_callback:
            progress_callback(10, 100, "正在从 ModelScope 下载...")

        # ModelScope uses different model ID format
        snapshot_download(
            model_id="AI-ModelScope/clip-vit-base-patch32",
            cache_dir=str(model_dir),
        )

        if progress_callback:
            progress_callback(100, 100, "下载完成！")

        return True

    except Exception as e:
        _LOGGER.error("ModelScope download failed: %s", e)
        raise


def create_download_script(model_dir: Path, script_path: Path) -> None:
    """Create a batch script for manual download.

    Parameters
    ----------
    model_dir : Path
        Directory where model should be saved.
    script_path : Path
        Path to save the script.
    """
    model_path = model_dir / _MODEL_NAME

    script_content = f"""@echo off
echo ========================================
echo CLIP Model Download Script
echo ========================================
echo.

echo Installing huggingface_hub...
pip install huggingface_hub

echo.
echo Setting mirror...
set HF_ENDPOINT=https://hf-mirror.com

echo.
echo Downloading model to: {model_path}
python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/clip-vit-base-patch32', local_dir=r'{model_path}')"

echo.
echo ========================================
echo Download complete!
echo Please restart the application.
echo ========================================
pause
"""

    script_path.write_text(script_content, encoding="utf-8")
