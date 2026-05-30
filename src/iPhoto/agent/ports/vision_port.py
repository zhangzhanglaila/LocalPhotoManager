"""Port protocol for vision/image understanding services."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol


@dataclass
class ImageCaption:
    """Caption or description for an image."""

    text: str
    """The generated caption text."""

    confidence: float = 1.0
    """Confidence score (0.0 to 1.0)."""

    language: str = "en"
    """Language of the caption."""


@dataclass
class ImageTag:
    """A tag/label for an image."""

    name: str
    """Tag name (e.g., 'beach', 'sunset', 'dog')."""

    confidence: float = 1.0
    """Confidence score (0.0 to 1.0)."""

    category: str = "general"
    """Tag category (e.g., 'scene', 'object', 'activity')."""


class VisionPort(Protocol):
    """Protocol for image understanding services.

    Implementations should handle image captioning, tagging,
    and other vision tasks.
    """

    @abstractmethod
    def caption_image(self, image_path: Path) -> Optional[ImageCaption]:
        """Generate a caption for an image.

        Parameters
        ----------
        image_path : Path
            Path to the image file.

        Returns
        -------
        Optional[ImageCaption]
            Generated caption, or None if captioning fails.
        """
        ...

    @abstractmethod
    def tag_image(
        self,
        image_path: Path,
        candidate_tags: Optional[List[str]] = None,
    ) -> List[ImageTag]:
        """Generate tags for an image.

        Parameters
        ----------
        image_path : Path
            Path to the image file.
        candidate_tags : Optional[List[str]]
            Optional list of candidate tags to check. If None,
            the service should generate tags freely.

        Returns
        -------
        List[ImageTag]
            List of tags with confidence scores.
        """
        ...

    @abstractmethod
    def describe_image(self, image_path: Path, question: str) -> Optional[str]:
        """Answer a question about an image.

        Parameters
        ----------
        image_path : Path
            Path to the image file.
        question : str
            Question about the image.

        Returns
        -------
        Optional[str]
            Answer to the question, or None if it cannot be answered.
        """
        ...

    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if the vision model is loaded and ready."""
        ...
