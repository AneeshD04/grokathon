"""HTTP + file helpers. NWS/USGS are public; no API key. No Grok."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

USER_AGENT = "grokathon-govwatch/1.0 (+https://github.com/AneeshD04/grokathon)"
NWS_URL = "https://api.weather.gov/alerts/active?status=actual&message_type=alert&area=TX"
USGS_URL = (
    "https://waterservices.usgs.gov/nwis/iv/"
    "?format=json&parameterCd=00065&siteStatus=active&bBox={bbox}"
)


class FetchError(Exception):
    pass


class MemoryCache:
    def __init__(self, ttl_s: float = 600.0, now: Callable[[], float] | None = None) -> None:
        self.ttl_s = ttl_s
        self.now = now or time.time
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        row = self._store.get(key)
        if row is None:
            return None
        stamped, value = row
        if self.now() - stamped >= self.ttl_s:
            return None
        return value

    def set(self, key: str, value: Any) -> Any:
        self._store[key] = (self.now(), value)
        return value


def http_get_json(
    url: str,
    *,
    timeout: float = 8.0,
    opener=urllib.request.urlopen,
) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"},
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise FetchError(f"GET {url} failed: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"GET {url} unreachable: {exc.reason}") from exc
    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise FetchError(f"GET {url} returned non-JSON") from exc
    if not isinstance(parsed, dict):
        raise FetchError(f"GET {url} returned a non-object")
    return parsed


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class FileAlertsClient:
    def __init__(self, path: Path) -> None:
        self.path = path

    def publish(self, alert: dict) -> dict:
        stored = dict(alert)
        record = {
            "alert": {
                "id": stored.pop("id", None) or uuid4().hex,
                **stored,
            },
            "deduped": False,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        return record


class HttpAlertsClient:
    def __init__(self, base_url: str, timeout: float = 5.0, opener=urllib.request.urlopen) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener

    def publish(self, alert: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/api/alerts",
            data=json.dumps(alert).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise FetchError(f"POST /api/alerts failed: HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise FetchError(f"POST /api/alerts unreachable: {exc.reason}") from exc
        parsed = json.loads(body.decode("utf-8"))
        if not isinstance(parsed, dict) or "alert" not in parsed:
            raise FetchError("POST /api/alerts response missing alert")
        return parsed
