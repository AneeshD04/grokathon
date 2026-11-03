# Sandbox notify (issue #13)

SMS-only notify sidecar. It does not import the alert bus. Run it beside that process on port **8001**.

`POST /api/notify` requires `approval_pin`. **Default is dry-run** (`NOTIFY_DRY_RUN=1` even if unset): the route logs the draft and roster and returns `delivered: []`. It does not call Twilio, 911, or Places numbers.

Live Twilio happens only when **all** of these are true: PIN matches `DEMO_APPROVAL_PIN`, `NOTIFY_DRY_RUN=0`, Twilio env is set, and the destination is in `NOTIFY_SANDBOX_PHONES`. Roster phones/emails are display-only. Emergency numbers are refused.

Hackathon PIN default is documented in `docs/SAFETY-AGENT-DESIGN.md`. Do not put it in issue titles. Rotate before any real deployment.

## Run

Bind localhost.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r notify/requirements.txt
uvicorn notify.main:app --host 127.0.0.1 --port 8001
```

```bash
curl -s -X POST 127.0.0.1:8001/api/notify \
  -H 'content-type: application/json' \
  -d '{"geofence":"galveston-county","severity":"warning","summary":"Standing water covering two lanes.","approval_pin":"<see-design-doc>"}'
```

## Environment

Set these in the shell. Do not commit them.

| Name | Purpose |
| --- | --- |
| `NOTIFY_DRY_RUN` | Default `1`. Unset is dry-run. Live SMS only if `0` **and** PIN matches |
| `DEMO_APPROVAL_PIN` | Confirm-send PIN (hackathon default in the design doc) |
| `NOTIFY_SANDBOX_PHONES` | Comma-separated team numbers. The only SMS destinations if live |
| `TWILIO_ACCOUNT_SID` | Twilio account SID (ignored unless dry-run is off) |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM_NUMBER` | Twilio from number |
| `XAI_API_KEY` | Optional. Used only when dry-run is off; dry-run uses a template |
| `XAI_MODEL` | Optional. Defaults to `grok-4`. |

If Twilio settings or sandbox numbers are missing, or dry-run is on, the route still returns the draft and roster with `delivered: []`. If `XAI_API_KEY` is missing or the draft call fails, `draft.source` is `template`.

Geofences that match the Houston–Galveston demo: `galveston`, `Galveston County`, `galveston-county`, `houston-galveston`, `houston-demo`. Anything else returns `matched: false` and `roster: []`.

## Tests

```bash
cd backend
python -m pytest notify/tests
```
