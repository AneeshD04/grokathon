# BDBI Aquatic Sustainability — how the current project actually works

Source: [gt-big-data/aquatic-sustainability](https://github.com/gt-big-data/aquatic-sustainability) (vendored here as [`aquatic-sustainability/`](../aquatic-sustainability/)).  
BDBI page: *Hydrological Disasters And Disparities* (Aug 2025–present). Leads: Rick Lee, Michael Xu.

This is a Georgia Tech Big Data Big Impact (BDBI) product: map-first tools that locate **flood/drought risk**, **coral bleaching**, **oil-spill-ish marine incidents**, and **news**, aimed at UN SDG 6 (clean water). The README’s ambition is broader than what is wired into production today. That gap is the hackathon opportunity.

## What you can click in the live app

Flask serves a multi-page site from `aquatic-sustainability/backend/static/` (not a separate SPA). Routes in `backend/app/__init__.py`:

| URL | Page | What is real vs dummy |
| --- | --- | --- |
| `/` | Landing | Marketing + cards |
| `/flood-drought` | Map tool | **Real DualCNN-LSTM** via `POST /api/flood-risk` *and* hardcoded Georgia dummy pins in `floodDrought.js`. Drought polygons from `GET /api/drought` are **hardcoded**. |
| `/coral-bleaching` | GBR map | **Real** LSTM + XGBoost weekly CSVs via `GET /api/coral-bleaching` |
| `/oil-spill` | Map tool | **Dummy** incidents in `oilSpill.js`. Keras oil/algal classifier is **not** on the API. |
| `/news` | Feed | **NewsAPI** if `NEWS_API_KEY` is set; else placeholders |
| `/water` | Route exists | Looks for `pages/water.html` which **does not exist** (404). There is a leftover `static/water.html`. |
| `/login` `/register` | Auth | **Supabase** email/password + Google OAuth if configured |
| `/about` | Team | Static |

Login is “protected” in `main.js`, but `localStorage.skippedLogin` can bypass it (dev leftover).

## Architecture (as shipped)

```
Browser (HTML/CSS/JS + Google Maps)
        |
        |  /api/*
        v
Flask (Gunicorn on Cloud Run, port from $PORT)
        |
        +-- DualCNN-LSTM flood model (PyTorch)  --> NASA SMAP soil moisture + GPM IMERG rain
        +-- Coral CSV loader                    --> precomputed GBR cluster predictions
        +-- NewsAPI
        +-- Supabase auth
        +-- optional Redis cache / RQ workers
        +-- MongoDB helper (broken / unused)
```

- **Deploy:** Docker → Cloud Build → Cloud Run (`DEPLOYMENT.md`). CORS allowlist includes the Cloud Run URL and localhost `:5000`/`:5001`.
- **UI:** vanilla JS, Google Maps JS API (key fetched from `/api/config/maps-key`).
- **Research folders** (not served by Flask): `coral-reef-model/`, `xgboost-model/`, `coral reef analysis/`, `Time Series Models/` (crop yield notebooks). `keras classifier/` (~5,637 JPEGs) is **excluded** from this vendor copy — see [`../aquatic-sustainability/UPSTREAM.md`](../aquatic-sustainability/UPSTREAM.md).

## Models and data sources (existing)

### 1. Flood risk — the only live geo model on the API

- Code: `backend/app/flood_model.py`, weights `DualCNNLSTM_best_model_V3.pt` + scaler pickle.
- Architecture: two CNNs (precip 250×250, soil 50×50×2 with NaN mask) → LSTM → sigmoid flood probability.
- Inputs: **NASA GPM IMERG** precipitation (4 days, 32×3-hour steps) and **SMAP** soil moisture (21 days), via `earthaccess` + Earthdata login.
- Inference: 56 points on rings 5–80 km around a clicked lat/lon. Cached in Redis for the UTC day.
- If NASA caches are missing: Cloud Run sets `FAST_START_FLOOD_DATA=1` and uses **synthetic random grids**. Local default tries a real download (needs Earthdata).
- Older experiment: `backend/new_model/flood_predict_v9.py`.

### 2. Coral bleaching — served as a static weekly bundle

- Training lives in `coral reef analysis/` and `coral-reef-model/` (LSTM, bidirectional LSTM, MLP, XGBoost on NOAA CRW / GBR clusters, DHW + SST).
- Production: CSV dumps `backend/data/coral_bleaching/gbr_predictions_temporal_{lstm,xgboost}.csv` plus `centroid_names.json`.
- Loader: `coral_bleaching_loader.py` → JSON centroids, weekly series, risk / DHW / SST.

### 3. Drought

- `GET /api/drought` returns eight **hand-drawn US polygons** with a risk float. Not a trained model.
- `Time Series Models/` notebooks are crop-yield LSTMs, not wired to the site.

### 4. Oil spill / algal bloom

- README promises CNN segmentation. `keras classifier/` is a large image set (excluded from this copy).
- The oil-spill **page does not call a model**. Dummy spills only.
- Home background uses `Algal-Bloom.png`.

### 5. Water affordability / disparities

- Stated product goal. `DummyData.csv` at repo root. `backend/app/models.py` is a stub (`# data viz team's job`). **No affordability API.**

### 6. News

- NewsAPI query over coral/flood/drought keywords, 10-minute cache, keyword categorizer.

## Backend API (Flask blueprint `/api`)

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | `{status: ok}` |
| GET | `/config/maps-key` | Exposes Maps key to the browser |
| GET | `/config/supabase` | Exposes anon key (intentional) |
| POST | `/register` `/login` | Supabase; 503 if unset |
| POST | `/flood-risk` | `{lat, lon}` → model points |
| GET | `/flood-risk/<job_id>` | RQ poll (legacy; current POST is sync) |
| GET | `/coral-bleaching` | 503 if CSVs missing |
| GET | `/drought` `/flood` | Hardcoded polygons |
| GET | `/news` | NewsAPI or placeholders |

## How to run this copy

```bash
cd aquatic-sustainability/backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy ..\..\.env.example .env   # then fill keys; SECRET_KEY is required
python run.py                  # http://127.0.0.1:5001
```

Docker: repo-root `Dockerfile` + `entrypoint.sh` (entrypoint **requires** Earthdata user/pass even if you only want the homepage).

Windows: Redis/RQ is optional; `__init__.py` already degrades if fork/Redis is missing.

## What is missing / broken (honest)

See also [MISSING-KEYS.md](MISSING-KEYS.md).

- `SECRET_KEY` **must** be set or `config.py` raises at import.
- Maps, Supabase, NewsAPI, Earthdata, Mongo, Redis are all extra; without them pages degrade unevenly.
- `mongodb.py` imports `mongoDB_uri` which does not exist — dead code.
- `config.py` has a typo `EDIS_URL` and then overwrites `REDIS_URL` to localhost.
- `/water` 404. Affordability not implemented. Oil-spill model not served.
- Flood UI mixes dummy Georgia events with the real model.
- Nested `webpage/` is leftover CSS, not the app.

## Why this is a good Grokathon base

The product already geolocates water risk and has a flood model + coral bundle. It does **not** have a conversational operator, live watchers, or camera/social/gov fusion. That is exactly the Safety Agent layer in [SAFETY-AGENT-DESIGN.md](SAFETY-AGENT-DESIGN.md).
