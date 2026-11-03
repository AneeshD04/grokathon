"""Run CamWatch: ``python -m camwatch --once`` from the ``bots/`` directory."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from camwatch.alerts import (
    AlertsPublishError,
    FileAlertsClient,
    HttpAlertsClient,
    fetch_watches,
    resolve_alerts_base_url,
)
from camwatch.catalog import load_city
from camwatch.config import load_config
from camwatch.flood import publish_new_flood_alerts
from camwatch.model import MAX_CAMERAS, Camera, check_interval
from camwatch.vision import build_classifier
from camwatch.worker import WatchState, run_once

# Preferred Houston watch list. Missing file falls back to the TranStar seed.
_DEFAULT_HOUSTON = Path(__file__).resolve().parent.parent / "data" / "camwatch_default.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CamWatch JPEG vision worker")
    parser.add_argument(
        "--cameras",
        type=Path,
        default=None,
        help="Local camera JSON. Houston default is camwatch_default.json when that file exists; otherwise the TranStar seed. Pinellas uses the FL511 seed.",
    )
    parser.add_argument(
        "--city",
        choices=("houston", "pinellas"),
        default="houston",
        help="houston = TranStar stills (cap 8). pinellas = FL511 backup city.",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Classify from the filename or sidecar. Do not call xAI.",
    )
    parser.add_argument(
        "--vision",
        choices=("fast", "grok", "fixture"),
        default=(os.environ.get("CAMWATCH_VISION") or "fast").strip().lower() or "fast",
        help="fast = JPEG color heuristic (default, no Grok). grok = one classify then exit.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="One pass then exit (this is the default). Not a loop.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep sampling every 15–30s. Do not leave this running overnight.",
    )
    parser.add_argument(
        "--sink",
        choices=("http", "file"),
        default=os.environ.get("CAMWATCH_SINK", "http"),
        help="http posts to the Flask alert bus; file writes JSONL when the API is down",
    )
    parser.add_argument(
        "--alerts-url",
        default=os.environ.get("ALERTS_BASE_URL"),
        help="Alert bus base URL. Default probes Flask :5001/:5000, then stub :8000.",
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
    parser.add_argument(
        "--honor-watches",
        action="store_true",
        help="GET Flask /api/watches even on --once. Default one-pass ignores model-only seed watches.",
    )
    parser.add_argument(
        "--card",
        action="store_true",
        help="Print one spoken demo card and exit. One still, one vision call, no loop.",
    )
    parser.add_argument(
        "--camera-id",
        default=None,
        help="With --card, which camera id to sample. Default is the first camera (Galveston Ferry).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("camwatch")
    if args.card:
        return _speak_card(args)
    try:
        if args.cameras is not None:
            config = load_config(args.cameras)
            interval = check_interval(
                args.interval if args.interval is not None else config.interval_seconds
            )
            cameras = list(config.cameras)
            max_cameras = config.max_cameras
        else:
            interval = check_interval(args.interval if args.interval is not None else 20)
            max_cameras = MAX_CAMERAS
            default_houston = _DEFAULT_HOUSTON if args.city == "houston" and _DEFAULT_HOUSTON.is_file() else None
            if default_houston is not None:
                config = load_config(default_houston)
                interval = check_interval(
                    args.interval if args.interval is not None else config.interval_seconds
                )
                cameras = list(config.cameras)
                max_cameras = config.max_cameras
            else:
                # Vision still samples at most 8. Pinellas keeps the rest of the seed loaded.
                city_limit = 64 if args.city == "pinellas" else max_cameras
                cameras = load_city(args.city, city_limit)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        log.error("%s", exc)
        return 2
    cameras = _apply_inbox(cameras, args.inbox)
    vision = "fixture" if args.fixture else args.vision
    classifier = build_classifier(fixture=args.fixture, vision=vision)
    bus_token = os.environ.get("ALERT_BUS_TOKEN", "").strip()
    alerts_url = args.alerts_url
    if args.sink == "http":
        alerts_url = resolve_alerts_base_url(args.alerts_url)
        log.info("alert bus %s", alerts_url)
    publisher = (
        FileAlertsClient(args.out)
        if args.sink == "file"
        else HttpAlertsClient(alerts_url, token=bus_token)
    )
    state = WatchState()
    ignore_watches = args.ignore_watches or (not args.loop and not args.honor_watches)
    # FAST one-pass: sample the catalog (cap 8). Grok: one classify then exit.
    max_frames = 1 if vision == "grok" else max_cameras

    def tick() -> int:
        watches = None
        if args.sink == "http" and not ignore_watches:
            watches = fetch_watches(alerts_url, token=bus_token)
        alerts = run_once(
            cameras,
            classifier=classifier,
            publisher=publisher,
            state=state,
            watches=watches,
            max_cameras=max_cameras,
            max_frames=max_frames,
        )
        if args.cameras is None and args.city == "houston":
            alerts.extend(publish_new_flood_alerts(publisher, state))
        log.info("published %s alert(s)", len(alerts))
        return len(alerts)

    try:
        if not args.loop or args.once:
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


def _speak_card(args) -> int:
    """One-pass demo. ``--loop`` does not apply here."""
    from camwatch.card import CardError, redact, run_card

    try:
        text = run_card(
            cameras_path=args.cameras,
            camera_id=args.camera_id,
            fixture=args.fixture,
        )
    except CardError as exc:
        logging.getLogger("camwatch").error("%s", redact(str(exc)))
        return 1
    except Exception as exc:
        logging.getLogger("camwatch").error(
            "demo card failed: %s",
            redact(f"{type(exc).__name__}: {exc}"),
        )
        return 1
    sys.stdout.write(text)
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
                    mp4_path=camera.mp4_path,
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
        mp4_path=first.mp4_path,
    )
    return updated


if __name__ == "__main__":
    sys.exit(main())
