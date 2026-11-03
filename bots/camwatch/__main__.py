"""Run CamWatch: ``python -m camwatch --once`` from the ``bots/`` directory."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from camwatch.alerts import AlertsPublishError, FileAlertsClient, HttpAlertsClient, fetch_watches
from camwatch.config import load_config
from camwatch.model import Camera, check_interval
from camwatch.vision import build_classifier
from camwatch.worker import WatchState, run_once

_PACKAGE_ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CamWatch JPEG vision worker")
    parser.add_argument(
        "--cameras",
        type=Path,
        default=_PACKAGE_ROOT / "cameras.example.json",
        help="Local camera JSON (id, name, lat, lon, still_url or inbox_dir)",
    )
    parser.add_argument("--once", action="store_true", help="Sample once and exit")
    parser.add_argument(
        "--sink",
        choices=("http", "file"),
        default=os.environ.get("CAMWATCH_SINK", "http"),
        help="http posts to the alert bus; file writes JSONL when the API is down",
    )
    parser.add_argument(
        "--alerts-url",
        default=os.environ.get("ALERTS_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(os.environ.get("CAMWATCH_OUT", "camwatch-alerts.jsonl")),
        help="JSONL path used when --sink file",
    )
    parser.add_argument(
        "--inbox",
        type=Path,
        default=None,
        help="Drop-folder override for cameras that read an inbox",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Seconds between passes (15–30). Default comes from the camera file or 20.",
    )
    parser.add_argument(
        "--ignore-watches",
        action="store_true",
        help="Do not GET /api/watches; sample the local camera file",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = load_config(args.cameras)
        interval = check_interval(
            args.interval if args.interval is not None else config.interval_seconds
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        logging.getLogger("camwatch").error("%s", exc)
        return 2
    cameras = _apply_inbox(list(config.cameras), args.inbox)
    classifier = build_classifier()
    publisher = (
        FileAlertsClient(args.out)
        if args.sink == "file"
        else HttpAlertsClient(args.alerts_url)
    )
    state = WatchState()

    def tick() -> int:
        watches = None
        if args.sink == "http" and not args.ignore_watches:
            watches = fetch_watches(args.alerts_url)
        alerts = run_once(
            cameras,
            classifier=classifier,
            publisher=publisher,
            state=state,
            watches=watches,
            max_cameras=config.max_cameras,
        )
        logging.getLogger("camwatch").info("published %s alert(s)", len(alerts))
        return len(alerts)

    try:
        if args.once:
            tick()
            return 0
        while True:
            try:
                tick()
            except AlertsPublishError:
                logging.getLogger("camwatch").warning("alert bus rejected the post; retrying next pass")
            time.sleep(interval)
    except AlertsPublishError:
        return 1
    except KeyboardInterrupt:
        return 0


def _apply_inbox(cameras: list[Camera], inbox: Path | None) -> list[Camera]:
    if inbox is None:
        return cameras
    resolved = inbox.resolve()
    updated: list[Camera] = []
    replaced = False
    for camera in cameras:
        if camera.inbox_dir is not None:
            updated.append(
                Camera(
                    id=camera.id,
                    name=camera.name,
                    lat=camera.lat,
                    lon=camera.lon,
                    geofence_id=camera.geofence_id,
                    still_url=camera.still_url,
                    inbox_dir=resolved,
                )
            )
            replaced = True
        else:
            updated.append(camera)
    if replaced:
        return updated
    if not updated:
        return updated
    first = updated[0]
    updated[0] = Camera(
        id=first.id,
        name=first.name,
        lat=first.lat,
        lon=first.lon,
        geofence_id=first.geofence_id,
        still_url=None,
        inbox_dir=resolved,
    )
    return updated


if __name__ == "__main__":
    sys.exit(main())
