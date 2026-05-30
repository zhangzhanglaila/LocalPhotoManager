"""Question-answering service for photo management.

Uses JIT (Just-in-Time) context loading for efficiency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..ports.llm_port import ChatMessage, LLMPort
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


# System prompt for photo QA with JIT context
_PHOTO_QA_PROMPT = """你是一个照片管理应用的AI助手。你帮助用户理解他们的照片和照片库。

你可以回答关于以下内容的问题：
1. 照片元数据（日期、位置、相机设置等）
2. 照片内容（照片里有什么、谁在里面等）
3. 照片库统计（有多少照片、什么时候拍的等）
4. 照片组织（相册、标签、人脸等）

## 可用工具
你可以使用以下工具来获取信息：

1. get_asset_count[] - 获取照片总数
2. get_date_range[] - 获取照片日期范围
3. get_locations[] - 获取所有地点
4. get_cameras[] - 获取所有相机型号
5. get_asset_info[asset_id] - 获取特定照片的详细信息
6. get_tags[asset_id] - 获取照片标签
7. get_caption[asset_id] - 获取照片描述
8. search_by_tag[tag_name] - 按标签搜索照片
9. search_by_location[location] - 按地点搜索照片
10. search_by_date[date] - 按日期搜索照片

## 工作流程
请严格按照以下格式进行回应：

Thought: 分析问题，确定需要哪些信息
Action: 调用工具获取信息（格式：工具名[参数]）
Observation: 工具返回的结果
... (可以重复多次)
Thought: 基于获取的信息，形成最终答案
Action: Finish[最终答案]

## 重要提醒
1. 只加载回答问题所需的最少信息
2. 如果问题简单，可以直接回答而不需要工具
3. 使用中文回答用户的问题

## 当前任务
**问题:** {question}

## 执行历史
{history}

