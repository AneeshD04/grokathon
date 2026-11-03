"""Default cameras from the checked-in feeds.

TranStar is the Houston demo (cap 8). FL511 Pinellas is the backup city.
Still URLs come from those files. This module does not invent any.
"""

from __future__ import annotations

from camwatch.model import MAX_CAMERAS, Camera


def load_city(city: str, limit: int = MAX_CAMERAS) -> list[Camera]:
    """Houston is capped at 8. Pinellas can return the whole backup seed."""
    if city == "houston":
        return _transtar(min(max(limit, 1), MAX_CAMERAS))
    if city == "pinellas":
        return _fl511(max(limit, 1))
    raise ValueError(f"unknown city {city}")


def _transtar(limit: int) -> list[Camera]:
    from feeds.transtar import load_cameras

    cameras: list[Camera] = []
    for record in load_cameras():
        cameras.append(
            Camera(
                id=f"transtar-{record['id']}",
                name=str(record["name"]),
                lat=float(record["lat"]),
                lon=float(record["lon"]),
                geofence_id="houston-demo",
                still_url=str(record["still_url"]),
            )
        )
        if len(cameras) >= limit:
            break
    return cameras


def _fl511(limit: int) -> list[Camera]:
    from feeds.fl511 import load_seed

    cameras: list[Camera] = []
    for record in load_seed():
        cameras.append(
            Camera(
                id=str(record["id"]),
                name=str(record["name"]),
                lat=float(record["lat"]),
                lon=float(record["lon"]),
                geofence_id="pinellas-demo",
                still_url=str(record["image_url"]),
            )
        )
        if len(cameras) >= limit:
            break
    return cameras
