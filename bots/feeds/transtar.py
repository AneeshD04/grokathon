# Catalog: https://traffic.houstontranstar.org/data/layers/cctvSnapshots_out.js
# (GET HTTP 200, 1396 cameras). Stills: https://www.houstontranstar.org/snapshots/cctv/{path}
#
# Live still GETs on 2026-11-03, User-Agent grokathon-transtar/0.1, timeout 20s.
# Snapshot length changes as TranStar refreshes the JPEG (about every 3 minutes).
# https://www.houstontranstar.org/snapshots/cctv/180.jpg HTTP 200 image/jpeg
# https://www.houstontranstar.org/snapshots/cctv/9061.jpg HTTP 200 image/jpeg
# https://www.houstontranstar.org/snapshots/cctv/8113.jpg HTTP 200 text/html; charset=utf-8
#   Failed as a still: body is HTML, not a JPEG. Yale@Washington (validimg False) is not seeded.
# Every still_url in bots/data/transtar_cameras.json was GET-checked the same day and returned
# HTTP 200 image/jpeg. HEAD on 180.jpg returned HTTP 200 text/html; this endpoint needs GET.
#
# Name/path notes from that catalog pull:
# - Snapshot path is the filename (180.jpg), not a directory.
# - No Galveston Island camera is named Broadway. 173.jpg is IH-45 at 61st St on the island.
#   Cameras named Broadway (113.jpg, 8021.jpg-8023.jpg) are Broadway Blvd / SH 3 in Houston.
# - Causeway snapshots 164.jpg, 165.jpg, and 166.jpg are validimg False. 164.jpg still
#   returned a JPEG (19855 bytes, distinct from blank.jpg) and is seeded.
# - SH-35 freeway mainlanes are not in the list. Seeded SH-35 is 9039.jpg at Orange St.
#   SH-6 at SH-35 is 1921.jpg and validimg False.
# - One out.js constructor ("10 Katy at Silber") is truncated and was skipped.

"""Houston TranStar live CCTV stills for the Houston-Galveston flood demo.

The seed is a hand-picked flood set (ferry landings, the causeway, bayou
crossings, and low coastal roads). It is not the full ~1,400-camera catalog.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CATALOG_URL = "https://traffic.houstontranstar.org/data/layers/cctvSnapshots_out.js"
STILL_BASE = "https://www.houstontranstar.org/snapshots/cctv/"
USER_AGENT = "grokathon-transtar/0.1"
TIMEOUT_S = 20
_MAX_STILL_BYTES = 5 * 1024 * 1024
_SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "transtar_cameras.json"
_FIELDS = ("id", "name", "lat", "lon", "still_url", "why")


class TranstarError(Exception):
    """A TranStar seed or still request failed."""


def load_cameras():
    """Return the flood-relevant seed list (id, name, lat, lon, still_url, why)."""
    with _SEED_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise TranstarError(f"seed is not a list: {_SEED_PATH}")
    cameras = []
    for index, record in enumerate(data):
        if not isinstance(record, dict) or any(field not in record for field in _FIELDS):
            raise TranstarError(f"seed record {index} is missing required fields")
        cameras.append(record)
    return cameras


def download_still(url, timeout=TIMEOUT_S):
    """GET one snapshot URL and return the JPEG bytes."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise TranstarError("still_url must be http or https")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            content_type = response.headers.get("Content-Type", "")
            data = response.read(_MAX_STILL_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise TranstarError(f"still GET failed: HTTP {exc.code} {url}") from exc
    except urllib.error.URLError as exc:
        raise TranstarError(f"still GET failed: {exc.reason} {url}") from exc
    if status != 200:
        raise TranstarError(f"still GET failed: HTTP {status} {url}")
    if len(data) > _MAX_STILL_BYTES:
        raise TranstarError(f"still is larger than {_MAX_STILL_BYTES} bytes")
    if not data.startswith(b"\xff\xd8"):
        kind = content_type or "unknown content type"
        raise TranstarError(f"response is not a JPEG (HTTP {status}, {kind})")
    return data


def fetch_still(camera, timeout=TIMEOUT_S):
    """Download the JPEG still for one seeded camera id or seed record."""
    if isinstance(camera, dict):
        url = camera.get("still_url")
        if not url:
            raise TranstarError("camera record has no still_url")
        return download_still(url, timeout=timeout)
    camera_id = str(camera)
    for record in load_cameras():
        if str(record.get("id")) == camera_id:
            return download_still(record["still_url"], timeout=timeout)
    raise TranstarError(f"unknown camera id: {camera_id}")
