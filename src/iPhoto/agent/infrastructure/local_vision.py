"""Local vision service using lightweight models."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import List, Optional

from ..ports.vision_port import ImageCaption, ImageTag, VisionPort

_LOGGER = logging.getLogger(__name__)

# Default model for image understanding
_DEFAULT_MODEL = "moondream2"


class LocalVisionService:
    """Local vision service using lightweight models.

    This service uses moondream2 or similar lightweight models
    for image captioning and understanding.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        """Initialize the local vision service.

        Parameters
        ----------
        model_name : str
            Name of the model to use.
        """
        self._model_name = model_name
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()
        self._loaded = False

    def _ensure_loaded(self) -> bool:
        """Load the vision model if not already loaded.

        Returns
        -------
        bool
            True if the model is loaded successfully.
        """
        if self._loaded:
            return True

        with self._lock:
            if self._loaded:
                return True

            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer

                _LOGGER.info("Loading vision model: %s", self._model_name)

                # Load model and tokenizer
                self._tokenizer = AutoTokenizer.from_pretrained(
                    f"vikhyatk/{self._model_name}",
                    trust_remote_code=True,
                )
                self._model = AutoModelForCausalLM.from_pretrained(
                    f"vikhyatk/{self._model_name}",
                    trust_remote_code=True,
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                    device_map="auto" if torch.cuda.is_available() else None,
                )

                self._loaded = True
                _LOGGER.info("Vision model loaded successfully")
                return True

            except ImportError as e:
                _LOGGER.error("Missing dependencies for vision model: %s", e)
                return False
            except Exception as e:
                _LOGGER.error("Failed to load vision model: %s", e)
                return False

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
        if not self._ensure_loaded():
            return None

        try:
            from PIL import Image

            # Load image
            image = Image.open(image_path).convert("RGB")

            # Generate caption
            caption = self._model.caption(image, length=50)

            if caption:
                return ImageCaption(
                    text=caption,
                    confidence=0.8,
                    language="en",
                )
            return None

        except Exception as e:
            _LOGGER.warning("Failed to caption image %s: %s", image_path, e)
            return None

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
            Optional list of candidate tags to check.

        Returns
        -------
        List[ImageTag]
            List of tags with confidence scores.
        """
        if not self._ensure_loaded():
            return []

        try:
            from PIL import Image

            # Load image
            image = Image.open(image_path).convert("RGB")

            # Generate caption and extract tags
            caption = self._model.caption(image, length=100)
            if not caption:
                return []

            # Simple tag extraction from caption
            tags = []
            tag_candidates = candidate_tags or [
                "beach", "mountain", "city", "forest", "sunset", "sunrise",
                "dog", "cat", "bird", "car", "building", "person",
                "food", "flower", "sky", "water", "snow", "rain",
                "indoor", "outdoor", "night", "day", "summer", "winter",
            ]

            caption_lower = caption.lower()
            for tag in tag_candidates:
                if tag.lower() in caption_lower:
                    tags.append(ImageTag(
                        name=tag,
                        confidence=0.7,
                        category="scene" if tag in ["beach", "mountain", "city", "forest"] else "object",
                    ))

            return tags

        except Exception as e:
            _LOGGER.warning("Failed to tag image %s: %s", image_path, e)
            return []

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
        if not self._ensure_loaded():
            return None

        try:
            from PIL import Image

            # Load image
            image = Image.open(image_path).convert("RGB")

            # Answer question
            answer = self._model.query(image, question)

            return answer if answer else None

        except Exception as e:
            _LOGGER.warning("Failed to describe image %s: %s", image_path, e)
            return None

    def is_loaded(self) -> bool:
        """Check if the vision model is loaded and ready."""
        return self._loaded


class CLIPVisionService:
    """CLIP-based vision service for zero-shot classification.

    This service uses CLIP for tag generation and image understanding
    without requiring a separate captioning model.
    """

    def __init__(self, embedding_service: object = None) -> None:
        """Initialize the CLIP vision service.

        Parameters
        ----------
        embedding_service : object
            Optional CLIP embedding service to reuse.
        """
        self._embedding_service = embedding_service
        self._loaded = False

    def _ensure_loaded(self) -> bool:
        """Ensure the CLIP service is available."""
        if self._loaded:
            return True

        if self._embedding_service and self._embedding_service.is_loaded():
            self._loaded = True
            return True

        return False

    def tag_image(
        self,
        image_path: Path,
        candidate_tags: Optional[List[str]] = None,
    ) -> List[ImageTag]:
        """Generate tags for an image using CLIP zero-shot classification.

        Parameters
        ----------
        image_path : Path
            Path to the image file.
        candidate_tags : Optional[List[str]]
            List of candidate tags to check.

        Returns
        -------
        List[ImageTag]
            List of tags with confidence scores.
        """
        if not self._ensure_loaded():
            return []

        if not candidate_tags:
            candidate_tags = [
                "beach", "mountain", "city", "forest", "sunset", "sunrise",
                "dog", "cat", "bird", "car", "building", "person",
                "food", "flower", "sky", "water", "snow", "rain",
                "indoor", "outdoor", "night", "day", "summer", "winter",
                "portrait", "landscape", "group photo", "selfie",
                "concert", "wedding", "birthday", "travel",
            ]

        try:
            import numpy as np

            # Get image embedding
            image_embedding = self._embedding_service.encode_image(image_path)
            if image_embedding is None:
                return []

            # Compute similarity with each candidate tag
            tags = []
            for tag in candidate_tags:
                tag_embedding = self._embedding_service.encode_text(f"a photo of {tag}")
                if tag_embedding is None:
                    continue

                similarity = float(np.dot(image_embedding, tag_embedding))

                # Only include if similarity is above threshold
                if similarity > 0.25:
                    # Determine category
                    if tag in ["beach", "mountain", "city", "forest", "indoor", "outdoor"]:
                        category = "scene"
                    elif tag in ["sunset", "sunrise", "night", "day", "summer", "winter"]:
                        category = "time"
                    elif tag in ["portrait", "landscape", "group photo", "selfie"]:
                        category = "composition"
                    else:
                        category = "object"

                    tags.append(ImageTag(
                        name=tag,
                        confidence=similarity,
                        category=category,
                    ))

            # Sort by confidence and return top tags
            tags.sort(key=lambda t: t.confidence, reverse=True)
            return tags[:10]

        except Exception as e:
            _LOGGER.warning("Failed to tag image %s: %s", image_path, e)
            return []

    def is_loaded(self) -> bool:
        """Check if the service is loaded."""
        return self._loaded
