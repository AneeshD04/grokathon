# ModelWatch

Separate process. It polls watches whose `sources` include `model`, samples the bbox centroid, and publishes `source: "model"` alerts on the port-8000 bus. It does not send SMS or email and it does not call `/api/notify`.

Run it from `aquatic-sustainability/backend` so `python -m modelwatch` can import the package:

```bash
python -m modelwatch.poll --once
python -m modelwatch.loop
```

Flask must already be serving flood, drought, and coral. The alert bus must already be serving watches, nearby businesses, and alerts.

## What one pass does

- `GET /api/watches` on the bus. County-only watches with no bbox are skipped.
- One `POST /api/flood-risk` per watch, at the centroid. Probability `>= 0.5` is `warning`; `>= 0.75` is `critical`.
- `GET /api/coral-bleaching` only when the watch bbox intersects the Great Barrier Reef (lon 142–154, lat -24–-10). Galveston does not.
- `GET /api/drought` dummy polygons. A centroid inside a polygon with `risk >= 0.7` publishes `severity: watch` with `evidence.raw.trained: false`.
- `POST /api/businesses/nearby` with restaurant, lodging, marina, supermarket, pharmacy, gas_station, and campground, cap 20. A fixture or an empty list still publishes the alert, and `evidence.raw.businesses_reason` says why.
- `POST /api/alerts`. The same `dedupe_key` is not posted again until the severity changes or 60 minutes pass.

## Env

| Name | Default | Role |
| --- | --- | --- |
| `FLASK_BASE_URL` | `http://127.0.0.1:5001` | Flood, drought, coral |
| `ALERT_BUS_URL` | `http://127.0.0.1:8000` | Watches, businesses, alerts |
| `ALERT_BUS_TOKEN` | unset | Sent as `x-alert-bus-token` when the bus requires it |
| `MODELWATCH_INTERVAL_S` | `600` | Loop sleep |
| `MODELWATCH_DEDUPE_S` | `3600` | Worker repost window |
| `MODELWATCH_TIMEOUT_S` | `120` | HTTP timeout |
| `FLOOD_WARNING_PROB` | `0.5` | Flood warning |
| `FLOOD_CRITICAL_PROB` | `0.75` | Flood critical |
| `DROUGHT_WATCH_RISK` | `0.7` | Dummy drought watch |
| `FAST_START_FLOOD_DATA` | unset | `1` marks the flood alert as synthetic |

Tests use a fake client. They do not call the flood model or Twilio:

```bash
python -m pytest modelwatch/tests -q
```
