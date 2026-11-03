"""Social items → alert payloads for XWatch.

Field names match docs/SAFETY-AGENT-DESIGN.md and the #11 AlertCreate
model. ``source`` is ``x`` for JSON fixtures (tweets) and ``news`` for RSS.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

HAZARD_KEYWORDS = (
    "flood",
    "flooding",
    "flooded",
    "storm surge",
    "surge",
    "road closed",
    "high water",
    "inundat",
    "overtop",
    "seawall",
)

GEO_KEYWORDS = (
    "galveston",
    "houston",
    "harris county",
    "bolivar",
    "the strand",
    "seawall blvd",
)

# Houston–Galveston coastal box used when a watch has no bbox.
DEFAULT_BBOX = (-95.9, 28.8, -94.4, 30.2)  # minLon, minLat, maxLon, maxLat
GALVESTON = (29.3013, -94.7977)
HOUSTON = (29.7604, -95.3698)
DEFAULT_GEOFENCE = "houston-demo"
MAX_ITEMS = 32


@dataclass(frozen=True)
class SocialItem:
    id: str
    text: str
    origin: str  # "fixture" or "rss"
    lat: float | None = None
    lon: float | None = None
    author: str = ""
    created_at: str | None = None
    url: str | None = None
    geofence_id: str | None = None


def iso_now(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def matched_keywords(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for word in HAZARD_KEYWORDS + GEO_KEYWORDS:
        if word in lowered and word not in found:
            found.append(word)
    return found


def pin_item(item: SocialItem) -> SocialItem:
    """Fill lat/lon from place names when the fixture omitted coords."""
    if item.lat is not None and item.lon is not None:
        return item
    text = item.text.lower()
    if any(token in text for token in ("galveston", "bolivar", "seawall", "the strand")):
        return replace(item, lat=GALVESTON[0], lon=GALVESTON[1])
    if "houston" in text or "harris county" in text:
        return replace(item, lat=HOUSTON[0], lon=HOUSTON[1])
    return item


def in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def matches(item: SocialItem, bbox: tuple[float, float, float, float] | None = None) -> bool:
    """Keep items that look like flood/surge chatter in the coastal geofence."""
    text = item.text.lower()
    hazard = any(word in text for word in HAZARD_KEYWORDS)
    geo = any(word in text for word in GEO_KEYWORDS)
    box = bbox or DEFAULT_BBOX
    inside = (
        item.lat is not None
        and item.lon is not None
        and in_bbox(item.lat, item.lon, box)
    )
    return hazard and (geo or inside)


def severity_for(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("storm surge", "overtop", "water over")):
        return "critical"
    if any(word in lowered for word in ("flood", "road closed", "high water", "surge")):
        return "warning"
    return "watch"


def title_for(item: SocialItem) -> str:
    prefix = "News" if item.origin == "rss" else "X"
    text = item.text.lower()
    if "galveston" in text and any(word in text for word in ("flood", "surge")):
        return f"{prefix}: Galveston flooding"
    snippet = " ".join(item.text.split())[:80].rstrip(" .,-")
    return f"{prefix}: {snippet}"[:200]


def source_for(item: SocialItem) -> str:
    return "news" if item.origin == "rss" else "x"


def build_alert(item: SocialItem, *, ts: str | None = None) -> dict:
    pinned = pin_item(item)
    lat = pinned.lat if pinned.lat is not None else GALVESTON[0]
    lon = pinned.lon if pinned.lon is not None else GALVESTON[1]
    source = source_for(pinned)
    return {
        "source": source,
        "severity": severity_for(pinned.text),
        "lat": lat,
        "lon": lon,
        "geofence_id": pinned.geofence_id or DEFAULT_GEOFENCE,
        "title": title_for(pinned),
        "summary": pinned.text.strip()[:4000],
        "evidence": {
            "thumb_url": None,
            "raw": {
                "item_id": pinned.id,
                "author": pinned.author,
                "url": pinned.url,
                "origin": pinned.origin,
                "fixture": pinned.origin == "fixture",
                "keywords": matched_keywords(pinned.text),
            },
        },
        "dedupe_key": f"{source}:{pinned.id}",
        "ts": ts or pinned.created_at or iso_now(),
    }
