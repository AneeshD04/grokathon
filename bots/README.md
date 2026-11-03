# bots/

**Owner:** Athithan (`@athithan-elamaran1`, `agent-athithan`)

Grok Bot workers live here. `TEAM.md` handle update is issue #2 (`@AneeshD04`); this lane does not edit that file.

## CamWatch (`camwatch/`)

Issue #17. The default camera list is the Houston TranStar seed in `bots/data/transtar_cameras.json` (first **8**). `--city pinellas` uses the FL511 seed in `bots/data/fl511_cameras.json` as the backup city. Each pass classifies **one** new JPEG, and `POST`s `/api/alerts` when the class **changes**. A loop waits **20s** (allowed range 15–30). That pace is the camera slice of the Grok cap on #33.

Live stills are classified by `grok_client.classify_frame`. Those labels map onto the #17 classes: dry → all-clear, wet / standing water → standing water, impassable / people in water → overtopped road. The filename fallback (`flooded-road.jpg`) runs only if that call raises `GrokClientError`, or when you pass `--fixture`.

Houston runs also import `feeds.flood_warnings.load_warnings` and post one alert per sensor id (saved point 145, JF13-3, water above bank). The bus has no `transtar` source yet, so the posted `source` is `usgs` and `evidence.raw.feed` is `transtar-flood-warning`.

Vision classes (issue #17 and `docs/SAFETY-AGENT-DESIGN.md`): standing water, overtopped road, debris, smoke, all-clear. `CAMERA-SOURCES.md` also mentions crowd; this worker does not emit that class.

Alert JSON matches the design doc and Devanshu's #11 `POST /api/alerts` body: `source`, `severity`, `lat`, `lon`, `geofence_id`, `title`, `summary`, `evidence`, `dedupe_key`, `ts`. A flooded roadway uses `dedupe_key` `cam:{id}:water_over_road` and severity `critical`.

### Run

From this directory:

```bash
# One-pass spoken demo. Loads the 8 cameras in data/camwatch_default.json,
# fetches the first still (Galveston Ferry), classifies it once, and stops.
# --loop is the worker below and does not run with --card.
python -m camwatch --card

# Same card, first camera only:
python demo_card.py

# Demo inject. --fixture does not call xAI:
mkdir -p camwatch/fixtures/inbox
cp camwatch/fixtures/flooded-road.jpg camwatch/fixtures/inbox/
python -m camwatch --once --fixture --sink file --out /tmp/camwatch-alerts.jsonl --inbox camwatch/fixtures/inbox --cameras camwatch/cameras.example.json

# Live Houston stills (TranStar, cap 8) plus the flood-warning loader.
# grok_client reads XAI_API_KEY from the environment or the gitignored .env.
python -m camwatch --once --ignore-watches --sink file --out /tmp/camwatch-alerts.jsonl

# Backup city:
python -m camwatch --once --city pinellas --ignore-watches

# Demo window only — do not leave this running overnight:
python -m camwatch --loop --ignore-watches
```

`--sink file` writes the same JSON when you are not running the sidecar. `--sink http` (the default) posts to `$ALERTS_BASE_URL/api/alerts` and, if the bus is up, honors `GET /api/watches`. A registry with no `camera` source samples nothing. Pass `--ignore-watches` for the inbox inject while some other watch is registered. There is no UI "on screen" flag yet; that stop signal is the watch list.

Class memory is in-process: the same JPEG is not posted twice until CamWatch restarts. The bus also dedupes an identical `dedupe_key` for 60s (#11). A failed POST is retried next pass without a second vision call.

### Keys

`XAI_API_KEY` is read by `grok_client` from the environment or the gitignored `.env`. Do not commit that file. A `GrokClientError` (missing key, HTTP error, bad label) falls back to the filename or a sidecar `image.jpg.json`. `flooded-road.jpg` maps to overtopped road. `GROK_MAX_RPM` defaults to **2**; when the window is full the frame is skipped and is not relabeled from its filename. `--fixture` skips xAI entirely.

`ALERT_BUS_TOKEN`, when the sidecar has it set, is sent as `X-Alert-Bus-Token`. It is not written into the alert or the log. `thumb_url` is null for an inbox drop and an http(s) URL for a live still.

### Proof

```bash
python -m unittest tests.test_flooded_road tests.test_demo_card -q
```

`test_flooded_road` drops `camwatch/fixtures/flooded-road.jpg` into a folder and asserts the alert. `test_demo_card` checks the one-pass card with a fake still and a fake vision call, so it does not hit the network.
