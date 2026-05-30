"""CLIP model downloader."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Optional

_LOGGER = logging.getLogger(__name__)

# CLIP model download URL (ONNX format)
# This is a lightweight version of CLIP ViT-B/32 in ONNX format
_CLIP_MODEL_URL = "https://huggingface.co/Qualcomm/CLIP-ViT-B-32/resolve/main/onnx/clip-vit-base-patch32.zip"

# Alternative: Use transformers to download and convert
_TRANSFORMERS_MODEL_ID = "openai/clip-vit-base-patch32"


def get_model_dir(library_root: Path) -> Path:
    """Get the model directory for CLIP.

    Parameters
    ----------
    library_root : Path
        Root directory of the library.

    Returns
    -------
    Path
        Path to the model directory.
    """
    return library_root.parent / "extension" / "models"


def is_model_available(model_dir: Path, model_name: str = "clip-vit-base-patch32") -> bool:
    """Check if CLIP model is available.

    Parameters
    ----------
    model_dir : Path
        Directory containing the model.
    model_name : str
        Name of the model.

    Returns
    -------
    bool
        True if model files exist.
    """
    model_path = model_dir / model_name
    image_encoder = model_path / "image_encoder.onnx"
    text_encoder = model_path / "text_encoder.onnx"

    # Check for ONNX files
    if image_encoder.exists() and text_encoder.exists():
        return True

    # Check for transformers format (config.json indicates transformers format)
    config_file = model_path / "config.json"
    if config_file.exists():
        return True

    return False


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

        model_path = model_dir / model_name

        if progress_callback:
            progress_callback(0, 100, "Downloading CLIP model...")

        _LOGGER.info("Downloading CLIP model to %s", model_path)

        # Create directory
        model_path.mkdir(parents=True, exist_ok=True)

        # Download model components
        if progress_callback:
            progress_callback(10, 100, "Downloading model...")

        model = CLIPModel.from_pretrained(_TRANSFORMERS_MODEL_ID)

        if progress_callback:
            progress_callback(50, 100, "Downloading processor...")

        processor = CLIPProcessor.from_pretrained(_TRANSFORMERS_MODEL_ID)

        if progress_callback:
            progress_callback(70, 100, "Downloading tokenizer...")

        tokenizer = CLIPTokenizer.from_pretrained(_TRANSFORMERS_MODEL_ID)

        # Save locally
        if progress_callback:
            progress_callback(80, 100, "Saving model...")

        model.save_pretrained(str(model_path))
        processor.save_pretrained(str(model_path))
        tokenizer.save_pretrained(str(model_path))

        if progress_callback:
            progress_callback(90, 100, "Converting to ONNX...")

        # Export to ONNX
        _export_to_onnx(model, model_path)

        if progress_callback:
            progress_callback(100, 100, "Download complete!")

        _LOGGER.info("CLIP model downloaded successfully")
        return True

    except Exception as e:
        _LOGGER.error("Failed to download CLIP model: %s", e)
        return False


def _export_to_onnx(model, model_path: Path) -> None:
    """Export CLIP model to ONNX format.

    Parameters
    ----------
    model : CLIPModel
        The CLIP model to export.
    model_path : Path
        Path to save the ONNX files.
    """
    try:
        import torch

        # Export image encoder
        image_encoder = model.vision_model
        image_encoder.eval()

        dummy_pixel_values = torch.randn(1, 3, 224, 224)
        image_encoder_path = model_path / "image_encoder.onnx"

        torch.onnx.export(
            image_encoder,
            dummy_pixel_values,
            str(image_encoder_path),
            input_names=["pixel_values"],
            output_names=["image_embeds"],
            dynamic_axes={
                "pixel_values": {0: "batch_size"},
                "image_embeds": {0: "batch_size"},
            },
        )

        # Export text encoder
        text_encoder = model.text_model
        text_encoder.eval()

        dummy_input_ids = torch.randint(0, 100, (1, 77))
        dummy_attention_mask = torch.ones(1, 77, dtype=torch.long)
        text_encoder_path = model_path / "text_encoder.onnx"

        torch.onnx.export(
            text_encoder,
            (dummy_input_ids, dummy_attention_mask),
            str(text_encoder_path),
            input_names=["input_ids", "attention_mask"],
            output_names=["text_embeds"],
            dynamic_axes={
                "input_ids": {0: "batch_size"},
                "attention_mask": {0: "batch_size"},
                "text_embeds": {0: "batch_size"},
            },
        )

        _LOGGER.info("ONNX export complete")

    except Exception as e:
        _LOGGER.warning("ONNX export failed (will use PyTorch instead): %s", e)


def download_model_simple(
    model_dir: Path,
    model_name: str = "clip-vit-base-patch32",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> bool:
    """Download CLIP model using simple HTTP download.

    This is a fallback method that downloads pre-exported ONNX files.

    Parameters
    ----------
    model_dir : Path
        Directory to save the model.
    model_name : str
        Name of the model.
    progress_callback : Optional[Callable]
        Callback for progress updates.

    Returns
    -------
    bool
        True if download was successful.
    """
    try:
        import requests

        model_path = model_dir / model_name
        model_path.mkdir(parents=True, exist_ok=True)

        # Download files
        files_to_download = [
            ("image_encoder.onnx", "Image encoder model"),
            ("text_encoder.onnx", "Text encoder model"),
            ("config.json", "Model config"),
            ("preprocessor_config.json", "Preprocessor config"),
            ("tokenizer.json", "Tokenizer"),
            ("vocab.json", "Vocabulary"),
            ("merges.txt", "Merges"),
        ]

        total = len(files_to_download)
        base_url = f"https://huggingface.co/{_TRANSFORMERS_MODEL_ID}/resolve/main"

        for i, (filename, description) in enumerate(files_to_download):
            if progress_callback:
                progress_callback(i, total, f"Downloading {description}...")

            url = f"{base_url}/{filename}"
            filepath = model_path / filename

            if filepath.exists():
                continue

            try:
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()

                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

            except Exception as e:
                _LOGGER.warning("Failed to download %s: %s", filename, e)
                # Continue with other files

        if progress_callback:
            progress_callback(total, total, "Download complete!")

        return is_model_available(model_dir, model_name)

    except Exception as e:
        _LOGGER.error("Failed to download model: %s", e)
        return False
