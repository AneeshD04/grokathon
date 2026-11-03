# Keys and services — what you need vs what degrades

Nothing in the BDBI repo contains live secrets (good). **You must supply them.** App import **fails** without `SECRET_KEY`. Everything else is optional with uneven fallbacks.

| Variable | Required to boot? | Used for | If missing |
| --- | --- | --- | --- |
| `SECRET_KEY` | **Yes** | Flask sessions | `RuntimeError` in `config.py` |
| `GOOGLE_MAPS_API_KEY` | For maps + Places | Maps JS; Places Nearby Search (same key **or** pair with `GOOGLE_PLACES_API_KEY`) | Map tiles never load (`/api/config/maps-key` returns `""`). Business pins / `find_businesses` degrade to a fixture list |
| `SUPABASE_URL` | For login | Auth | Register/login 503; Google OAuth dead |
| `SUPABASE_ANON_KEY` | For login | Auth | Same |
| `NEWS_API_KEY` | No | `/api/news` | Hardcoded placeholder articles |
| `EARTHDATA_USERNAME` | For **real** flood grids | NASA Earthdata / `earthaccess` | Docker **entrypoint exits**. Local flood path uses synthetic data if `FAST_START_FLOOD_DATA=1` or download throws |
| `EARTHDATA_PASSWORD` | Same | Same | Same |
| `REDIS_URL` | No | Flood result cache, RQ | App starts; cache off. RQ skipped on Windows |
| `MONGODB_URI` | No | Unused broken helper | Ignore |
| `PORT` | No | Bind port | `5001` locally, `8080` in Docker |
| `FAST_START_FLOOD_DATA` | No | Skip NASA download | Defaults on in Cloud Run (`K_SERVICE`) |
| `XAI_API_KEY` | **Our** add | Safety Agent / Grok | Not in upstream. Needed for the Grokathon layer |
| `X_BEARER_TOKEN` | Our add | X/Twitter watcher | Demo can mock or use RSS |
| `GOOGLE_PLACES_API_KEY` | Our add (optional) | Places Nearby Search server-side if you do **not** reuse the Maps key | Falls back to `GOOGLE_MAPS_API_KEY`. If both empty, `find_businesses` uses a fixture roster and dry-run only |
| `DEMO_APPROVAL_PIN` | Our add | **Send alerts** confirm modal | Hackathon default **`3408`** (also fine hardcoded with a rotate comment). Wrong PIN → reject, no send. Correct PIN → dry-run log by default. Live send only if `NOTIFY_DRY_RUN=0` **and** the number is sandbox / Twilio trial verified. Never put this value in issue titles |
| `NOTIFY_DRY_RUN` | Our add | Default **`1`** | If unset, treat as dry-run (log would-be recipients). Live send only when explicitly `0` **and** the number is on the sandbox roster or Twilio trial verified list. Never blast Places-scraped phones |
| `TWILIO_ACCOUNT_SID` | Our add (#13 notify) | Optional live SMS to **trial verified** / sandbox numbers after PIN | Dry-run logs only if missing or `NOTIFY_DRY_RUN=1` |
| `TWILIO_AUTH_TOKEN` | Our add | Twilio auth | Same |
| `TWILIO_FROM_NUMBER` | Our add | Twilio trial from-number | Same |
| IPAWS / WEA | No key | Stub button only | There is no IPAWS-OPEN credential in this hackathon. Button logs `ipaws_stub` |
| Opt-in resident list | File upload, not a key | County CSV/JSON of consenting contacts | If missing, skip public SMS and say so in the UI |
| Camera URLs | Our add | Watcher workers | Demo: 1–2 public webcam/YouTube live URLs |

## Google Places + Maps — enable and restrict (Aneesh)

Use the **same** Cloud project as the existing Maps key when possible. Places Nearby Search (New) **or** legacy Nearby Search + Place Details. Geocoding only if we turn a county name into a lat/lng (bbox from #14 already has coords — skip Geocoding if so).

Restrict the key: **Places API (New)** and/or **Places API** + **Maps JavaScript API** (+ **Geocoding API** only if enabled). Do not leave the key unrestricted.

Twilio is already the #13 notify path. Default `NOTIFY_DRY_RUN=1` (log only). Live send, if ever enabled, is **sandbox roster or Twilio trial verified numbers only**. Do **not** point Twilio at scraped Google Places phones. Approval PIN gated — value in [`SAFETY-AGENT-DESIGN.md`](SAFETY-AGENT-DESIGN.md#demo-send-gate-dry-run--approval-pin), not in issue titles. No `NOTIFY_ALLOW_SCRAPED_PLACES_NUMBERS` flag.

### Paste to Claude computer-use

```
Open https://console.cloud.google.com/apis/library
Use the SAME GCP project that already has GOOGLE_MAPS_API_KEY for this Grokathon app.
Enable: Places API (New). Also enable Places API if we use legacy Nearby Search + Place Details.
Enable: Geocoding API ONLY if we must geocode a county name to lat/lng. Skip if the map already has a bbox/polygon.
Credentials → APIs & Services → Credentials.
Either (A) edit the existing Maps key or (B) create a second key named GOOGLE_PLACES_API_KEY.
API restrictions on that key: Maps JavaScript API + Places API (New) [+ Places API if legacy] [+ Geocoding API only if enabled]. No other APIs.
Application restrictions: HTTP referrers for the Maps JS browser key (localhost + Cloud Run URL). If Places is called server-side, prefer a separate IP-restricted key — do not put an unrestricted server key in frontend JS.
Save. Put the key in aquatic-sustainability/backend/.env as GOOGLE_MAPS_API_KEY and/or GOOGLE_PLACES_API_KEY. Never commit .env.
Twilio: already in the #13 notify design. Set NOTIFY_DRY_RUN=1. Put TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER in aquatic-sustainability/backend/.env only if testing trial-verified numbers. Never commit .env.
Do not add any flag that allows blasting scraped Google Places phone numbers.
Do not enable unattended robocall. Do not impersonate 911, NWS, or IPAWS/WEA. Do not claim we texted everyone in the county.
```

### Places fields we ask for

- Legacy Nearby Search + Details: `name`, `place_id`, `geometry`, `formatted_phone_number`, `website`
- New Nearby Search field mask: `places.id`, `places.displayName`, `places.location`, `places.nationalPhoneNumber`, `places.websiteUri`

Cap **N=20** businesses per geofence for the demo. Phone/website are display + dry-run log only unless that exact number is also on the sandbox / Twilio trial verified list.

Generate a Flask secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy [`.env.example`](../.env.example) to `aquatic-sustainability/backend/.env` (gitignored). Add `GOOGLE_PLACES_API_KEY`, `TWILIO_*`, `NOTIFY_DRY_RUN=1`, and `DEMO_APPROVAL_PIN` there when #13 / #24 implement — do not commit `.env` or `.venv`.

**We do not have BDBI’s production Maps/Supabase/News/Earthdata keys.** Ask Rick/Michael only if you need their Cloud Run project; otherwise create your own free-tier keys for the hackathon.
