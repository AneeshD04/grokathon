"""Publish alerts to POST /api/alerts, or to a local JSONL file when the API is down.

The file sink is the seam for tests and for running before issue #11 is on main.
Both sinks speak the same alert object.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from camwatch.model import iso_now, new_ulid


class AlertsPublishError(Exception):
    pass


class HttpAlertsClient:
    """POST {base}/api/alerts. Response is ``{alert, deduped}`` (issue #11)."""

    def __init__(self, base_url: str, timeout: float = 5.0, opener=urllib.request.urlopen) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener

    def publish(self, alert: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/api/alerts",
            data=json.dumps(alert).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise AlertsPublishError(f"POST /api/alerts failed: HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise AlertsPublishError(f"POST /api/alerts unreachable: {exc.reason}") from exc
        try:
            parsed = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise AlertsPublishError("POST /api/alerts returned non-JSON") from exc
        if not isinstance(parsed, dict) or "alert" not in parsed:
            raise AlertsPublishError("POST /api/alerts response missing alert")
        return parsed


class FileAlertsClient:
    """Append ``{alert, deduped}`` lines. Used when the alert bus is not running."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def publish(self, alert: dict) -> dict:
        stored = dict(alert)
        record = {
            "alert": {
                "id": new_ulid(),
                "ts": stored.pop("ts", None) or iso_now(),
                **stored,
            },
            "deduped": False,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        return record


def fetch_watches(base_url: str, timeout: float = 3.0, opener=urllib.request.urlopen) -> list[dict] | None:
    """Return watches, or None when the API cannot be reached.

    None means "no registry yet" — CamWatch keeps using the local camera file.
    An empty list means the registry is up and nobody has called set_watch.
    """
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/watches",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, list):
        return None
    return [item for item in payload if isinstance(item, dict)]
