"""Role definitions shared by the album models."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Dict

from PySide6.QtCore import Qt


class _DictHolder:
    """Wrap a dict so PySide6 shiboken won't auto-convert it to C++."""

    __slots__ = ("_data",)

    def __init__(self, data: dict) -> None:
        self._data = data

    @property
    def data(self) -> dict:
        return self._data

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __contains__(self, key):
        return key in self._data

    def __repr__(self):
        return f"_DictHolder({self._data!r})"


def unwrap_dict(value: Any) -> dict | None:
    """Extract a dict from a _DictHolder, or return value if already a dict."""
    if isinstance(value, _DictHolder):
        return value.data
    if isinstance(value, dict):
        return value
    return None


class Roles(IntEnum):
    """Custom roles exposed to QML or widgets."""

    REL = Qt.UserRole + 1
    ABS = Qt.UserRole + 2
    ASSET_ID = Qt.UserRole + 3
    IS_IMAGE = Qt.UserRole + 4
    IS_VIDEO = Qt.UserRole + 5
    IS_LIVE = Qt.UserRole + 6
    LIVE_GROUP_ID = Qt.UserRole + 7
    SIZE = Qt.UserRole + 8
    DT = Qt.UserRole + 9
    FEATURED = Qt.UserRole + 10
    LIVE_MOTION_REL = Qt.UserRole + 11
    LIVE_MOTION_ABS = Qt.UserRole + 12
    IS_CURRENT = Qt.UserRole + 13
    IS_SPACER = Qt.UserRole + 14
    LOCATION = Qt.UserRole + 15
    INFO = Qt.UserRole + 16
    IS_PANO = Qt.UserRole + 17
    COMPOSITE = Qt.UserRole + 18
    DT_SORT = Qt.UserRole + 19
    MICRO_THUMBNAIL = Qt.UserRole + 20


def role_names(base: Dict[int, bytes] | None = None) -> Dict[int, bytes]:
    """Return a mapping of Qt role numbers to byte names."""

    mapping: Dict[int, bytes] = {} if base is None else dict(base)
    mapping.update(
        {
            Roles.REL: b"rel",
            Roles.ABS: b"abs",
            Roles.ASSET_ID: b"assetId",
            Roles.IS_IMAGE: b"isImage",
            Roles.IS_VIDEO: b"isVideo",
            Roles.IS_LIVE: b"isLive",
            Roles.LIVE_GROUP_ID: b"liveGroupId",
            Roles.LIVE_MOTION_REL: b"liveMotion",
            Roles.LIVE_MOTION_ABS: b"liveMotionAbs",
            Roles.SIZE: b"size",
            Roles.DT: b"dt",
            Roles.FEATURED: b"featured",
            Roles.IS_CURRENT: b"isCurrent",
            Roles.IS_SPACER: b"isSpacer",
            Roles.LOCATION: b"location",
            Roles.INFO: b"info",
            Roles.IS_PANO: b"isPano",
            Roles.COMPOSITE: b"composite",
            Roles.DT_SORT: b"dtSort",
            Roles.MICRO_THUMBNAIL: b"microThumbnail",
        }
    )
    return mapping
