"""One GovWatch pass: NWS + USGS → alerts. Fixture replay is the demo path."""

from __future__ import annotations

import argparse
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from govwatch.clients import (
    USGS_URL,
    FileAlertsClient,
    HttpAlertsClient,
    MemoryCache,
    FetchError,
    http_get_json,
    load_json,
)
from govwatch.normalize import normalize_nws_collection, normalize_usgs_collection

logger = logging.getLogger("govwatch")

PACKAGE = Path(__file__).resolve().parent
FIXTURE_DIR = PACKAGE / "fixtures"
DEFAULT_BBOX = [-95.17, 29.02, -94.37, 29.67]
DEFAULT_GEOFENCE = "galveston-county"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def parse_bbox(raw: str | None) -> list[float]:
    if not raw or not raw.strip():
        return list(DEFAULT_BBOX)
    parts = [float(item) for item in raw.split(",")]
    if len(parts) != 4 or parts[0] >= parts[2] or parts[1] >= parts[3]:
        raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
    return parts


class Poller:
    def __init__(
        self,
        *,
        publisher: Any,
        fetch_nws: Callable[[], dict] | None = None,
        fetch_usgs: Callable[[], dict] | None = None,
        cache: MemoryCache | None = None,
        now: Callable[[], float] | None = None,
        bbox: list[float] | None = None,
        geofence_id: str = DEFAULT_GEOFENCE,
        flood_stage_ft: float | None = None,
        dedupe_s: float | None = None,
    ) -> None:
        self.publisher = publisher
        self.fetch_nws = fetch_nws
        self.fetch_usgs = fetch_usgs
        self.cache = cache or MemoryCache()
        self.now = now or time.time
        self.bbox = list(bbox or DEFAULT_BBOX)
        self.geofence_id = geofence_id
        self.flood_stage_ft = (
            flood_stage_ft if flood_stage_ft is not None else _env_float("GOVWATCH_USGS_FLOOD_STAGE_FT", 4.0)
        )
        self.dedupe_s = dedupe_s if dedupe_s is not None else _env_float("GOVWATCH_DEDUPE_S", 3600.0)
        self._seen: dict[str, tuple[str, float]] = {}

    def once(self) -> list[dict]:
        posted: list[dict] = []
        for alert in self._nws_alerts() + self._usgs_alerts():
            published = self._publish(alert)
            if published is not None:
                posted.append(published)
        return posted

    def _nws_alerts(self) -> list[dict]:
        payload = self._cached("nws", self.fetch_nws)
        if payload is None:
            return []
        return normalize_nws_collection(payload, geofence_id=self.geofence_id, bbox=self.bbox)

    def _usgs_alerts(self) -> list[dict]:
        payload = self._cached("usgs", self.fetch_usgs)
        if payload is None:
            return []
        return normalize_usgs_collection(
            payload,
            geofence_id=self.geofence_id,
            bbox=self.bbox,
            flood_stage_ft=self.flood_stage_ft,
        )

    def _cached(self, key: str, fetcher: Callable[[], dict] | None) -> dict | None:
        if fetcher is None:
            return None
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        try:
            payload = fetcher()
        except Exception:
            logger.exception("govwatch %s fetch failed", key)
            return None
        if not isinstance(payload, dict):
            return None
        return self.cache.set(key, payload)

    def _publish(self, alert: dict) -> dict | None:
        key = str(alert.get("dedupe_key") or "")
        severity = str(alert.get("severity") or "")
        previous = self._seen.get(key)
        now = self.now()
        if previous is not None:
            last_severity, last_at = previous
            if last_severity == severity and (now - last_at) < self.dedupe_s:
                return None
        result = self.publisher.publish(alert)
        self._seen[key] = (severity, now)
        stored = result.get("alert") if isinstance(result, dict) else alert
        return stored if isinstance(stored, dict) else alert


def fixture_fetchers(directory: Path | None = None) -> tuple[Callable[[], dict], Callable[[], dict]]:
    folder = directory or FIXTURE_DIR

    def nws() -> dict:
        return load_json(folder / "nws-texas-flash-flood.json")

    def usgs() -> dict:
        return load_json(folder / "usgs-galveston-gauge.json")

    return nws, usgs


def live_fetchers(bbox: list[float]) -> tuple[Callable[[], dict], Callable[[], dict]]:
    box = ",".join(f"{item:.5f}" for item in bbox)

    def nws() -> dict:
        return http_get_json(os.environ.get("GOVWATCH_NWS_URL", "https://api.weather.gov/alerts/active?status=actual&message_type=alert&area=TX"))

    def usgs() -> dict:
        return http_get_json(os.environ.get("GOVWATCH_USGS_URL", USGS_URL.format(bbox=box)))

    return nws, usgs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GovWatch: replay or poll NWS + USGS onto the Flask alert bus. No Grok. No Twilio."
    )
    parser.add_argument("--once", action="store_true", help="one pass (default)")
    parser.add_argument(
        "--live",
        action="store_true",
        help="hit api.weather.gov + USGS IV (cached). Default is the recorded Texas fixture.",
    )
    parser.add_argument("--bbox", default=os.environ.get("GOVWATCH_BBOX", ""), help="minLon,minLat,maxLon,maxLat")
    parser.add_argument("--geofence-id", default=os.environ.get("GOVWATCH_GEOFENCE_ID", DEFAULT_GEOFENCE))
    parser.add_argument(
        "--sink",
        choices=("http", "file"),
        default=os.environ.get("GOVWATCH_SINK", "http"),
    )
    parser.add_argument(
        "--alerts-url",
        default=os.environ.get("ALERTS_BASE_URL", "http://127.0.0.1:5001"),
        help="Flask app that already has POST /api/alerts",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(os.environ.get("GOVWATCH_OUT", "govwatch-alerts.jsonl")),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    bbox = parse_bbox(args.bbox)
    if args.live:
        nws, usgs = live_fetchers(bbox)
    else:
        nws, usgs = fixture_fetchers()
    if args.sink == "file":
        publisher = FileAlertsClient(args.out)
    else:
        publisher = HttpAlertsClient(args.alerts_url)
    try:
        posted = Poller(
            publisher=publisher,
            fetch_nws=nws,
            fetch_usgs=usgs,
            bbox=bbox,
            geofence_id=args.geofence_id,
        ).once()
    except FetchError as exc:
        logger.error("%s", exc)
        return 1
    print(f"posted {len(posted)} alert(s)")
    for alert in posted:
        print(f"{alert.get('source')} {alert.get('severity')} {alert.get('title')} @ {alert.get('lat')},{alert.get('lon')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
