"""Base classes for agent tools."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Protocol


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    """Whether the execution was successful."""

    data: Any
    """The result data."""

    error: Optional[str] = None
    """Error message if execution failed."""


class Tool(Protocol):
    """Protocol for agent tools.

    Tools are the primary way agents interact with the system.
    Each tool has a name, description, and can execute operations.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the tool."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """A description of what the tool does."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> str:
        """Description of the tool's parameters."""
        ...

    @abstractmethod
    def execute(self, params: str) -> ToolResult:
        """Execute the tool with the given parameters.

        Parameters
        ----------
        params : str
            Parameters string (format depends on the tool).

        Returns
        -------
        ToolResult
            The result of the execution.
        ...

    def get_help(self) -> str:
        """Get help text for this tool.

        Returns
        -------
        str
            Help text describing the tool and its usage.
        """
        return f"{self.name}: {self.description}\nParameters: {self.parameters}"
