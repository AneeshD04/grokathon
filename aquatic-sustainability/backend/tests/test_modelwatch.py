"""In-process ModelWatch: cache-only flood, on-disk coral, Flask alert bus."""

import json
import os
import sys
import unittest

from flask import Flask

os.environ.setdefault("SECRET_KEY", "test-secret-for-modelwatch")
os.environ.setdefault("MODELWATCH_BACKGROUND", "0")

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "modelwatch",
    os.path.join(BACKEND_DIR, "app", "modelwatch.py"),
)
mw = importlib.util.module_from_spec(_spec)
sys.modules["modelwatch"] = mw
_spec.loader.exec_module(mw)

GALVESTON = [-95.0, 29.2, -94.7, 29.4]
GBR = [142.0, -24.0, 154.0, -10.0]


class FakeRedis:
    def __init__(self, mapping=None):
        self.mapping = dict(mapping or {})
        self.gets = []

    def get(self, key):
        self.gets.append(key)
        value = self.mapping.get(key)
        if value is None or isinstance(value, (bytes, str)):
            return value
        return json.dumps(value)


def _flood_payload(lat, lon, prob):
    return {
        "center": {"lat": lat, "lon": lon},
        "points": [
            {"lat": lat, "lon": lon, "prob": prob, "risk": "warning"},
            {"lat": lat + 0.01, "lon": lon + 0.01, "prob": max(0.0, prob - 0.1), "risk": "medium"},
        ],
    }


class ModelWatchTests(unittest.TestCase):
    def setUp(self):
        mw.state.reset()
        os.environ.pop("FAST_START_FLOOD_DATA", None)

    def tearDown(self):
        mw.state.reset()

    def test_cache_hit_062_publishes_warning(self):
        watch = mw.create_watch(
            {"geofence_id": "galveston-county", "bbox": GALVESTON, "sources": ["model"]}
        )
        lat, lon = mw.centroid(GALVESTON)
        key = f"flood_risk_{lat:.2f}_{lon:.2f}"
        redis = FakeRedis({key: _flood_payload(lat, lon, 0.62)})
        report = mw.poll_once(redis, now=1_000.0)
        self.assertEqual(report["posted"], 1)
        self.assertFalse(report["nasa_redownload"])
        alert = report["alerts"][0]
        self.assertEqual(alert["source"], "model")
        self.assertEqual(alert["severity"], "warning")
        self.assertEqual(alert["dedupe_key"], "model:flood-risk:galveston-county:0.62")
        self.assertEqual(alert["evidence"]["model"], "DualCNN-LSTM")
        self.assertEqual(alert["evidence"]["max_prob"], 0.62)
        self.assertTrue(alert["evidence"]["trained"])
        self.assertFalse(alert["evidence"]["synthetic"])
        self.assertIn("0.62", alert["summary"])
        self.assertIn("delayed", alert["summary"])
        self.assertIn("Not a water-quality lab result", alert["summary"])
        self.assertEqual(alert["impacted_businesses"], [])
        self.assertEqual(mw.poll_once(redis, now=1_100.0)["posted"], 0)

        redis.mapping[key] = _flood_payload(lat, lon, 0.80)
        upgraded = mw.poll_once(redis, now=1_200.0)
        self.assertEqual(upgraded["posted"], 1)
        self.assertEqual(upgraded["alerts"][0]["severity"], "critical")
        self.assertIs(watch, mw.get_watch(watch["id"]))

    def test_no_cache_skips_live_inference(self):
        mw.create_watch(
            {"geofence_id": "galveston-county", "bbox": GALVESTON, "sources": ["model"]}
        )
        redis = FakeRedis()
        report = mw.poll_once(redis, now=1.0)
        self.assertEqual(report["posted"], 0)
        self.assertEqual(mw.list_alerts(), [])
        self.assertTrue(any("NASA" in (item.get("reason") or "") for item in report["skipped"]))
        self.assertTrue(report["nasa_redownload"] is False)
        self.assertTrue(any(k.startswith("flood_risk_") for k in redis.gets))
        self.assertTrue(any(k.startswith("flood_inference:") for k in redis.gets))

    def test_below_threshold_publishes_nothing(self):
        mw.create_watch(
            {"geofence_id": "galveston-county", "bbox": GALVESTON, "sources": ["model"]}
        )
        lat, lon = mw.centroid(GALVESTON)
        key = f"flood_risk_{lat:.2f}_{lon:.2f}"
        redis = FakeRedis({key: _flood_payload(lat, lon, 0.2)})
        report = mw.poll_once(redis, now=1.0)
        self.assertEqual(report["posted"], 0)
        self.assertEqual(mw.list_alerts(), [])
        self.assertTrue(any("below warning" in (item.get("reason") or "") for item in report["skipped"]))

    def test_galveston_does_not_load_coral(self):
        mw.create_watch(
            {"geofence_id": "galveston-county", "bbox": GALVESTON, "sources": ["model"]}
        )
        called = {"n": 0}

        def boom():
            called["n"] += 1
            raise AssertionError("Galveston must not load coral")

        original = mw.load_coral_bundle
        mw.load_coral_bundle = boom
        try:
            mw.poll_once(FakeRedis(), now=1.0)
        finally:
            mw.load_coral_bundle = original
        self.assertEqual(called["n"], 0)

    def test_coral_gbr_watch_publishes_warning(self):
        mw.create_watch({"geofence_id": "gbr-demo", "bbox": GBR, "sources": ["model"]})
        bundle = {
            "centroids": [{"lat": -18.0, "lon": 147.0, "cluster_id": 0}],
            "models": {
                "lstm": {
                    "prob_severe": [[0.1, 0.61]],
                    "predicted_class": [[0, 1]],
                }
            },
        }
        report = mw.poll_once(FakeRedis(), now=1.0, coral_bundle=bundle)
        coral = [item for item in report["alerts"] if "coral" in item["dedupe_key"]]
        self.assertEqual(len(coral), 1)
        self.assertEqual(coral[0]["severity"], "warning")
        self.assertEqual(coral[0]["evidence"]["model"], "gbr-lstm")
        self.assertTrue(coral[0]["evidence"]["trained"])
        self.assertIn("prob_severe 0.61", coral[0]["summary"])

    def test_county_only_watch_is_skipped(self):
        mw.create_watch({"county": "Harris County", "sources": ["model"]})
        report = mw.poll_once(FakeRedis({}), now=1.0)
        self.assertEqual(report["posted"], 0)
        self.assertTrue(any("no bbox" in (item.get("reason") or "") for item in report["skipped"]))

    def test_flask_poll_models_and_sse_bus(self):
        app = Flask(__name__)
        app.redis = FakeRedis()
        app.register_blueprint(mw.bp, url_prefix="/api")
        with app.app_context():
            created = mw.create_watch(
                {"geofence_id": "galveston-county", "bbox": GALVESTON, "sources": ["model"]}
            )
            lat, lon = mw.centroid(GALVESTON)
            key = f"flood_risk_{lat:.2f}_{lon:.2f}"
            app.redis.mapping[key] = _flood_payload(lat, lon, 0.62)
        client = app.test_client()
        response = client.post(f"/api/watches/{created['id']}/poll-models")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["posted"], 1)
        listed = client.get("/api/alerts")
        self.assertEqual(listed.status_code, 200)
        alerts = listed.get_json()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["source"], "model")
        status = client.get("/api/modelwatch/status")
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.get_json()["nasa_redownload"])
        self.assertEqual(status.get_json()["flood_mode"], "redis-cache-only")


if __name__ == "__main__":
    unittest.main()
