"""Sandbox notify sidecar.

POST /api/notify drafts an SMS and sends it only to NOTIFY_SANDBOX_PHONES.
The org roster is returned for display. Those contacts are never texted.
"""

from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from notify.draft import draft_sms
from notify.models import Delivery, NotifyRequest, NotifyResponse, RosterOrg
from notify.roster import load_orgs, match_geofence
from notify.send import SandboxRejected, SmsSender, check_allowlist, sandbox_numbers, sender_from_env

app = FastAPI(title="Grokathon sandbox notify", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_sender() -> SmsSender | None:
    return sender_from_env()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/notify", response_model=NotifyResponse)
def create_notification(
    body: NotifyRequest,
    sender: SmsSender | None = Depends(get_sender),
) -> NotifyResponse:
    canonical, orgs = match_geofence(body.geofence)
    place = canonical or body.geofence
    draft = draft_sms(body.severity.value, place, body.summary)
    numbers = sandbox_numbers()
    forbidden = {org.phone for org in load_orgs() if org.phone}
    try:
        check_allowlist(numbers, forbidden)
        delivered = _deliver(sender, numbers, draft.body)
    except SandboxRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Sandbox SMS provider failed") from exc

    return NotifyResponse(
        id=str(uuid4()),
        severity=body.severity,
        geofence=place,
        matched=canonical is not None,
        draft=draft,
        delivered=delivered,
        roster=[RosterOrg(**org.model_dump(), would_notify=True) for org in orgs],
    )


def _deliver(sender: SmsSender | None, numbers: list[str], body: str) -> list[Delivery]:
    if sender is None or not numbers:
        return []
    delivered: list[Delivery] = []
    for number in numbers:
        sender.send(number, body)
        delivered.append(Delivery(channel="sms", to=number))
    return delivered
