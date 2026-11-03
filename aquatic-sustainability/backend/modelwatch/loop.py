"""Interval loop for ModelWatch. One process, not a Flask thread."""

from __future__ import annotations

import logging
import os
import time

from modelwatch.clients import HttpClients
from modelwatch.poll import Poller

logger = logging.getLogger("modelwatch")


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    interval = float(os.environ.get("MODELWATCH_INTERVAL_S", "600"))
    poller = Poller(HttpClients())
    logger.info("modelwatch loop every %s seconds", interval)
    while True:
        try:
            posted = poller.once()
            logger.info("modelwatch posted %s alert(s)", len(posted))
        except Exception:
            logger.exception("modelwatch pass failed")
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