现在开始你的推理和行动：
"""


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
    """Manages JIT (Just-in-Time) context loading.

    This class provides lazy-loaded context items that are only
    fetched when actually needed.
    """

    def __init__(self, asset_repository: object, embedding_repository: object, library_root: Path):
        """Initialize the JIT context manager.

        Parameters
        ----------
        asset_repository : object
            Repository for accessing asset data.
        embedding_repository : object
            Repository for accessing embeddings and tags.
        library_root : Path
            Root directory of the library.
        """
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
        """Get a context item by name.

        Parameters
        ----------
        name : str
            Name of the context item.

        Returns
        -------
        any
            The context value.
        """
        if name in self._context_items:
            return self._context_items[name].load()
        return None

    def get_asset_info(self, asset_id: str) -> Optional[dict]:
        """Get asset info (JIT loaded).

        Parameters
        ----------
        asset_id : str
            The asset ID.

        Returns
        -------
        Optional[dict]
            Asset information.
        """
        if asset_id in self._asset_cache:
            return self._asset_cache[asset_id]

        asset_rows = self._asset_repository.get_rows_by_ids([asset_id])
        if asset_rows:
            info = asset_rows[0]
            self._asset_cache[asset_id] = info
            return info
        return None

    def get_asset_tags(self, asset_id: str) -> List[dict]:
        """Get asset tags (JIT loaded).

        Parameters
        ----------
        asset_id : str
            The asset ID.

        Returns
        -------
        List[dict]
            List of tags.
        """
        cache_key = f"tags_{asset_id}"
        if cache_key in self._asset_cache:
            return self._asset_cache[cache_key]

        tags = self._embedding_repository.get_tags(asset_id)
        self._asset_cache[cache_key] = tags
        return tags

    def get_asset_caption(self, asset_id: str) -> Optional[str]:
        """Get asset caption (JIT loaded).

        Parameters
        ----------
        asset_id : str
            The asset ID.

        Returns
        -------
        Optional[str]
            The caption.
        """
        cache_key = f"caption_{asset_id}"
        if cache_key in self._asset_cache:
            return self._asset_cache[cache_key]

        caption = self._embedding_repository.get_caption(asset_id)
        self._asset_cache[cache_key] = caption
        return caption

    def search_by_tag(self, tag_name: str) -> List[str]:
        """Search assets by tag.

        Parameters
        ----------
        tag_name : str
            The tag name.

        Returns
        -------
        List[str]
            List of asset IDs.
        """
        return self._embedding_repository.search_by_tag(tag_name)

    def search_by_location(self, location: str) -> List[str]:
        """Search assets by location.

        Parameters
        ----------
        location : str
            The location name.

        Returns
        -------
        List[str]
            List of asset IDs.
        """
        all_assets = self._asset_repository.read_all()
        return [a["id"] for a in all_assets if location.lower() in a.get("location", "").lower()]

    def search_by_date(self, date: str) -> List[str]:
        """Search assets by date.

        Parameters
        ----------
        date : str
            The date string (partial match).

        Returns
        -------
        List[str]
            List of asset IDs.
        """
        all_assets = self._asset_repository.read_all()
        return [a["id"] for a in all_assets if date in a.get("dt", "")]

    def invalidate_all(self):
        """Invalidate all cached context."""
        for item in self._context_items.values():
            item.invalidate()
        self._asset_cache.clear()

    def _load_asset_count(self) -> dict:
        """Load asset count."""
        all_assets = self._asset_repository.read_all()
        total = len(all_assets)
        images = sum(1 for a in all_assets if a.get("media_type") == 0)
        videos = sum(1 for a in all_assets if a.get("media_type") == 1)
        return {"total": total, "images": images, "videos": videos}

    def _load_date_range(self) -> dict:
        """Load date range."""
        all_assets = self._asset_repository.read_all()
        dates = [a.get("dt", "") for a in all_assets if a.get("dt")]
        if dates:
            return {"earliest": min(dates)[:10], "latest": max(dates)[:10]}
        return {"earliest": None, "latest": None}

    def _load_locations(self) -> List[str]:
        """Load all unique locations."""
        all_assets = self._asset_repository.read_all()
        locations = set()
        for asset in all_assets:
            loc = asset.get("location", "")
            if loc:
                locations.add(loc)
        return sorted(list(locations))

    def _load_cameras(self) -> List[str]:
        """Load all unique cameras."""
        all_assets = self._asset_repository.read_all()
        cameras = set()
        for asset in all_assets:
            model = asset.get("model", "")
            if model:
                cameras.add(model)
        return sorted(list(cameras))


class QAService:
    """Question-answering service for photos.

    Uses JIT context loading for efficient resource usage.
    """

    def __init__(
        self,
        llm_service: Optional[LLMPort] = None,
        vision_service: Optional[VisionPort] = None,
        asset_repository: object = None,
        embedding_repository: object = None,
        library_root: Path = None,
    ) -> None:
        """Initialize the QA service.

        Parameters
        ----------
        llm_service : Optional[LLMPort]
            LLM service for text-based QA.
        vision_service : Optional[VisionPort]
            Vision service for image-based QA.
        asset_repository : object
            Repository for accessing asset data.
        embedding_repository : object
            Repository for accessing embeddings and tags.
        library_root : Path
            Root directory of the library.
        """
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

        # Try ReAct-based QA if LLM is available
        if self._llm_service and self._llm_service.is_available():
            try:
                return self._answer_with_react(question, context)
            except Exception as e:
                _LOGGER.warning("ReAct QA failed, falling back to simple: %s", e)

        # Fall back to simple QA
        return self._answer_simple(question, context)

    def _answer_with_react(
        self,
        question: str,
        context: Optional[dict],
    ) -> QAResult:
        """Answer using ReAct pattern with JIT context loading.

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
        import re

        history = []
        context_used = []
        max_steps = 5

        for step in range(max_steps):
            # Build prompt
            history_str = "\n".join(history) if history else "无"
            prompt = _PHOTO_QA_PROMPT.format(question=question, history=history_str)

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
                history.append(f"Thought: {thought}")

            if not action_match:
                break

            action = action_match.group(1).strip()

            # Check if this is a Finish action
            if action.startswith("Finish"):
                final_answer = self._parse_action_input(action)
                return QAResult(
                    question=question,
                    answer=final_answer,
                    confidence=0.8,
                    sources=["llm", "jit_context"],
                    context_used=context_used,
                )

            # Execute tool call (JIT loading)
            tool_name, tool_input = self._parse_action(action)
            observation = self._execute_tool(tool_name, tool_input)
            context_used.append(f"{tool_name}[{tool_input}]")

            history.append(f"Action: {action}")
            history.append(f"Observation: {observation}")

        # If ReAct didn't complete, return what we have
        return QAResult(
            question=question,
            answer="I couldn't fully answer your question. Please try rephrasing.",
            confidence=0.3,
            sources=[],
            context_used=context_used,
        )

    def _parse_action(self, action: str) -> tuple:
        """Parse action string into tool name and input."""
        match = re.match(r'(\w+)\[(.+?)\]', action)
        if match:
            return match.group(1), match.group(2)
        return action, ""

    def _parse_action_input(self, action: str) -> str:
        """Extract input from Finish action."""
        match = re.match(r'Finish\[(.+?)\]$', action, re.DOTALL)
        if match:
            return match.group(1)
        return action

    def _execute_tool(self, tool_name: str, tool_input: str) -> str:
        """Execute a tool and return the result.

        This is where JIT context loading happens.
        """
        if tool_name == "get_asset_count":
            stats = self._context_manager.get_context("asset_count")
            return f"照片总数: {stats['total']} (照片: {stats['images']}, 视频: {stats['videos']})"

        elif tool_name == "get_date_range":
            date_range = self._context_manager.get_context("date_range")
            if date_range["earliest"]:
                return f"日期范围: {date_range['earliest']} 到 {date_range['latest']}"
            return "无日期信息"

        elif tool_name == "get_locations":
            locations = self._context_manager.get_context("locations")
            return f"所有地点: {', '.join(locations[:10])}" if locations else "无地点信息"

        elif tool_name == "get_cameras":
            cameras = self._context_manager.get_context("cameras")
            return f"所有相机: {', '.join(cameras[:5])}" if cameras else "无相机信息"

        elif tool_name == "get_asset_info":
            info = self._context_manager.get_asset_info(tool_input)
            if info:
                return self._format_asset_info(info)
            return "未找到照片信息"

        elif tool_name == "get_tags":
            tags = self._context_manager.get_asset_tags(tool_input)
            if tags:
                tag_names = [t["name"] for t in tags]
                return f"标签: {', '.join(tag_names)}"
            return "无标签"

        elif tool_name == "get_caption":
            caption = self._context_manager.get_asset_caption(tool_input)
            return f"描述: {caption}" if caption else "无描述"

        elif tool_name == "search_by_tag":
            asset_ids = self._context_manager.search_by_tag(tool_input)
            return f"找到 {len(asset_ids)} 张标签为 '{tool_input}' 的照片"

        elif tool_name == "search_by_location":
            asset_ids = self._context_manager.search_by_location(tool_input)
            return f"找到 {len(asset_ids)} 张在 '{tool_input}' 拍摄的照片"

        elif tool_name == "search_by_date":
            asset_ids = self._context_manager.search_by_date(tool_input)
            return f"找到 {len(asset_ids)} 张在 '{tool_input}' 期间的照片"

        else:
            return f"未知工具: {tool_name}"

    def _format_asset_info(self, info: dict) -> str:
        """Format asset info as string."""
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

    def _answer_simple(
        self,
        question: str,
        context: Optional[dict],
    ) -> QAResult:
        """Simple fallback QA without LLM.

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
