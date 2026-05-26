"""Live Photo pairing logic."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from dateutil import parser

from ..config import LIVE_DURATION_PREFERRED, PAIR_TIME_DELTA_SEC
from ..domain.models.core import LiveGroup

_logger = logging.getLogger(__name__)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parser.isoparse(value)
    except (ValueError, TypeError):
        return None


_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".heif",
    ".heifs",
    ".heicf",
}

def _is_photo(row: Dict[str, object]) -> bool:
    mime = row.get("mime")
    if isinstance(mime, str) and mime.lower().startswith("image/"):
        return True
    rel = row.get("rel")
    if isinstance(rel, str):
        return Path(rel).suffix.lower() in _IMAGE_EXTENSIONS
    return False


def _is_video(row: Dict[str, object]) -> bool:
    """Return True if the row represents a Live Photo motion component."""

    # If the asset has an explicit Content Identifier, it is definitely part of
    # a Live Photo pair regardless of the container format (e.g. MP4).
    # We must explicitly exclude the still image component (which shares the
    # same identifier) to avoid ambiguity if the caller checks predicates in
    # isolation or in a different order.
    if row.get("content_id") and not _is_photo(row):
        return True

    # Restrict Live Photo pairing to QuickTime movie sources. Generic videos like
    # MP4 clips should remain visible in the main asset list instead of being
    # paired and hidden behind a still image.
    mime = row.get("mime")
    if isinstance(mime, str) and mime.lower() == "video/quicktime":
        return True

    rel = row.get("rel")
    if isinstance(rel, str):
        return Path(rel).suffix.lower() in {".mov", ".qt"}

    return False


def _normalise_content_id(value: object) -> str | None:
    """Return a stable comparison key for Live Photo content identifiers."""

    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed.casefold()


def pair_live(index_rows: List[Dict[str, object]]) -> List[LiveGroup]:
    """Pair still and motion assets into :class:`LiveGroup` objects."""

    photos: Dict[str, Dict[str, object]] = {}
    videos: Dict[str, Dict[str, object]] = {}
    unclassified = 0
    for row in index_rows:
        if _is_photo(row):
            photos[row["rel"]] = row
        elif _is_video(row):
            videos[row["rel"]] = row
        else:
            unclassified += 1

    photos_with_cid = sum(1 for r in photos.values() if _normalise_content_id(r.get("content_id")))
    videos_with_cid = sum(1 for r in videos.values() if _normalise_content_id(r.get("content_id")))
    _logger.info(
        "pair_live: %d rows → %d photos (%d with cid), %d videos (%d with cid), %d unclassified",
        len(index_rows), len(photos), photos_with_cid,
        len(videos), videos_with_cid, unclassified,
    )

    matched: Dict[str, LiveGroup] = {}
    used_videos: set[str] = set()

    # Pre-build lookup indices to avoid O(photos × videos) scans.
    video_by_cid: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    videos_by_stem: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    videos_by_stem_cf: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    videos_by_folder: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for video in videos.values():
        cid = _normalise_content_id(video.get("content_id"))
        if cid:
            video_by_cid[cid].append(video)
        vpath = Path(video["rel"])
        videos_by_stem[vpath.stem].append(video)
        videos_by_stem_cf[vpath.stem.casefold()].append(video)
        videos_by_folder[str(vpath.parent)].append(video)

    # 1) strong match by content_id
    for photo in photos.values():
        cid = _normalise_content_id(photo.get("content_id"))
        if not cid or cid not in video_by_cid:
            continue
        candidates = [v for v in video_by_cid[cid] if v["rel"] not in used_videos]
        chosen = _select_best_video(candidates)
        if chosen:
            content_id = chosen.get("content_id") or photo.get("content_id")
            matched[photo["rel"]] = LiveGroup(
                id=f"live_{hash((photo['rel'], chosen['rel'])) & 0xFFFFFF:x}",
                still=photo["rel"],
                motion=chosen["rel"],
                content_id=content_id if isinstance(content_id, str) else None,
                still_image_time=chosen.get("still_image_time"),
                confidence=1.0,
            )
            used_videos.add(chosen["rel"])

    # 2) medium match by same stem + time delta
    for photo in photos.values():
        if photo["rel"] in matched:
            continue
        stem = Path(photo["rel"]).stem
        candidates = videos_by_stem.get(stem, [])
        chosen = _match_by_time(photo, candidates, used_videos)
        if chosen:
            used_videos.add(chosen["rel"])
            matched[photo["rel"]] = _build_group(photo, chosen, confidence=0.7)

    # 2b) same-stem match without time delta — iPhone Live Photos always
    #     share the same filename stem (e.g. IMG_1234.HEIC + IMG_1234.MOV).
    for photo in photos.values():
        if photo["rel"] in matched:
            continue
        stem = Path(photo["rel"]).stem.casefold()
        candidates = [
            v for v in videos_by_stem_cf.get(stem, [])
            if v["rel"] not in used_videos
        ]
        if len(candidates) == 1:
            chosen = candidates[0]
            used_videos.add(chosen["rel"])
            matched[photo["rel"]] = _build_group(photo, chosen, confidence=0.6)

    # 3) weak match by directory proximity
    for photo in photos.values():
        if photo["rel"] in matched:
            continue
        folder = str(Path(photo["rel"]).parent)
        candidates = videos_by_folder.get(folder, [])
        chosen = _match_by_time(photo, candidates, used_videos)
        if chosen:
            used_videos.add(chosen["rel"])
            matched[photo["rel"]] = _build_group(photo, chosen, confidence=0.5)

    _logger.info("pair_live: matched %d Live Photo pairs", len(matched))
    return list(matched.values())


def _match_by_time(
    photo: Dict[str, object],
    candidates: Iterable[Dict[str, object]],
    used_videos: set[str],
) -> Dict[str, object] | None:
    photo_dt = _parse_dt(photo.get("dt"))
    best: Tuple[float, Dict[str, object]] | None = None
    for candidate in candidates:
        if candidate["rel"] in used_videos:
            continue
        video_dt = _parse_dt(candidate.get("dt"))
        if not photo_dt or not video_dt:
            continue
        delta = abs((photo_dt - video_dt).total_seconds())
        if delta > PAIR_TIME_DELTA_SEC:
            continue
        if best is None or delta < best[0]:
            best = (delta, candidate)
    return best[1] if best else None


def _select_best_video(candidates: Iterable[Dict[str, object]]) -> Dict[str, object] | None:
    best: Dict[str, object] | None = None
    preferred_min, preferred_max = LIVE_DURATION_PREFERRED
    for candidate in candidates:
        dur = candidate.get("dur")
        still_time = candidate.get("still_image_time")
        if best is None:
            best = candidate
            continue
        best_dur = best.get("dur")
        if dur is not None and best_dur is not None:
            current_score = _duration_score(dur, preferred_min, preferred_max)
            best_score = _duration_score(best_dur, preferred_min, preferred_max)
            if current_score > best_score:
                best = candidate
                continue
            elif current_score < best_score:
                continue
        # Prefer video with still_image_time over one without
        best_time = best.get("still_image_time")
        if still_time is not None and best_time is None:
            best = candidate
        elif still_time is not None and best_time is not None:
            # Prefer valid non-negative still_image_time,
            # then prefer smaller values.
            if still_time >= 0 and (best_time < 0 or still_time < best_time):
                best = candidate
    return best


def _duration_score(duration: float, preferred_min: float, preferred_max: float) -> float:
    if duration < preferred_min:
        return -preferred_min + duration
    if duration > preferred_max:
        return -duration
    midpoint = (preferred_min + preferred_max) / 2
    return preferred_max - abs(midpoint - duration)


def _build_group(photo: Dict[str, object], video: Dict[str, object], confidence: float) -> LiveGroup:
    return LiveGroup(
        id=f"live_{hash((photo['rel'], video['rel'])) & 0xFFFFFF:x}",
        still=photo["rel"],
        motion=video["rel"],
        content_id=video.get("content_id") or photo.get("content_id"),
        still_image_time=video.get("still_image_time"),
        confidence=confidence,
    )
