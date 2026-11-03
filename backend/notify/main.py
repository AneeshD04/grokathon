"""Sandbox notify sidecar.

POST /api/notify drafts an SMS. Default is dry-run (log only). Live Twilio
requires a matching approval PIN and NOTIFY_DRY_RUN=0, and then texts only
NOTIFY_SANDBOX_PHONES. Roster contacts and 911 are never dialed.
"""

import hmac
import os
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from notify.draft import draft_sms, template_body
from notify.models import Delivery, Draft, NotifyRequest, NotifyResponse, RosterOrg
from notify.roster import load_orgs, match_geofence
from notify.send import (
    SandboxRejected,
    SmsSender,
    check_allowlist,
    dry_run_enabled,
    expected_approval_pin,
    sandbox_numbers,
    sender_from_env,
)


def _cors_origins() -> list[str]:
    raw = os.environ.get("NOTIFY_CORS_ORIGINS", "").strip()
    if raw == "*":
        return ["*"]
    if not raw:
        return [
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:5000",
            "http://localhost:5000",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "http://127.0.0.1:8001",
            "http://localhost:8001",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ]
    return [part.strip() for part in raw.split(",") if part.strip()]


app = FastAPI(title="Grokathon sandbox notify", version="0.1.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def get_sender() -> SmsSender | None:
    return sender_from_env()


def _pin_ok(provided: str) -> bool:
    expected = expected_approval_pin()
    if not expected:
        return False
    return hmac.compare_digest(provided, expected)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/notify", response_model=NotifyResponse)
def create_notification(
    body: NotifyRequest,
    sender: SmsSender | None = Depends(get_sender),
) -> NotifyResponse:
    if not _pin_ok(body.approval_pin):
        raise HTTPException(status_code=403, detail="invalid_approval_pin")

    canonical, orgs = match_geofence(body.geofence)
    place = canonical or body.geofence
    dry_run = dry_run_enabled()
    if dry_run:
        draft = Draft(body=template_body(body.severity.value, place, body.summary), source="template")
    else:
        draft = draft_sms(body.severity.value, place, body.summary)

    numbers = sandbox_numbers()
    forbidden = {org.phone for org in load_orgs() if org.phone}
    try:
        check_allowlist(numbers, forbidden)
        delivered = [] if dry_run else _deliver(sender, numbers, draft.body)
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
        sandbox_only=True,
        mode="dry-run-logged" if dry_run else "live-sandbox",
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
