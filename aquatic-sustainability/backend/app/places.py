"""POST /api/businesses/nearby on the Flask app.

Lookup only. Does not send SMS or email. Fixture businesses have no phones.
Places numbers are never auto-dialed by notify.
"""

from __future__ import annotations

import math
import os
from typing import Any

import requests
from flask import Blueprint, jsonify, request

bp = Blueprint("places", __name__)

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

FIXTURE_BUSINESSES = [
    {
        "place_id": "fixture-utmb",
        "name": "Fixture UTMB Health",
        "lat": 29.3106,
        "lon": -94.7774,
        "phone": None,
        "website": None,
        "types": ["hospital"],
        "maps_url": "https://maps.google.com/?q=place_id:fixture-utmb",
    },
    {
        "place_id": "fixture-school",
        "name": "Fixture Ball High School",
        "lat": 29.2905,
        "lon": -94.8094,
        "phone": None,
        "website": None,
        "types": ["school"],
        "maps_url": "https://maps.google.com/?q=place_id:fixture-school",
    },
    {
        "place_id": "fixture-lodging",
        "name": "Fixture Seawall Lodging",
        "lat": 29.2722,
        "lon": -94.815,
        "phone": None,
        "website": None,
        "types": ["lodging"],
        "maps_url": "https://maps.google.com/?q=place_id:fixture-lodging",
    },
]


class PlacesError(Exception):
    """Google Places returned a non-200 response."""


def _check_lon_lat(lon: float, lat: float) -> None:
    if not -180 <= lon <= 180:
        raise ValueError("longitude out of range")
    if not -90 <= lat <= 90:
        raise ValueError("latitude out of range")


def parse_nearby(body: dict[str, Any]) -> dict[str, Any]:
    types = body.get("types")
    if types is not None:
        if not isinstance(types, list) or not types or len(types) > 10:
            raise ValueError("types must contain 1 to 10 entries")
        cleaned = []
        for item in types:
            text = str(item).strip()
            if not text or len(text) > 40:
                raise ValueError("invalid place type")
            cleaned.append(text)
        types = cleaned
    limit = body.get("limit", 20)
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an int") from exc
    if not 1 <= limit <= 20:
        raise ValueError("limit must be 1 to 20")
    polygon = body.get("polygon")
    bbox = body.get("bbox")
    if polygon is not None:
        if not isinstance(polygon, list) or len(polygon) < 3:
            raise ValueError("polygon needs at least 3 points")
        ring = []
        for point in polygon:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("polygon points are [lon, lat]")
            lon, lat = float(point[0]), float(point[1])
            _check_lon_lat(lon, lat)
            ring.append([lon, lat])
        return {"polygon": ring, "bbox": None, "limit": limit, "types": types}
    if bbox is None:
        raise ValueError("bbox or polygon is required")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError("bbox must be [minLon, minLat, maxLon, maxLat]")
    min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
    _check_lon_lat(min_lon, min_lat)
    _check_lon_lat(max_lon, max_lat)
    if not (min_lon < max_lon and min_lat < max_lat):
        raise ValueError("bbox min must be less than max")
    return {
        "bbox": [min_lon, min_lat, max_lon, max_lat],
        "polygon": None,
        "limit": limit,
        "types": types,
    }


def _ring(body: dict[str, Any]) -> list[tuple[float, float]]:
    if body.get("polygon") is not None:
        return [(point[0], point[1]) for point in body["polygon"]]
    min_lon, min_lat, max_lon, max_lat = body["bbox"]
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


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    chord = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(chord))


def _cover_radius_m(center_lat: float, center_lon: float, ring: list[tuple[float, float]]) -> float:
    farthest = max(_haversine_m(center_lat, center_lon, lat, lon) for lon, lat in _open_ring(ring))
    return min(MAX_RADIUS_M, max(1.0, farthest))


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


def _business_from_place(place: dict[str, Any]) -> dict[str, Any] | None:
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
    return {
        "place_id": place_id,
        "name": name,
        "lat": float(latitude),
        "lon": float(longitude),
        "phone": place.get("nationalPhoneNumber"),
        "website": place.get("websiteUri"),
        "types": list(place.get("types") or []),
        "maps_url": maps_url,
    }


def search_nearby(
    center_lat: float,
    center_lon: float,
    radius_m: float,
    api_key: str,
    included_types: list[str] | None = None,
) -> list[dict[str, Any]]:
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
    response = requests.post(
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
    businesses = []
    for place in places:
        parsed = _business_from_place(place)
        if parsed is not None:
            businesses.append(parsed)
    return businesses


def lookup(body: dict[str, Any]) -> dict[str, Any]:
    ring = _ring(body)
    center_lat, center_lon = _centroid(ring)
    radius_m = _cover_radius_m(center_lat, center_lon, ring)
    api_key = (
        os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
        or os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    )
    if api_key:
        found = search_nearby(center_lat, center_lon, radius_m, api_key, body.get("types"))
        source = "google"
    else:
        found = list(FIXTURE_BUSINESSES)
        source = "fixture"
    inside = [place for place in found if _contains(place["lon"], place["lat"], ring)]
    inside.sort(key=lambda place: _haversine_m(center_lat, center_lon, place["lat"], place["lon"]))
    limit = body["limit"]
    return {
        "businesses": inside[:limit],
        "truncated": len(inside) > limit or len(found) >= MAX_RESULTS,
        "source": source,
    }


@bp.route("/businesses/nearby", methods=["POST"])
def nearby():
    if not request.is_json:
        return jsonify({"detail": "JSON body required"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"detail": "JSON object required"}), 400
    try:
        parsed = parse_nearby(body)
        result = lookup(parsed)
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    except PlacesError:
        return jsonify({"detail": "Places lookup failed"}), 502
    return jsonify(result)
