"""Person-based map filtering service."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Set

if TYPE_CHECKING:
    from ...library.geo_aggregator import GeotaggedAsset
    from ...people.service import PeopleService

_LOGGER = logging.getLogger(__name__)


class PersonLocation:
    """A location where a person appears in photos."""

    __slots__ = ("location_name", "photo_count", "latitude", "longitude", "date_range")

    def __init__(
        self,
        location_name: str,
        photo_count: int,
        latitude: float,
        longitude: float,
        date_range: tuple[datetime, datetime],
    ) -> None:
        self.location_name = location_name
        self.photo_count = photo_count
        self.latitude = latitude
        self.longitude = longitude
        self.date_range = date_range


class PersonMapSummary:
    """Summary of a person's photo locations."""

    __slots__ = ("person_id", "total_photos", "unique_locations", "locations")

    def __init__(
        self,
        person_id: str,
        total_photos: int,
        unique_locations: int,
        locations: List[PersonLocation],
    ) -> None:
        self.person_id = person_id
        self.total_photos = total_photos
        self.unique_locations = unique_locations
        self.locations = locations


class PersonMapFilter:
    """Filters geotagged photos by person for map display."""

    def __init__(self, people_service: "PeopleService") -> None:
        self._people_service = people_service
        self._all_geotagged: List[GeotaggedAsset] = []
        self._active_person_id: Optional[str] = None
        # Cache: person_id -> set of asset_ids
        self._person_asset_cache: dict[str, Set[str]] = {}

    def set_all_geotagged(self, assets: List["GeotaggedAsset"]) -> None:
        """Set the full list of geotagged assets."""
        self._all_geotagged = list(assets)

    @property
    def active_person_id(self) -> Optional[str]:
        return self._active_person_id

    def filter_by_person(
        self, person_id: Optional[str]
    ) -> List["GeotaggedAsset"]:
        """Filter geotagged assets by person.

        Parameters
        ----------
        person_id : str or None
            Person ID to filter by, or None to show all.

        Returns
        -------
        list[GeotaggedAsset]
            Filtered list of geotagged assets.
        """
        self._active_person_id = person_id

        if person_id is None:
            return list(self._all_geotagged)

        asset_ids = self._get_person_asset_ids(person_id)
        if not asset_ids:
            return []

        return [a for a in self._all_geotagged if a.asset_id in asset_ids]

    def get_person_locations(self, person_id: str) -> List[PersonLocation]:
        """Get locations where a person appears."""
        filtered = self.filter_by_person(person_id)
        if not filtered:
            return []

        # Group by location name
        groups: dict[str, list[GeotaggedAsset]] = defaultdict(list)
        for asset in filtered:
            key = asset.location_name or f"{asset.latitude:.2f},{asset.longitude:.2f}"
            groups[key].append(asset)

        locations: List[PersonLocation] = []
        for key, assets in groups.items():
            dates = [a.timestamp for a in assets if a.timestamp]
            date_range = (min(dates), max(dates)) if dates else (datetime.now(), datetime.now())
            locations.append(PersonLocation(
                location_name=key,
                photo_count=len(assets),
                latitude=assets[0].latitude,
                longitude=assets[0].longitude,
                date_range=date_range,
            ))

        return sorted(locations, key=lambda loc: loc.photo_count, reverse=True)

    def get_person_summary(self, person_id: str) -> PersonMapSummary:
        """Get a summary of a person's photo locations."""
        locations = self.get_person_locations(person_id)
        filtered = self.filter_by_person(person_id)
        return PersonMapSummary(
            person_id=person_id,
            total_photos=len(filtered),
            unique_locations=len(locations),
            locations=locations,
        )

    def _get_person_asset_ids(self, person_id: str) -> Set[str]:
        """Get asset IDs for a person (with caching)."""
        if person_id in self._person_asset_cache:
            return self._person_asset_cache[person_id]

        try:
            asset_ids = set(self._people_service.cluster_asset_ids(person_id))
            self._person_asset_cache[person_id] = asset_ids
            return asset_ids
        except Exception as e:
            _LOGGER.warning("Failed to get asset IDs for person %s: %s", person_id, e)
            return set()

    def invalidate_cache(self) -> None:
        """Clear the person-asset cache."""
        self._person_asset_cache.clear()
