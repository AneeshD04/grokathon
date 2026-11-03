# backend/

**Stub only. Not the app.** Owner: [@DevanshuShahs](https://github.com/DevanshuShahs)

Product APIs (alert bus, PIN notify, Places nearby) live on the BDBI Flask app:

```bash
cd aquatic-sustainability/backend
python run.py
```

| Sidecar (do not extend) | Flask path |
| --- | --- |
| `POST /api/watches`, `GET/POST /api/alerts`, SSE `/api/alerts/stream` | `aquatic-sustainability/backend/app/alertbus.py` |
| `POST /api/notify`, `POST /api/notify/send` | `aquatic-sustainability/backend/app/notify.py` |
| `POST /api/businesses/nearby` | `aquatic-sustainability/backend/app/places.py` |

Notify is approval-PIN gated and `NOTIFY_DRY_RUN=1` by default. There is **no live Twilio** on the demo path. Do not commit `.env`.

This tree is a leftover FastAPI sidecar from early PRs. Judges running `python run.py` hit Flask, not uvicorn on :8000/:8001.
