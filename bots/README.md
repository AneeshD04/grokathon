# bots/

**Owner:** Athithan (`@athithan-elamaran1`, `agent-athithan`)

Grok Bot workers live here. `TEAM.md` handle update is issue #2 (`@AneeshD04`); this lane does not edit that file.

## CamWatch (`camwatch/`)

Issue #17 / #94. The default camera list is the Houston TranStar seed in `bots/data/camwatch_default.json` (8 Houston/Galveston stills). `--city pinellas` uses the FL511 seed in `bots/data/fl511_cameras.json` as the backup city.

**Default is one pass, not a loop.** FAST/heuristic classifies flood/water from the JPEG (no Grok). `--vision grok` is **one** classify then exit. `POST`s Flask `/api/alerts` when the class **changes**. `--loop` waits **20s** (15–30) and must not run overnight.

Live stills default to the FAST color heuristic. `--vision grok` uses `grok_client.classify_frame` once. Those labels map onto the #17 classes: dry → all-clear, wet / standing water → standing water, impassable / people in water → overtopped road. The filename fallback (`flooded-road.jpg`) runs if Grok raises `GrokClientError`, or when you pass `--fixture`.

Houston runs also import `feeds.flood_warnings.load_warnings` and post one alert per sensor id (saved point 145, JF13-3, water above bank). The bus has no `transtar` source yet, so the posted `source` is `usgs` and `evidence.raw.feed` is `transtar-flood-warning`.

Vision classes (issue #17 and `docs/SAFETY-AGENT-DESIGN.md`): standing water, overtopped road, debris, smoke, all-clear. `CAMERA-SOURCES.md` also mentions crowd; this worker does not emit that class.

Alert JSON matches the design doc and Devanshu's #11 `POST /api/alerts` body: `source`, `severity`, `lat`, `lon`, `geofence_id`, `title`, `summary`, `evidence`, `dedupe_key`, `ts`. A flooded roadway uses `dedupe_key` `cam:{id}:water_over_road` and severity `critical`.

### Run

From this directory (`bots/`):

Flask (`aquatic-sustainability/backend`, `python run.py`, port **5001**) must already be up so `/api/alerts` exists. Then **one demo command** from this directory:

```bash
python -m camwatch --once
```

That loads the 8 Houston/Galveston TranStar JPEGs, FAST-classifies flood/water (no Grok), POSTs Flask `/api/alerts` when a class is not all-clear, and exits. It does not loop. Stub `:8000` is not used when Flask answers on `:5001` or `:5000`.

```bash
# Spoken card (one still, then exit):
python -m camwatch --card

# Optional single Grok classify, then exit (burns quota):
python -m camwatch --once --vision grok

# Demo inject. --fixture does not call xAI:
mkdir -p camwatch/fixtures/inbox
cp camwatch/fixtures/flooded-road.jpg camwatch/fixtures/inbox/
python -m camwatch --once --fixture --sink file --out /tmp/camwatch-alerts.jsonl --inbox camwatch/fixtures/inbox --cameras camwatch/cameras.example.json

# File sink when Flask is down:
python -m camwatch --once --sink file --out /tmp/camwatch-alerts.jsonl

# Demo window only — do not leave this running overnight:
python -m camwatch --loop
```

`--sink file` writes the same JSON when you are not running Flask. `--sink http` (the default) probes Flask `:5001` then `:5000` and POSTs `$ALERTS_BASE_URL/api/alerts` only if you set that env and Flask is down. One-pass ignores `GET /api/watches` so ModelWatch's model-only seed does not sample nothing. Pass `--honor-watches` for the loop.

Class memory is in-process: the same JPEG is not posted twice until CamWatch restarts. The bus also dedupes an identical `dedupe_key` for 60s (#11). A failed POST is retried next pass without a second vision call.

### Keys

`XAI_API_KEY` is read by `grok_client` from the environment or the gitignored `.env`. Do not commit that file. A `GrokClientError` (missing key, HTTP error, bad label) falls back to the filename or a sidecar `image.jpg.json`. `flooded-road.jpg` maps to overtopped road. `GROK_MAX_RPM` defaults to **2**; when the window is full the frame is skipped and is not relabeled from its filename. `--fixture` skips xAI entirely.

`ALERT_BUS_TOKEN`, when the sidecar has it set, is sent as `X-Alert-Bus-Token`. It is not written into the alert or the log. `thumb_url` is null for an inbox drop and an http(s) URL for a live still.

### Proof

```bash
python -m unittest tests.test_flooded_road tests.test_demo_card tests.test_camwatch_flask -q
```

`test_flooded_road` drops `camwatch/fixtures/flooded-road.jpg` into a folder and asserts the alert. `test_demo_card` checks the one-pass card with a fake still and a fake vision call, so it does not hit the network. `test_camwatch_flask` checks Flask bus preference and the FAST heuristic.
