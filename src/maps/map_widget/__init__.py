"""Public package interface for the map widget components.

This module re-exports the high-level classes that external callers relied on
before the refactor, keeping backwards compatibility for imports such as
``from map_widget import LayerPlan``.
"""

from .apple_mapkit_widget import AppleMapKitWidget
from .layer import LayerPlan
from .leaflet_online_widget import LeafletOnlineMapWidget
from .map_gl_widget import MapGLWidget, MapGLWindowWidget
from .map_widget import MapWidget
from .native_osmand_widget import NativeOsmAndWidget
from .qt_location_map_widget import QtLocationMapWidget

__all__ = [
    "MapWidget",
    "AppleMapKitWidget",
    "LeafletOnlineMapWidget",
    "MapGLWidget",
    "MapGLWindowWidget",
    "NativeOsmAndWidget",
    "QtLocationMapWidget",
    "LayerPlan",
]
