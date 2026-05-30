"""AI Agent module for intelligent photo management.

This module provides local AI capabilities using CLIP model:
- Semantic search (text-to-image)
- Image similarity search
- Duplicate detection
- Smart album creation
"""

from .services.search_service import SearchService
from .models.search_result import SearchResult

__all__ = ["SearchService", "SearchResult"]
