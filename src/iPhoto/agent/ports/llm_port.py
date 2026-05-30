"""Port protocol for LLM (Large Language Model) services."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class ToolDefinition:
    """Definition of a tool that can be called by the LLM."""

    name: str
    """Name of the tool."""

    description: str
    """Description of what the tool does."""

    parameters: Dict[str, Any]
    """JSON Schema for the tool's parameters."""


@dataclass
class ToolCall:
    """A tool call from the LLM."""

    id: str
    """Unique identifier for this tool call."""

    name: str
    """Name of the tool to call."""

    arguments: Dict[str, Any]
    """Arguments to pass to the tool."""


@dataclass
class ChatMessage:
    """A single chat message."""

    role: str  # "system", "user", "assistant", "tool"
    content: Optional[str] = None
    """The message content."""

    tool_calls: Optional[List[ToolCall]] = None
    """Tool calls made by the assistant."""

    tool_call_id: Optional[str] = None
    """ID of the tool call this message is responding to."""

    name: Optional[str] = None
    """Name of the tool (for tool role messages)."""


@dataclass
class ChatResponse:
    """Response from an LLM."""

    content: Optional[str]
    """The text content of the response."""

    model: str
    """The model used."""

    tokens_used: int = 0
    """Total tokens used."""

    tool_calls: Optional[List[ToolCall]] = None
    """Tool calls requested by the model."""

    finish_reason: str = "stop"
    """Why the model stopped (stop, tool_calls, length)."""


class LLMPort(Protocol):
    """Protocol for interacting with Large Language Models.

    Implementations should handle model connection, message formatting,
    function calling, and response parsing.
    """

    @abstractmethod
    def chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Optional[ChatResponse]:
        """Send a chat request to the LLM.

        Parameters
        ----------
        messages : List[ChatMessage]
            List of chat messages in conversation order.
        tools : Optional[List[ToolDefinition]]
            List of tools available for the model to call.
        temperature : float
            Sampling temperature (0.0 = deterministic, 1.0 = creative).
        max_tokens : int
            Maximum tokens in the response.

        Returns
        -------
        Optional[ChatResponse]
            Response from the LLM, or None if the request fails.
        """
        ...

    @abstractmethod
    def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Optional[str]:
        """Simple text completion.

        Parameters
        ----------
        prompt : str
            The prompt to complete.
        temperature : float
            Sampling temperature.
        max_tokens : int
            Maximum tokens in the response.

        Returns
        -------
        Optional[str]
            Completed text, or None if the request fails.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM service is available and responsive."""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the name of the current model."""
        ...

    def chat_with_tools(
        self,
        messages: List[ChatMessage],
        tools: List[ToolDefinition],
        tool_executor: callable,
        max_iterations: int = 5,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Optional[ChatResponse]:
        """Chat with automatic tool execution loop.

        This method handles the full tool-calling loop:
        1. Send messages + tools to LLM
        2. If LLM requests tool calls, execute them
        3. Send tool results back to LLM
        4. Repeat until LLM gives a final response

        Parameters
        ----------
        messages : List[ChatMessage]
            Initial messages.
        tools : List[ToolDefinition]
            Available tools.
        tool_executor : callable
            Function that takes (tool_name, arguments) and returns result string.
        max_iterations : int
            Maximum number of tool-calling iterations.
        temperature : float
            Sampling temperature.
        max_tokens : int
            Maximum tokens per response.

        Returns
        -------
        Optional[ChatResponse]
            Final response from the LLM.
        """
        current_messages = list(messages)

        for _ in range(max_iterations):
            response = self.chat(
                current_messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            if response is None:
                return None

            # If no tool calls, return the response
            if not response.tool_calls:
                return response

            # Add assistant message with tool calls
            current_messages.append(ChatMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            ))

            # Execute each tool call and add results
            for tool_call in response.tool_calls:
                try:
                    result = tool_executor(tool_call.name, tool_call.arguments)
                    current_messages.append(ChatMessage(
                        role="tool",
                        content=str(result),
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    ))
                except Exception as e:
                    current_messages.append(ChatMessage(
                        role="tool",
                        content=f"Error: {str(e)}",
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    ))

        # If we exhausted iterations, return the last response
        return response
