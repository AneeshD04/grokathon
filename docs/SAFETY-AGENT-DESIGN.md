# Safety Agent — high-level design (Grokathon)

## Verdict: county OEM copilot on BDBI, not a civilian app

A **Safety Agent** sits on top of Aquatic Sustainability and is aimed at a **county OEM / emergency manager** (Harris, Galveston, …), not a random citizen with a phone. The BDBI app is **predictive**. Ours is **AI-native + real-time**: the OEM marks a county → watchers (NWS/USGS, cameras, optional X) detect an emergency → a human **confirms** → the agent **shows** a fan-out to (1) **local businesses** found via Google Places in the polygon and (2) **opted-in residents** plus a **stub IPAWS/WEA** action.

It is **not** possible to watch every camera in a metro, call 911, or “text everyone in Harris County.” Wireless Emergency Alerts are IPAWS/FEMA/carrier-only. This demo **never** places real calls, SMS, email, or X DMs. **Send alerts** is dry-run by default and **approval-PIN gated** (see [Demo send gate](#demo-send-gate-dry-run--approval-pin)). Never impersonate 911/NWS/IPAWS.

Camera inventory: [`CAMERA-SOURCES.md`](CAMERA-SOURCES.md). Business POIs are **Places**, not that catalog.

## Primary user

| Role | In demo? |
| --- | --- |
| **County OEM / emergency manager** (duty officer at a laptop) | **Yes — this is the product** |
| Local business owner receiving a call/SMS | Shown as *intended* recipients only |
| Resident with a cell phone in the polygon | Only if they are on a **county-uploaded opt-in list**. No WEA blast |
| Random citizen drawing a box for themselves | Not the persona. Do not pitch it that way |

Copy in the UI should read like an incident console (“Watch Harris County”, “Send alerts”, “Submit to IPAWS/WEA”) not like a consumer chat toy.

## What already exists (agent context)

Treat these as tools, not rebuild them:

- Flood probabilities: `POST /api/flood-risk` `{lat, lon}`
- Coral GBR bundle: `GET /api/coral-bleaching`
- Hardcoded drought/flood polygons: `GET /api/drought`, `GET /api/flood`
- News: `GET /api/news`
- Maps UI pages for human follow-up

Watchers add **streaming, local, unofficial** signal the models never see (a flooded underpass on a traffic cam; a county emergency tweet; a USGS gauge spike).

## Target user story (demo)

1. OEM draws/selects a **county polygon** (not just a point). Chat: “Watch Galveston County.”
2. Map fills with **live source pins** (cameras + NWS zones + USGS gauges). Click a camera → watch the feed.
3. Safety Agent starts sub-agents on coastal cams in that bbox. Vision classes: standing water, overtopped road, debris, smoke, all-clear.
4. **X/news watcher** for geo + keywords (`flood`, `storm surge`, `road closed`, county name).
5. If severity ≥ warning: agent **drafts** risk/evac copy and **prepares** two fan-out lists (does not send):
   1. **Businesses** — Google Places Nearby in the polygon, pins on the map, Grok-personalized message per type (marina vs grocery vs hotel).
   2. **Public** — opted-in resident rows the county uploaded, plus a disabled-looking **Submit to IPAWS/WEA** stub.
6. OEM clicks **Send alerts** → confirm modal → types the approval PIN → UI shows success **as if sent**. Server **logs intended recipients** and drafted text. It does **not** hit Twilio, SMTP, X, `tel:`, or IPAWS.
7. Agent also pulls the **old** flood model so judges see predictive vs now.

## Fan-out (after confirm)

### 1) Local businesses (real lookup, fake contact)

- **Discover:** Google Places Nearby Search (New `places:searchNearby` or legacy Nearby Search + Place Details) covering the marked polygon (centroid + radius, then **point-in-polygon** filter). Cap **N** for demo (**20** default; 60 max). Prefer store-like types (grocery, pharmacy, lodging, gas, marina).
- **Fields:** `name`, `place_id`, `geometry`. Phone: `formatted_phone_number` (legacy Details) or `nationalPhoneNumber` (New). Website: `website` / `websiteUri`.
- **Key:** same `GOOGLE_MAPS_API_KEY` with Places enabled, or `GOOGLE_PLACES_API_KEY`. Restrict to Places + Maps JS. See [`MISSING-KEYS.md`](MISSING-KEYS.md).
- **Show:** map pins distinct from cameras. Click → name, types, phone/website **for display**.
- **Draft:** Grok `draft_alert` personalizes (“marina: secure vessels / move upland”) — **never sends**.
- **Contact:** Grok-agent call/SMS is **simulated**. Places phone numbers are **not** a dial list. No auto-robocall, no impersonating 911/NWS.

Implementation: [#24](https://github.com/AneeshD04/grokathon/issues/24) (API) · [#25](https://github.com/AneeshD04/grokathon/issues/25) (pins + confirm UI) · [#26](https://github.com/AneeshD04/grokathon/issues/26) (tools) · send path stays [#13](https://github.com/AneeshD04/grokathon/issues/13). Spec: [#27](https://github.com/AneeshD04/grokathon/issues/27).

Business POI (`shared/`, extend #8):

```json
{
  "name": "Example Grocery",
  "place_id": "ChIJ...",
  "lat": 29.30,
  "lon": -94.80,
  "formatted_phone_number": "+1-409-555-0100",
  "website": "https://example.invalid",
  "source": "places"
}
```

### 2) Local people (honest: we cannot geo-SMS a county)

**Do not promise WEA / cell-broadcast / “text everyone in Harris County.”** That path is **IPAWS → FEMA → wireless carriers** only. Third-party APIs (Twilio, Grok, Google) cannot address “all handsets in this polygon.” See [Why mass public geo-SMS is not available](#why-mass-public-geo-sms-is-not-available).

**Demo picks (a)+(b):**

| Option | What judges see | What actually happens |
| --- | --- | --- |
| **(a) Opted-in resident list** | OEM uploaded a CSV/JSON of consenting contacts (name, phone/email, optional lat/lon). Listed as public recipients. | Same PIN-gated dry-run log. **No SMS/email.** |
| **(b) Stub “Submit to IPAWS/WEA”** | Button on the confirm modal. Copy: *Would submit this polygon + message to IPAWS-OPEN (WEA). Not connected.* | Click records a log row `ipaws_stub`. **Does not send.** |
| (c) Shareable public alert page/QR | Out of demo scope unless leftover time | n/a |

If the county has **no** opt-in list, the UI says so and **skips** public SMS. It still offers the IPAWS stub. Do not invent residents.

### Org roster (still useful)

Keep the static “would have notified” orgs (county EM, NWS, USCG sector, 311) as a **display roster**. Those are not live phones either.

## Demo send gate (dry-run + approval PIN)

**No real contact in the demo.** Not businesses, not residents, not orgs, not 911. The PIN does **not** enable Twilio — it only unlocks the **as-if-sent** log.

| Rule | Behavior |
| --- | --- |
| Default | `NOTIFY_DRY_RUN=1`. Every notify/call/email/Grok-contact tool is a no-op besides logging. |
| UI | **Send alerts** opens a confirm modal: recipient counts (businesses, opted-in residents, IPAWS stub), drafted message, PIN field. Cancel / no PIN → nothing. |
| PIN match | If the typed value equals `DEMO_APPROVAL_PIN` (hackathon default **`3408`**), return success **as if sent**. Persist a `notify_log` of intended recipients + drafts + timestamp. **Do not** call Twilio, X, SMTP, carrier APIs, or IPAWS. |
| PIN mismatch | Reject (`403` / inline error). No log of a send. No side effects. |
| Env | `DEMO_APPROVAL_PIN` from environment. Hardcoding `3408` for the hackathon is OK with a comment to **rotate before any real deployment**. There is **no** `NOTIFY_ALLOW_SCRAPED_PLACES_NUMBERS` flag; do not add one. Do not ship a live-send toggle for this demo. |
| Issues | Never put the PIN in **public issue titles**. Say “approval PIN gated, see design doc.” |

Suggested API shape (implement on [#13](https://github.com/AneeshD04/grokathon/issues/13)):

```http
POST /api/notify/send
{ "geofence_id", "message", "business_place_ids": [], "resident_ids": [], "include_ipaws_stub": true, "approval_pin": "...." }
```

```json
{
  "ok": true,
  "mode": "dry-run-logged",
  "would_notify": { "businesses": 18, "residents": 4, "ipaws_stub": true },
  "log_id": "ulid"
}
```

Wrong PIN → `{ "ok": false, "error": "invalid_approval_pin" }` with no `log_id`.

Compare the PIN with a constant-time compare. Do not echo it back. Do not print it in SSE payloads or screenshots in issues.

## Architecture

```
                    ┌────────────┐
  OEM  ────────────►│  Safety UI │◄──── WebSocket / SSE alerts
                    │  (Kabir)   │
                    └─────┬──────┘
                          │ chat
                    ┌─────▼──────────┐
                    │ Safety Agent   │  Grok + tools  (Athithan / Grok Bot)
                    │  - query_flood │
                    │  - query_coral │
                    │  - get_alerts  │
                    │  - set_watch   │
                    │  - find_businesses │
                    │  - draft_alert │
                    │  - notify_orgs │  dry-run + PIN
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
                          │
                    Places Nearby ──► business roster (no dial)
                    Opt-in CSV    ──► resident roster (no dial)
                    IPAWS stub    ──► log only
```

**Do not** put watchers inside the Flask request path. They are long-running. Flask (or a small FastAPI sidecar) only: CRUD watches, poll/push alerts, proxy Grok chat, Places lookup, PIN-gated notify (dry-run default).

### Alert schema (shared contract → `shared/`)

```json
{
  "id": "ulid",
  "ts": "ISO-8601",
  "source": "camera|nws|usgs|x|model|news|places",
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
| **Places** | Google Places Nearby in the geofence | Maps key with Places API enabled | Cap N. Pins + roster. Phones are display only. [#24](https://github.com/AneeshD04/grokathon/issues/24) |
| **Notify** | Drafts + intended rosters (businesses, opt-in residents, org list, IPAWS stub) | `DEMO_APPROVAL_PIN`; Twilio keys **must not** be called | Dry-run log only. PIN gate. [#13](https://github.com/AneeshD04/grokathon/issues/13) |
| **Model** | Existing `/api/flood-risk` on a timer | Earthdata or synthetic | Re-query the pin every N minutes; alert if prob jumps. |

Grok Bots can *be* the watchers (each bot owns a source) and `@mention` / POST into the bus. GitHub Issues stay the **team** bus; the **runtime** bus is Redis/HTTP, not GitHub.

## Safety Agent tools (Grok)

- `set_watch(geofence, sources[])`
- `list_alerts(since, severity)`
- `get_flood_risk(lat, lon)` → existing Flask
- `get_coral_summary()` → existing Flask
- `get_nws(lat, lon)`
- `list_cameras(bbox)` / `ask_camera(camera_id)`
- `find_businesses(geofence)` → Places Nearby; cap N; **never dials** ([#26](https://github.com/AneeshD04/grokathon/issues/26))
- `draft_alert(severity, hazard, businesses[])` → personalized evacuate-or-risk text; **never sends**
- `notify_orgs(severity, geofence, summary, approval_pin)` → **dry-run log** after PIN match; no Twilio

System prompt: you are an **incident officer for county OEM**, not a consumer chatbot. Cite source + time. Never invent gauges. If vision is uncertain, say so. Never impersonate 911/NWS/IPAWS. Never send without PIN. Never treat Places numbers or opt-in phones as a live blast list. Never claim you WEA-blasted a county.

## UI (minimal)

- Reuse flood-drought map + **draw rectangle / pick county** ([#14](https://github.com/AneeshD04/grokathon/issues/14)).
- Camera layer: pins, click = live still/HLS ([#15](https://github.com/AneeshD04/grokathon/issues/15)).
- Business layer: distinct pins from Places ([#25](https://github.com/AneeshD04/grokathon/issues/25)).
- Right drawer: Safety Agent chat + alert feed ([#16](https://github.com/AneeshD04/grokathon/issues/16)).
- Alert → fly-to + evidence thumb.
- **Send alerts** → confirm modal → PIN → success-as-if-sent or reject. Include **Submit to IPAWS/WEA** stub checkbox/button (non-sending). Opt-in resident count or “no list uploaded — public SMS skipped.”

## Why mass public geo-SMS is not available

Wireless Emergency Alerts (WEA) are **geo-targeted cell broadcasts**, not SMS from an app. Only an authorized public alerting authority can submit a WEA through **IPAWS-OPEN** (FEMA). Carriers then broadcast to handsets camped in the polygon. There is no Google / Twilio / Grok API that means “text every phone in Harris County”: carriers do not sell that location list, TCPA/consent still applies to A2P SMS, and impersonating WEA is illegal. Places works for **businesses** because they opted into a public listing with a published phone. Residents did not. So the honest demo is: Places roster + county **opt-in** list + a **stub** IPAWS button, with every “send” PIN-gated and logged, never transmitted.

## What is *not* in scope tonight

- City-scale camera grid, licensed video, or storing PII faces.
- Full X firehose.
- Live Twilio/X/phone/IPAWS send, even after a correct PIN.
- Unattended / robocall blast to Places-scraped numbers. No `NOTIFY_ALLOW_SCRAPED_PLACES_NUMBERS`.
- Impersonating 911, NWS, USCG, or IPAWS/WEA.
- Replacing DualCNN-LSTM or training keras oil-spill into prod.
- Water-affordability model (still a hole in BDBI; do not pretend).

## Feasibility risks

| Risk | Mitigation |
| --- | --- |
| Webcam CORS / ToS / dead URL | Server-side fetch; have an MP4 fallback |
| Grok vision cost/latency | 15–30s sample; only alert on class change |
| Earthdata missing | `FAST_START_FLOOD_DATA=1` + say “synthetic precip” in the agent |
| Maps / Places key missing | Chat-only demo still works; business pins empty with a banner |
| Windows Redis | In-memory bus for demo |
| Overlap with BDBI dummy pins | Label agent alerts vs dummy vs model |
| Judges think we WEA-blasted Houston | UI copy + IPAWS stub disclaimer + dry-run log panel |
| Accidental real SMS | No Twilio client on the send path; PIN only unlocks the **log** |

## Team split

- `@AneeshD04` — product, this doc, contracts in `shared/`, agent prompt ([#26](https://github.com/AneeshD04/grokathon/issues/26), [#8](https://github.com/AneeshD04/grokathon/issues/8))
- `@DevanshuShahs` — alert bus, Places nearby ([#24](https://github.com/AneeshD04/grokathon/issues/24)), PIN-gated dry-run notify ([#13](https://github.com/AneeshD04/grokathon/issues/13)), Grok chat proxy ([#12](https://github.com/AneeshD04/grokathon/issues/12)) in `aquatic-sustainability/backend` **or** `backend/` sidecar (HANDOFF, don’t dual-write)
- `@buzzkabir` — `/safety` drawer, business pins, **Send alerts** modal + PIN ([#16](https://github.com/AneeshD04/grokathon/issues/16), [#25](https://github.com/AneeshD04/grokathon/issues/25), [#14](https://github.com/AneeshD04/grokathon/issues/14))
- Athithan via `@AneeshD04` — Grok Bot watchers + camera worker in `bots/`

## Demo script (judges)

1. Show **old** BDBI flood/drought page (predictive). Switch to `/safety`. Say: **county OEM console**.
2. Draw Galveston County. Camera pins + business pins appear; click one of each.
3. Chat: “Watch this area.” Sub-agents go live.
4. Inject a flooded-road frame or a real NWS alert. UI + agent fire. Grok drafts evac copy.
5. **Send alerts** → modal lists businesses + opted-in residents + IPAWS stub. Wrong PIN fails. Correct PIN (see this doc) shows **sent** and a log of who *would* have been contacted. Compare to `/api/flood-risk`. Say out loud: we did not WEA the county; we did not call the marinas.
