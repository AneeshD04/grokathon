"""Run XWatch: ``python -m xwatch --once`` from the ``bots/`` directory."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from camwatch.alerts import AlertsPublishError, FileAlertsClient, HttpAlertsClient, fetch_watches
from xwatch.feed import FeedError, load_fixture, load_rss
from xwatch.model import SocialItem
from xwatch.worker import WatchState, run_once

PACKAGE = Path(__file__).resolve().parent
DEFAULT_FIXTURE = PACKAGE / "fixtures" / "galveston-flood.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="XWatch fixture/RSS worker. Does not call the X API or Grok."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="JSON fixture of mock tweets. Default: xwatch/fixtures/galveston-flood.json",
    )
    parser.add_argument(
        "--rss",
        default=None,
        help="Optional local RSS file or non-X http(s) URL. Omitted = JSON fixture only.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Load and publish once, then exit (this is the default)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Reload the fixture/RSS on an interval. Do not leave this running overnight.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=30.0,
        help="Seconds between loop passes (default 30)",
    )
    parser.add_argument(
        "--sink",
        choices=("http", "file"),
        default=os.environ.get("XWATCH_SINK", "http"),
        help="http posts to the alert bus; file writes JSONL when the API is down",
    )
    parser.add_argument(
        "--alerts-url",
        default=os.environ.get("ALERTS_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(os.environ.get("XWATCH_OUT", "xwatch-alerts.jsonl")),
        help="JSONL path used when --sink file",
    )
    parser.add_argument(
        "--ignore-watches",
        action="store_true",
        help="Do not GET /api/watches; publish matching fixture/RSS items",
    )
    parser.add_argument(
        "--no-fixture",
        action="store_true",
        help="Skip the JSON fixture (use with --rss)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("xwatch")
    if os.environ.get("X_BEARER_TOKEN", "").strip():
        log.info("X_BEARER_TOKEN is set but ignored; XWatch is fixture/RSS only")

    bus_token = os.environ.get("ALERT_BUS_TOKEN", "").strip()
    publisher = (
        FileAlertsClient(args.out)
        if args.sink == "file"
        else HttpAlertsClient(args.alerts_url, token=bus_token)
    )
    state = WatchState()

    def load_items() -> list[SocialItem]:
        items: list[SocialItem] = []
        if not args.no_fixture:
            items.extend(load_fixture(args.fixture))
        if args.rss:
            items.extend(load_rss(args.rss))
        return items

    def tick() -> int:
        try:
            items = load_items()
        except FeedError as exc:
            log.error("%s", exc)
            return -1
        watches = None
        if args.sink == "http" and not args.ignore_watches:
            watches = fetch_watches(args.alerts_url, token=bus_token)
        alerts = run_once(items, publisher=publisher, state=state, watches=watches)
        log.info("published %s alert(s)", len(alerts))
        return len(alerts)

    try:
        if not args.loop or args.once:
            result = tick()
            return 0 if result >= 0 else 2
        while True:
            try:
                tick()
            except AlertsPublishError:
                log.warning("alert bus rejected the post; retrying next pass")
            time.sleep(args.interval)
    except AlertsPublishError:
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
