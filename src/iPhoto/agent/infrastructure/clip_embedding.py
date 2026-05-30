"""CLIP embedding service using ONNX Runtime."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import List, Optional

import numpy as np

_LOGGER = logging.getLogger(__name__)

# CLIP model configuration
_DEFAULT_MODEL_NAME = "clip-vit-base-patch32"
_EMBEDDING_DIMENSION = 512
_IMAGE_SIZE = 224


class CLIPEmbeddingService:
    """CLIP embedding service using ONNX Runtime.

    This service loads a CLIP model in ONNX format and provides
    methods for encoding images and text into embeddings.
    """

    def __init__(
        self,
        model_dir: Path,
        model_name: str = _DEFAULT_MODEL_NAME,
    ) -> None:
        """Initialize the CLIP embedding service.

        Parameters
        ----------
        model_dir : Path
            Directory containing the ONNX model files.
        model_name : str
            Name of the CLIP model to load.
        """
        self._model_dir = Path(model_dir)
        self._model_name = model_name
        self._image_session = None
        self._text_session = None
        self._processor = None
        self._lock = threading.Lock()
        self._loaded = False

    def _ensure_loaded(self) -> bool:
        """Load the CLIP model if not already loaded.

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
                import onnxruntime as ort
                from transformers import CLIPImageProcessor, CLIPTokenizerFast

                # Check if model files exist
                image_model_path = self._model_dir / self._model_name / "image_encoder.onnx"
                text_model_path = self._model_dir / self._model_name / "text_encoder.onnx"

                if not image_model_path.exists() or not text_model_path.exists():
                    _LOGGER.warning(
                        "CLIP model files not found at %s. "
                        "Please download the model first.",
                        self._model_dir / self._model_name,
                    )
                    return False

                # Create ONNX Runtime sessions
                providers = self._get_providers()
                self._image_session = ort.InferenceSession(
                    str(image_model_path),
                    providers=providers,
                )
                self._text_session = ort.InferenceSession(
                    str(text_model_path),
                    providers=providers,
                )

                # Load processor and tokenizer
                self._processor = CLIPImageProcessor.from_pretrained(
                    str(self._model_dir / self._model_name)
                )
                self._tokenizer = CLIPTokenizerFast.from_pretrained(
                    str(self._model_dir / self._model_name)
                )

                self._loaded = True
                _LOGGER.info("CLIP model loaded successfully from %s", self._model_dir)
                return True

            except ImportError as e:
                _LOGGER.error("Missing dependencies for CLIP: %s", e)
                return False
            except Exception as e:
                _LOGGER.error("Failed to load CLIP model: %s", e)
                return False

    def _get_providers(self) -> List[str]:
        """Get available ONNX Runtime providers.

        Returns
        -------
        List[str]
            List of available providers (CUDA first, then CPU).
        """
        import onnxruntime as ort

        available = ort.get_available_providers()
        providers = []

        if "CUDAExecutionProvider" in available:
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")

        return providers

    def encode_image(self, image_path: Path) -> Optional[np.ndarray]:
        """Generate embedding for a single image.

        Parameters
        ----------
        image_path : Path
            Path to the image file.

        Returns
        -------
        Optional[np.ndarray]
            Normalized embedding vector (512-dim), or None if encoding fails.
        """
        if not self._ensure_loaded():
            return None

        try:
            from PIL import Image

            # Load and preprocess image
            image = Image.open(image_path).convert("RGB")
            inputs = self._processor(images=image, return_tensors="np")
            pixel_values = inputs["pixel_values"]

            # Run inference
            outputs = self._image_session.run(None, {"pixel_values": pixel_values})
            embedding = outputs[0][0]  # Shape: (512,)

            # Normalize
            embedding = embedding / np.linalg.norm(embedding)
            return embedding.astype(np.float32)

        except Exception as e:
            _LOGGER.warning("Failed to encode image %s: %s", image_path, e)
            return None

    def encode_images(self, image_paths: List[Path]) -> List[Optional[np.ndarray]]:
        """Generate embeddings for multiple images (batch processing).

        Parameters
        ----------
        image_paths : List[Path]
            List of paths to image files.

        Returns
        -------
        List[Optional[np.ndarray]]
            List of normalized embedding vectors. None for failed encodings.
        """
        if not self._ensure_loaded():
            return [None] * len(image_paths)

        results: List[Optional[np.ndarray]] = []
        for path in image_paths:
            results.append(self.encode_image(path))
        return results

    def encode_text(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for text query.

        Parameters
        ----------
        text : str
            Text to encode.

        Returns
        -------
        Optional[np.ndarray]
            Normalized embedding vector (512-dim), or None if encoding fails.
        """
        if not self._ensure_loaded():
            return None

        try:
            # Tokenize text
            inputs = self._tokenizer(
                text,
                padding=True,
                truncation=True,
                max_length=77,
                return_tensors="np",
            )

            # Run inference
            outputs = self._text_session.run(
                None,
                {
                    "input_ids": inputs["input_ids"],
                    "attention_mask": inputs["attention_mask"],
                },
            )
            embedding = outputs[0][0]  # Shape: (512,)

            # Normalize
            embedding = embedding / np.linalg.norm(embedding)
            return embedding.astype(np.float32)

        except Exception as e:
            _LOGGER.warning("Failed to encode text '%s': %s", text, e)
            return None

    def compute_similarity(
        self, embedding1: np.ndarray, embedding2: np.ndarray
    ) -> float:
        """Compute cosine similarity between two embeddings.

        Parameters
        ----------
        embedding1 : np.ndarray
            First embedding vector.
        embedding2 : np.ndarray
            Second embedding vector.

        Returns
        -------
        float
            Cosine similarity score in [-1, 1].
        """
        return float(np.dot(embedding1, embedding2))

    def is_loaded(self) -> bool:
        """Check if the embedding model is loaded and ready."""
        return self._loaded

    def get_embedding_dimension(self) -> int:
        """Return the dimension of the embedding vectors."""
        return _EMBEDDING_DIMENSION
