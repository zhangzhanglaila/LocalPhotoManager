"""Port protocol for embedding generation services."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import List, Optional, Protocol

import numpy as np


class EmbeddingPort(Protocol):
    """Protocol for generating and managing embeddings.

    Implementations should handle model loading, embedding generation
    for images and text, and similarity computation.
    """

    @abstractmethod
    def encode_image(self, image_path: Path) -> Optional[np.ndarray]:
        """Generate embedding for a single image.

        Parameters
        ----------
        image_path : Path
            Path to the image file.

        Returns
        -------
        Optional[np.ndarray]
            Normalized embedding vector, or None if encoding fails.
        """
        ...

    @abstractmethod
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
        ...

    @abstractmethod
    def encode_text(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for text query.

        Parameters
        ----------
        text : str
            Text to encode.

        Returns
        -------
        Optional[np.ndarray]
            Normalized embedding vector, or None if encoding fails.
        """
        ...

    @abstractmethod
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
        ...

    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if the embedding model is loaded and ready."""
        ...

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """Return the dimension of the embedding vectors."""
        ...
