# bots/

**Owner:** Athithan (`@athithan-elamaran1`, `agent-athithan`)

Grok Bot workers live here. `TEAM.md` handle update is issue #2 (`@AneeshD04`); this lane does not edit that file.

## CamWatch (`camwatch/`)

Issue #17. Samples at most **8** cameras, pulls a JPEG every **20s** (allowed range 15–30), classifies it, and `POST`s `/api/alerts` when the class **changes**.

Vision classes (issue #17 and `docs/SAFETY-AGENT-DESIGN.md`): standing water, overtopped road, debris, smoke, all-clear. `CAMERA-SOURCES.md` also mentions crowd; this worker does not emit that class.

Alert JSON matches the design doc and Devanshu's #11 `POST /api/alerts` body: `source`, `severity`, `lat`, `lon`, `geofence_id`, `title`, `summary`, `evidence`, `dedupe_key`, `ts`. A flooded roadway uses `dedupe_key` `cam:{id}:water_over_road` and severity `critical`.

### Run

From this directory:

```bash
# Demo inject, no alert bus and no XAI_API_KEY required:
mkdir -p camwatch/fixtures/inbox
cp camwatch/fixtures/flooded-road.jpg camwatch/fixtures/inbox/
python -m camwatch --once --sink file --out /tmp/camwatch-alerts.jsonl

# Live bus (issue #11, default http://127.0.0.1:8000):
python -m camwatch
```

`--sink file` is the stand-in until `POST /api/alerts` is on main. `--sink http` posts to `$ALERTS_BASE_URL/api/alerts` and, if the bus is up, honors `GET /api/watches`. Pass `--ignore-watches` when you only want the local file (for example the inbox inject while another watch is registered).

Class memory is in-process: the same JPEG is not posted twice until CamWatch restarts. The bus also dedupes an identical `dedupe_key` for 60s (#11).

### Keys

`XAI_API_KEY` optional (`docs/MISSING-KEYS.md`). When it is unset, classification uses the filename or a sidecar `image.jpg.json` with `{"class":"overtopped_road"}`. `flooded-road.jpg` maps to overtopped road. Set `XAI_VISION_MODEL` to override the default `grok-4.7`.

### Proof

```bash
python -m unittest tests.test_flooded_road -v
```

That test drops `camwatch/fixtures/flooded-road.jpg` into a folder and asserts the alert.
