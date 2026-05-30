"""Intent parser for natural language photo management."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from ..ports.llm_port import ChatMessage, LLMPort

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


# System prompt for intent parsing
_INTENT_PARSER_PROMPT = """You are an AI assistant for a photo management application.
Your job is to parse user requests and determine their intent.

Possible intents:
1. SEARCH - User wants to find photos matching certain criteria
2. ORGANIZE - User wants to organize photos (create albums, find duplicates, etc.)
3. QUESTION - User is asking a question about their photos
4. ACTION - User wants to perform an action on photos (favorite, delete, share, etc.)

For each request, extract:
- intent_type: SEARCH, ORGANIZE, QUESTION, or ACTION
- search_terms: list of keywords to search for
- filters: dict of filters like {"date": "2024", "location": "Tokyo", "person": "John"}
- action: the action to perform (if ACTION intent)
- confidence: how confident you are in the parsing (0.0 to 1.0)
- response: a friendly response to the user

Respond in JSON format:
{
    "intent_type": "SEARCH",
    "search_terms": ["sunset", "beach"],
    "filters": {"date": "2024 summer"},
    "action": null,
    "confidence": 0.9,
    "response": "I'll search for sunset beach photos from summer 2024."
}

Examples:
- "Find photos of my dog" -> SEARCH, search_terms: ["dog"]
- "Show me photos from Tokyo" -> SEARCH, filters: {"location": "Tokyo"}
- "Create an album of my vacation" -> ORGANIZE
- "How many photos do I have?" -> QUESTION
- "Favorite these photos" -> ACTION, action: "favorite"
- "找去年夏天在海边的照片" -> SEARCH, search_terms: ["海边"], filters: {"date": "去年夏天"}
"""


class IntentParser:
    """Parser for natural language photo management requests.

    This class uses an LLM to parse user requests into structured intents
    that can be processed by the application.
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

        # Try LLM-based parsing first
        if self._llm_service and self._llm_service.is_available():
            try:
                return self._parse_with_llm(query)
            except Exception as e:
                _LOGGER.warning("LLM parsing failed, falling back to rule-based: %s", e)

        # Fall back to rule-based parsing
        return self._parse_with_rules(query)

    def _parse_with_llm(self, query: str) -> ParsedIntent:
        """Parse using LLM.

        Parameters
        ----------
        query : str
            The user's query.

        Returns
        -------
        ParsedIntent
            The parsed intent.
        """
        import json

        messages = [
            ChatMessage(role="system", content=_INTENT_PARSER_PROMPT),
            ChatMessage(role="user", content=query),
        ]

        response = self._llm_service.chat(messages, temperature=0.3, max_tokens=500)
        if not response:
            return self._parse_with_rules(query)

        try:
            # Parse JSON response
            result = json.loads(response.content)

            intent_type_str = result.get("intent_type", "UNKNOWN")
            try:
                intent_type = IntentType(intent_type_str.lower())
            except ValueError:
                intent_type = IntentType.UNKNOWN

            return ParsedIntent(
                intent_type=intent_type,
                query=query,
                search_terms=result.get("search_terms", []),
                filters=result.get("filters", {}),
                action=result.get("action"),
                confidence=result.get("confidence", 0.5),
                response=result.get("response"),
            )
        except (json.JSONDecodeError, KeyError) as e:
            _LOGGER.warning("Failed to parse LLM response: %s", e)
            return self._parse_with_rules(query)

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
        """Extract search terms from query.

        Parameters
        ----------
        query : str
            The user's query.

        Returns
        -------
        List[str]
            List of search terms.
        """
        # Remove common stop words
        stop_words = {
            "的", "了", "在", "是", "我", "你", "他", "她", "它",
            "the", "a", "an", "is", "are", "was", "were", "be",
            "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might",
            "find", "show", "search", "look", "for", "找", "搜索", "显示",
        }

        words = query.split()
        terms = [w for w in words if w.lower() not in stop_words and len(w) > 1]

        return terms

    def _extract_filters(self, query: str) -> dict:
        """Extract filters from query.

        Parameters
        ----------
        query : str
            The user's query.

        Returns
        -------
        dict
            Extracted filters.
        """
        filters = {}

        # Date filters
        date_patterns = {
            "去年": "last year",
            "今年": "this year",
            "前年": "year before last",
            "夏天": "summer",
            "冬天": "winter",
            "春天": "spring",
            "秋天": "autumn",
            "last year": "last year",
            "this year": "this year",
            "summer": "summer",
            "winter": "winter",
            "spring": "spring",
            "autumn": "autumn",
        }

        for pattern, value in date_patterns.items():
            if pattern in query.lower():
                filters["date"] = value
                break

        # Location filters
        location_keywords = ["在", "at", "in", "from"]
        for keyword in location_keywords:
            if keyword in query:
                # Try to extract location after keyword
                idx = query.index(keyword)
                remaining = query[idx + len(keyword):].strip()
                # Take first few words as location
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
        """Generate a response based on the parsed intent.

        Parameters
        ----------
        intent_type : IntentType
            The intent type.
        search_terms : List[str]
            Search terms.
        filters : dict
            Filters.
        action : Optional[str]
            Action to perform.

        Returns
        -------
        str
            Generated response.
        """
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
