"""AI subsystem configuration constants."""

from __future__ import annotations

from pathlib import Path

# Model cache directory (under user home)
DEFAULT_MODEL_CACHE_DIR = Path.home() / ".cache" / "iphoto" / "ai_models"

# OCR configuration
OCR_BATCH_SIZE = 16
OCR_CONFIDENCE_THRESHOLD = 0.5

# Supported image extensions for OCR
OCR_IMAGE_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".heic",
})

# Database name
OCR_DB_NAME = "ocr_index.db"
