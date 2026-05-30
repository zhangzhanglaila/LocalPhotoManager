"""Organize tool for managing photos."""

from __future__ import annotations

from ..base import Tool, ToolResult


class OrganizeTool:
    """Tool for organizing photos.

    Supports:
    - Finding duplicates
    - Creating smart albums
    - Quality assessment
    """

    def __init__(self, organize_service: object = None):
        """Initialize the organize tool.

        Parameters
        ----------
        organize_service : object
            Organize service for photo management.
        """
        self._organize_service = organize_service

    @property
    def name(self) -> str:
        return "organize"

    @property
    def description(self) -> str:
        return "整理照片。支持查找重复照片、创建智能相册、质量评估。"

    @property
    def parameters(self) -> str:
        return "action: 操作类型 (duplicates, smart_album, quality)"

    def execute(self, params: str) -> ToolResult:
        """Execute the organize tool.

        Parameters
        ----------
        params : str
            Action to perform.

        Returns
        -------
        ToolResult
            Action results.
        """
        try:
            action = params.strip().lower()

            if not self._organize_service:
                return ToolResult(
                    success=False,
                    data=None,
                    error="Organize service not available",
                )

            if action == "duplicates":
                duplicates = self._organize_service.find_duplicates()
                return ToolResult(
                    success=True,
                    data={
                        "groups": len(duplicates),
                        "total_photos": sum(len(g.asset_ids) for g in duplicates),
                    },
                )

            elif action.startswith("smart_album"):
                # Parse group_by from action (e.g., "smart_album:event")
                group_by = "event"
                if ":" in action:
                    group_by = action.split(":")[1]

                albums = self._organize_service.create_smart_albums(group_by=group_by)
                return ToolResult(
                    success=True,
                    data={
                        "albums": len(albums),
                        "group_by": group_by,
                    },
                )

            elif action == "quality":
                return ToolResult(
                    success=True,
                    data={"message": "Quality assessment requires a specific photo."},
                )

            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Unknown action: {action}",
                )

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
