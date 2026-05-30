"""Question-answering service for photo management.

Uses function calling for reliable tool invocation and JIT context loading.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..ports.llm_port import ChatMessage, LLMPort, ToolDefinition
from ..ports.vision_port import VisionPort

_LOGGER = logging.getLogger(__name__)


@dataclass
class QAResult:
    """Result of a question-answering request."""

    question: str
    """The original question."""

    answer: str
    """The answer to the question."""

    confidence: float
    """Confidence in the answer (0.0 to 1.0)."""

    sources: List[str]
    """Sources used to generate the answer."""

    context_used: List[str] = None
    """Context items that were loaded (for JIT tracking)."""

    def __post_init__(self):
        if self.context_used is None:
            self.context_used = []


class ContextItem:
    """Represents a piece of context that can be loaded on demand."""

    def __init__(self, name: str, loader, cacheable: bool = True):
        self.name = name
        self.loader = loader
        self.cacheable = cacheable
        self._cached_value = None
        self._loaded = False

    def load(self):
        """Load the context item (with caching)."""
        if self._loaded and self.cacheable:
            return self._cached_value

        value = self.loader()
        if self.cacheable:
            self._cached_value = value
            self._loaded = True
        return value

    def invalidate(self):
        """Invalidate the cache."""
        self._cached_value = None
        self._loaded = False


class JITContextManager:
    """Manages JIT (Just-in-Time) context loading."""

    def __init__(self, asset_repository: object, embedding_repository: object, library_root: Path):
        self._asset_repository = asset_repository
        self._embedding_repository = embedding_repository
        self._library_root = library_root

        # Lazy-loaded context items
        self._context_items = {
            "asset_count": ContextItem("asset_count", self._load_asset_count),
            "date_range": ContextItem("date_range", self._load_date_range),
            "locations": ContextItem("locations", self._load_locations),
            "cameras": ContextItem("cameras", self._load_cameras),
        }

        # Per-asset context (not cached globally)
        self._asset_cache = {}

    def get_context(self, name: str):
        if name in self._context_items:
            return self._context_items[name].load()
        return None

    def get_asset_info(self, asset_id: str) -> Optional[dict]:
        if asset_id in self._asset_cache:
            return self._asset_cache[asset_id]

        asset_rows = self._asset_repository.get_rows_by_ids([asset_id])
        if asset_rows:
            info = asset_rows[0]
            self._asset_cache[asset_id] = info
            return info
        return None

    def get_asset_tags(self, asset_id: str) -> List[dict]:
        cache_key = f"tags_{asset_id}"
        if cache_key in self._asset_cache:
            return self._asset_cache[cache_key]

        tags = self._embedding_repository.get_tags(asset_id)
        self._asset_cache[cache_key] = tags
        return tags

    def get_asset_caption(self, asset_id: str) -> Optional[str]:
        cache_key = f"caption_{asset_id}"
        if cache_key in self._asset_cache:
            return self._asset_cache[cache_key]

        caption = self._embedding_repository.get_caption(asset_id)
        self._asset_cache[cache_key] = caption
        return caption

    def search_by_tag(self, tag_name: str) -> List[str]:
        return self._embedding_repository.search_by_tag(tag_name)

    def search_by_location(self, location: str) -> List[str]:
        all_assets = self._asset_repository.read_all()
        return [a["id"] for a in all_assets if location.lower() in a.get("location", "").lower()]

    def search_by_date(self, date: str) -> List[str]:
        all_assets = self._asset_repository.read_all()
        return [a["id"] for a in all_assets if date in a.get("dt", "")]

    def invalidate_all(self):
        for item in self._context_items.values():
            item.invalidate()
        self._asset_cache.clear()

    def _load_asset_count(self) -> dict:
        all_assets = self._asset_repository.read_all()
        total = len(all_assets)
        images = sum(1 for a in all_assets if a.get("media_type") == 0)
        videos = sum(1 for a in all_assets if a.get("media_type") == 1)
        return {"total": total, "images": images, "videos": videos}

    def _load_date_range(self) -> dict:
        all_assets = self._asset_repository.read_all()
        dates = [a.get("dt", "") for a in all_assets if a.get("dt")]
        if dates:
            return {"earliest": min(dates)[:10], "latest": max(dates)[:10]}
        return {"earliest": None, "latest": None}

    def _load_locations(self) -> List[str]:
        all_assets = self._asset_repository.read_all()
        locations = set()
        for asset in all_assets:
            loc = asset.get("location", "")
            if loc:
                locations.add(loc)
        return sorted(list(locations))

    def _load_cameras(self) -> List[str]:
        all_assets = self._asset_repository.read_all()
        cameras = set()
        for asset in all_assets:
            model = asset.get("model", "")
            if model:
                cameras.add(model)
        return sorted(list(cameras))


# Tool definitions for function calling
QA_TOOLS = [
    ToolDefinition(
        name="get_library_stats",
        description="获取照片库统计信息（总数、日期范围、地点、相机等）",
        parameters={
            "type": "object",
            "properties": {
                "stat_type": {
                    "type": "string",
                    "enum": ["count", "date_range", "locations", "cameras"],
                    "description": "统计类型"
                }
            },
            "required": ["stat_type"]
        }
    ),
    ToolDefinition(
        name="get_asset_info",
        description="获取特定照片的详细信息（元数据、标签、描述等）",
        parameters={
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "照片ID"
                },
                "info_type": {
                    "type": "string",
                    "enum": ["metadata", "tags", "caption", "all"],
                    "description": "信息类型"
                }
            },
            "required": ["asset_id"]
        }
    ),
    ToolDefinition(
        name="search_assets",
        description="搜索照片（按标签、地点、日期等）",
        parameters={
            "type": "object",
            "properties": {
                "search_type": {
                    "type": "string",
                    "enum": ["tag", "location", "date"],
                    "description": "搜索类型"
                },
                "query": {
                    "type": "string",
                    "description": "搜索关键词"
                }
            },
            "required": ["search_type", "query"]
        }
    ),
    ToolDefinition(
        name="generate_answer",
        description="生成最终答案",
        parameters={
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "答案内容"
                },
                "confidence": {
                    "type": "number",
                    "description": "置信度 (0.0-1.0)"
                }
            },
            "required": ["answer"]
        }
    )
]

# System prompt for QA
_QA_SYSTEM_PROMPT = """你是一个照片管理应用的AI助手，负责回答用户关于照片库的问题。

