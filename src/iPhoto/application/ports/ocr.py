"""OCR port interfaces."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class OCRSearchPort(Protocol):
    """Port for OCR text search operations."""

    def search(self, query: str, limit: int = 100) -> list:
        """Search for photos containing the given text."""
        ...

    def get_asset_ids_with_ocr(self) -> set[str]:
        """Get asset IDs that have been OCR-processed."""
        ...
