"""Load JSON fixtures and RSS. Never call the X API."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from xwatch.model import SocialItem, iso_now

# Live X/Twitter search is out of scope for #18 (no bearer firehose).
_BLOCKED_HOSTS = (
    "api.twitter.com",
    "api.x.com",
    "twitter.com",
    "x.com",
    "www.twitter.com",
    "www.x.com",
)

MAX_RSS_BYTES = 1_000_000


class FeedError(Exception):
    pass


def load_fixture(path: Path) -> list[SocialItem]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FeedError(f"fixture unreadable: {path}: {exc}") from exc
    rows = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise FeedError("fixture must be a list or {items: [...]}")
    items: list[SocialItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = _item_from_dict(row, origin="fixture")
        if parsed is not None:
            items.append(parsed)
    return items


def load_rss(source: str, *, opener=urlopen, timeout: float = 5.0) -> list[SocialItem]:
    xml_text = _read_rss(source, opener=opener, timeout=timeout)
    return parse_rss(xml_text)


def parse_rss(xml_text: str) -> list[SocialItem]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise FeedError(f"RSS is not valid XML: {exc}") from exc
    items: list[SocialItem] = []
    for node in root.iter():
        if _local(node.tag) != "item" and _local(node.tag) != "entry":
            continue
        parsed = _item_from_rss(node)
        if parsed is not None:
            items.append(parsed)
    return items


def _read_rss(source: str, *, opener, timeout: float) -> str:
    path = Path(source)
    if path.exists() and path.is_file():
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FeedError(f"RSS file unreadable: {source}: {exc}") from exc
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        host = (parsed.hostname or "").lower()
        if host in _BLOCKED_HOSTS or host.endswith(".twitter.com") or host.endswith(".x.com"):
            raise FeedError("X/Twitter hosts are blocked; use a JSON fixture or a non-X RSS file")
        request = Request(source, headers={"Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
        try:
            with opener(request, timeout=timeout) as response:
                body = response.read(MAX_RSS_BYTES + 1)
        except HTTPError as exc:
            raise FeedError(f"RSS fetch failed: HTTP {exc.code}") from exc
        except URLError as exc:
            raise FeedError(f"RSS fetch failed: {exc.reason}") from exc
        if len(body) > MAX_RSS_BYTES:
            raise FeedError("RSS feed larger than 1MB")
        return body.decode("utf-8", "replace")
    raise FeedError(f"RSS source is not a local file or http(s) URL: {source}")


def _item_from_dict(row: dict, *, origin: str) -> SocialItem | None:
    item_id = str(row.get("id") or "").strip()
    text = str(row.get("text") or row.get("title") or "").strip()
    if not item_id or not text:
        return None
    lat = _coord(row.get("lat"))
    lon = _coord(row.get("lon"))
    created = row.get("created_at")
    created_at = created.strip() if isinstance(created, str) and created.strip() else None
    author = str(row.get("author") or "").strip()
    url = row.get("url")
    url_text = url.strip() if isinstance(url, str) and url.strip() else None
    geofence = row.get("geofence_id")
    geofence_id = geofence.strip() if isinstance(geofence, str) and geofence.strip() else None
    return SocialItem(
        id=item_id,
        text=text,
        origin=origin,
        lat=lat,
        lon=lon,
        author=author,
        created_at=created_at,
        url=url_text,
        geofence_id=geofence_id,
    )


def _item_from_rss(node: ET.Element) -> SocialItem | None:
    fields = {_local(child.tag): (child.text or "").strip() for child in list(node)}
    title = fields.get("title") or ""
    description = fields.get("description") or fields.get("summary") or fields.get("content") or ""
    text = " ".join(part for part in (title, description) if part).strip()
    item_id = fields.get("guid") or fields.get("id") or fields.get("link") or title
    item_id = item_id.strip()
    if not item_id or not text:
        return None
    lat, lon = _geo_from_rss(node)
    created_at = _rss_date(fields.get("pubDate") or fields.get("updated") or fields.get("published"))
    return SocialItem(
        id=item_id,
        text=text,
        origin="rss",
        lat=lat,
        lon=lon,
        author=fields.get("author") or fields.get("creator") or "",
        created_at=created_at,
        url=fields.get("link") or None,
    )


def _geo_from_rss(node: ET.Element) -> tuple[float | None, float | None]:
    lat = lon = None
    for child in list(node):
        name = _local(child.tag)
        value = (child.text or "").strip()
        if name in ("point",) and value:
            parts = value.replace(",", " ").split()
            if len(parts) >= 2:
                lat, lon = _coord(parts[0]), _coord(parts[1])
        elif name == "lat":
            lat = _coord(value)
        elif name in ("long", "lon", "lng"):
            lon = _coord(value)
    return lat, lon


def _rss_date(value: str | None) -> str | None:
    if not value:
        return iso_now()
    text = value.strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        try:
            iso = text[:-1] + "+00:00" if text.endswith("Z") else text
            parsed = datetime.fromisoformat(iso)
        except ValueError:
            return iso_now()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _coord(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag
