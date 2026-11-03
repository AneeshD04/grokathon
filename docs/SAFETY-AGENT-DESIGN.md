# Safety Agent — high-level design (Grokathon)

## Verdict: county OEM copilot on BDBI, not a civilian app

A **Safety Agent** sits on top of Aquatic Sustainability and is aimed at a **county OEM / emergency manager** (Harris, Galveston, …) — the **local government** duty officer, not a random citizen with a phone. The BDBI app is **predictive**. Ours is **AI-native + real-time**: the OEM marks a county → **ModelWatch** polls the *existing* aquatic analysis APIs on an interval and on-demand → watchers (NWS/USGS, cameras, optional X) add live signal → a human **confirms** → the agent **shows** a fan-out to (1) **local businesses** found via Google Places in the polygon and (2) **opted-in residents** plus a **stub IPAWS/WEA** action.

It is **not** possible to watch every camera in a metro, call 911, or “text everyone in Harris County.” Wireless Emergency Alerts are IPAWS/FEMA/carrier-only. This demo **never** places real calls, SMS, email, or X DMs. **Send alerts** is dry-run by default and **approval-PIN gated** (see [Demo send gate](#demo-send-gate-dry-run--approval-pin)). Never impersonate 911/NWS/IPAWS.

Camera inventory: [`CAMERA-SOURCES.md`](CAMERA-SOURCES.md). Business POIs are **Places**, not that catalog.

## Primary user

| Role | In demo? |
| --- | --- |
| **County OEM / emergency manager** (duty officer at a laptop) | **Yes — this is the product** |
| Local business owner receiving a call/SMS | Shown as *intended* recipients only |
| Resident with a cell phone in the polygon | Only if they are on a **county-uploaded opt-in list**. No WEA blast |
| Random citizen drawing a box for themselves | Not the persona. Do not pitch it that way |

Copy in the UI should read like an incident console (“Watch Harris County”, “Notify impacted businesses”, “Submit to IPAWS/WEA”) not like a consumer chat toy.

## What already exists (agent context)

Treat these as tools, not rebuild them. **Do not pretend more analysis exists.** Honest inventory: [`BDBI-AQUATIC-SUSTAINABILITY.md`](BDBI-AQUATIC-SUSTAINABILITY.md). Glue: [ModelWatch](#modelwatch--bdbi-analysis-glue).

| API | Real vs dummy | Safety Agent use |
| --- | --- | --- |
| `POST /api/flood-risk` `{lat, lon}` | **Real** DualCNN-LSTM (NASA GPM IMERG precip + SMAP soil). Delayed (UTC-day Redis cache). Synthetic grids if `FAST_START_FLOOD_DATA=1`. Model bins: `high` ≥ 0.75, `warning` ≥ 0.5, `medium` ≥ 0.3. | **Primary** ModelWatch trigger |
| `GET /api/coral-bleaching` | **Real batch** GBR LSTM + XGBoost weekly CSVs (`prob_severe`, DHW, SST) | Alert only if the watch bbox intersects GBR centroids |
| `GET /api/drought` | **Dummy** eight hardcoded US polygons + `risk` float | Optional overlay; copy **must** say dummy |
| `GET /api/flood` | **Dummy** hardcoded polygons | **Not** DualCNN-LSTM evidence. Do not emit `source:model` from this route |
| oil-spill page | **Dummy** JS; keras classifier is **not** on the API | Ignore |
| water affordability | **Not implemented** | Never mention as a model |
| `GET /api/news` | NewsAPI or placeholders | Not hydrology evidence |

Watchers add **streaming, local, unofficial** signal the models never see (a flooded underpass on a traffic cam; a county emergency tweet; a USGS gauge spike).

## Target user story (demo)

1. OEM draws/selects a **county polygon** (not just a point). Chat: “Watch Galveston County.” Watch `sources` includes `model`.
2. **ModelWatch** starts: poll `POST /api/flood-risk` on an interval **and** on-demand. If max in-polygon flood `prob >= 0.5`, emit `Alert{source:model}` on the same bus as cameras/NWS, with Places businesses likely impacted.
3. Map fills with **live source pins** (cameras + NWS zones + USGS gauges + business pins). Click a camera → watch the feed.
4. Safety Agent starts sub-agents on coastal cams in that bbox. Vision classes: standing water, overtopped road, debris, smoke, all-clear.
5. **X/news watcher** for geo + keywords (`flood`, `storm surge`, `road closed`, county name).
6. If severity ≥ warning: agent **drafts** risk/evac copy that **cites the model evidence** (flood probability, DualCNN-LSTM, NASA GPM+SMAP — not fake water-quality lab data) and **prepares** two fan-out lists (does not send):
   1. **Businesses** — Google Places Nearby in the polygon, pins on the map, Grok-personalized message per type (marina vs grocery vs hotel).
   2. **Public** — opted-in resident rows the county uploaded, plus a disabled-looking **Submit to IPAWS/WEA** stub.
7. OEM clicks **Notify impacted businesses** (model path) or **Send alerts** → confirm modal → types the approval PIN → UI shows success **as if sent**. Server **logs intended recipients** and drafted text. It does **not** hit Twilio, SMTP, X, `tel:`, or IPAWS.

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
| UI | **Notify impacted businesses** (model-alert path) or **Send alerts** opens a confirm modal: recipient counts (Places businesses in the polygon, opted-in residents, IPAWS stub), drafted message **with model evidence**, PIN field. Cancel / no PIN → nothing. |
| PIN match | If the typed value equals `DEMO_APPROVAL_PIN` (hackathon default **`3408`**), return success **as if sent**. Persist a `notify_log` of intended recipients + drafts + timestamp. **Do not** call Twilio, X, SMTP, carrier APIs, or IPAWS. |
| PIN mismatch | Reject (`403` / inline error). No log of a send. No side effects. |
| Env | `DEMO_APPROVAL_PIN` from environment. Hardcoding `3408` for the hackathon is OK with a comment to **rotate before any real deployment**. There is **no** `NOTIFY_ALLOW_SCRAPED_PLACES_NUMBERS` flag; do not add one. Do not ship a live-send toggle for this demo. |
| Issues | Never put the PIN in **public issue titles**. Say “approval PIN gated, see design doc.” |

Suggested API shape (implement on [#13](https://github.com/AneeshD04/grokathon/issues/13)):

```http
POST /api/notify/send
{ "geofence_id", "alert_id", "message", "business_place_ids": [], "resident_ids": [], "include_ipaws_stub": true, "approval_pin": "...." }
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
                    │  - poll_models │
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
         ModelWatch  GovWatch XWatch CamWatch   (workers / Grok Bots)
              │         │      │      │
     /api/flood-risk  NWS/USGS  X   JPEG → vision
     /api/coral-bleaching
     /api/drought (dummy overlay)
                          │
                    Places Nearby ──► impacted businesses (no dial)
                    Opt-in CSV    ──► resident roster (no dial)
                    IPAWS stub    ──► log only
```

**Do not** put watchers inside the Flask request path. They are long-running. Flask (or a small FastAPI sidecar) only: CRUD watches, on-demand `poll-models`, poll/push alerts, proxy Grok chat, Places lookup, PIN-gated notify (dry-run default).

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
  "title": "DualCNN-LSTM flood probability 0.62",
  "summary": "Model: max flood prob 0.62 at (29.76,-95.37). NASA GPM+SMAP, delayed. Not a water-quality lab result.",
  "evidence": {
    "model": "DualCNN-LSTM",
    "endpoint": "POST /api/flood-risk",
    "max_prob": 0.62,
    "threshold": 0.5,
    "inputs": "NASA GPM IMERG + SMAP",
    "latency": "delayed",
    "synthetic": false,
    "trained": true
  },
  "impacted_businesses": [
    {"place_id": "...", "name": "...", "types": ["marina"], "lat": 29.3, "lon": -94.8}
  ],
  "dedupe_key": "model:flood-risk:houston-demo:0.62"
}
```

Dedup by `dedupe_key` + time window so cameras and the flood-risk cache don’t spam. `impacted_businesses` is required on `source:model` (empty list + reason is OK if Places is unset). Additive fields land in `shared/` via [#8](https://github.com/AneeshD04/grokathon/issues/8).

## Sub-agents (watchers)

Each watcher is a loop: `pull → normalize → (optional Grok classify) → publish alert if new`.

| Watcher | Data | Auth | Hackathon plan |
| --- | --- | --- | --- |
| **Gov** | [NWS alerts](https://api.weather.gov/alerts) (no key), [USGS IV](https://waterservices.usgs.gov/), [NASA EONET](https://eonet.gsfc.nasa.gov/api/v3/events) | None | **Ship this first.** Real and impressive. |
| **Camera** | TranStar, FL511, NDBC BuoyCAM, WebCOOS, USGS CoastCam — see `CAMERA-SOURCES.md` | Usually none; WebCOOS token | List **all** in bbox on the map. Vision workers on ≤8. JPEG every 15–30s. MP4 fallback. |
| **X / social** | X recent search, Grok web search, or RSS | Bearer optional | **In demo.** Geo + disaster keywords. Fixture tweets if no token. |
| **Places** | Google Places Nearby in the geofence | Maps key with Places API enabled | Cap N. Pins + roster. Phones are display only. [#24](https://github.com/AneeshD04/grokathon/issues/24) |
| **Notify** | Drafts + intended rosters (businesses, opt-in residents, org list, IPAWS stub) | `DEMO_APPROVAL_PIN`; Twilio keys **must not** be called | Dry-run log only. PIN gate. [#13](https://github.com/AneeshD04/grokathon/issues/13) |
| **Model** | Existing BDBI analysis APIs (see [ModelWatch](#modelwatch--bdbi-analysis-glue)) | Earthdata or `FAST_START` synthetic | Poll on interval + on-demand. Emit `Alert{source:model}` when thresholds trip. [#35](https://github.com/AneeshD04/grokathon/issues/35) |

Grok Bots can *be* the watchers (each bot owns a source) and `@mention` / POST into the bus. GitHub Issues stay the **team** bus; the **runtime** bus is Redis/HTTP, not GitHub.

## ModelWatch — BDBI analysis glue

**Target user:** local government (county OEM). **Goal:** if water-safety / hydrology analysis in the marked region crosses a threshold, the platform updates and can **show** a message to businesses that may be impacted. **No real Twilio.** Implementation: [#35](https://github.com/AneeshD04/grokathon/issues/35) (poller) · [#14](https://github.com/AneeshD04/grokathon/issues/14) / [#25](https://github.com/AneeshD04/grokathon/issues/25) (region + impacted list) · [#26](https://github.com/AneeshD04/grokathon/issues/26) (`poll_models`) · notify/Places [#13](https://github.com/AneeshD04/grokathon/issues/13) [#24](https://github.com/AneeshD04/grokathon/issues/24) · product ping [#7](https://github.com/AneeshD04/grokathon/issues/7) · this spec [#34](https://github.com/AneeshD04/grokathon/issues/34).

Do **not** train a new model. Do **not** invent water-quality labs, oil-spill CNN, or affordability. Subscribe to what already ships.

### Subscribe

1. OEM marks a county / bbox ([#14](https://github.com/AneeshD04/grokathon/issues/14)).
2. `POST /api/watches` includes `sources: ["model", …]` ([#11](https://github.com/AneeshD04/grokathon/issues/11)).
3. ModelWatch (long-running worker, **not** in the Flask request path) attaches to that watch.

### Poll (interval + on-demand)

| Source | Cadence | How to sample |
| --- | --- | --- |
| `POST /api/flood-risk` `{lat, lon}` | Every **10–15 min** (NASA inputs are delayed; Redis caches the UTC day) **and** on-demand | Call at the polygon **centroid**. The existing job already returns ~56 radial points (5–80 km). **Point-in-polygon** filter to the watch. `max_prob` = max in-polygon `prob`. |
| `GET /api/coral-bleaching` | On watch start + hourly (weekly CSV bundle) | Fire only if the watch bbox **intersects** GBR `centroids`. Use latest week `prob_severe` / `predicted_class`. Houston–Galveston demo **will not** trip this — that is honest. |
| `GET /api/drought` | On watch start only (static dummy) | If a hardcoded polygon intersects the watch **and** `risk >= 0.7`, emit a **dummy** overlay alert. Copy must say hardcoded, not a trained drought model. Most Houston watches will **not** intersect these US polygons. |
| `GET /api/flood` dummy polygons | **Never** as DualCNN-LSTM evidence | Distinct from `POST /api/flood-risk`. Label dummy if shown on the map at all. |
| oil / affordability / news | **Never** as hydrology evidence | News is not a water-quality model. |

On-demand route (name TBD on #35): `POST /api/watches/:id/poll-models`. OEM refresh button and the `poll_models` agent tool both hit it.

If `FAST_START_FLOOD_DATA=1`, set `evidence.synthetic: true` and say **synthetic precip** in the summary. Still a DualCNN-LSTM forward pass — not a lab result.

### Thresholds → `Alert{source:model}`

Same bus as cameras / NWS (`POST /api/alerts` on #11). Defaults env-overridable.

| Condition | Severity | `evidence.trained` |
| --- | --- | --- |
| In-polygon flood `prob >= 0.5` (model's own `warning` bin) | `warning` | `true` |
| In-polygon flood `prob >= 0.75` (`high`) | `critical` | `true` |
| Coral latest week `prob_severe > 0.5` or `predicted_class` severe (GBR intersect only) | `warning` / `critical` | `true` |
| Dummy drought intersect + `risk >= 0.7` | `watch` | **`false`** |

Do not emit a flood-risk alert below `prob` 0.5. Dedup: `model:{endpoint}:{geofence_id}:{rounded_max}` + time window so the UTC-day cache does not re-fire every poll.

### Impacted businesses

On a tripped alert, call Places Nearby ([#24](https://github.com/AneeshD04/grokathon/issues/24)) for the watch polygon (centroid + cover radius, then PIP). Cap **N** (20 default). Prefer types: `restaurant` / food, `lodging` / hotel, `marina`, `campground`, `grocery_or_supermarket`, `pharmacy`, `gas_station`. Attach `impacted_businesses[]` on the alert. Phones are **display only**.

### Notify impacted businesses (dry-run)

Gov UI button **Notify impacted businesses** ([#25](https://github.com/AneeshD04/grokathon/issues/25)):

1. Confirm modal lists the Places roster + drafted copy.
2. OEM types the approval PIN (hackathon default in [Demo send gate](#demo-send-gate-dry-run--approval-pin); **never** put the PIN in issue titles).
3. `POST /api/notify/send` with `business_place_ids` from the alert ([#13](https://github.com/AneeshD04/grokathon/issues/13)).
4. PIN match → `{ "ok": true, "mode": "dry-run-logged", "log_id" }`. Persist intended recipients + text. **Do not** call Twilio, SMTP, X, `tel:`, or IPAWS.
5. Wrong PIN → reject, no log.

Drafted SMS/email **must** mention the model evidence actually present, for example:

> Harris County OEM (demo, not sent): DualCNN-LSTM flood probability **0.62** near your location from NASA GPM IMERG + SMAP (delayed). This is a hydrology model, **not** a water-quality lab result. Marina: secure vessels / move upland.

Never write “e.coli / turbidity / boil-water lab sample” unless we add a real source later (we have not). Dummy drought copy must say **hardcoded overlay**. Synthetic flood must say **synthetic precip**.

## Safety Agent tools (Grok)

- `set_watch(geofence, sources[])` — include `"model"` for ModelWatch
- `list_alerts(since, severity)`
- `get_flood_risk(lat, lon)` → existing Flask DualCNN-LSTM
- `poll_models(geofence)` → on-demand ModelWatch refresh; **never sends** ([#26](https://github.com/AneeshD04/grokathon/issues/26), [#35](https://github.com/AneeshD04/grokathon/issues/35))
- `get_coral_summary()` → existing Flask GBR bundle
- `get_nws(lat, lon)`
- `list_cameras(bbox)` / `ask_camera(camera_id)`
- `find_businesses(geofence)` → Places Nearby; cap N; **never dials** ([#26](https://github.com/AneeshD04/grokathon/issues/26))
- `draft_alert(severity, hazard, businesses[], evidence)` → personalized evacuate-or-risk text that **cites `evidence.model` / `max_prob`**; **never sends**
- `notify_orgs(severity, geofence, summary, approval_pin)` → **dry-run log** after PIN match; no Twilio

System prompt: you are an **incident officer for county OEM / local government**, not a consumer chatbot. Cite source + time. Never invent gauges, lab water-quality, oil CNN, or affordability. Distinguish **real** DualCNN-LSTM and GBR coral CSVs from **dummy** drought/flood polygons. If `evidence.synthetic` or vision is uncertain, say so. Never impersonate 911/NWS/IPAWS. Never send without PIN. Never treat Places numbers or opt-in phones as a live blast list. Never claim you WEA-blasted a county.

## UI (minimal)

- Reuse flood-drought map + **draw rectangle / pick county** ([#14](https://github.com/AneeshD04/grokathon/issues/14)). Marking a region **subscribes ModelWatch**.
- Camera layer: pins, click = live still/HLS ([#15](https://github.com/AneeshD04/grokathon/issues/15)).
- Business layer: distinct pins from Places; on a model alert, highlight **impacted** types ([#25](https://github.com/AneeshD04/grokathon/issues/25)).
- Right drawer: Safety Agent chat + alert feed ([#16](https://github.com/AneeshD04/grokathon/issues/16)). Model alerts show `max_prob` / dummy label, not a camera thumb.
- Alert → fly-to + evidence (prob, endpoint, synthetic flag).
- **Notify impacted businesses** → confirm modal → PIN → success-as-if-sent or reject. Same gate as **Send alerts**. Include **Submit to IPAWS/WEA** stub (non-sending). Opt-in resident count or “no list uploaded — public SMS skipped.”
- On-demand **Refresh models** control that calls `poll-models`.

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
| Judges think dummy drought is DualCNN-LSTM | Label `evidence.trained: false`; never emit `source:model` from `GET /api/flood` |
| Judges think we have water-quality labs | Copy cites flood **probability** / NASA GPM+SMAP only |

## Team split

- `@AneeshD04` — product, this doc, contracts in `shared/`, agent prompt + `poll_models` ([#26](https://github.com/AneeshD04/grokathon/issues/26), [#8](https://github.com/AneeshD04/grokathon/issues/8), [#34](https://github.com/AneeshD04/grokathon/issues/34))
- `@DevanshuShahs` — ModelWatch poller ([#35](https://github.com/AneeshD04/grokathon/issues/35)), alert bus ([#11](https://github.com/AneeshD04/grokathon/issues/11)), Places nearby ([#24](https://github.com/AneeshD04/grokathon/issues/24)), PIN-gated dry-run notify ([#13](https://github.com/AneeshD04/grokathon/issues/13)), Grok chat proxy ([#12](https://github.com/AneeshD04/grokathon/issues/12)) in `aquatic-sustainability/backend` **or** `backend/` sidecar (HANDOFF, don’t dual-write)
- `@buzzkabir` — `/safety` region subscribe, impacted-businesses list, **Notify impacted businesses** modal + PIN ([#16](https://github.com/AneeshD04/grokathon/issues/16), [#25](https://github.com/AneeshD04/grokathon/issues/25), [#14](https://github.com/AneeshD04/grokathon/issues/14))
- Athithan via `@AneeshD04` — Grok Bot watchers + camera worker in `bots/`

## Demo script (judges)

1. Show **old** BDBI flood/drought page (predictive DualCNN-LSTM click). Switch to `/safety`. Say: **county OEM / local government console**.
2. Draw Galveston County. ModelWatch subscribes. Camera pins + business pins appear; click one of each.
3. Chat: “Watch this area.” Sub-agents go live. Hit **Refresh models** (or wait for the interval) so `POST /api/flood-risk` runs for the centroid.
4. If max `prob >= 0.5` (or inject a fixture / NWS / flooded-road frame): UI shows `Alert{source:model}` with flood **probability** and the impacted-businesses list. Grok drafts copy that cites DualCNN-LSTM + NASA GPM+SMAP, **not** a lab result.
5. **Notify impacted businesses** → modal lists Places roster. Wrong PIN fails. Correct PIN (see this doc) shows **sent** and a log of who *would* have been contacted. **No Twilio.** Say out loud: dummy drought/flood polygons are not this model; we did not WEA the county; we did not call the marinas.
