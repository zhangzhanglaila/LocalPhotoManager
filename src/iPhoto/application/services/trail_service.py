"""Trail building service for photo timeline visualization."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List, Optional

from ...gui.ui.models.trail_models import TrailData, TrailPoint, TrailSegment

if TYPE_CHECKING:
    from ...library.geo_aggregator import GeotaggedAsset

_LOGGER = logging.getLogger(__name__)

# Time-based color gradient: early → middle → late
# Warm orange → sky blue → deep purple (high contrast against map backgrounds)
_EARLY_COLOR = (255, 120, 44)    # #FF782C warm orange
_MID_COLOR = (35, 136, 255)      # #2388FF sky blue
_LATE_COLOR = (153, 51, 204)     # #9933CC deep purple


def _interpolate_color(
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    """Linearly interpolate between two RGB colors."""
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _segment_color(
    segment_index: int,
    total_segments: int,
) -> tuple[int, int, int]:
    """Return a color for a segment based on its time position.

    Early segments → warm orange, middle → sky blue, late → deep purple.
    """
    if total_segments <= 1:
        return _MID_COLOR
    t = segment_index / (total_segments - 1)
    if t < 0.5:
        return _interpolate_color(_EARLY_COLOR, _MID_COLOR, t * 2)
    else:
        return _interpolate_color(_MID_COLOR, _LATE_COLOR, (t - 0.5) * 2)


class TrailService:
    """Builds trail data from geotagged photos for map visualization."""

    def build_trail(
        self,
        geotagged_assets: List["GeotaggedAsset"],
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        granularity: str = "day",
    ) -> TrailData:
        """Build trail data from geotagged photos.

        Parameters
        ----------
        geotagged_assets : list[GeotaggedAsset]
            All geotagged photos in the library.
        date_from : datetime, optional
            Start date filter (None = earliest).
        date_to : datetime, optional
            End date filter (None = latest).
        granularity : str
            Grouping granularity: "day", "week", or "month".

        Returns
        -------
        TrailData
            Trail segments ready for rendering.
        """
        if not geotagged_assets:
            return TrailData()

        # Convert epoch timestamps to datetime and filter out assets
        # that have no valid timestamp.
        # Prefer ``still_image_time`` (Live Photo hero-frame time), falling
        # back to the generic ``timestamp`` field (file mtime / EXIF date).
        def _ts(a):
            if a.still_image_time is not None:
                return datetime.fromtimestamp(a.still_image_time)
            if a.timestamp is not None:
                return datetime.fromtimestamp(a.timestamp)
            return None

        filtered = [(a, _ts(a)) for a in geotagged_assets]
        filtered = [(a, ts) for a, ts in filtered if ts is not None]

        if date_from is not None:
            filtered = [(a, ts) for a, ts in filtered if ts >= date_from]
        if date_to is not None:
            filtered = [(a, ts) for a, ts in filtered if ts <= date_to]

        if not filtered:
            return TrailData()

        # Sort by timestamp
        filtered.sort(key=lambda pair: pair[1])

        # Convert to TrailPoint
        points = [
            TrailPoint(
                asset_id=a.asset_id,
                asset_rel=a.album_relative,
                latitude=a.latitude,
                longitude=a.longitude,
                timestamp=ts,
            )
            for a, ts in filtered
        ]

        # Group by granularity, splitting on gaps > 24h
        segments = self._group_points(points, granularity)
        total = len(segments)

        # Assign time-gradient colors to each segment
        for i, seg in enumerate(segments):
            seg.color = _segment_color(i, total)
            # Long trails (>5 points) get thicker line
            seg.line_width = 3 if len(seg.points) > 5 else 2

        return TrailData(
            segments=segments,
            total_photos=len(points),
            start_date=points[0].timestamp if points else None,
            end_date=points[-1].timestamp if points else None,
        )

    def _group_points(
        self, points: List[TrailPoint], granularity: str
    ) -> List[TrailSegment]:
        """Group points into segments by time granularity.

        Points are grouped by day/week/month. If there's a gap > 24 hours
        within a group, it's split into separate segments.
        """
        if not points:
            return []

        # Group by time key
        groups: dict[str, list[TrailPoint]] = defaultdict(list)
        for p in points:
            key = self._time_key(p.timestamp, granularity)
            groups[key].append(p)

        # Build segments, splitting on gaps
        segments: List[TrailSegment] = []

        for key in sorted(groups.keys()):
            group = groups[key]
            # Split on gaps > 24h
            sub_groups: list[list[TrailPoint]] = [[group[0]]]
            for prev, curr in zip(group, group[1:]):
                gap = (curr.timestamp - prev.timestamp).total_seconds()
                if gap > 86400:  # 24 hours
                    sub_groups.append([curr])
                else:
                    sub_groups[-1].append(curr)

            for sg in sub_groups:
                if not sg:
                    continue
                segments.append(TrailSegment(
                    points=sg,
                    start_time=sg[0].timestamp,
                    end_time=sg[-1].timestamp,
                ))

        return segments

    @staticmethod
    def _time_key(dt: datetime, granularity: str) -> str:
        """Generate a grouping key for the given datetime."""
        if granularity == "week":
            iso = dt.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        elif granularity == "month":
            return dt.strftime("%Y-%m")
        else:  # day
            return dt.strftime("%Y-%m-%d")
