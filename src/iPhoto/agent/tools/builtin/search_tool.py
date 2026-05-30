"""Search tool for finding photos."""

from __future__ import annotations

from typing import Optional

from ..base import Tool, ToolResult


class SearchTool:
    """Tool for searching photos.

    Supports searching by:
    - Text query (semantic search)
    - Tag
    - Location
    - Date
    """

    def __init__(self, search_service: object = None, embedding_repository: object = None):
        """Initialize the search tool.

        Parameters
        ----------
        search_service : object
            Search service for semantic search.
        embedding_repository : object
            Repository for tag-based search.
        """
        self._search_service = search_service
        self._embedding_repository = embedding_repository

    @property
    def name(self) -> str:
        return "search"

    @property
    def description(self) -> str:
        return "搜索照片。支持语义搜索、标签搜索、地点搜索、日期搜索。"

    @property
    def parameters(self) -> str:
        return "query: 搜索关键词或描述"

    def execute(self, params: str) -> ToolResult:
        """Execute the search tool.

        Parameters
        ----------
        params : str
            Search query.

        Returns
        -------
        ToolResult
            Search results.
        """
        try:
            # Parse parameters
            query = params.strip()

            # Try semantic search first
            if self._search_service:
                results = self._search_service.search(query, top_k=10)
                if results:
                    asset_ids = [r.asset_id for r in results]
                    return ToolResult(
                        success=True,
                        data={
                            "count": len(asset_ids),
                            "asset_ids": asset_ids,
                            "query": query,
                        },
                    )

            # Fall back to tag search
            if self._embedding_repository:
                asset_ids = self._embedding_repository.search_by_tag(query)
                if asset_ids:
                    return ToolResult(
                        success=True,
                        data={
                            "count": len(asset_ids),
                            "asset_ids": asset_ids,
                            "query": query,
                        },
                    )

            return ToolResult(
                success=True,
                data={"count": 0, "asset_ids": [], "query": query},
            )

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
