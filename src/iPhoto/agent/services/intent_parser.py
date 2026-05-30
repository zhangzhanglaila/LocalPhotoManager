"""Intent parser for natural language photo management.

Uses function calling for reliable tool invocation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from ..ports.llm_port import ChatMessage, LLMPort, ToolCall, ToolDefinition

_LOGGER = logging.getLogger(__name__)


class IntentType(Enum):
    """Types of intents the parser can recognize."""

    SEARCH = "search"
    """Search for photos matching criteria."""

    ORGANIZE = "organize"
    """Organize photos (create albums, find duplicates, etc.)."""

    QUESTION = "question"
    """Ask a question about photos."""

    ACTION = "action"
    """Perform an action on photos (favorite, delete, share, etc.)."""

    UNKNOWN = "unknown"
    """Intent could not be determined."""


@dataclass
class ParsedIntent:
    """Result of parsing a natural language request."""

    intent_type: IntentType
    """The type of intent."""

    query: str
    """The original query text."""

    search_terms: List[str]
    """Extracted search terms."""

    filters: dict
    """Extracted filters (date, location, person, etc.)."""

    action: Optional[str]
    """The action to perform (if intent_type is ACTION)."""

    confidence: float
    """Confidence in the parsing (0.0 to 1.0)."""

    response: Optional[str] = None
    """Suggested response to the user."""


# Tool definitions for function calling
INTENT_TOOLS = [
    ToolDefinition(
        name="classify_intent",
        description="对用户查询进行意图分类",
        parameters={
            "type": "object",
            "properties": {
                "intent_type": {
                    "type": "string",
                    "enum": ["search", "organize", "question", "action"],
                    "description": "意图类型"
                },
                "confidence": {
                    "type": "number",
                    "description": "置信度 (0.0-1.0)"
                }
            },
            "required": ["intent_type", "confidence"]
        }
    ),
    ToolDefinition(
        name="extract_search_params",
        description="从用户查询中提取搜索参数",
        parameters={
            "type": "object",
            "properties": {
                "search_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "搜索关键词列表"
                },
                "filters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "日期/时间筛选"},
                        "location": {"type": "string", "description": "地点筛选"},
                        "person": {"type": "string", "description": "人物筛选"},
                        "camera": {"type": "string", "description": "相机筛选"}
                    },
                    "description": "筛选条件"
                }
            },
            "required": ["search_terms"]
        }
    ),
    ToolDefinition(
        name="extract_action",
        description="从用户查询中提取操作类型",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["favorite", "delete", "share", "create_album"],
                    "description": "操作类型"
                },
                "target": {
                    "type": "string",
                    "description": "操作目标"
                }
            },
            "required": ["action"]
        }
    ),
    ToolDefinition(
        name="generate_response",
        description="生成给用户的回复",
        parameters={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "回复内容"
                }
            },
            "required": ["message"]
        }
    )
]

# System prompt for intent parsing
_SYSTEM_PROMPT = """你是一个照片管理应用的AI助手，负责解析用户的自然语言请求。

你的任务是：
1. 理解用户的意图（搜索、整理、提问、操作）
2. 提取关键信息（搜索词、筛选条件、操作类型）
3. 生成友好的回复

