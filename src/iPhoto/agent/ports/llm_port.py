"""Port protocol for LLM (Large Language Model) services."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Protocol


@dataclass
class ChatMessage:
    """A single chat message."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class ChatResponse:
    """Response from an LLM."""

    content: str
    model: str
    tokens_used: int = 0


class LLMPort(Protocol):
    """Protocol for interacting with Large Language Models.

    Implementations should handle model connection, message formatting,
    and response parsing.
    """

    @abstractmethod
    def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Optional[ChatResponse]:
        """Send a chat request to the LLM.

        Parameters
        ----------
        messages : List[ChatMessage]
            List of chat messages in conversation order.
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
