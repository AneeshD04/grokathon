# Sandbox notify (issue #13)

SMS-only notify sidecar. It does not import the alert bus. Run it beside that process on port **8001**.

`POST /api/notify` drafts a message and texts **only** the numbers in `NOTIFY_SANDBOX_PHONES`. The JSON `roster` lists local orgs the demo would have notified. Those phone and email fields are display-only and are never passed to Twilio.

Emergency numbers and any number that matches a roster contact are refused.

## Run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r notify/requirements.txt
uvicorn notify.main:app --port 8001
```

```bash
curl -s -X POST localhost:8001/api/notify \
  -H 'content-type: application/json' \
  -d '{"geofence":"galveston-county","severity":"warning","summary":"Standing water covering two lanes."}'
```

## Environment

Set these in the shell. Do not commit them.

| Name | Purpose |
| --- | --- |
| `NOTIFY_SANDBOX_PHONES` | Comma-separated team numbers. The only SMS destinations. |
| `TWILIO_ACCOUNT_SID` | Twilio account SID. |
| `TWILIO_AUTH_TOKEN` | Twilio auth token. |
| `TWILIO_FROM_NUMBER` | Twilio from number. |
| `XAI_API_KEY` | Optional. When set, Grok drafts the SMS. |
| `XAI_MODEL` | Optional. Defaults to `grok-4`. |

If Twilio settings or sandbox numbers are missing, the route still returns the draft and roster with `delivered: []`. If `XAI_API_KEY` is missing or the draft call fails, `draft.source` is `template`.

Geofences that match the Houston–Galveston demo: `galveston`, `Galveston County`, `galveston-county`, `houston-galveston`, `houston-demo`. Anything else returns `matched: false` and `roster: []`.

## Tests

```bash
cd backend
python -m pytest notify/tests
```
