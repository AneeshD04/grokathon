# Keys and services — what you need vs what degrades

Nothing in the BDBI repo contains live secrets (good). **You must supply them.** App import **fails** without `SECRET_KEY`. Everything else is optional with uneven fallbacks.

| Variable | Required to boot? | Used for | If missing |
| --- | --- | --- | --- |
| `SECRET_KEY` | **Yes** | Flask sessions | `RuntimeError` in `config.py` |
| `GOOGLE_MAPS_API_KEY` | For maps | Maps JS on flood/coral/oil/news-adjacent pages | Map tiles never load (`/api/config/maps-key` returns `""`) |
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
| Camera URLs | Our add | Watcher workers | Demo: 1–2 public webcam/YouTube live URLs |

Generate a Flask secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy [`.env.example`](../.env.example) to `aquatic-sustainability/backend/.env` (gitignored).

**We do not have BDBI’s production Maps/Supabase/News/Earthdata keys.** Ask Rick/Michael only if you need their Cloud Run project; otherwise create your own free-tier keys for the hackathon.
