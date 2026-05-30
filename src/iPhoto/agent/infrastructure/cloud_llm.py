"""Cloud LLM service using OpenAI API compatible interface.

Supports:
- OpenAI API
- Azure OpenAI
- DeepSeek API
- Qwen API (通义千问)
- Zhipu API (智谱)
- Any OpenAI API compatible service
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from ..ports.llm_port import (
    ChatMessage,
    ChatResponse,
    LLMPort,
    ToolCall,
    ToolDefinition,
)

_LOGGER = logging.getLogger(__name__)

# Default configurations for common providers
_PROVIDER_CONFIGS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-turbo",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-flash",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
    },
}


class CloudLLMService:
    """Cloud LLM service using OpenAI API compatible interface.

    This service connects to cloud LLM providers using the OpenAI API format,
    which is supported by most major providers.
    """

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider: str = "openai",
    ) -> None:
        """Initialize the cloud LLM service.

        Parameters
        ----------
        api_key : str
            API key for the provider.
        base_url : Optional[str]
            Base URL for the API. If None, uses provider default.
        model : Optional[str]
            Model name. If None, uses provider default.
        provider : str
            Provider name (openai, deepseek, qwen, zhipu, moonshot).
        """
        self._api_key = api_key
        self._provider = provider

        # Get provider config
        config = _PROVIDER_CONFIGS.get(provider, _PROVIDER_CONFIGS["openai"])

        self._base_url = (base_url or config["base_url"]).rstrip("/")
        self._model = model or config["default_model"]
        self._client = None
        self._available: Optional[bool] = None

    def _ensure_client(self) -> bool:
        """Ensure the OpenAI client is initialized.

        Returns
        -------
        bool
            True if the client is ready.
        """
        if self._client is not None:
            return True

        try:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
            return True
        except ImportError:
            _LOGGER.error("openai package not installed. Run: pip install openai")
            return False
        except Exception as e:
            _LOGGER.error("Failed to initialize OpenAI client: %s", e)
            return False

    def chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Optional[ChatResponse]:
        """Send a chat request to the cloud LLM.

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
        if not self._ensure_client():
            return None

        try:
            # Convert messages to OpenAI format
            openai_messages = self._convert_messages(messages)

            # Build request kwargs
            kwargs = {
                "model": self._model,
                "messages": openai_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            # Add tools if provided
            if tools:
                kwargs["tools"] = self._convert_tools(tools)
                kwargs["tool_choice"] = "auto"

            # Call API
            response = self._client.chat.completions.create(**kwargs)

            # Parse response
            choice = response.choices[0]
            message = choice.message

            # Parse tool calls
            tool_calls = None
            if message.tool_calls:
                tool_calls = [
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=self._parse_arguments(tc.function.arguments),
                    )
                    for tc in message.tool_calls
                ]

            return ChatResponse(
                content=message.content,
                model=response.model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason,
            )

        except Exception as e:
            _LOGGER.error("Cloud LLM chat request failed: %s", e)
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
        """Check if the LLM service is available and responsive.

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
            # Try a simple completion
            response = self.complete("Hello", max_tokens=5)
            self._available = response is not None
            return self._available
        except Exception as e:
            _LOGGER.warning("Cloud LLM service not available: %s", e)
            self._available = False
            return False

    def get_model_name(self) -> str:
        """Return the name of the current model."""
        return self._model

    def _convert_messages(self, messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        """Convert ChatMessage list to OpenAI format.

        Parameters
        ----------
        messages : List[ChatMessage]
            List of chat messages.

        Returns
        -------
        List[Dict[str, Any]]
            OpenAI format messages.
        """
        openai_messages = []

        for msg in messages:
            if msg.role == "tool":
                # Tool response message
                openai_messages.append({
                    "role": "tool",
                    "content": msg.content or "",
                    "tool_call_id": msg.tool_call_id,
                    "name": msg.name,
                })
            elif msg.role == "assistant" and msg.tool_calls:
                # Assistant message with tool calls
                openai_messages.append({
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": self._serialize_arguments(tc.arguments),
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })
            else:
                # Regular message
                openai_messages.append({
                    "role": msg.role,
                    "content": msg.content or "",
                })

        return openai_messages

    def _convert_tools(self, tools: List[ToolDefinition]) -> List[Dict[str, Any]]:
        """Convert ToolDefinition list to OpenAI format.

        Parameters
        ----------
        tools : List[ToolDefinition]
            List of tool definitions.

        Returns
        -------
        List[Dict[str, Any]]
            OpenAI format tools.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _parse_arguments(self, arguments: str) -> Dict[str, Any]:
        """Parse JSON arguments string.

        Parameters
        ----------
        arguments : str
            JSON string of arguments.

        Returns
        -------
        Dict[str, Any]
            Parsed arguments.
        """
        import json
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse tool arguments: %s", arguments)
            return {}

    def _serialize_arguments(self, arguments: Dict[str, Any]) -> str:
        """Serialize arguments to JSON string.

        Parameters
        ----------
        arguments : Dict[str, Any]
            Arguments to serialize.

        Returns
        -------
        str
            JSON string.
        """
        import json
        return json.dumps(arguments, ensure_ascii=False)
