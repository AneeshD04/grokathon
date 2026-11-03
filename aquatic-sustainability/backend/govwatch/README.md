# GovWatch

In-tree poller on the Aquatic Flask app. Pulls **NWS alerts** and **USGS gage height**, caches the responses, and posts `source: "nws"` / `source: "usgs"` alerts onto the existing Flask bus (`POST /api/alerts`).

No API key. No Grok. No Twilio. Does not edit `app/__init__.py`, `routes.py`, or `modelwatch.py`.

## Demo replay (no network)

From `aquatic-sustainability/backend`:

```bash
python -m govwatch --once --sink file
```

That reads the recorded Texas Flash Flood Warning + Galveston-area USGS snapshot in `govwatch/fixtures/` and writes `govwatch-alerts.jsonl`. The NWS feature is inside the Galveston bbox so the map can show a pin at ~29.33, -94.87.

If Flask is already running (`python run.py`):

```bash
python -m govwatch --once --sink http --alerts-url http://127.0.0.1:5001
```

`--live` hits `api.weather.gov/alerts/active?area=TX` and USGS IV for the bbox. Responses are cached 10 minutes. If a live Texas flood alert intersects the bbox, it publishes the same way. Tests never call the network.

## Env

| Name | Default | Role |
| --- | --- | --- |
| `GOVWATCH_BBOX` | `-95.17,29.02,-94.37,29.67` | Galveston County |
| `GOVWATCH_GEOFENCE_ID` | `galveston-county` | Alert `geofence_id` |
| `GOVWATCH_USGS_FLOOD_STAGE_FT` | `4.0` | Publish USGS only above this |
| `GOVWATCH_DEDUPE_S` | `3600` | Same `dedupe_key` is skipped |
| `ALERTS_BASE_URL` | `http://127.0.0.1:5001` | Flask bus |
| `GOVWATCH_SINK` | `http` | `http` or `file` |

```bash
python -m pytest govwatch/tests -q
```
