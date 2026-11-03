# Safety Agent — high-level design (Grokathon)

## Verdict: possible for a 1-day demo if we scope location + sensors

A **Safety Agent** that sits on top of Aquatic Sustainability, talks to the user, and is fed by **small watchers** (X, government feeds, cameras) is a good Grokathon bet: it uses **Grok Bot + Grok (tools + vision)** on a real BDBI system, and it does not require retraining DualCNN-LSTM tonight.

Pitch: the BDBI app is **predictive**. Ours is **AI-native + real-time**. User marks a county/area → Safety Agent fans out **CamWatch** sub-agents on every mapped coastal/traffic cam in the bbox (cap 8 live vision workers; rest stay previewable on the map) plus NWS/USGS/X.

It is **not** possible to watch every camera in a metro or call 911. Demo: Houston–Galveston (or a Florida county), clickable camera pins, vision on a subset, **sandbox** notify (email/SMS to our numbers + a “would have notified” org roster).

Camera inventory: [`CAMERA-SOURCES.md`](CAMERA-SOURCES.md).

## What already exists (agent context)

The agent should treat these as tools, not rebuild them:

- Flood probabilities: `POST /api/flood-risk` `{lat, lon}`
- Coral GBR bundle: `GET /api/coral-bleaching`
- Hardcoded drought/flood polygons: `GET /api/drought`, `GET /api/flood`
- News: `GET /api/news`
- Maps UI pages for human follow-up

Watchers add **streaming, local, unofficial** signal the models never see (a flooded underpass on a traffic cam; a county emergency tweet; a USGS gauge spike).

## Target user story (demo)

1. User draws/selects a **county or coastal bbox** (not just a point). Chat: “Watch Galveston County.”
2. Map fills with **live source pins** (cameras + NWS zones + USGS gauges). Click a pin → watch the feed yourself.
3. Safety Agent starts sub-agents on coastal cams in that bbox. Vision classes: standing water, overtopped road, debris, smoke, all-clear.
4. **X/news watcher** for geo + keywords (`flood`, `storm surge`, `road closed`, county name).
5. If severity ≥ warning: agent **notifies** — Grok drafts the message; we send sandbox SMS/email and show the org roster we *would* call (county EM, NWS, USCG sector, 311). No live 911.
6. Agent also pulls the **old** flood model so judges see predictive vs now.

## Architecture

```
                    ┌────────────┐
  User  ───────────►│  Safety UI │◄──── WebSocket / SSE alerts
                    │  (Kabir)   │
                    └─────┬──────┘
                          │ chat
                    ┌─────▼──────────┐
                    │ Safety Agent   │  Grok + tools  (Athithan / Grok Bot)
                    │  - query_flood │
                    │  - query_coral │
                    │  - get_alerts  │
                    │  - set_watch   │
                    │  - notify_orgs │
                    └─────┬──────────┘
                          │
                    ┌─────▼──────────┐
                    │ Alert bus      │  Redis list or in-proc queue (Devanshu)
                    │ + Watch registry│
                    └─┬────┬────┬────┘
                      │    │    │
              GovWatch XWatch CamWatch   (workers / Grok Bots)
                      │    │    │
              NWS/USGS  X   JPEG frames → vision
```

**Do not** put watchers inside the Flask request path. They are long-running. Flask (or a small FastAPI sidecar) only: CRUD watches, poll/push alerts, proxy Grok chat.

### Alert schema (shared contract → `shared/`)

```json
{
  "id": "ulid",
  "ts": "ISO-8601",
  "source": "camera|nws|usgs|x|model|news",
  "severity": "info|watch|warning|critical",
  "lat": 29.76,
  "lon": -95.37,
  "geofence_id": "houston-demo",
  "title": "Water over roadway",
  "summary": "Vision: standing water covering two lanes.",
  "evidence": { "thumb_url": "...", "raw": {} },
  "dedupe_key": "cam:buffalo-1:water_over_road"
}
```

