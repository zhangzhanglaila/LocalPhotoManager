"""Search result model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SearchResult:
    """Result from a semantic search query."""

    asset_id: str
    """Unique identifier for the asset."""

    asset_rel: str
    """Library-relative path to the asset."""

    score: float
    """Similarity score (0.0 to 1.0)."""

    caption: Optional[str] = None
    """Optional caption or description of the asset."""

    metadata: Optional[dict] = None
    """Optional additional metadata."""
