"""Stats tool for library statistics."""

from __future__ import annotations

from ..base import Tool, ToolResult


class StatsTool:
    """Tool for getting library statistics.

    Provides:
    - Total photo/video count
    - Date range
    - Location list
    - Camera list
    """

    def __init__(self, context_manager: object = None):
        """Initialize the stats tool.

        Parameters
        ----------
        context_manager : object
            JIT context manager for lazy loading.
        """
        self._context_manager = context_manager

    @property
    def name(self) -> str:
        return "stats"

    @property
    def description(self) -> str:
        return "获取照片库统计信息。支持获取总数、日期范围、地点、相机等。"

    @property
    def parameters(self) -> str:
        return "query: 统计类型 (count, dates, locations, cameras)"

    def execute(self, params: str) -> ToolResult:
        """Execute the stats tool.

        Parameters
        ----------
        params : str
            Query type.

        Returns
        -------
        ToolResult
            Statistics results.
        """
        try:
            query = params.strip().lower()

            if not self._context_manager:
                return ToolResult(
                    success=False,
                    data=None,
                    error="Context manager not available",
                )

            if query == "count":
                stats = self._context_manager.get_context("asset_count")
                return ToolResult(success=True, data=stats)

            elif query == "dates":
                date_range = self._context_manager.get_context("date_range")
                return ToolResult(success=True, data=date_range)

            elif query == "locations":
                locations = self._context_manager.get_context("locations")
                return ToolResult(
                    success=True,
                    data={"count": len(locations), "locations": locations[:20]},
                )

            elif query == "cameras":
                cameras = self._context_manager.get_context("cameras")
                return ToolResult(
                    success=True,
                    data={"count": len(cameras), "cameras": cameras},
                )

            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Unknown query: {query}",
                )

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
