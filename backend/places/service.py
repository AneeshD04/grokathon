"""Centroid search, Places Nearby call, and point-in-polygon filter."""

import math
import os
from typing import Any

import httpx

from places.fixtures import FIXTURE_BUSINESSES
from places.models import Business, NearbyRequest, NearbyResponse

PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
FIELD_MASK = (
    "places.id,places.displayName,places.location,places.nationalPhoneNumber,"
    "places.websiteUri,places.types,places.googleMapsUri"
)
INCLUDED_TYPES = [
    "hospital",
    "school",
    "lodging",
    "supermarket",
    "gas_station",
    "pharmacy",
]
MAX_RESULTS = 20
MAX_RADIUS_M = 50_000.0
EARTH_RADIUS_M = 6_371_000.0


class PlacesError(Exception):
    """Google Places returned a non-200 response."""


def lookup(body: NearbyRequest) -> NearbyResponse:
    ring = _ring(body)
    center_lat, center_lon = _centroid(ring)
    radius_m = _cover_radius_m(center_lat, center_lon, ring)
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if api_key:
        if body.types:
            found = search_nearby(center_lat, center_lon, radius_m, api_key, body.types)
        else:
            found = search_nearby(center_lat, center_lon, radius_m, api_key)
        source = "google"
    else:
        found = list(FIXTURE_BUSINESSES)
        source = "fixture"
    inside = [place for place in found if _contains(place.lon, place.lat, ring)]
    inside.sort(key=lambda place: _haversine_m(center_lat, center_lon, place.lat, place.lon))
    limit = body.limit
    return NearbyResponse(
        businesses=inside[:limit],
        truncated=len(inside) > limit or len(found) >= MAX_RESULTS,
        source=source,
    )


def search_nearby(
    center_lat: float,
    center_lon: float,
    radius_m: float,
    api_key: str,
    included_types: list[str] | None = None,
) -> list[Business]:
    payload = {
        "includedTypes": included_types or INCLUDED_TYPES,
        "maxResultCount": MAX_RESULTS,
        "rankPreference": "DISTANCE",
        "locationRestriction": {
            "circle": {
                "center": {"latitude": center_lat, "longitude": center_lon},
                "radius": radius_m,
            }
        },
    }
    response = httpx.post(
        PLACES_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        json=payload,
        timeout=10.0,
    )
    if response.status_code != 200:
        raise PlacesError(str(response.status_code))
    places = response.json().get("places") or []
    businesses: list[Business] = []
    for place in places:
        parsed = _business_from_place(place)
        if parsed is not None:
            businesses.append(parsed)
    return businesses


def _ring(body: NearbyRequest) -> list[tuple[float, float]]:
    if body.polygon is not None:
        return [(point[0], point[1]) for point in body.polygon]
    assert body.bbox is not None
    min_lon, min_lat, max_lon, max_lat = body.bbox
    return [
        (min_lon, min_lat),
        (max_lon, min_lat),
        (max_lon, max_lat),
        (min_lon, max_lat),
    ]


def _open_ring(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(ring) > 1 and ring[0] == ring[-1]:
        return ring[:-1]
    return ring


def _centroid(ring: list[tuple[float, float]]) -> tuple[float, float]:
    points = _open_ring(ring)
    count = len(points)
    latitude = sum(lat for _, lat in points) / count
    longitude = sum(lon for lon, _ in points) / count
    return latitude, longitude


def _cover_radius_m(center_lat: float, center_lon: float, ring: list[tuple[float, float]]) -> float:
    farthest = max(
        _haversine_m(center_lat, center_lon, lat, lon) for lon, lat in _open_ring(ring)
    )
    return min(MAX_RADIUS_M, max(1.0, farthest))


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    chord = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(chord))


def _contains(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    points = _open_ring(ring)
    inside = False
    previous = len(points) - 1
    for index, (xi, yi) in enumerate(points):
        xj, yj = points[previous]
        crosses = (yi > lat) != (yj > lat)
        if crosses and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        previous = index
    return inside


def _business_from_place(place: dict[str, Any]) -> Business | None:
    location = place.get("location") or {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    place_id = place.get("id")
    if place_id is None or latitude is None or longitude is None:
        return None
    display = place.get("displayName") or {}
    name = display.get("text") if isinstance(display, dict) else None
    if not name:
        return None
    maps_url = place.get("googleMapsUri") or f"https://maps.google.com/?q=place_id:{place_id}"
    return Business(
        place_id=place_id,
        name=name,
        lat=float(latitude),
        lon=float(longitude),
        phone=place.get("nationalPhoneNumber"),
        website=place.get("websiteUri"),
        types=list(place.get("types") or []),
        maps_url=maps_url,
    )