请使用提供的工具来完成解析。首先使用 classify_intent 分类意图，然后根据意图类型使用相应工具提取信息，最后使用 generate_response 生成回复。"""


class IntentParser:
    """Parser for natural language photo management requests.

    Uses function calling for reliable tool invocation.
    """

    def __init__(self, llm_service: Optional[LLMPort] = None) -> None:
        """Initialize the intent parser.

        Parameters
        ----------
        llm_service : Optional[LLMPort]
            LLM service for parsing. If None, uses rule-based parsing.
        """
        self._llm_service = llm_service

    def parse(self, query: str) -> ParsedIntent:
        """Parse a natural language query into a structured intent.

        Parameters
        ----------
        query : str
            The user's query in natural language.

        Returns
        -------
        ParsedIntent
            The parsed intent.
        """
        if not query.strip():
            return ParsedIntent(
                intent_type=IntentType.UNKNOWN,
                query=query,
                search_terms=[],
                filters={},
                action=None,
                confidence=0.0,
                response="Please provide a query.",
            )

        # Try function calling parsing first
        if self._llm_service and self._llm_service.is_available():
            try:
                return self._parse_with_function_calling(query)
            except Exception as e:
                _LOGGER.warning("Function calling parsing failed, falling back to rule-based: %s", e)

        # Fall back to rule-based parsing
        return self._parse_with_rules(query)

    def _parse_with_function_calling(self, query: str) -> ParsedIntent:
        """Parse using function calling.

        Parameters
        ----------
        query : str
            The user's query.

        Returns
        -------
        ParsedIntent
            The parsed intent.
        """
        # State tracking
        intent_type = None
        confidence = 0.0
        search_terms = []
        filters = {}
        action = None
        response = None

        # Tool executor
        def tool_executor(tool_name: str, arguments: Dict[str, Any]) -> str:
            nonlocal intent_type, confidence, search_terms, filters, action, response

            if tool_name == "classify_intent":
                intent_type_str = arguments.get("intent_type", "search")
                try:
                    intent_type = IntentType(intent_type_str)
                except ValueError:
                    intent_type = IntentType.SEARCH
                confidence = arguments.get("confidence", 0.8)
                return f"Intent classified as: {intent_type.value}"

            elif tool_name == "extract_search_params":
                search_terms = arguments.get("search_terms", [])
                filters = arguments.get("filters", {})
                return f"Extracted search terms: {search_terms}, filters: {filters}"

            elif tool_name == "extract_action":
                action = arguments.get("action")
                return f"Extracted action: {action}"

            elif tool_name == "generate_response":
                response = arguments.get("message")
                return "Response generated"

            else:
                return f"Unknown tool: {tool_name}"

        # Create messages
        messages = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=f"用户查询: {query}"),
        ]

        # Use chat_with_tools for automatic tool execution loop
        result = self._llm_service.chat_with_tools(
            messages=messages,
            tools=INTENT_TOOLS,
            tool_executor=tool_executor,
            max_iterations=5,
            temperature=0.3,
            max_tokens=500,
        )

        # If we got a response, use it
        if result and result.content and not response:
            response = result.content

        # Default values if tools weren't called
        if intent_type is None:
            intent_type = IntentType.SEARCH
        if confidence == 0.0:
            confidence = 0.7

        return ParsedIntent(
            intent_type=intent_type,
            query=query,
            search_terms=search_terms,
            filters=filters,
            action=action,
            confidence=confidence,
            response=response or f"I'll help you with: {query}",
        )

    def _parse_with_rules(self, query: str) -> ParsedIntent:
        """Parse using rules (fallback).

        Parameters
        ----------
        query : str
            The user's query.

        Returns
        -------
        ParsedIntent
            The parsed intent.
        """
        query_lower = query.lower()

        # Detect intent type
        intent_type = IntentType.SEARCH
        action = None

        # Check for organize intent
        organize_keywords = ["创建相册", "整理", "分类", "create album", "organize", "group"]
        if any(kw in query_lower for kw in organize_keywords):
            intent_type = IntentType.ORGANIZE

        # Check for question intent
        question_keywords = ["多少", "什么时候", "哪里", "谁", "how many", "when", "where", "who", "what"]
        if any(kw in query_lower for kw in question_keywords):
            intent_type = IntentType.QUESTION

        # Check for action intent
        action_keywords = {
            "收藏": "favorite",
            "删除": "delete",
            "分享": "share",
            "favorite": "favorite",
            "delete": "delete",
            "share": "share",
        }
        for keyword, action_name in action_keywords.items():
            if keyword in query_lower:
                intent_type = IntentType.ACTION
                action = action_name
                break

        # Extract search terms
        search_terms = self._extract_search_terms(query)

        # Extract filters
        filters = self._extract_filters(query)

        # Generate response
        response = self._generate_response(intent_type, search_terms, filters, action)

        return ParsedIntent(
            intent_type=intent_type,
            query=query,
            search_terms=search_terms,
            filters=filters,
            action=action,
            confidence=0.7,
            response=response,
        )

    def _extract_search_terms(self, query: str) -> List[str]:
        """Extract search terms from query."""
        stop_words = {
            "的", "了", "在", "是", "我", "你", "他", "她", "它",
            "the", "a", "an", "is", "are", "was", "were", "be",
            "have", "has", "had", "do", "does", "did", "will",
            "find", "show", "search", "look", "for", "找", "搜索", "显示",
        }

        words = query.split()
        terms = [w for w in words if w.lower() not in stop_words and len(w) > 1]

        return terms

    def _extract_filters(self, query: str) -> dict:
        """Extract filters from query."""
        filters = {}

        # Date filters
        date_patterns = {
            "去年": "last year",
            "今年": "this year",
            "夏天": "summer",
            "冬天": "winter",
            "春天": "spring",
            "秋天": "autumn",
        }

        for pattern, value in date_patterns.items():
            if pattern in query:
                filters["date"] = value
                break

        # Location filters
        location_keywords = ["在", "at", "in", "from"]
        for keyword in location_keywords:
            if keyword in query:
                idx = query.index(keyword)
                remaining = query[idx + len(keyword):].strip()
                location_words = remaining.split()[:3]
                if location_words:
                    filters["location"] = " ".join(location_words)
                break

        return filters

    def _generate_response(
        self,
        intent_type: IntentType,
        search_terms: List[str],
        filters: dict,
        action: Optional[str],
    ) -> str:
        """Generate a response based on the parsed intent."""
        if intent_type == IntentType.SEARCH:
            terms_str = ", ".join(search_terms) if search_terms else "all"
            filter_str = ""
            if filters:
                filter_parts = [f"{k}: {v}" for k, v in filters.items()]
                filter_str = f" with filters: {', '.join(filter_parts)}"
            return f"Searching for photos matching: {terms_str}{filter_str}"

        elif intent_type == IntentType.ORGANIZE:
            return "I'll help you organize your photos."

        elif intent_type == IntentType.QUESTION:
            return "Let me look that up for you."

        elif intent_type == IntentType.ACTION:
            return f"I'll {action} the selected photos."

        return "I'm not sure what you're asking. Could you rephrase?"
