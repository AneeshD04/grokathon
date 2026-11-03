"""PIN-gated sandbox notify on the Flask app.

Demo send is dry-run only. Correct PIN logs intended recipients and returns
success as if sent. Wrong PIN rejects with no log. Live Twilio, Grok drafts,
911, and Places phone dialing are not implemented on this path.

Rotate DEMO_APPROVAL_PIN before any real deployment. Hackathon default is
documented in docs/SAFETY-AGENT-DESIGN.md — do not put it in issue titles.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Blueprint, jsonify, request

bp = Blueprint("notify", __name__)
log = logging.getLogger(__name__)

SEVERITIES = {"info", "watch", "warning", "critical"}
ORG_TYPES = {"county_em", "nws", "uscg", "311"}
SMS_LIMIT = 320
EMERGENCY_DIGITS = {"911", "1911", "112", "999"}
DEMO_COUNTY = "galveston"
CANONICAL_GEOFENCE = "galveston-county"
ALIASES = {
    "galveston": DEMO_COUNTY,
    "houston galveston": DEMO_COUNTY,
    "houston demo": DEMO_COUNTY,
}
NOTIFY_FIELDS = {"geofence", "severity", "summary", "approval_pin"}
SEND_FIELDS = {
    "geofence_id",
    "geofence",
    "alert_id",
    "message",
    "summary",
    "severity",
    "business_place_ids",
    "resident_ids",
    "include_ipaws_stub",
    "approval_pin",
}

_logs: list[dict[str, Any]] = []


def dry_run_enabled() -> bool:
    """Unset and any value other than an explicit live flag is dry-run.

    The demo has no live-send path: even NOTIFY_DRY_RUN=0 does not call Twilio.
    """
    raw = os.environ.get("NOTIFY_DRY_RUN", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def expected_approval_pin() -> str:
    # Hackathon default matches docs/SAFETY-AGENT-DESIGN.md. Rotate before deploy.
    return os.environ.get("DEMO_APPROVAL_PIN", "3408")


def digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def is_emergency(value: str) -> bool:
    stripped = digits(value)
    return stripped in EMERGENCY_DIGITS or stripped.endswith("911")


def sandbox_numbers() -> list[str]:
    raw = os.environ.get("NOTIFY_SANDBOX_PHONES", "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def pin_ok(provided: str) -> bool:
    expected = expected_approval_pin()
    if not expected or not provided:
        return False
    if len(provided) != len(expected):
        return False
    return hmac.compare_digest(provided, expected)


def template_body(severity: str, geofence: str, summary: str) -> str:
    return f"{severity.upper()} for {geofence}: {summary}"[:SMS_LIMIT]


def normalize(value: str) -> str:
    text = value.strip().lower().replace("-", " ").replace("_", " ")
    text = " ".join(text.split())
    if text.endswith(" county"):
        text = text[: -len(" county")].strip()
    return text


def roster_path() -> Path:
    override = os.environ.get("NOTIFY_ROSTER_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "orgs.json"


def load_orgs() -> list[dict[str, Any]]:
    payload = json.loads(roster_path().read_text(encoding="utf-8"))
    orgs = []
    for item in payload:
        org_type = item.get("type")
        if org_type not in ORG_TYPES:
            continue
        orgs.append(
            {
                "name": item.get("name"),
                "type": org_type,
                "county": item.get("county"),
                "email": item.get("email"),
                "phone": item.get("phone"),
            }
        )
    return orgs


def match_geofence(geofence: str) -> tuple[str | None, list[dict[str, Any]]]:
    county = ALIASES.get(normalize(geofence))
    if county is None:
        return None, []
    orgs = [org for org in load_orgs() if normalize(str(org.get("county") or "")) == county]
    return CANONICAL_GEOFENCE, orgs


def reset_logs() -> None:
    _logs.clear()


def notify_log_path() -> Path:
    override = os.environ.get("NOTIFY_LOG_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "data" / "notify_log.json"


def persist_log(entry: dict[str, Any]) -> None:
    _logs.append(entry)
    path = notify_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: list[dict[str, Any]] = []
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    existing = loaded
            except json.JSONDecodeError:
                existing = []
        existing.append(entry)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("notify_log persist failed: %s", exc)


def check_allowlist(numbers: list[str], forbidden: set[str]) -> None:
    blocked = {digits(number) for number in forbidden if digits(number)}
    for number in numbers:
        if is_emergency(number) or digits(number) in blocked:
            raise ValueError(
                "Sandbox SMS cannot go to an emergency number or a roster contact"
            )


def _json() -> tuple[dict[str, Any] | None, tuple | None]:
    if not request.is_json:
        return None, (jsonify({"detail": "JSON body required"}), 400)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, (jsonify({"detail": "JSON object required"}), 400)
    return body, None


def _unknown_fields(body: dict[str, Any], allowed: set[str]):
    extra = [key for key in body if key not in allowed]
    if extra:
        return jsonify({"detail": f"unknown field: {extra[0]}"}), 400
    return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@bp.route("/notify", methods=["POST"])
def create_notification():
    body, err = _json()
    if err:
        return err
    extra = _unknown_fields(body, NOTIFY_FIELDS)
    if extra:
        return extra

    geofence = str(body.get("geofence") or "").strip()
    summary = str(body.get("summary") or "").strip()
    severity = str(body.get("severity") or "").strip()
    approval_pin = str(body.get("approval_pin") or "")
    if not geofence or len(geofence) > 120 or not summary or len(summary) > 4000:
        return jsonify({"detail": "geofence and summary are required"}), 400
    if severity not in SEVERITIES:
        return jsonify({"detail": "invalid severity"}), 400
    if not pin_ok(approval_pin):
        return jsonify({"detail": "invalid_approval_pin", "ok": False, "error": "invalid_approval_pin"}), 403

    canonical, orgs = match_geofence(geofence)
    place = canonical or geofence
    draft_text = template_body(severity, place, summary)
    if "911" in draft_text:
        return jsonify({"detail": "draft must not mention 911"}), 400

    numbers = sandbox_numbers()
    forbidden = {org["phone"] for org in load_orgs() if org.get("phone")}
    try:
        check_allowlist(numbers, forbidden)
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400

    intended = [{"channel": "sms", "to": number, "sent": False} for number in numbers]
    roster = [{**org, "would_notify": True} for org in orgs]
    entry = {
        "id": str(uuid4()),
        "ts": _iso_now(),
        "mode": "dry-run-logged",
        "severity": severity,
        "geofence": place,
        "draft": {"body": draft_text, "source": "template"},
        "intended": intended,
        "roster": roster,
        "live_send": False,
    }
    persist_log(entry)
    log.info(
        "notify dry-run id=%s geofence=%s intended=%s roster=%s (no Twilio)",
        entry["id"],
        place,
        len(intended),
        len(roster),
    )
    return jsonify(
        {
            "id": entry["id"],
            "severity": severity,
            "geofence": place,
            "matched": canonical is not None,
            "draft": entry["draft"],
            "delivered": [],
            "sandbox_only": True,
            "mode": "dry-run-logged",
            "roster": roster,
        }
    )


@bp.route("/notify/send", methods=["POST"])
def send_notification():
    """Confirm-send for the flood-drought tools. Always dry-run; never Twilio."""
    body, err = _json()
    if err:
        return err
    extra = _unknown_fields(body, SEND_FIELDS)
    if extra:
        return extra

    approval_pin = str(body.get("approval_pin") or "")
    if not pin_ok(approval_pin):
        return jsonify({"ok": False, "error": "invalid_approval_pin"}), 403

    geofence = str(body.get("geofence_id") or body.get("geofence") or "").strip()
    summary = str(body.get("message") or body.get("summary") or "").strip()
    severity = str(body.get("severity") or "warning").strip() or "warning"
    if severity not in SEVERITIES:
        return jsonify({"ok": False, "error": "invalid severity"}), 400
    if not geofence:
        geofence = "unspecified"
    if not summary:
        summary = "Confirmed flood-risk notify (sandbox dry-run)."

    canonical, orgs = match_geofence(geofence)
    place = canonical or geofence
    draft_text = template_body(severity, place, summary)
    if "911" in draft_text:
        return jsonify({"ok": False, "error": "draft must not mention 911"}), 400

    business_ids = body.get("business_place_ids") or []
    resident_ids = body.get("resident_ids") or []
    if not isinstance(business_ids, list) or not isinstance(resident_ids, list):
        return jsonify({"ok": False, "error": "ids must be lists"}), 400
    business_ids = [str(item) for item in business_ids]
    resident_ids = [str(item) for item in resident_ids]
    include_ipaws = bool(body.get("include_ipaws_stub", True))

    numbers = sandbox_numbers()
    forbidden = {org["phone"] for org in load_orgs() if org.get("phone")}
    try:
        check_allowlist(numbers, forbidden)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    would_notify = {
        "businesses": len(business_ids),
        "residents": len(resident_ids),
        "orgs": len(orgs),
        "ipaws_stub": include_ipaws,
    }
    entry = {
        "id": str(uuid4()),
        "ts": _iso_now(),
        "mode": "dry-run-logged",
        "alert_id": body.get("alert_id"),
        "geofence": place,
        "draft": {"body": draft_text, "source": "template"},
        "business_place_ids": business_ids,
        "resident_ids": resident_ids,
        "ipaws_stub": include_ipaws,
        "intended_sms": [{"channel": "sms", "to": number, "sent": False} for number in numbers],
        "roster": [{**org, "would_notify": True} for org in orgs],
        "would_notify": would_notify,
        "live_send": False,
    }
    persist_log(entry)
    log.info(
        "notify/send dry-run log_id=%s would_notify=%s (no Twilio, no IPAWS)",
        entry["id"],
        would_notify,
    )
    return jsonify(
        {
            "ok": True,
            "mode": "dry-run-logged",
            "would_notify": would_notify,
            "log_id": entry["id"],
            "draft": entry["draft"],
            "sandbox_only": True,
        }
    )
