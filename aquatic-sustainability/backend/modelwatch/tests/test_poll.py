"""ModelWatch pass with a fake bus and a fake flood response."""

from modelwatch.poll import Poller

GALVESTON = [-95.0, 29.2, -94.7, 29.4]
PANHANDLE = [-102.0, 34.2, -100.2, 35.8]


class FakeClients:
    def __init__(self, flood_prob: float, watches: list[dict], drought: list | None = None) -> None:
        self.flood_prob = flood_prob
        self.watches = watches
        self.drought_regions = drought or []
        self.posted: list[dict] = []
        self.business_calls: list[dict] = []
        self.flood_calls: list[tuple[float, float]] = []
        self.coral_calls = 0

    def list_watches(self) -> list[dict]:
        return self.watches

    def flood_risk(self, lat: float, lon: float) -> dict:
        self.flood_calls.append((lat, lon))
        return {
            "status": "finished",
            "cached": False,
            "result": {
                "center": {"lat": lat, "lon": lon},
                "points": [{"lat": lat, "lon": lon, "prob": self.flood_prob, "risk": "warning"}],
            },
        }

    def drought(self) -> list:
        return self.drought_regions

    def coral(self) -> dict:
        self.coral_calls += 1
        raise AssertionError("Galveston must not request coral")

    def businesses(self, bbox: list[float], types: list[str]) -> dict:
        self.business_calls.append({"bbox": bbox, "types": types})
        return {
            "source": "google",
            "truncated": False,
            "businesses": [
                {
                    "place_id": "pier",
                    "name": "Pier Cafe",
                    "lat": 29.3,
                    "lon": -94.85,
                    "types": ["restaurant"],
                    "phone": None,
                }
            ],
        }

    def publish(self, alert: dict) -> dict:
        self.posted.append(alert)
        return {"deduped": False}


def _watch(geofence_id: str, bbox: list[float] | None) -> dict:
    return {
        "id": geofence_id,
        "geofence_id": geofence_id,
        "bbox": bbox,
        "county": None if bbox else "Harris",
        "sources": ["model"],
    }


def test_flood_probability_062_publishes_warning() -> None:
    clock = {"now": 1_000.0}
    client = FakeClients(0.62, [_watch("galveston-county", GALVESTON)])
    poller = Poller(client, now=lambda: clock["now"], dedupe_s=3600)
    posted = poller.once()
    assert len(posted) == 1
    alert = posted[0]
    assert alert["source"] == "model"
    assert alert["severity"] == "warning"
    assert alert["dedupe_key"] == "model:galveston-county:flood"
    assert alert["evidence"]["raw"]["model"] == "DualCNN-LSTM"
    assert alert["evidence"]["raw"]["max_prob"] == 0.62
    assert alert["evidence"]["raw"]["trained"] is True
    assert "0.62" in alert["summary"]
    assert "delayed" in alert["summary"]
    assert alert["evidence"]["raw"]["businesses"][0]["name"] == "Pier Cafe"
    assert client.business_calls[0]["types"] == [
        "restaurant",
        "lodging",
        "marina",
        "supermarket",
        "pharmacy",
        "gas_station",
        "campground",
    ]
    assert client.coral_calls == 0
    clock["now"] = 1_100.0
    assert poller.once() == []
    client.flood_prob = 0.8
    clock["now"] = 1_200.0
    upgraded = poller.once()
    assert len(upgraded) == 1
    assert upgraded[0]["severity"] == "critical"


def test_flood_probability_02_publishes_nothing() -> None:
    client = FakeClients(0.2, [_watch("galveston-county", GALVESTON)])
    posted = Poller(client, now=lambda: 0.0, dedupe_s=3600).once()
    assert posted == []
    assert client.posted == []
    assert client.flood_calls
    assert client.business_calls == []
    assert client.coral_calls == 0


def test_dummy_drought_is_labeled_untrained() -> None:
    region = {
        "name": "Texas Panhandle",
        "risk": 0.75,
        "coords": [
            {"lat": 34.2, "lng": -102.0},
            {"lat": 35.8, "lng": -102.0},
            {"lat": 35.8, "lng": -100.2},
            {"lat": 34.2, "lng": -100.2},
        ],
    }
    client = FakeClients(0.2, [_watch("panhandle", PANHANDLE)], drought=[region])
    posted = Poller(client, now=lambda: 0.0, dedupe_s=3600).once()
    assert len(posted) == 1
    alert = posted[0]
    assert alert["severity"] == "watch"
    assert alert["dedupe_key"] == "model:panhandle:drought"
    assert alert["evidence"]["raw"]["trained"] is False
    assert alert["evidence"]["raw"]["hazard"] == "drought"
    lowered = alert["summary"].lower()
    assert "dummy" in lowered
    assert "hardcoded" in lowered


def test_county_only_watch_is_skipped() -> None:
    client = FakeClients(0.9, [_watch("harris", None)])
    assert Poller(client, now=lambda: 0.0).once() == []
    assert client.flood_calls == []
