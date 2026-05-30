"""Tool registry for managing available tools."""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from .base import Tool, ToolResult

_LOGGER = logging.getLogger(__name__)

# Pattern for parsing tool calls: [TOOL_CALL:name:params]
_TOOL_CALL_PATTERN = re.compile(r'\[TOOL_CALL:(\w+):(.*?)\]', re.DOTALL)


class ToolRegistry:
    """Registry for managing and executing tools.

    This class provides a unified interface for tool registration,
    discovery, and execution using the simple text format:
    [TOOL_CALL:name:params]
    """

    def __init__(self) -> None:
        """Initialize the tool registry."""
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool.

        Parameters
        ----------
        tool : Tool
            The tool to register.
        """
        self._tools[tool.name] = tool
        _LOGGER.debug("Registered tool: %s", tool.name)

    def unregister(self, name: str) -> bool:
        """Unregister a tool.

        Parameters
        ----------
        name : str
            Name of the tool to unregister.

        Returns
        -------
        bool
            True if the tool was unregistered.
        """
        if name in self._tools:
            del self._tools[name]
            _LOGGER.debug("Unregistered tool: %s", name)
            return True
        return False

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name.

        Parameters
        ----------
        name : str
            Name of the tool.

        Returns
        -------
        Optional[Tool]
            The tool, or None if not found.
        """
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """List all registered tool names.

        Returns
        -------
        List[str]
            List of tool names.
        """
        return list(self._tools.keys())

    def get_tools_description(self) -> str:
        """Get a description of all registered tools.

        Returns
        -------
        str
            Formatted description of all tools.
        """
        if not self._tools:
            return "暂无可用工具"

        descriptions = []
        for tool in self._tools.values():
            descriptions.append(f"- {tool.name}: {tool.description}")
        return "\n".join(descriptions)

    def execute_tool(self, name: str, params: str) -> ToolResult:
        """Execute a tool by name.

        Parameters
        ----------
        name : str
            Name of the tool to execute.
        params : str
            Parameters for the tool.

        Returns
        -------
        ToolResult
            The result of the execution.
        """
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                success=False,
                data=None,
                error=f"未找到工具: {name}",
            )

        try:
            return tool.execute(params)
        except Exception as e:
            _LOGGER.error("Tool execution failed: %s - %s", name, e)
            return ToolResult(
                success=False,
                data=None,
                error=f"工具执行失败: {str(e)}",
            )

    def parse_tool_calls(self, text: str) -> List[dict]:
        """Parse tool calls from text.

        Parameters
        ----------
        text : str
            Text containing tool calls in format: [TOOL_CALL:name:params]

        Returns
        -------
        List[dict]
            List of parsed tool calls with 'name', 'params', and 'original' keys.
        """
        matches = _TOOL_CALL_PATTERN.findall(text)

        tool_calls = []
        for name, params in matches:
            tool_calls.append({
                "name": name.strip(),
                "params": params.strip(),
                "original": f"[TOOL_CALL:{name}:{params}]",
            })

        return tool_calls

    def execute_tool_calls(self, text: str) -> List[dict]:
        """Parse and execute all tool calls in text.

        Parameters
        ----------
        text : str
            Text containing tool calls.

        Returns
        -------
        List[dict]
            List of results with 'name', 'params', 'result', and 'success' keys.
        """
        tool_calls = self.parse_tool_calls(text)
        results = []

        for call in tool_calls:
            result = self.execute_tool(call["name"], call["params"])
            results.append({
                "name": call["name"],
                "params": call["params"],
                "result": result.data if result.success else result.error,
                "success": result.success,
            })

        return results

    def format_tool_results(self, results: List[dict]) -> str:
        """Format tool results as text.

        Parameters
        ----------
        results : List[dict]
            List of tool results.

        Returns
        -------
        str
            Formatted text.
        """
        if not results:
            return ""

        parts = []
        for r in results:
            if r["success"]:
                parts.append(f"工具 {r['name']} 执行结果:\n{r['result']}")
            else:
                parts.append(f"工具 {r['name']} 执行失败: {r['result']}")

        return "\n\n".join(parts)
