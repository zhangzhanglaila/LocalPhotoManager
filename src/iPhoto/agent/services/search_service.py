"""Lightweight search service using metadata (Apple-style).

No large model downloads required. Uses existing metadata:
- Date/time
- Location (GPS)
- Camera model
- File name
- Album path
- People (face recognition)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Protocol

from ..models.search_result import SearchResult

_LOGGER = logging.getLogger(__name__)

# Default number of results to return
_DEFAULT_TOP_K = 50

# Chinese to English translations for common terms
_ZH_EN_TRANSLATIONS = {
    # 时间
    "去年": "last year",
    "今年": "this year",
    "前年": "year before last",
    "春天": "spring",
    "夏天": "summer",
    "秋天": "autumn",
    "冬天": "winter",
    "新年": "new year",
    "圣诞": "christmas",
    "生日": "birthday",

    # 地点
    "海边": "beach",
    "海滩": "beach",
    "山": "mountain",
    "湖": "lake",
    "河": "river",
    "公园": "park",
    "城市": "city",
    "乡村": "village",
    "家": "home",
    "公司": "office",
    "学校": "school",
    "医院": "hospital",
    "机场": "airport",
    "车站": "station",
    "餐厅": "restaurant",
    "酒店": "hotel",

    # 内容
    "日落": "sunset",
    "日出": "sunrise",
    "花": "flower",
    "树": "tree",
    "天空": "sky",
    "云": "cloud",
    "雨": "rain",
    "雪": "snow",
    "夜景": "night",
    "美食": "food",
    "咖啡": "coffee",
    "蛋糕": "cake",

    # 人物
    "家人": "family",
    "朋友": "friends",
    "孩子": "children",
    "宝宝": "baby",
    "宠物": "pet",
    "狗": "dog",
    "猫": "cat",

    # 活动
    "旅行": "travel",
    "婚礼": "wedding",
    "聚会": "party",
    "运动": "sports",
    "游泳": "swimming",
    "滑雪": "skiing",
    "音乐会": "concert",
    "毕业": "graduation",
}


class AssetRepositoryProtocol(Protocol):
    """Protocol for accessing asset data."""

    def get_rows_by_ids(self, asset_ids: List[str]) -> List[dict]:
        """Get asset rows by their IDs."""
        ...

    def read_all(self) -> List[dict]:
        """Read all assets."""
        ...


class SearchService:
    """Lightweight search service using metadata.

    This service provides search capabilities using existing metadata
    without requiring any large model downloads. Similar to Apple Photos'
    approach of using on-device metadata and lightweight classifiers.
    """

    def __init__(
        self,
        asset_repository: AssetRepositoryProtocol,
        embedding_repository: object = None,
    ) -> None:
        """Initialize the search service.

        Parameters
        ----------
        asset_repository : AssetRepositoryProtocol
            Repository for accessing asset data.
        embedding_repository : object
            Repository for face embeddings (optional).
        """
        self._asset_repository = asset_repository
        self._embedding_repository = embedding_repository

    def search(
        self,
        query: str,
        top_k: int = _DEFAULT_TOP_K,
    ) -> List[SearchResult]:
        """Search for photos matching a natural language query.

        Parameters
        ----------
        query : str
            Natural language search query.
        top_k : int
            Maximum number of results to return.

        Returns
        -------
        List[SearchResult]
            List of matching assets, sorted by relevance.
        """
        if not query.strip():
            return []

        # Parse query into search terms
        search_terms = self._parse_query(query)

        # Get all assets
        all_assets = self._asset_repository.read_all()
        if not all_assets:
            return []

        # Score each asset
        scored_assets = []
        for asset in all_assets:
            score = self._score_asset(asset, search_terms)
            if score > 0:
                scored_assets.append((asset, score))

        # Sort by score (highest first)
        scored_assets.sort(key=lambda x: x[1], reverse=True)

        # Limit results
        scored_assets = scored_assets[:top_k]

        # Convert to SearchResult
        results = []
        for asset, score in scored_assets:
            results.append(SearchResult(
                asset_id=asset.get("id", ""),
                asset_rel=asset.get("rel", ""),
                score=score,
            ))

        return results

    def _parse_query(self, query: str) -> dict:
        """Parse query into structured search terms.

        Parameters
        ----------
        query : str
            The search query.

        Returns
        -------
        dict
            Parsed search terms with categories.
        """
        query_lower = query.lower().strip()

        terms = {
            "keywords": [],
            "date": None,
            "location": None,
            "camera": None,
            "media_type": None,
            "year": None,
            "month": None,
        }

        # Translate Chinese to English
        for zh, en in _ZH_EN_TRANSLATIONS.items():
            if zh in query_lower:
                terms["keywords"].append(en)
                query_lower = query_lower.replace(zh, "")

        # Extract year (4 digits)
        year_match = re.search(r'(\d{4})', query)
        if year_match:
            year = int(year_match.group(1))
            if 2000 <= year <= 2030:
                terms["year"] = year

        # Extract month
        month_match = re.search(r'(\d{1,2})月', query)
        if month_match:
            month = int(month_match.group(1))
            if 1 <= month <= 12:
                terms["month"] = month

        # Extract date-related keywords
        date_keywords = {
            "去年": "last_year",
            "今年": "this_year",
            "前年": "year_before_last",
            "春天": "spring",
            "夏天": "summer",
            "秋天": "autumn",
            "冬天": "winter",
        }
        for keyword, date_type in date_keywords.items():
            if keyword in query:
                terms["date"] = date_type

        # Extract media type
        if any(kw in query for kw in ["视频", "video", "录像"]):
            terms["media_type"] = "video"
        elif any(kw in query for kw in ["照片", "photo", "图片", "image"]):
            terms["media_type"] = "image"

        # Extract remaining keywords
        remaining = query_lower.strip()
        if remaining:
            # Split by spaces and common separators
            words = re.findall(r'[a-zA-Z]+', remaining)
            terms["keywords"].extend(words)

        return terms

    def _score_asset(self, asset: dict, search_terms: dict) -> float:
        """Score an asset based on search terms.

        Parameters
        ----------
        asset : dict
            Asset data.
        search_terms : dict
            Parsed search terms.

        Returns
        -------
        float
            Score (0.0 to 1.0).
        """
        score = 0.0
        max_score = 0.0

        # Date matching
        if search_terms.get("year"):
            max_score += 1.0
            asset_year = self._extract_year(asset.get("dt", ""))
            if asset_year == search_terms["year"]:
                score += 1.0

        if search_terms.get("month"):
            max_score += 1.0
            asset_month = self._extract_month(asset.get("dt", ""))
            if asset_month == search_terms["month"]:
                score += 1.0

        if search_terms.get("date"):
            max_score += 1.0
            date_type = search_terms["date"]
            if date_type == "last_year":
                # Check if asset is from last year
                from datetime import datetime
                last_year = datetime.now().year - 1
                if self._extract_year(asset.get("dt", "")) == last_year:
                    score += 1.0
            elif date_type == "this_year":
                from datetime import datetime
                this_year = datetime.now().year
                if self._extract_year(asset.get("dt", "")) == this_year:
                    score += 1.0

        # Media type matching
        if search_terms.get("media_type"):
            max_score += 1.0
            is_video = asset.get("media_type") == 1
            if search_terms["media_type"] == "video" and is_video:
                score += 1.0
            elif search_terms["media_type"] == "image" and not is_video:
                score += 1.0

        # Location matching
        if search_terms.get("location"):
            max_score += 1.0
            location = asset.get("location", "").lower()
            if search_terms["location"] in location:
                score += 1.0

        # Camera matching
        if search_terms.get("camera"):
            max_score += 1.0
            camera = asset.get("model", "").lower()
            if search_terms["camera"] in camera:
                score += 1.0

        # Keyword matching (in filename, location, etc.)
        if search_terms.get("keywords"):
            max_score += len(search_terms["keywords"])
            for keyword in search_terms["keywords"]:
                # Check filename
                filename = asset.get("rel", "").lower()
                if keyword in filename:
                    score += 1.0
                    continue

                # Check location
                location = asset.get("location", "").lower()
                if keyword in location:
                    score += 1.0
                    continue

                # Check camera model
                camera = asset.get("model", "").lower()
                if keyword in camera:
                    score += 0.5
                    continue

        # Normalize score
        if max_score > 0:
            return score / max_score

        return 0.0

    def _extract_year(self, dt_str: str) -> Optional[int]:
        """Extract year from datetime string."""
        if not dt_str or len(dt_str) < 4:
            return None
        try:
            return int(dt_str[:4])
        except ValueError:
            return None

    def _extract_month(self, dt_str: str) -> Optional[int]:
        """Extract month from datetime string."""
        if not dt_str or len(dt_str) < 7:
            return None
        try:
            return int(dt_str[5:7])
        except ValueError:
            return None

    def search_by_person(self, person_id: str) -> List[SearchResult]:
        """Search for photos containing a specific person.

        Parameters
        ----------
        person_id : str
            The person ID to search for.

        Returns
        -------
        List[SearchResult]
            List of matching assets.
        """
        if not self._embedding_repository:
            return []

        try:
            # Get assets with this person's faces
            # This would need to be implemented based on the face repository
            return []
        except Exception as e:
            _LOGGER.error("Failed to search by person: %s", e)
            return []

    def search_by_location(self, location: str) -> List[SearchResult]:
        """Search for photos at a specific location.

        Parameters
        ----------
        location : str
            The location name to search for.

        Returns
        -------
        List[SearchResult]
            List of matching assets.
        """
        all_assets = self._asset_repository.read_all()
        results = []

        location_lower = location.lower()
        for asset in all_assets:
            asset_location = asset.get("location", "").lower()
            if location_lower in asset_location:
                results.append(SearchResult(
                    asset_id=asset.get("id", ""),
                    asset_rel=asset.get("rel", ""),
                    score=1.0,
                ))

        return results

    def search_by_date_range(
        self,
        start_date: str,
        end_date: str,
    ) -> List[SearchResult]:
        """Search for photos within a date range.

        Parameters
        ----------
        start_date : str
            Start date (YYYY-MM-DD format).
        end_date : str
            End date (YYYY-MM-DD format).

        Returns
        -------
        List[SearchResult]
            List of matching assets.
        """
        all_assets = self._asset_repository.read_all()
        results = []

        for asset in all_assets:
            dt = asset.get("dt", "")
            if dt and start_date <= dt[:10] <= end_date:
                results.append(SearchResult(
                    asset_id=asset.get("id", ""),
                    asset_rel=asset.get("rel", ""),
                    score=1.0,
                ))

        return results

    def search_by_camera(self, camera: str) -> List[SearchResult]:
        """Search for photos taken with a specific camera.

        Parameters
        ----------
        camera : str
            The camera model to search for.

        Returns
        -------
        List[SearchResult]
            List of matching assets.
        """
        all_assets = self._asset_repository.read_all()
        results = []

        camera_lower = camera.lower()
        for asset in all_assets:
            asset_camera = asset.get("model", "").lower()
            if camera_lower in asset_camera:
                results.append(SearchResult(
                    asset_id=asset.get("id", ""),
                    asset_rel=asset.get("rel", ""),
                    score=1.0,
                ))

        return results
