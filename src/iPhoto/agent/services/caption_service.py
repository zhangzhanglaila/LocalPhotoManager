"""Caption service for generating image descriptions and tags."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from ..ports.vision_port import ImageCaption, ImageTag, VisionPort

_LOGGER = logging.getLogger(__name__)


class CaptionService:
    """Service for generating image captions and tags.

    This service coordinates between the vision service and
    the storage layer to generate and persist captions/tags.
    """

    def __init__(
        self,
        vision_service: VisionPort,
        metadata_repository: object,
    ) -> None:
        """Initialize the caption service.

        Parameters
        ----------
        vision_service : VisionPort
            Service for image understanding.
        metadata_repository : object
            Repository for storing captions and tags.
        """
        self._vision_service = vision_service
        self._metadata_repository = metadata_repository

    def generate_caption(self, image_path: Path) -> Optional[ImageCaption]:
        """Generate a caption for an image.

        Parameters
        ----------
        image_path : Path
            Path to the image file.

        Returns
        -------
        Optional[ImageCaption]
            Generated caption, or None if generation fails.
        """
        return self._vision_service.caption_image(image_path)

    def generate_tags(
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
            Optional list of candidate tags to check.

        Returns
        -------
        List[ImageTag]
            List of generated tags.
        """
        return self._vision_service.tag_image(image_path, candidate_tags)

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
            Answer to the question.
        """
        return self._vision_service.describe_image(image_path, question)

    def generate_metadata(
        self,
        image_path: Path,
        include_caption: bool = True,
        include_tags: bool = True,
    ) -> dict:
        """Generate all metadata for an image.

        Parameters
        ----------
        image_path : Path
            Path to the image file.
        include_caption : bool
            Whether to generate a caption.
        include_tags : bool
            Whether to generate tags.

        Returns
        -------
        dict
            Dictionary with 'caption' and 'tags' keys.
        """
        result = {}

        if include_caption:
            caption = self.generate_caption(image_path)
            if caption:
                result["caption"] = caption.text

        if include_tags:
            tags = self.generate_tags(image_path)
            if tags:
                result["tags"] = [
                    {"name": t.name, "confidence": t.confidence, "category": t.category}
                    for t in tags
                ]

        return result