你的任务是：
1. 理解用户的问题
2. 使用工具获取相关信息
3. 基于获取的信息生成准确的答案

请使用提供的工具来获取信息。首先分析问题需要哪些信息，然后使用相应工具获取，最后使用 generate_answer 生成答案。

常见问题类型：
- 统计类：多少张照片、什么时候拍的、去过哪里 → 使用 get_library_stats
- 查询类：特定照片的信息 → 使用 get_asset_info
- 搜索类：找特定标签、地点、日期的照片 → 使用 search_assets

重要：只获取回答问题所需的最少信息，不要过度查询。"""


class QAService:
    """Question-answering service for photos.

    Uses function calling for reliable tool invocation and JIT context loading.
    """

    def __init__(
        self,
        llm_service: Optional[LLMPort] = None,
        vision_service: Optional[VisionPort] = None,
        asset_repository: object = None,
        embedding_repository: object = None,
        library_root: Path = None,
    ) -> None:
        self._llm_service = llm_service
        self._vision_service = vision_service
        self._context_manager = JITContextManager(
            asset_repository=asset_repository,
            embedding_repository=embedding_repository,
            library_root=library_root,
        )
        self._library_root = library_root

    def answer_question(
        self,
        question: str,
        context: Optional[dict] = None,
    ) -> QAResult:
        """Answer a question about photos.

        Parameters
        ----------
        question : str
            The question to answer.
        context : Optional[dict]
            Optional context (e.g., current photo, selected photos).

        Returns
        -------
        QAResult
            The answer to the question.
        """
        if not question.strip():
            return QAResult(
                question=question,
                answer="Please provide a question.",
                confidence=0.0,
                sources=[],
            )

        # Try function calling QA if LLM is available
        if self._llm_service and self._llm_service.is_available():
            try:
                return self._answer_with_function_calling(question, context)
            except Exception as e:
                _LOGGER.warning("Function calling QA failed, falling back to simple: %s", e)

        # Fall back to simple QA
        return self._answer_simple(question, context)

    def _answer_with_function_calling(
        self,
        question: str,
        context: Optional[dict],
    ) -> QAResult:
        """Answer using function calling.

        Parameters
        ----------
        question : str
            The question.
        context : Optional[dict]
            Optional context.

        Returns
        -------
        QAResult
            The answer.
        """
        # State tracking
        answer = None
        confidence = 0.0
        context_used = []

        # Tool executor
        def tool_executor(tool_name: str, arguments: Dict[str, Any]) -> str:
            nonlocal answer, confidence

            if tool_name == "get_library_stats":
                stat_type = arguments.get("stat_type", "count")
                context_used.append(f"stats:{stat_type}")

                if stat_type == "count":
                    stats = self._context_manager.get_context("asset_count")
                    return f"照片总数: {stats['total']} (照片: {stats['images']}, 视频: {stats['videos']})"

                elif stat_type == "date_range":
                    date_range = self._context_manager.get_context("date_range")
                    if date_range["earliest"]:
                        return f"日期范围: {date_range['earliest']} 到 {date_range['latest']}"
                    return "无日期信息"

                elif stat_type == "locations":
                    locations = self._context_manager.get_context("locations")
                    return f"所有地点: {', '.join(locations[:10])}" if locations else "无地点信息"

                elif stat_type == "cameras":
                    cameras = self._context_manager.get_context("cameras")
                    return f"所有相机: {', '.join(cameras[:5])}" if cameras else "无相机信息"

                return "未知统计类型"

            elif tool_name == "get_asset_info":
                asset_id = arguments.get("asset_id")
                info_type = arguments.get("info_type", "all")
                context_used.append(f"asset:{asset_id}")

                if info_type in ["metadata", "all"]:
                    info = self._context_manager.get_asset_info(asset_id)
                    if info:
                        parts = []
                        if info.get("rel"):
                            parts.append(f"文件: {info['rel']}")
                        if info.get("dt"):
                            parts.append(f"日期: {info['dt']}")
                        if info.get("location"):
                            parts.append(f"地点: {info['location']}")
                        if info.get("model"):
                            parts.append(f"相机: {info['model']}")
                        if info.get("w") and info.get("h"):
                            parts.append(f"尺寸: {info['w']}x{info['h']}")
                        return "\n".join(parts) if parts else "无详细信息"

                if info_type in ["tags", "all"]:
                    tags = self._context_manager.get_asset_tags(asset_id)
                    if tags:
                        tag_names = [t["name"] for t in tags]
                        return f"标签: {', '.join(tag_names)}"

                if info_type in ["caption", "all"]:
                    caption = self._context_manager.get_asset_caption(asset_id)
                    if caption:
                        return f"描述: {caption}"

                return "未找到信息"

            elif tool_name == "search_assets":
                search_type = arguments.get("search_type")
                query = arguments.get("query")
                context_used.append(f"search:{search_type}:{query}")

                if search_type == "tag":
                    asset_ids = self._context_manager.search_by_tag(query)
                    return f"找到 {len(asset_ids)} 张标签为 '{query}' 的照片"

                elif search_type == "location":
                    asset_ids = self._context_manager.search_by_location(query)
                    return f"找到 {len(asset_ids)} 张在 '{query}' 拍摄的照片"

                elif search_type == "date":
                    asset_ids = self._context_manager.search_by_date(query)
                    return f"找到 {len(asset_ids)} 张在 '{query}' 期间的照片"

                return "未知搜索类型"

            elif tool_name == "generate_answer":
                answer = arguments.get("answer")
                confidence = arguments.get("confidence", 0.8)
                return "答案已生成"

            else:
                return f"未知工具: {tool_name}"

        # Create messages
        messages = [
            ChatMessage(role="system", content=_QA_SYSTEM_PROMPT),
            ChatMessage(role="user", content=f"问题: {question}"),
        ]

        # Use chat_with_tools for automatic tool execution loop
        result = self._llm_service.chat_with_tools(
            messages=messages,
            tools=QA_TOOLS,
            tool_executor=tool_executor,
            max_iterations=5,
            temperature=0.3,
            max_tokens=500,
        )

        # If we got a response but no answer was generated, use the response
        if result and result.content and not answer:
            answer = result.content
            confidence = 0.7

        # Default answer if nothing was generated
        if not answer:
            answer = "I couldn't answer your question. Please try rephrasing."
            confidence = 0.3

        return QAResult(
            question=question,
            answer=answer,
            confidence=confidence,
            sources=["function_calling", "jit_context"],
            context_used=context_used,
        )

    def _answer_simple(
        self,
        question: str,
        context: Optional[dict],
    ) -> QAResult:
        """Simple fallback QA without LLM."""
        question_lower = question.lower()

        # Check for stats questions
        if any(kw in question_lower for kw in ["多少", "how many", "total", "count"]):
            stats = self._context_manager.get_context("asset_count")
            answer = f"你的图库包含 {stats['total']} 张照片和视频 ({stats['images']} 张照片, {stats['videos']} 个视频)。"
            return QAResult(
                question=question,
                answer=answer,
                confidence=0.95,
                sources=["jit_context"],
                context_used=["asset_count"],
            )

        # Check for date questions
        if any(kw in question_lower for kw in ["什么时候", "when", "日期", "date"]):
            date_range = self._context_manager.get_context("date_range")
            if date_range["earliest"]:
                answer = f"你的照片日期范围是从 {date_range['earliest']} 到 {date_range['latest']}。"
            else:
                answer = "没有找到日期信息。"
            return QAResult(
                question=question,
                answer=answer,
                confidence=0.9,
                sources=["jit_context"],
                context_used=["date_range"],
            )

        # Check for location questions
        if any(kw in question_lower for kw in ["哪里", "where", "地点", "location"]):
            locations = self._context_manager.get_context("locations")
            if locations:
                answer = f"你去过的地方包括: {', '.join(locations[:10])}。"
            else:
                answer = "没有找到地点信息。"
            return QAResult(
                question=question,
                answer=answer,
                confidence=0.85,
                sources=["jit_context"],
                context_used=["locations"],
            )

        # Default response
        return QAResult(
            question=question,
            answer="我可以帮你回答关于照片的问题。试试问我关于照片数量、日期、地点等问题。",
            confidence=0.3,
            sources=[],
        )
