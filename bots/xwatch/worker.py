"""One XWatch pass: load fixture/RSS items, filter, publish new alerts."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from xwatch.model import MAX_ITEMS, build_alert, matches, pin_item, source_for

logger = logging.getLogger("xwatch")


@dataclass
class WatchState:
    seen_ids: list[str] = field(default_factory=list)


def select_items(
    items: list[SocialItem],
    watches: list[dict] | None,
) -> list[SocialItem]:
    """Keep flood/surge items that a watch with source x/news would accept.

    ``watches is None`` or ``[]`` → local geofence filter only.
    A non-empty registry with no ``x`` or ``news`` source publishes nothing.
    """
    wanted_sources: set[str] | None = None
    bbox = None
    geofence_id = None
    if watches:
        wanted_sources = set()
        for watch in watches:
            sources = [str(item) for item in watch.get("sources") or []]
            for source in sources:
                if source in ("x", "news"):
                    wanted_sources.add(source)
            raw_bbox = watch.get("bbox")
            if isinstance(raw_bbox, list) and len(raw_bbox) == 4:
                try:
                    bbox = tuple(float(part) for part in raw_bbox)
                except (TypeError, ValueError):
                    bbox = None
            gid = watch.get("geofence_id")
            if isinstance(gid, str) and gid.strip():
                geofence_id = gid.strip()
        if not wanted_sources:
            return []

    chosen: list[SocialItem] = []
    for item in items:
        pinned = pin_item(item)
        if geofence_id and pinned.geofence_id is None:
            pinned = replace(pinned, geofence_id=geofence_id)
        if not matches(pinned, bbox):
            continue
        if wanted_sources is not None and source_for(pinned) not in wanted_sources:
            continue
        chosen.append(pinned)
        if len(chosen) >= MAX_ITEMS:
            break
    return chosen


def run_once(
    items: list[SocialItem],
    *,
    publisher,
    state: WatchState,
    watches: list[dict] | None = None,
) -> list[dict]:
    published: list[dict] = []
    for item in select_items(items, watches):
        if item.id in state.seen_ids:
            continue
        alert = build_alert(item)
        publisher.publish(alert)
        state.seen_ids.append(item.id)
        published.append(alert)
        logger.info("social alert %s", alert["dedupe_key"])
    return published
