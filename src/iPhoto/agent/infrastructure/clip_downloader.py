"""CLIP model downloader."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Optional

_LOGGER = logging.getLogger(__name__)

# CLIP model ID
_MODEL_ID = "openai/clip-vit-base-patch32"


def get_model_dir(library_root: Path) -> Path:
    """Get the model directory for CLIP."""
    return library_root.parent / "extension" / "models"


def get_model_path(library_root: Path) -> Path:
    """Get the full path to the CLIP model."""
    return get_model_dir(library_root) / "clip-vit-base-patch32"


def is_model_available(model_dir: Path) -> bool:
    """Check if CLIP model is available."""
    model_path = model_dir / "clip-vit-base-patch32"
    config_file = model_path / "config.json"
    return config_file.exists()


def download_model(
    model_dir: Path,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """Download CLIP model.

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
    model_path = model_dir / "clip-vit-base-patch32"
    model_path.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(0, 100, "准备下载...")

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
    from huggingface_hub import snapshot_download

    # Try mirror first
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

    if progress_callback:
        progress_callback(10, 100, "正在从镜像下载...")

    _LOGGER.info("Downloading CLIP model to %s", model_path)

    snapshot_download(
        repo_id=_MODEL_ID,
        local_dir=str(model_path),
        local_dir_use_symlinks=False,
    )

    if progress_callback:
        progress_callback(100, 100, "下载完成！")

    return True


def _download_with_modelscope(
    model_dir: Path,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """Download using ModelScope (Chinese mirror)."""
    from modelscope import snapshot_download

    if progress_callback:
        progress_callback(10, 100, "正在从 ModelScope 下载...")

    snapshot_download(
        model_id="AI-ModelScope/clip-vit-base-patch32",
        cache_dir=str(model_dir),
    )

    if progress_callback:
        progress_callback(100, 100, "下载完成！")

    return True


def get_download_instructions(model_dir: Path) -> str:
    """Get instructions for manually downloading the model."""
    model_path = model_dir / "clip-vit-base-patch32"

    return f"""手动下载 CLIP 模型：

方法1：使用 HuggingFace 镜像（推荐）
========================================
pip install huggingface_hub
set HF_ENDPOINT=https://hf-mirror.com
python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/clip-vit-base-patch32', local_dir=r'{model_path}')"

方法2：使用 ModelScope（国内镜像）
========================================
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('AI-ModelScope/clip-vit-base-patch32', cache_dir=r'{model_dir}')"

下载完成后重启应用即可使用语义搜索功能。
"""
