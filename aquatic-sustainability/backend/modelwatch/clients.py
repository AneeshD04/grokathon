"""HTTP calls from ModelWatch to Flask and the port-8000 alert bus."""

from __future__ import annotations

import os

import httpx

PLACE_TYPES = [
    "restaurant",
    "lodging",
    "marina",
    "supermarket",
    "pharmacy",
    "gas_station",
    "campground",
]


class HttpClients:
    """One-shot HTTP. ModelWatch does not import Twilio or call /api/notify."""

    def __init__(
        self,
        flask_base: str | None = None,
        bus_base: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.flask = (flask_base or os.environ.get("FLASK_BASE_URL", "http://127.0.0.1:5001")).rstrip("/")
        self.bus = (bus_base or os.environ.get("ALERT_BUS_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.timeout = timeout_s if timeout_s is not None else float(os.environ.get("MODELWATCH_TIMEOUT_S", "120"))
        token = os.environ.get("ALERT_BUS_TOKEN", "").strip()
        self.bus_headers = {"x-alert-bus-token": token} if token else {}

    def list_watches(self) -> list[dict]:
        response = httpx.get(f"{self.bus}/api/watches", headers=self.bus_headers, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, list):
            raise ValueError("GET /api/watches did not return a list")
        return body

    def flood_risk(self, lat: float, lon: float) -> dict:
        response = httpx.post(
            f"{self.flask}/api/flood-risk",
            json={"lat": lat, "lon": lon},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def drought(self) -> list:
        response = httpx.get(f"{self.flask}/api/drought", timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, list) else []

    def coral(self) -> dict:
        response = httpx.get(f"{self.flask}/api/coral-bleaching", timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {}

    def businesses(self, bbox: list[float], types: list[str]) -> dict:
        response = httpx.post(
            f"{self.bus}/api/businesses/nearby",
            headers=self.bus_headers,
            json={"bbox": bbox, "types": types, "limit": 20},
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {}

    def publish(self, alert: dict) -> dict:
        response = httpx.post(
            f"{self.bus}/api/alerts",
            headers=self.bus_headers,
            json=alert,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {}
