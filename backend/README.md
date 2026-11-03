# backend/

**Owner:** [@DevanshuShahs](https://github.com/DevanshuShahs) (`agent-devanshu`)

Other agents: do not edit this tree. Open a `handoff` or comment `@DevanshuShahs` on a Task.

## Alert bus (issue #11)

In-memory watch registry and alert bus. A `POST /api/alerts` is pushed to every open SSE client before the response returns. Redis is not required.

Alert JSON matches `docs/SAFETY-AGENT-DESIGN.md`. `shared/` stays on issue #8.

### Run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

`ALERT_DEDUPE_WINDOW_S` defaults to `60`. The same `dedupe_key` inside that window returns the original alert with `deduped: true` and does not broadcast again.

### Watches

`POST /api/watches` needs `sources` plus a `county` and/or `bbox` (`[minLon, minLat, maxLon, maxLat]`).

```bash
curl -s -X POST localhost:8000/api/watches \
  -H 'content-type: application/json' \
  -d '{"county":"Galveston County","sources":["nws","camera"]}'
```

`GET /api/watches` lists them.

### Alerts

```bash
curl -N localhost:8000/api/alerts/stream
```

```bash
curl -s -X POST localhost:8000/api/alerts \
  -H 'content-type: application/json' \
  -d '{"source":"camera","severity":"warning","lat":29.3,"lon":-94.8,"geofence_id":"galveston-county","title":"Water over roadway","summary":"Vision: standing water covering two lanes.","evidence":{"thumb_url":"https://example.test/frame.jpg","raw":{}},"dedupe_key":"cam:buffalo-1:water_over_road"}'
```

`GET /api/alerts?since=` takes an ISO-8601 timestamp and returns alerts with `ts >= since`. SSE events use `event: alert` and a JSON `data` line.

### Tests

```bash
cd backend && .venv/bin/python -m pytest
```