Dedup by `dedupe_key` + time window so cameras don’t spam.

## Sub-agents (watchers)

Each watcher is a loop: `pull → normalize → (optional Grok classify) → publish alert if new`.

| Watcher | Data | Auth | Hackathon plan |
| --- | --- | --- | --- |
| **Gov** | [NWS alerts](https://api.weather.gov/alerts) (no key), [USGS IV](https://waterservices.usgs.gov/), [NASA EONET](https://eonet.gsfc.nasa.gov/api/v3/events) | None | **Ship this first.** Real and impressive. |
| **Camera** | TranStar, FL511, NDBC BuoyCAM, WebCOOS, USGS CoastCam — see `CAMERA-SOURCES.md` | Usually none; WebCOOS token | List **all** in bbox on the map. Vision workers on ≤8. JPEG every 15–30s. MP4 fallback. |
| **X / social** | X recent search, Grok web search, or RSS | Bearer optional | **In demo.** Geo + disaster keywords. Fixture tweets if no token. |
| **Notify** | Grok-drafted email/SMS; org roster JSON | Twilio/email sandbox | **Never** auto-call 911. Log + send to team phones. |
| **Model** | Existing `/api/flood-risk` on a timer | Earthdata or synthetic | Re-query the pin every N minutes; alert if prob jumps. |

Grok Bots can *be* the watchers (each bot owns a source) and `@mention` / POST into the bus. GitHub Issues stay the **team** bus; the **runtime** bus is Redis/HTTP, not GitHub.

## Safety Agent tools (Grok)

- `set_watch(geofence, sources[])`
- `list_alerts(since, severity)`
- `get_flood_risk(lat, lon)` → existing Flask
- `get_coral_summary()` → existing Flask
- `get_nws(lat, lon)`
- `list_cameras(bbox)` / `ask_camera(camera_id)`
- `notify_orgs(severity, geofence, summary)` → sandbox send + roster

System prompt: you are an incident officer, not a chatbot. Cite source + time. Never invent gauges. If vision is uncertain, say so.

## UI (minimal)

- Reuse flood-drought map + **draw rectangle / pick county**.
- Camera layer: pins, click = live still/HLS.
- Right drawer: Safety Agent chat + alert feed.
- Alert → fly-to + evidence thumb + “notify orgs” confirmation.

## What is *not* in scope tonight

- City-scale camera grid, licensed video, or storing PII faces.
- Full X firehose.
- Replacing DualCNN-LSTM or training keras oil-spill into prod.
- Water-affordability model (still a hole in BDBI; do not pretend).

## Feasibility risks

| Risk | Mitigation |
| --- | --- |
| Webcam CORS / ToS / dead URL | Server-side fetch; have an MP4 fallback |
| Grok vision cost/latency | 15–30s sample; only alert on class change |
| Earthdata missing | `FAST_START_FLOOD_DATA=1` + say “synthetic precip” in the agent |
| Maps key missing | Chat-only demo still works; map is degraded |
| Windows Redis | In-memory bus for demo |
| Overlap with BDBI dummy pins | Label agent alerts vs dummy vs model |

## Team split (after this issue)

- `@AneeshD04` — product, contracts in `shared/`, agent prompt
- `@DevanshuShahs` — alert bus + `/api/watches` + `/api/alerts` + Grok chat proxy in `aquatic-sustainability/backend` **or** `backend/` sidecar (HANDOFF, don’t dual-write)
- `@buzzkabir` — `/safety` drawer on the existing static UI
- Athithan via `@AneeshD04` — Grok Bot watchers + camera worker in `bots/`

## Demo script (judges)

1. Show **old** BDBI flood/drought page (predictive). Switch to `/safety`.
2. Draw Galveston County. Camera pins appear; click one to watch.
3. Chat: “Watch this area.” Sub-agents go live.
4. Inject a flooded-road frame or a real NWS alert. UI + agent fire.
5. Confirm notify → sandbox SMS/email + org roster. Compare to `/api/flood-risk`.
