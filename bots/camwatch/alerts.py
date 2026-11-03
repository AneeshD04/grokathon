"""Publish alerts to POST /api/alerts, or to a local JSONL file when the API is down.

Prefer the Flask bus on ``aquatic-sustainability`` (``python run.py``,
port 5001). The repo-root stub ``:8000`` is only the fallback when Flask
``/api/alerts`` is not reachable. Both sinks speak the same alert object.
``thumb_url`` is either null or an http(s) URL.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from camwatch.model import iso_now, new_ulid

logger = logging.getLogger("camwatch")

FLASK_ALERT_CANDIDATES = (
    "http://127.0.0.1:5001",
    "http://127.0.0.1:5000",
)
STUB_ALERTS_URL = "http://127.0.0.1:8000"


class AlertsPublishError(Exception):
    pass


def _headers(token: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token.strip():
        headers["X-Alert-Bus-Token"] = token.strip()
    return headers


class HttpAlertsClient:
    """POST {base}/api/alerts. Response is ``{alert, deduped}`` (issue #11).

    ``ALERT_BUS_TOKEN``, when set, is sent as ``X-Alert-Bus-Token`` and is
    never written to the alert body or the log.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 5.0,
        opener=urllib.request.urlopen,
        token: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener
        self._token = token.strip()

    def publish(self, alert: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/api/alerts",
            data=json.dumps(alert).encode("utf-8"),
            headers=_headers(self._token),
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


def _normalize_base(url: str) -> str:
    return url.strip().rstrip("/")


def flask_alerts_up(
    base_url: str,
    timeout: float = 0.6,
    opener=urllib.request.urlopen,
) -> bool:
    """True when GET /api/alerts on this base returns JSON (Flask ModelWatch bus)."""
    request = urllib.request.Request(
        f"{_normalize_base(base_url)}/api/alerts",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = getattr(response, "code", 200)
            if int(status) >= 400:
                return False
            body = response.read(4096)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False
    text = body.lstrip()
    return text.startswith(b"[") or text.startswith(b"{")


def resolve_alerts_base_url(
    explicit: str | None = None,
    *,
    probe=flask_alerts_up,
) -> str:
    """Use Flask :5001/:5000 when that bus exists; otherwise the explicit URL or stub.

    A custom ``--alerts-url`` (tests, Cloud Run) is kept. The stub ``:8000``
    loses to a live Flask bus so a demo does not POST the empty sidecar.
    """
    chosen = _normalize_base(explicit) if (explicit or "").strip() else None
    flask_set = set(FLASK_ALERT_CANDIDATES)
    if chosen and chosen not in flask_set and chosen != STUB_ALERTS_URL:
        return chosen
    for candidate in FLASK_ALERT_CANDIDATES:
        if probe(candidate):
            if chosen and chosen != candidate:
                logger.info("Flask /api/alerts is up at %s; not using %s", candidate, chosen)
            return candidate
    return chosen or STUB_ALERTS_URL


def fetch_watches(
    base_url: str,
    timeout: float = 3.0,
    opener=urllib.request.urlopen,
    token: str = "",
) -> list[dict] | None:
    """Return watches, or None when the API cannot be reached.

    None means "no registry yet" — CamWatch keeps using the local camera file.
    An empty list means the registry is up and nobody has called set_watch.
    """
    headers = _headers(token)
    headers["Accept"] = "application/json"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/watches",
        headers=headers,
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
