"""Question-answering service for photo management."""

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


# System prompt for photo QA
_PHOTO_QA_PROMPT = """You are an AI assistant for a photo management application.
You help users understand their photos and photo library.

You can answer questions about:
1. Photo metadata (date, location, camera settings, etc.)
2. Photo content (what's in the photo, who's in it, etc.)
3. Photo library statistics (how many photos, when they were taken, etc.)
4. Photo organization (albums, tags, faces, etc.)

Be helpful, concise, and accurate. If you don't know the answer, say so.
"""


class QAService:
    """Question-answering service for photos.

    This service answers questions about photos using LLM and vision models.
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
        self._asset_repository = asset_repository
        self._embedding_repository = embedding_repository
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

        # Determine what kind of question this is
        question_lower = question.lower()

        # Check for library statistics questions
        if self._is_stats_question(question_lower):
            return self._answer_stats_question(question)

        # Check for photo-specific questions
        if context and context.get("asset_id"):
            return self._answer_photo_question(question, context["asset_id"])

        # General question about the library
        return self._answer_general_question(question)

    def _is_stats_question(self, question: str) -> bool:
        """Check if the question is about library statistics."""
        stats_keywords = [
            "多少张", "多少照片", "总共", "统计",
            "how many", "total", "count", "statistics",
        ]
        return any(kw in question for kw in stats_keywords)

    def _answer_stats_question(self, question: str) -> QAResult:
        """Answer a statistics question.

        Parameters
        ----------
        question : str
            The question.

        Returns
        -------
        QAResult
            The answer.
        """
        try:
            # Get all assets
            all_assets = self._asset_repository.read_all()
            total_count = len(all_assets)

            # Count by type
            image_count = sum(1 for a in all_assets if a.get("media_type") == 0)
            video_count = sum(1 for a in all_assets if a.get("media_type") == 1)

            # Get date range
            dates = [a.get("dt", "") for a in all_assets if a.get("dt")]
            date_range = ""
            if dates:
                earliest = min(dates)[:10]
                latest = max(dates)[:10]
                date_range = f" from {earliest} to {latest}"

            answer = (
                f"Your library contains {total_count} photos and videos"
                f" ({image_count} photos, {video_count} videos){date_range}."
            )

            return QAResult(
                question=question,
                answer=answer,
                confidence=0.95,
                sources=["library_statistics"],
            )

        except Exception as e:
            _LOGGER.error("Failed to answer stats question: %s", e)
            return QAResult(
                question=question,
                answer="I couldn't retrieve the library statistics.",
                confidence=0.0,
                sources=[],
            )

    def _answer_photo_question(self, question: str, asset_id: str) -> QAResult:
        """Answer a question about a specific photo.

        Parameters
        ----------
        question : str
            The question.
        asset_id : str
            The asset ID.

        Returns
        -------
        QAResult
            The answer.
        """
        try:
            # Get asset metadata
            asset_rows = self._asset_repository.get_rows_by_ids([asset_id])
            if not asset_rows:
                return QAResult(
                    question=question,
                    answer="Photo not found.",
                    confidence=0.0,
                    sources=[],
                )

            asset = asset_rows[0]
            metadata_str = self._format_asset_metadata(asset)

            # Get tags
            tags = []
            if self._embedding_repository:
                tags = self._embedding_repository.get_tags(asset_id)
            tags_str = ", ".join([t["name"] for t in tags]) if tags else "none"

            # Get caption
            caption = ""
            if self._embedding_repository:
                caption = self._embedding_repository.get_caption(asset_id) or ""

            # Use vision service if available for image-specific questions
            if self._vision_service and self._vision_service.is_loaded():
                rel_path = asset.get("rel", "")
                abs_path = self._library_root / rel_path
                if abs_path.exists():
                    answer = self._vision_service.describe_image(abs_path, question)
                    if answer:
                        return QAResult(
                            question=question,
                            answer=answer,
                            confidence=0.8,
                            sources=["vision_model"],
                        )

            # Use LLM if available
            if self._llm_service and self._llm_service.is_available():
                prompt = (
                    f"{_PHOTO_QA_PROMPT}\n\n"
                    f"Photo metadata:\n{metadata_str}\n\n"
                    f"Tags: {tags_str}\n\n"
                    f"Caption: {caption}\n\n"
                    f"Question: {question}\n\n"
                    f"Answer:"
                )

                response = self._llm_service.complete(prompt, temperature=0.3, max_tokens=200)
                if response:
                    return QAResult(
                        question=question,
                        answer=response,
                        confidence=0.7,
                        sources=["llm", "metadata"],
                    )

            # Fallback to simple metadata-based answer
            answer = f"Here's what I know about this photo:\n{metadata_str}"
            if tags_str:
                answer += f"\nTags: {tags_str}"
            if caption:
                answer += f"\nDescription: {caption}"

            return QAResult(
                question=question,
                answer=answer,
                confidence=0.5,
                sources=["metadata"],
            )

        except Exception as e:
            _LOGGER.error("Failed to answer photo question: %s", e)
            return QAResult(
                question=question,
                answer="I couldn't retrieve information about this photo.",
                confidence=0.0,
                sources=[],
            )

    def _answer_general_question(self, question: str) -> QAResult:
        """Answer a general question about the library.

        Parameters
        ----------
        question : str
            The question.

        Returns
        -------
        QAResult
            The answer.
        """
        # Use LLM if available
        if self._llm_service and self._llm_service.is_available():
            try:
                # Get some context about the library
                all_assets = self._asset_repository.read_all()
                total_count = len(all_assets)

                # Get unique locations
                locations = set()
                for asset in all_assets:
                    loc = asset.get("location", "")
                    if loc:
                        locations.add(loc)

                # Get unique cameras
                cameras = set()
                for asset in all_assets:
                    model = asset.get("model", "")
                    if model:
                        cameras.add(model)

                context_str = (
                    f"Library contains {total_count} photos/videos.\n"
                    f"Locations: {', '.join(list(locations)[:10]) if locations else 'none'}\n"
                    f"Cameras: {', '.join(list(cameras)[:5]) if cameras else 'none'}"
                )

                prompt = (
                    f"{_PHOTO_QA_PROMPT}\n\n"
                    f"Library context:\n{context_str}\n\n"
                    f"Question: {question}\n\n"
                    f"Answer:"
                )

                response = self._llm_service.complete(prompt, temperature=0.3, max_tokens=200)
                if response:
                    return QAResult(
                        question=question,
                        answer=response,
                        confidence=0.6,
                        sources=["llm", "library_context"],
                    )

            except Exception as e:
                _LOGGER.warning("LLM QA failed: %s", e)

        return QAResult(
            question=question,
            answer="I can help you with questions about your photos. Try asking about specific photos or your library statistics.",
            confidence=0.3,
            sources=[],
        )

    def _format_asset_metadata(self, asset: dict) -> str:
        """Format asset metadata as a string.

        Parameters
        ----------
        asset : dict
            Asset metadata.

        Returns
        -------
        str
            Formatted metadata string.
        """
        parts = []

        if asset.get("rel"):
            parts.append(f"File: {asset['rel']}")
        if asset.get("dt"):
            parts.append(f"Date: {asset['dt']}")
        if asset.get("location"):
            parts.append(f"Location: {asset['location']}")
        if asset.get("model"):
            parts.append(f"Camera: {asset['model']}")
        if asset.get("w") and asset.get("h"):
            parts.append(f"Size: {asset['w']}x{asset['h']}")
        if asset.get("bytes"):
            size_mb = asset["bytes"] / (1024 * 1024)
            parts.append(f"File size: {size_mb:.1f} MB")

        return "\n".join(parts) if parts else "No metadata available"
