from fastapi.testclient import TestClient

from app.main import app
from places.models import Business

GALVESTON_BBOX = [-95.0, 29.2, -94.7, 29.4]
INSIDE_POLYGON = [
    [-94.9, 29.2],
    [-94.7, 29.2],
    [-94.7, 29.4],
    [-94.9, 29.4],
]


def test_requires_bbox_or_polygon(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    client = TestClient(app)
    assert client.post("/api/businesses/nearby", json={}).status_code == 422


def test_missing_key_returns_galveston_fixtures(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    client = TestClient(app)
    response = client.post("/api/businesses/nearby", json={"bbox": GALVESTON_BBOX})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fixture"
    assert body["truncated"] is False
    assert body["businesses"]
    for business in body["businesses"]:
        assert business["phone"] is None
        assert GALVESTON_BBOX[0] <= business["lon"] <= GALVESTON_BBOX[2]
        assert GALVESTON_BBOX[1] <= business["lat"] <= GALVESTON_BBOX[3]


def test_google_results_drop_points_outside_the_polygon(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")

    def fake_search(center_lat, center_lon, radius_m, api_key):
        inside = _place("in", 29.3, -94.8, phone="+1-409-555-0100")
        outside = [_place(f"out-{index}", 30.0, -95.5) for index in range(19)]
        return [inside, *outside]

    monkeypatch.setattr("places.service.search_nearby", fake_search)
    client = TestClient(app)
    response = client.post(
        "/api/businesses/nearby",
        json={"bbox": [-95.5, 30.0, -95.4, 30.1], "polygon": INSIDE_POLYGON},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "google"
    assert body["truncated"] is True
    assert [item["place_id"] for item in body["businesses"]] == ["in"]
    assert body["businesses"][0]["phone"] == "+1-409-555-0100"


def _place(place_id: str, lat: float, lon: float, phone: str | None = None) -> Business:
    return Business(
        place_id=place_id,
        name=place_id,
        lat=lat,
        lon=lon,
        phone=phone,
        website=None,
        types=["hospital"],
        maps_url=f"https://maps.google.com/?q=place_id:{place_id}",
    )
