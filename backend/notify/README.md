# Sandbox notify (issue #13)

**Product path is Flask**, not this sidecar.

```bash
cd aquatic-sustainability/backend
python run.py
# POST http://127.0.0.1:5001/api/notify
# POST http://127.0.0.1:5001/api/notify/send
```

Implementation: `aquatic-sustainability/backend/app/notify.py`.

- Approval PIN required (`DEMO_APPROVAL_PIN`; hackathon default in `docs/SAFETY-AGENT-DESIGN.md`).
- `NOTIFY_DRY_RUN` defaults to `1`. Unset is dry-run.
- Correct PIN logs intended recipients and returns success as if sent.
- Wrong PIN → 403, no log.
- **No live Twilio**, no Grok draft, no 911, no Places phone dialing.

Do not extend this FastAPI process. Do not commit `.env`.
