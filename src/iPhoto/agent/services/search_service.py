"""Semantic search service for photos."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, List, Optional, Protocol

import numpy as np

from ..models.search_result import SearchResult
from ..ports.embedding_port import EmbeddingPort

_LOGGER = logging.getLogger(__name__)

# Default number of results to return
_DEFAULT_TOP_K = 20

# Minimum similarity score to include in results
_MIN_SIMILARITY_THRESHOLD = 0.2


class AssetRepositoryProtocol(Protocol):
    """Protocol for accessing asset data."""

    def get_rows_by_ids(self, asset_ids: List[str]) -> List[dict]:
        """Get asset rows by their IDs."""
        ...


class EmbeddingRepositoryProtocol(Protocol):
    """Protocol for accessing embedding data."""

    def get_all_embeddings(self) -> List[dict]:
        """Get all stored embeddings.

        Returns
        -------
        List[dict]
            List of dicts with 'asset_id' and 'embedding' keys.
        """
        ...

    def store_embedding(self, asset_id: str, embedding: np.ndarray) -> None:
        """Store an embedding for an asset.

        Parameters
        ----------
        asset_id : str
            The asset identifier.
        embedding : np.ndarray
            The embedding vector.
        """
        ...

    def get_embedding(self, asset_id: str) -> Optional[np.ndarray]:
        """Get the embedding for an asset.

        Parameters
        ----------
        asset_id : str
            The asset identifier.

        Returns
        -------
        Optional[np.ndarray]
            The embedding vector, or None if not found.
        """
        ...


class SearchService:
    """Semantic search service for photos.

    This service provides natural language search capabilities
    using CLIP embeddings for semantic understanding.
    """

    def __init__(
        self,
        embedding_service: EmbeddingPort,
        asset_repository: AssetRepositoryProtocol,
        embedding_repository: EmbeddingRepositoryProtocol,
    ) -> None:
        """Initialize the search service.

        Parameters
        ----------
        embedding_service : EmbeddingPort
            Service for generating embeddings.
        asset_repository : AssetRepositoryProtocol
            Repository for accessing asset data.
        embedding_repository : EmbeddingRepositoryProtocol
            Repository for storing and retrieving embeddings.
        """
        self._embedding_service = embedding_service
        self._asset_repository = asset_repository
        self._embedding_repository = embedding_repository

    def search(
        self,
        query: str,
        top_k: int = _DEFAULT_TOP_K,
        threshold: float = _MIN_SIMILARITY_THRESHOLD,
    ) -> List[SearchResult]:
        """Search for photos matching a natural language query.

        Parameters
        ----------
        query : str
            Natural language search query (e.g., "sunset beach").
        top_k : int
            Maximum number of results to return.
        threshold : float
            Minimum similarity score (0.0 to 1.0).

        Returns
        -------
        List[SearchResult]
            List of matching assets, sorted by relevance.
        """
        if not query.strip():
            return []

        # Generate text embedding for the query
        query_embedding = self._embedding_service.encode_text(query)
        if query_embedding is None:
            _LOGGER.warning("Failed to generate embedding for query: %s", query)
            return []

        # Get all stored embeddings
        all_embeddings = self._embedding_repository.get_all_embeddings()
        if not all_embeddings:
            _LOGGER.info("No embeddings found. Please run embedding generation first.")
            return []

        # Compute similarities
        results: List[SearchResult] = []
        for item in all_embeddings:
            asset_id = item["asset_id"]
            stored_embedding = item["embedding"]

            if stored_embedding is None:
                continue

            # Compute cosine similarity
            similarity = self._embedding_service.compute_similarity(
                query_embedding, stored_embedding
            )

            if similarity >= threshold:
                results.append(
                    SearchResult(
                        asset_id=asset_id,
                        asset_rel="",  # Will be filled later
                        score=float(similarity),
                    )
                )

        # Sort by similarity (highest first)
        results.sort(key=lambda x: x.score, reverse=True)

        # Limit results
        results = results[:top_k]

        # Enrich with asset metadata
        if results:
            asset_ids = [r.asset_id for r in results]
            asset_rows = self._asset_repository.get_rows_by_ids(asset_ids)

            # Create a lookup map
            row_map = {row["id"]: row for row in asset_rows}

            # Update results with metadata
            for result in results:
                row = row_map.get(result.asset_id)
                if row:
                    result.asset_rel = row.get("rel", "")

        return results

    def search_by_image(
        self,
        image_path: Path,
        top_k: int = _DEFAULT_TOP_K,
        threshold: float = _MIN_SIMILARITY_THRESHOLD,
    ) -> List[SearchResult]:
        """Search for photos similar to a given image.

        Parameters
        ----------
        image_path : Path
            Path to the reference image.
        top_k : int
            Maximum number of results to return.
        threshold : float
            Minimum similarity score (0.0 to 1.0).

        Returns
        -------
        List[SearchResult]
            List of similar assets, sorted by similarity.
        """
        # Generate embedding for the reference image
        image_embedding = self._embedding_service.encode_image(image_path)
        if image_embedding is None:
            _LOGGER.warning("Failed to generate embedding for image: %s", image_path)
            return []

        # Get all stored embeddings
        all_embeddings = self._embedding_repository.get_all_embeddings()
        if not all_embeddings:
            return []

        # Compute similarities
        results: List[SearchResult] = []
        for item in all_embeddings:
            asset_id = item["asset_id"]
            stored_embedding = item["embedding"]

            if stored_embedding is None:
                continue

            similarity = self._embedding_service.compute_similarity(
                image_embedding, stored_embedding
            )

            if similarity >= threshold:
                results.append(
                    SearchResult(
                        asset_id=asset_id,
                        asset_rel="",
                        score=float(similarity),
                    )
                )

        # Sort and limit
        results.sort(key=lambda x: x.score, reverse=True)
        results = results[:top_k]

        # Enrich with metadata
        if results:
            asset_ids = [r.asset_id for r in results]
            asset_rows = self._asset_repository.get_rows_by_ids(asset_ids)
            row_map = {row["id"]: row for row in asset_rows}

            for result in results:
                row = row_map.get(result.asset_id)
                if row:
                    result.asset_rel = row.get("rel", "")

        return results

    def find_duplicates(
        self,
        threshold: float = 0.95,
    ) -> List[List[SearchResult]]:
        """Find duplicate or near-duplicate photos.

        Parameters
        ----------
        threshold : float
            Similarity threshold for considering photos as duplicates (0.0 to 1.0).

        Returns
        -------
        List[List[SearchResult]]
            Groups of duplicate photos.
        """
        all_embeddings = self._embedding_repository.get_all_embeddings()
        if not all_embeddings:
            return []

        # Build similarity groups using Union-Find
        n = len(all_embeddings)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Compare all pairs
        for i in range(n):
            for j in range(i + 1, n):
                emb_i = all_embeddings[i]["embedding"]
                emb_j = all_embeddings[j]["embedding"]

                if emb_i is None or emb_j is None:
                    continue

                similarity = self._embedding_service.compute_similarity(emb_i, emb_j)
                if similarity >= threshold:
                    union(i, j)

        # Group by connected components
        groups: dict[int, List[int]] = {}
        for i in range(n):
            root = find(i)
            if root not in groups:
                groups[root] = []
            groups[root].append(i)

        # Convert to SearchResult groups
        result_groups: List[List[SearchResult]] = []
        for group_indices in groups.values():
            if len(group_indices) < 2:
                continue

            group_results = []
            for idx in group_indices:
                item = all_embeddings[idx]
                group_results.append(
                    SearchResult(
                        asset_id=item["asset_id"],
                        asset_rel="",
                        score=1.0,
                    )
                )

            # Enrich with metadata
            asset_ids = [r.asset_id for r in group_results]
            asset_rows = self._asset_repository.get_rows_by_ids(asset_ids)
            row_map = {row["id"]: row for row in asset_rows}

            for result in group_results:
                row = row_map.get(result.asset_id)
                if row:
                    result.asset_rel = row.get("rel", "")

            result_groups.append(group_results)

        return result_groups
