"""Smart organization service for photos."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

from ..ports.embedding_port import EmbeddingPort

_LOGGER = logging.getLogger(__name__)


@dataclass
class DuplicateGroup:
    """A group of duplicate or near-duplicate photos."""

    asset_ids: List[str]
    """List of asset IDs in the group."""

    asset_rels: List[str]
    """List of relative paths."""

    similarity: float
    """Average similarity score within the group."""

    recommended_keep: Optional[str] = None
    """Asset ID recommended to keep (highest quality)."""


@dataclass
class QualityScore:
    """Quality score for a photo."""

    asset_id: str
    """Asset identifier."""

    overall: float
    """Overall quality score (0.0 to 1.0)."""

    sharpness: float
    """Sharpness score (0.0 to 1.0)."""

    exposure: float
    """Exposure quality score (0.0 to 1.0)."""

    composition: float
    """Composition score (0.0 to 1.0)."""


@dataclass
class SmartAlbum:
    """A smart album suggestion."""

    name: str
    """Suggested album name."""

    description: str
    """Album description."""

    asset_ids: List[str]
    """List of asset IDs to include."""

    album_type: str
    """Type of album (event, location, time, theme)."""


class OrganizeService:
    """Smart organization service for photos.

    This service provides features for organizing photos:
    - Duplicate detection
    - Quality assessment
    - Smart album creation
    - Best photo selection
    """

    def __init__(
        self,
        embedding_service: EmbeddingPort,
        embedding_repository: object,
        asset_repository: object,
        library_root: Path,
    ) -> None:
        """Initialize the organize service.

        Parameters
        ----------
        embedding_service : EmbeddingPort
            Service for generating embeddings.
        embedding_repository : object
            Repository for storing embeddings.
        asset_repository : object
            Repository for accessing asset data.
        library_root : Path
            Root directory of the library.
        """
        self._embedding_service = embedding_service
        self._embedding_repository = embedding_repository
        self._asset_repository = asset_repository
        self._library_root = library_root

    def find_duplicates(
        self,
        threshold: float = 0.95,
        min_group_size: int = 2,
    ) -> List[DuplicateGroup]:
        """Find duplicate or near-duplicate photos.

        Parameters
        ----------
        threshold : float
            Similarity threshold for considering photos as duplicates (0.0 to 1.0).
        min_group_size : int
            Minimum number of photos in a duplicate group.

        Returns
        -------
        List[DuplicateGroup]
            Groups of duplicate photos.
        """
        all_embeddings = self._embedding_repository.get_all_embeddings()
        if not all_embeddings:
            return []

        # Build similarity groups using Union-Find
        n = len(all_embeddings)
        parent = list(range(n))
        rank = [0] * n

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px == py:
                return
            if rank[px] < rank[py]:
                px, py = py, px
            parent[py] = px
            if rank[px] == rank[py]:
                rank[px] += 1

        # Compare all pairs (optimized with early termination)
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
        groups: dict[int, List[int]] = defaultdict(list)
        for i in range(n):
            root = find(i)
            groups[root].append(i)

        # Convert to DuplicateGroup objects
        result_groups = []
        for group_indices in groups.values():
            if len(group_indices) < min_group_size:
                continue

            asset_ids = [all_embeddings[i]["asset_id"] for i in group_indices]
            asset_rels = self._get_asset_rels(asset_ids)

            # Calculate average similarity
            similarities = []
            for i in range(len(group_indices)):
                for j in range(i + 1, len(group_indices)):
                    emb_i = all_embeddings[group_indices[i]]["embedding"]
                    emb_j = all_embeddings[group_indices[j]]["embedding"]
                    if emb_i is not None and emb_j is not None:
                        sim = self._embedding_service.compute_similarity(emb_i, emb_j)
                        similarities.append(sim)

            avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0

            result_groups.append(DuplicateGroup(
                asset_ids=asset_ids,
                asset_rels=asset_rels,
                similarity=avg_similarity,
            ))

        # Sort by group size (largest first)
        result_groups.sort(key=lambda g: len(g.asset_ids), reverse=True)

        return result_groups

    def assess_quality(self, image_path: Path) -> Optional[QualityScore]:
        """Assess the quality of a photo.

        Parameters
        ----------
        image_path : Path
            Path to the image file.

        Returns
        -------
        Optional[QualityScore]
            Quality scores, or None if assessment fails.
        """
        try:
            import cv2

            # Load image
            img = cv2.imread(str(image_path))
            if img is None:
                return None

            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Calculate sharpness (Laplacian variance)
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            sharpness = min(1.0, laplacian.var() / 500.0)

            # Calculate exposure quality
            mean_brightness = np.mean(gray)
            # Ideal brightness is around 128 (middle of 0-255)
            exposure = 1.0 - abs(mean_brightness - 128) / 128.0

            # Calculate composition (rule of thirds heuristic)
            h, w = gray.shape
            # Divide into 3x3 grid
            third_h, third_w = h // 3, w // 3
            # Check if main subject is near rule-of-thirds lines
            center_region = gray[third_h:2*third_h, third_w:2*third_w]
            edge_region = gray.copy()
            edge_region[third_h:2*third_h, third_w:2*third_w] = 0

            # Simple composition score based on contrast distribution
            center_std = np.std(center_region)
            edge_std = np.std(edge_region[edge_region > 0])
            composition = min(1.0, (center_std + edge_std) / 100.0)

            # Overall score (weighted average)
            overall = 0.4 * sharpness + 0.3 * exposure + 0.3 * composition

            return QualityScore(
                asset_id="",
                overall=overall,
                sharpness=sharpness,
                exposure=exposure,
                composition=composition,
            )

        except Exception as e:
            _LOGGER.warning("Failed to assess quality for %s: %s", image_path, e)
            return None

    def select_best_photo(self, asset_ids: List[str]) -> Optional[str]:
        """Select the best photo from a group.

        Parameters
        ----------
        asset_ids : List[str]
            List of asset IDs to choose from.

        Returns
        -------
        Optional[str]
            Asset ID of the best photo, or None if selection fails.
        """
        if not asset_ids:
            return None

        if len(asset_ids) == 1:
            return asset_ids[0]

        # Get asset paths
        asset_rels = self._get_asset_rels(asset_ids)
        if not asset_rels:
            return asset_ids[0]

        # Assess quality for each photo
        scores = []
        for asset_id, rel_path in zip(asset_ids, asset_rels):
            abs_path = self._library_root / rel_path
            if abs_path.exists():
                quality = self.assess_quality(abs_path)
                if quality:
                    scores.append((asset_id, quality.overall))
                else:
                    scores.append((asset_id, 0.0))
            else:
                scores.append((asset_id, 0.0))

        # Return the photo with highest quality score
        if scores:
            best = max(scores, key=lambda x: x[1])
            return best[0]

        return asset_ids[0]

    def create_smart_albums(
        self,
        group_by: str = "event",
    ) -> List[SmartAlbum]:
        """Create smart album suggestions.

        Parameters
        ----------
        group_by : str
            How to group photos: 'event', 'location', 'time', 'theme'.

        Returns
        -------
        List[SmartAlbum]
            List of smart album suggestions.
        """
        # Get all assets
        all_assets = self._asset_repository.read_all()
        if not all_assets:
            return []

        albums = []

        if group_by == "time":
            albums = self._group_by_time(all_assets)
        elif group_by == "location":
            albums = self._group_by_location(all_assets)
        elif group_by == "event":
            albums = self._group_by_event(all_assets)
        elif group_by == "theme":
            albums = self._group_by_theme(all_assets)

        return albums

    def _group_by_time(self, assets: List[dict]) -> List[SmartAlbum]:
        """Group photos by time periods."""
        # Group by year-month
        groups = defaultdict(list)
        for asset in assets:
            dt = asset.get("dt", "")
            if dt and len(dt) >= 7:
                year_month = dt[:7]  # YYYY-MM
                groups[year_month].append(asset["id"])

        albums = []
        for year_month, asset_ids in groups.items():
            if len(asset_ids) >= 5:  # Minimum 5 photos for an album
                albums.append(SmartAlbum(
                    name=f"Photos from {year_month}",
                    description=f"Photos taken in {year_month}",
                    asset_ids=asset_ids,
                    album_type="time",
                ))

        return albums

    def _group_by_location(self, assets: List[dict]) -> List[SmartAlbum]:
        """Group photos by location."""
        groups = defaultdict(list)
        for asset in assets:
            location = asset.get("location", "")
            if location:
                groups[location].append(asset["id"])

        albums = []
        for location, asset_ids in groups.items():
            if len(asset_ids) >= 3:
                albums.append(SmartAlbum(
                    name=f"Photos at {location}",
                    description=f"Photos taken at {location}",
                    asset_ids=asset_ids,
                    album_type="location",
                ))

        return albums

    def _group_by_event(self, assets: List[dict]) -> List[SmartAlbum]:
        """Group photos by events (clusters of photos taken close together in time)."""
        # Sort by timestamp
        sorted_assets = sorted(assets, key=lambda a: a.get("ts", 0))

        # Find clusters (photos taken within 1 hour of each other)
        clusters = []
        current_cluster = []
        last_ts = 0

        for asset in sorted_assets:
            ts = asset.get("ts", 0)
            if ts - last_ts > 3600 * 1000000:  # 1 hour in microseconds
                if current_cluster:
                    clusters.append(current_cluster)
                current_cluster = []
            current_cluster.append(asset)
            last_ts = ts

        if current_cluster:
            clusters.append(current_cluster)

        albums = []
        for i, cluster in enumerate(clusters):
            if len(cluster) >= 5:
                # Get date range for cluster
                dates = [a.get("dt", "") for a in cluster if a.get("dt")]
                if dates:
                    start_date = min(dates)[:10]
                    end_date = max(dates)[:10]
                    name = f"Event {i+1}: {start_date}"
                    if start_date != end_date:
                        name += f" to {end_date}"

                    albums.append(SmartAlbum(
                        name=name,
                        description=f"Photos from {start_date} to {end_date}",
                        asset_ids=[a["id"] for a in cluster],
                        album_type="event",
                    ))

        return albums

    def _group_by_theme(self, assets: List[dict]) -> List[SmartAlbum]:
        """Group photos by theme using tags."""
        # Get tags for all assets
        asset_ids = [a["id"] for a in assets]
        tags_by_asset = self._embedding_repository.get_tags_batch(asset_ids)

        # Group by tag
        tag_groups = defaultdict(list)
        for asset_id, tags in tags_by_asset.items():
            for tag in tags:
                tag_groups[tag["name"]].append(asset_id)

        albums = []
        for tag_name, tag_asset_ids in tag_groups.items():
            if len(tag_asset_ids) >= 3:
                albums.append(SmartAlbum(
                    name=f"{tag_name.title()} Photos",
                    description=f"Photos tagged with '{tag_name}'",
                    asset_ids=tag_asset_ids,
                    album_type="theme",
                ))

        return albums

    def _get_asset_rels(self, asset_ids: List[str]) -> List[str]:
        """Get relative paths for asset IDs."""
        if not asset_ids:
            return []

        asset_rows = self._asset_repository.get_rows_by_ids(asset_ids)
        row_map = {row["id"]: row for row in asset_rows}

        return [row_map.get(aid, {}).get("rel", "") for aid in asset_ids]
