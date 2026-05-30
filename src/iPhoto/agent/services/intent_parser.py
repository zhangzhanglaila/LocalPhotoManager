"""Intent parser for natural language photo management.

Uses ReAct (Reasoning + Acting) pattern for multi-step reasoning.
"""

from __future__ import annotations

import logging
import re
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

    reasoning_steps: List[str] = None
    """Steps of reasoning (for ReAct mode)."""

    def __post_init__(self):
        if self.reasoning_steps is None:
            self.reasoning_steps = []


# ReAct prompt for intent parsing
_REACT_INTENT_PROMPT = """你是一个具备推理和行动能力的AI助手，用于解析照片管理应用中的用户请求。

## 可用工具
你可以使用以下工具来帮助解析用户请求：

1. analyze_query[query] - 分析用户查询，提取关键信息
2. extract_date[query] - 从查询中提取日期/时间信息
3. extract_location[query] - 从查询中提取地点信息
4. extract_person[query] - 从查询中提取人物信息
5. extract_action[query] - 从查询中提取操作类型
6. classify_intent[query] - 对查询进行意图分类

## 工作流程
请严格按照以下格式进行回应，每次只能执行一个步骤：

Thought: 你的思考过程，用于分析问题、拆解任务和规划下一步行动。
Action: 你决定采取的行动，必须是以下格式之一：
- `{{tool_name}}[{{tool_input}}]` - 调用指定工具
- `Finish[最终答案]` - 当你有足够信息给出最终答案时

## 重要提醒
1. 每次回应必须包含Thought和Action两部分
2. 工具调用的格式必须严格遵循：工具名[参数]
3. 只有当你确信有足够信息回答问题时，才使用Finish
4. Finish时请输出JSON格式的最终结果

## 最终输出格式
当你使用Finish时，请输出以下JSON格式：
```json
{{
    "intent_type": "SEARCH|ORGANIZE|QUESTION|ACTION",
    "search_terms": ["关键词1", "关键词2"],
    "filters": {{"date": "日期", "location": "地点", "person": "人物"}},
    "action": "操作类型或null",
    "confidence": 0.9,
    "response": "给用户的回复"
}}
```

## 当前任务
**用户查询:** {query}

## 执行历史
{history}

现在开始你的推理和行动：
"""


