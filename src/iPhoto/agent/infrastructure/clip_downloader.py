"""CLIP model downloader with progress tracking."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Optional

_LOGGER = logging.getLogger(__name__)

# CLIP model ID
_TRANSFORMERS_MODEL_ID = "openai/clip-vit-base-patch32"


def get_model_dir(library_root: Path) -> Path:
    """Get the model directory for CLIP."""
    return library_root.parent / "extension" / "models"


def is_model_available(model_dir: Path, model_name: str = "clip-vit-base-patch32") -> bool:
    """Check if CLIP model is available."""
    model_path = model_dir / model_name
    config_file = model_path / "config.json"
    return config_file.exists()


def download_model_with_transformers(
    model_dir: Path,
    model_name: str = "clip-vit-base-patch32",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """Download CLIP model using transformers library.

    Parameters
    ----------
    model_dir : Path
        Directory to save the model.
    model_name : str
        Name of the model.
    progress_callback : Optional[Callable]
        Callback for progress updates (current, total, message).

    Returns
    -------
    bool
        True if download was successful.
    """
    try:
        from transformers import CLIPModel, CLIPProcessor, CLIPTokenizer
        from huggingface_hub import snapshot_download

        model_path = model_dir / model_name
        model_path.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(5, 100, "Preparing download...")

        # Use snapshot_download for better progress tracking
        if progress_callback:
            progress_callback(10, 100, "Downloading model files...")

        _LOGGER.info("Downloading CLIP model to %s", model_path)

        # Download with progress
        snapshot_download(
            repo_id=_TRANSFORMERS_MODEL_ID,
            local_dir=str(model_path),
            local_dir_use_symlinks=False,
        )

        if progress_callback:
            progress_callback(80, 100, "Loading model...")

        # Verify model can be loaded
        model = CLIPModel.from_pretrained(str(model_path))
        processor = CLIPProcessor.from_pretrained(str(model_path))

        if progress_callback:
            progress_callback(90, 100, "Saving tokenizer...")

        # Ensure tokenizer is saved
        tokenizer = CLIPTokenizer.from_pretrained(str(model_path))
        tokenizer.save_pretrained(str(model_path))

        if progress_callback:
            progress_callback(100, 100, "Download complete!")

        _LOGGER.info("CLIP model downloaded successfully")
        return True

    except Exception as e:
        _LOGGER.error("Failed to download CLIP model: %s", e)

        # Fallback: try simpler download
        return _download_simple(model_dir, model_name, progress_callback)


def _download_simple(
    model_dir: Path,
    model_name: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """Simple fallback download method.

    Downloads only the essential files needed for inference.
    """
    try:
        import requests

        model_path = model_dir / model_name
        model_path.mkdir(parents=True, exist_ok=True)

        # Essential files to download
        files = {
            "config.json": "Model configuration",
            "vocab.json": "Vocabulary",
            "merges.txt": "Tokenizer merges",
            "special_tokens_map.json": "Special tokens",
            "preprocessor_config.json": "Preprocessor config",
            "tokenizer_config.json": "Tokenizer config",
        }

        base_url = f"https://huggingface.co/{_TRANSFORMERS_MODEL_ID}/resolve/main"
        total = len(files) + 2  # +2 for model files

        if progress_callback:
            progress_callback(0, total, "Starting download...")

        for i, (filename, desc) in enumerate(files.items(), 1):
            if progress_callback:
                progress_callback(i, total, f"Downloading {desc}...")

            filepath = model_path / filename
            if not filepath.exists():
                url = f"{base_url}/{filename}"
                _download_file(url, filepath)

        # Download model files (larger)
        model_files = [
            ("model.safetensors", "Model weights"),
        ]

        for filename, desc in model_files:
            if progress_callback:
                progress_callback(total - 1, total, f"Downloading {desc}...")

            filepath = model_path / filename
            if not filepath.exists():
                url = f"{base_url}/{filename}"
                _download_file(url, filepath)

        if progress_callback:
            progress_callback(total, total, "Download complete!")

        return is_model_available(model_dir, model_name)

    except Exception as e:
        _LOGGER.error("Simple download failed: %s", e)
        return False


def _download_file(url: str, filepath: Path) -> None:
    """Download a file with progress."""
    import requests

    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    with open(filepath, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
