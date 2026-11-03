# backend/

**Owner:** [@DevanshuShahs](https://github.com/DevanshuShahs) (`agent-devanshu`)

Other agents: do not edit this tree. Open a `handoff` or comment `@DevanshuShahs` on a Task.

## Alert bus (issue #11)

In-memory watch registry and alert bus. A `POST /api/alerts` is pushed to every open SSE client before the response returns. Redis is not required.

This sidecar **does not send** SMS, email, phone calls, or 911. Fan-out notify is issue #13 (approval-PIN gated, `NOTIFY_DRY_RUN=1` by default, log only). `evidence.thumb_url` is stored, never fetched (no camera SSRF).

Alert JSON matches `docs/SAFETY-AGENT-DESIGN.md`. `shared/` stays on issue #8.

### Run

Bind localhost. Do not expose this port on a public interface without `ALERT_BUS_TOKEN`.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

| Env | Default | Meaning |
| --- | --- | --- |
| `ALERT_DEDUPE_WINDOW_S` | `60` | Same `dedupe_key` inside this window returns `{deduped: true}` and is not broadcast |
| `ALERT_BUS_TOKEN` | unset | If set, `/api/*` requires `X-Alert-Bus-Token` or `Authorization: Bearer` |
| `ALERT_BUS_CORS_ORIGINS` | localhost ports | Comma-separated origins. Use `*` only for throwaway local experiments |
| `ALERT_BUS_MAX_ALERTS` | `500` | Oldest alerts are dropped |
| `ALERT_BUS_MAX_WATCHES` | `200` | Further `POST /api/watches` returns `429` |
| `ALERT_BUS_MAX_SUBSCRIBERS` | `32` | Further SSE clients get `503` |

### Watches

`POST /api/watches` needs `sources` plus a `county` and/or `bbox` (`[minLon, minLat, maxLon, maxLat]`).

```bash
curl -s -X POST 127.0.0.1:8000/api/watches \
  -H 'content-type: application/json' \
  -d '{"county":"Galveston County","sources":["nws","camera"]}'
```

`GET /api/watches` lists them.

### Alerts

```bash
curl -N 127.0.0.1:8000/api/alerts/stream
```

```bash
curl -s -X POST 127.0.0.1:8000/api/alerts \
  -H 'content-type: application/json' \
  -d '{"source":"camera","severity":"warning","lat":29.3,"lon":-94.8,"geofence_id":"galveston-county","title":"Water over roadway","summary":"Vision: standing water covering two lanes.","evidence":{"thumb_url":"https://example.test/frame.jpg","raw":{}},"dedupe_key":"cam:buffalo-1:water_over_road"}'
```

`GET /api/alerts?since=` takes an ISO-8601 timestamp and returns alerts with `ts >= since`. SSE events use `event: alert` and a JSON `data` line.

### Tests

```bash
cd backend && .venv/bin/python -m pytest
```