class IntentParser:
    """Parser for natural language photo management requests.

    Uses ReAct (Reasoning + Acting) pattern for multi-step reasoning.
    """

    def __init__(self, llm_service: Optional[LLMPort] = None, max_steps: int = 5) -> None:
        """Initialize the intent parser.

        Parameters
        ----------
        llm_service : Optional[LLMPort]
            LLM service for parsing. If None, uses rule-based parsing.
        max_steps : int
            Maximum number of reasoning steps.
        """
        self._llm_service = llm_service
        self._max_steps = max_steps

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

        # Try ReAct-based parsing first
        if self._llm_service and self._llm_service.is_available():
            try:
                return self._parse_with_react(query)
            except Exception as e:
                _LOGGER.warning("ReAct parsing failed, falling back to rule-based: %s", e)

        # Fall back to rule-based parsing
        return self._parse_with_rules(query)

    def _parse_with_react(self, query: str) -> ParsedIntent:
        """Parse using ReAct pattern.

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

        history = []
        reasoning_steps = []

        for step in range(self._max_steps):
            # Build prompt
            history_str = "\n".join(history) if history else "无"
            prompt = _REACT_INTENT_PROMPT.format(query=query, history=history_str)

            # Call LLM
            messages = [ChatMessage(role="user", content=prompt)]
            response = self._llm_service.chat(messages, temperature=0.3, max_tokens=500)

            if not response:
                break

            response_text = response.content

            # Parse Thought and Action
            thought_match = re.search(r'Thought:\s*(.+?)(?=Action:|$)', response_text, re.DOTALL)
            action_match = re.search(r'Action:\s*(.+?)$', response_text, re.DOTALL)

            if thought_match:
                thought = thought_match.group(1).strip()
                reasoning_steps.append(f"Thought: {thought}")
                history.append(f"Thought: {thought}")

            if not action_match:
                break

            action = action_match.group(1).strip()

            # Check if this is a Finish action
            if action.startswith("Finish"):
                final_answer = self._parse_action_input(action)
                try:
                    # Parse JSON result
                    result = json.loads(final_answer)
                    return self._create_intent_from_result(query, result, reasoning_steps)
                except json.JSONDecodeError:
                    # Try to extract JSON from the text
                    json_match = re.search(r'\{.*\}', final_answer, re.DOTALL)
                    if json_match:
                        try:
                            result = json.loads(json_match.group())
                            return self._create_intent_from_result(query, result, reasoning_steps)
                        except json.JSONDecodeError:
                            pass
                    break

            # Execute tool call
            tool_name, tool_input = self._parse_action(action)
            observation = self._execute_tool(tool_name, tool_input, query)

            history.append(f"Action: {action}")
            history.append(f"Observation: {observation}")
            reasoning_steps.append(f"Action: {action}")
            reasoning_steps.append(f"Observation: {observation}")

        # If ReAct didn't complete, fall back to rule-based
        return self._parse_with_rules(query)

    def _parse_action(self, action: str) -> tuple:
        """Parse action string into tool name and input.

        Parameters
        ----------
        action : str
            Action string in format: tool_name[input]

        Returns
        -------
        tuple
            (tool_name, tool_input)
        """
        match = re.match(r'(\w+)\[(.+?)\]', action)
        if match:
            return match.group(1), match.group(2)
        return action, ""

    def _parse_action_input(self, action: str) -> str:
        """Extract input from Finish action.

        Parameters
        ----------
        action : str
            Finish action string.

        Returns
        -------
        str
            The input content.
        """
        match = re.match(r'Finish\[(.+?)\]$', action, re.DOTALL)
        if match:
            return match.group(1)
        return action

    def _execute_tool(self, tool_name: str, tool_input: str, original_query: str) -> str:
        """Execute a tool and return the result.

        Parameters
        ----------
        tool_name : str
            Name of the tool to execute.
        tool_input : str
            Input for the tool.
        original_query : str
            The original user query.

        Returns
        -------
        str
            Tool execution result.
        """
        if tool_name == "analyze_query":
            return self._tool_analyze_query(tool_input)
        elif tool_name == "extract_date":
            return self._tool_extract_date(tool_input)
        elif tool_name == "extract_location":
            return self._tool_extract_location(tool_input)
        elif tool_name == "extract_person":
            return self._tool_extract_person(tool_input)
        elif tool_name == "extract_action":
            return self._tool_extract_action(tool_input)
        elif tool_name == "classify_intent":
            return self._tool_classify_intent(tool_input)
        else:
            return f"未知工具: {tool_name}"

    def _tool_analyze_query(self, query: str) -> str:
        """Analyze query and extract key information."""
        keywords = []
        # Extract Chinese and English words
        words = re.findall(r'[一-鿿]+|[a-zA-Z]+', query)
        keywords.extend(words)
        return f"关键词: {', '.join(keywords)}"

    def _tool_extract_date(self, query: str) -> str:
        """Extract date/time information from query."""
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
        }

        found_dates = []
        for pattern, value in date_patterns.items():
            if pattern in query.lower():
                found_dates.append(value)

        # Check for specific dates (YYYY-MM-DD or YYYY/MM/DD)
        date_match = re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', query)
        if date_match:
            found_dates.append(date_match.group())

        if found_dates:
            return f"日期信息: {', '.join(found_dates)}"
        return "未找到日期信息"

    def _tool_extract_location(self, query: str) -> str:
        """Extract location information from query."""
        location_keywords = ["在", "at", "in", "from"]
        locations = []

        for keyword in location_keywords:
            if keyword in query:
                idx = query.index(keyword)
                remaining = query[idx + len(keyword):].strip()
                location_words = remaining.split()[:3]
                if location_words:
                    locations.append(" ".join(location_words))

        if locations:
            return f"地点信息: {', '.join(locations)}"
        return "未找到地点信息"

    def _tool_extract_person(self, query: str) -> str:
        """Extract person information from query."""
        person_keywords = ["和", "with", "跟", "一起"]
        persons = []

        for keyword in person_keywords:
            if keyword in query:
                idx = query.index(keyword)
                remaining = query[idx + len(keyword):].strip()
                person_words = remaining.split()[:2]
                if person_words:
                    persons.append(" ".join(person_words))

        if persons:
            return f"人物信息: {', '.join(persons)}"
        return "未找到人物信息"

    def _tool_extract_action(self, query: str) -> str:
        """Extract action type from query."""
        action_keywords = {
            "收藏": "favorite",
            "删除": "delete",
            "分享": "share",
            "找": "search",
            "搜索": "search",
            "显示": "show",
            "favorite": "favorite",
            "delete": "delete",
            "share": "share",
            "find": "search",
            "search": "search",
            "show": "show",
        }

        found_actions = []
        for keyword, action in action_keywords.items():
            if keyword in query.lower():
                found_actions.append(action)

        if found_actions:
            return f"操作类型: {', '.join(set(found_actions))}"
        return "未找到明确的操作类型"

    def _tool_classify_intent(self, query: str) -> str:
        """Classify the intent of the query."""
        query_lower = query.lower()

        # Check for organize intent
        organize_keywords = ["创建相册", "整理", "分类", "create album", "organize"]
        if any(kw in query_lower for kw in organize_keywords):
            return "意图: ORGANIZE"

        # Check for question intent
        question_keywords = ["多少", "什么时候", "哪里", "谁", "how many", "when", "where", "who"]
        if any(kw in query_lower for kw in question_keywords):
            return "意图: QUESTION"

        # Check for action intent
        action_keywords = ["收藏", "删除", "分享", "favorite", "delete", "share"]
        if any(kw in query_lower for kw in action_keywords):
            return "意图: ACTION"

        # Default to search
        return "意图: SEARCH"

    def _create_intent_from_result(
        self, query: str, result: dict, reasoning_steps: List[str]
    ) -> ParsedIntent:
        """Create ParsedIntent from JSON result.

        Parameters
        ----------
        query : str
            Original query.
        result : dict
            Parsed JSON result.
        reasoning_steps : List[str]
            List of reasoning steps.

        Returns
        -------
        ParsedIntent
            The parsed intent.
        """
        intent_type_str = result.get("intent_type", "SEARCH")
        try:
            intent_type = IntentType(intent_type_str.lower())
        except ValueError:
            intent_type = IntentType.SEARCH

        return ParsedIntent(
            intent_type=intent_type,
            query=query,
            search_terms=result.get("search_terms", []),
            filters=result.get("filters", {}),
            action=result.get("action"),
            confidence=result.get("confidence", 0.8),
            response=result.get("response"),
            reasoning_steps=reasoning_steps,
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
