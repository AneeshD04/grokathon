# bots/

**Owner:** Athithan (`@athithan-elamaran1`, `agent-athithan`)

Grok Bot workers live here. `TEAM.md` handle update is issue #2 (`@AneeshD04`); this lane does not edit that file.

## CamWatch (`camwatch/`)

Issue #17. Up to **8** cameras are eligible. Each pass classifies **one** new JPEG (so a full set takes several intervals), and `POST`s `/api/alerts` when the class **changes**. A loop waits **20s** (allowed range 15–30) between passes. That one-call pace is the camera slice of the Grok cap on #33.

Vision classes (issue #17 and `docs/SAFETY-AGENT-DESIGN.md`): standing water, overtopped road, debris, smoke, all-clear. `CAMERA-SOURCES.md` also mentions crowd; this worker does not emit that class.

Alert JSON matches the design doc and Devanshu's #11 `POST /api/alerts` body: `source`, `severity`, `lat`, `lon`, `geofence_id`, `title`, `summary`, `evidence`, `dedupe_key`, `ts`. A flooded roadway uses `dedupe_key` `cam:{id}:water_over_road` and severity `critical`.

### Run

From this directory:

```bash
# Demo inject, no alert bus and no XAI_API_KEY required:
mkdir -p camwatch/fixtures/inbox
cp camwatch/fixtures/flooded-road.jpg camwatch/fixtures/inbox/
python -m camwatch --once --sink file --out /tmp/camwatch-alerts.jsonl

# Live bus on main (backend/, uvicorn port 8000). One pass by default:
python -m camwatch --ignore-watches
# Demo window only — do not leave this running overnight:
python -m camwatch --loop
```

`--sink file` writes the same JSON when you are not running the sidecar. `--sink http` (the default) posts to `$ALERTS_BASE_URL/api/alerts` and, if the bus is up, honors `GET /api/watches`. A registry with no `camera` source samples nothing. Pass `--ignore-watches` for the inbox inject while some other watch is registered. There is no UI "on screen" flag yet; that stop signal is the watch list.

Class memory is in-process: the same JPEG is not posted twice until CamWatch restarts. The bus also dedupes an identical `dedupe_key` for 60s (#11). A failed POST is retried next pass without a second vision call.

### Keys

`XAI_API_KEY` optional (`docs/MISSING-KEYS.md`). When it is unset, `GROK_MAX_RPM` is 0, the per-minute window is full, or xAI returns 429, classification uses the filename or a sidecar `image.jpg.json` with `{"class":"overtopped_road"}`. `flooded-road.jpg` maps to overtopped road. Unset `GROK_MAX_RPM` defaults to **2** (shared name with the chat proxy, not a CamWatch-only counter). Set `XAI_VISION_MODEL` to override the default `grok-4.7`.

`ALERT_BUS_TOKEN`, when the sidecar has it set, is sent as `X-Alert-Bus-Token`. It is not written into the alert or the log. `thumb_url` is null for an inbox drop and an http(s) URL for a live still.

### Proof

```bash
python -m unittest tests.test_flooded_road -v
```

That test drops `camwatch/fixtures/flooded-road.jpg` into a folder and asserts the alert.
