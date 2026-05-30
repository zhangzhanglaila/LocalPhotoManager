"""Ollama LLM service for local language model inference."""

from __future__ import annotations

import logging
from typing import List, Optional

from ..ports.llm_port import ChatMessage, ChatResponse, LLMPort

_LOGGER = logging.getLogger(__name__)

_DEFAULT_MODEL = "qwen2.5:7b"
_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaLLMService:
    """Ollama LLM service for local language model inference.

    This service connects to a local Ollama instance and provides
    methods for chat completion and text generation.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        """Initialize the Ollama LLM service.

        Parameters
        ----------
        model : str
            Name of the Ollama model to use.
        base_url : str
            Base URL of the Ollama API.
        """
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = None
        self._available: Optional[bool] = None

    def _ensure_client(self) -> bool:
        """Ensure the Ollama client is initialized.

        Returns
        -------
        bool
            True if the client is ready.
        """
        if self._client is not None:
            return True

        try:
            import ollama

            self._client = ollama.Client(host=self._base_url)
            return True
        except ImportError:
            _LOGGER.error("ollama package not installed. Run: pip install ollama")
            return False
        except Exception as e:
            _LOGGER.error("Failed to initialize Ollama client: %s", e)
            return False

    def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Optional[ChatResponse]:
        """Send a chat request to the Ollama model.

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
            Response from the model, or None if the request fails.
        """
        if not self._ensure_client():
            return None

        try:
            # Convert messages to Ollama format
            ollama_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]

            # Call Ollama API
            response = self._client.chat(
                model=self._model,
                messages=ollama_messages,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            )

            return ChatResponse(
                content=response["message"]["content"],
                model=response.get("model", self._model),
                tokens_used=response.get("eval_count", 0),
            )

        except Exception as e:
            _LOGGER.error("Ollama chat request failed: %s", e)
            self._available = False
            return None

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
        messages = [ChatMessage(role="user", content=prompt)]
        response = self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        return response.content if response else None

    def is_available(self) -> bool:
        """Check if the Ollama service is available and responsive.

        Returns
        -------
        bool
            True if the service is available.
        """
        if self._available is not None:
            return self._available

        if not self._ensure_client():
            self._available = False
            return False

        try:
            # Try to list models to check connectivity
            self._client.list()
            self._available = True
            return True
        except Exception as e:
            _LOGGER.warning("Ollama service not available: %s", e)
            self._available = False
            return False

    def get_model_name(self) -> str:
        """Return the name of the current model."""
        return self._model
