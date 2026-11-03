"""Gov-uploaded opt-in resident roster, scoped to a marked region.

JSON file store + CRUD. This is the only public-recipient list for
"Text everyone" — not WEA, not a county-wide blast, not scraped phones.

No Twilio / SMS / voice. Send stays issue #13 (PIN dry-run).
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("roster", __name__)

_LOCK = threading.RLock()

EMERGENCY_DIGITS = {"911", "1911", "112", "999", "000", "110"}
REGION_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_HEADER = {"phone", "phones", "mobile", "cell", "number", "e164"}
LABEL_HEADER = {"label", "name", "contact", "resident"}
EMAIL_HEADER = {"email", "mail"}


class RosterError(ValueError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def register_roster(app, store_path: str | os.PathLike[str] | None = None) -> None:
    """Attach roster routes. Safe to call more than once. No send path."""
    if store_path is not None:
        app.config["ROSTER_STORE_PATH"] = str(store_path)
    if "roster" not in app.blueprints:
        app.register_blueprint(bp, url_prefix="/api")


def roster_store_path() -> Path:
    try:
        configured = current_app.config.get("ROSTER_STORE_PATH")
    except RuntimeError:
        configured = None
    if configured:
        return Path(configured)
    env = os.environ.get("ROSTER_STORE_PATH", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data" / "optin-rosters.json"


def normalize_region_id(value: str) -> str:
    text = (value or "").strip().lower().replace("_", "-").replace(" ", "-")
    text = re.sub(r"-{2,}", "-", text).strip("-")
    if not REGION_RE.fullmatch(text):
        raise RosterError("invalid_region_id")
    return text


def digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def is_emergency(value: str) -> bool:
    stripped = digits_only(value)
    return stripped in EMERGENCY_DIGITS or (stripped.endswith("911") and len(stripped) <= 4)


def normalize_phone(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise RosterError("invalid_phone")
    if is_emergency(text):
        raise RosterError("emergency_number")
    plus = text.startswith("+")
    digits = digits_only(text)
    if is_emergency(digits):
        raise RosterError("emergency_number")
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if plus and 10 <= len(digits) <= 15:
        return "+" + digits
    if 10 <= len(digits) <= 15:
        return "+" + digits
    raise RosterError("invalid_phone")


def normalize_email(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if not EMAIL_RE.fullmatch(text):
        raise RosterError("invalid_email")
    return text


def normalize_label(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text[:120] or None


def empty_store() -> dict[str, Any]:
    return {"version": 1, "regions": {}}


def empty_region(region_id: str) -> dict[str, Any]:
    return {
        "region_id": region_id,
        "updated_at": None,
        "contacts": [],
    }


def public_recipients(
    region_id: str,
    store_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    """Contacts the #13 dry-run send path should list. Empty → skip public SMS."""
    rid = normalize_region_id(region_id)
    if store_path is not None:
        path = Path(store_path)
        with _LOCK:
            payload = _read_store_unlocked(path)
        return list(_region_view(payload, rid)["contacts"])
    region = _region_view(load_store(), rid)
    return list(region["contacts"])


def _read_store_unlocked(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return empty_store()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_store()
    if not isinstance(payload, dict):
        return empty_store()
    regions = payload.get("regions")
    if not isinstance(regions, dict):
        payload["regions"] = {}
    payload["version"] = 1
    return payload


def load_store() -> dict[str, Any]:
    path = roster_store_path()
    with _LOCK:
        return _read_store_unlocked(path)


def save_store(payload: dict[str, Any]) -> None:
    path = roster_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    with _LOCK:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)


def mutate_store(mutator):
    path = roster_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        payload = _read_store_unlocked(path)
        result = mutator(payload)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    return result


def _region_view(payload: dict[str, Any], region_id: str) -> dict[str, Any]:
    raw = payload.get("regions", {}).get(region_id)
    if not isinstance(raw, dict):
        region = empty_region(region_id)
    else:
        contacts = raw.get("contacts") or []
        if not isinstance(contacts, list):
            contacts = []
        region = {
            "region_id": region_id,
            "updated_at": raw.get("updated_at"),
            "contacts": [c for c in contacts if isinstance(c, dict)],
        }
    count = len(region["contacts"])
    region["count"] = count
    region["empty"] = count == 0
    region["public_sms"] = "skipped" if count == 0 else "roster"
    return region


def _new_contact(phone: str, label: str | None, email: str | None) -> dict[str, Any]:
    return {
        "id": "r_" + uuid.uuid4().hex[:10],
        "phone": phone,
        "label": label,
        "email": email,
    }


def _contact_from_body(body: dict[str, Any]) -> dict[str, Any]:
    phone = normalize_phone(str(body.get("phone") or body.get("number") or ""))
    label = normalize_label(body.get("label") if "label" in body else body.get("name"))
    email = normalize_email(body.get("email"))
    return _new_contact(phone, label, email)


def _parse_csv_text(text: str) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return []
    sample = raw[:2048]
    delimiter = "," if ("," in sample or "\t" not in sample) else "\t"
    reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return []

    header = [cell.strip().lower() for cell in rows[0]]
    has_header = any(cell in PHONE_HEADER or cell in LABEL_HEADER or cell in EMAIL_HEADER for cell in header)
    contacts: list[dict[str, Any]] = []

    def from_parts(phone_raw: str, label_raw: str | None, email_raw: str | None) -> None:
        contact = _new_contact(
            normalize_phone(phone_raw),
            normalize_label(label_raw),
            normalize_email(email_raw),
        )
        contacts.append(contact)

    if has_header:
        idx = {name: i for i, name in enumerate(header)}

        def col(names: set[str]) -> int | None:
            for name in names:
                if name in idx:
                    return idx[name]
            return None

        phone_i = col(PHONE_HEADER)
        label_i = col(LABEL_HEADER)
        email_i = col(EMAIL_HEADER)
        if phone_i is None:
            phone_i = 0
        for row in rows[1:]:
            phone_raw = row[phone_i] if phone_i < len(row) else ""
            label_raw = row[label_i] if label_i is not None and label_i < len(row) else None
            email_raw = row[email_i] if email_i is not None and email_i < len(row) else None
            if not str(phone_raw).strip():
                continue
            from_parts(str(phone_raw), label_raw, email_raw)
        return contacts

    for row in rows:
        phone_raw = row[0] if row else ""
        label_raw = row[1] if len(row) > 1 else None
        email_raw = row[2] if len(row) > 2 else None
        if not str(phone_raw).strip():
            continue
        from_parts(str(phone_raw), label_raw, email_raw)
    return contacts


def _contacts_from_request() -> list[dict[str, Any]] | None:
    """Parse replace/import body. None means the client sent no contact payload."""
    if request.files:
        upload = request.files.get("file") or request.files.get("csv")
        if upload is not None:
            text = upload.read().decode("utf-8-sig")
            return _parse_csv_text(text)

    body = request.get_json(silent=True)
    if isinstance(body, list):
        return [_contact_from_body(item if isinstance(item, dict) else {"phone": item}) for item in body]
    if not isinstance(body, dict):
        form_csv = request.form.get("csv") or request.form.get("text")
        if form_csv is not None:
            return _parse_csv_text(form_csv)
        return None

    if "contacts" in body:
        items = body.get("contacts") or []
        if not isinstance(items, list):
            raise RosterError("invalid_contacts")
        return [_contact_from_body(item if isinstance(item, dict) else {"phone": item}) for item in items]
    if "csv" in body or "text" in body:
        return _parse_csv_text(str(body.get("csv") or body.get("text") or ""))
    if "phone" in body or "number" in body:
        return [_contact_from_body(body)]
    return None


def _dedupe(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for contact in contacts:
        key = digits_only(contact["phone"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(contact)
    return unique


def _write_region(payload: dict[str, Any], region_id: str, contacts: list[dict[str, Any]]) -> dict[str, Any]:
    unique = _dedupe(contacts)
    payload.setdefault("regions", {})[region_id] = {
        "region_id": region_id,
        "updated_at": utcnow(),
        "contacts": unique,
    }
    return _region_view(payload, region_id)


def _err(exc: RosterError):
    return jsonify({"ok": False, "error": exc.code}), exc.status


@bp.route("/roster", methods=["GET"])
def list_regions():
    payload = load_store()
    regions = []
    for region_id in sorted(payload.get("regions", {})):
        regions.append(_region_view(payload, region_id))
    return jsonify({"ok": True, "regions": regions})


@bp.route("/roster/<region_id>", methods=["GET"])
def get_region(region_id: str):
    try:
        rid = normalize_region_id(region_id)
    except RosterError as exc:
        return _err(exc)
    return jsonify({"ok": True, **_region_view(load_store(), rid)})


@bp.route("/roster/<region_id>", methods=["PUT", "POST"])
def replace_region(region_id: str):
    try:
        rid = normalize_region_id(region_id)
        contacts = _contacts_from_request()
        if contacts is None:
            raise RosterError("invalid_contacts")
    except RosterError as exc:
        return _err(exc)

    def mutator(payload: dict[str, Any]):
        return _write_region(payload, rid, contacts)

    region = mutate_store(mutator)
    return jsonify({"ok": True, **region})


@bp.route("/roster/<region_id>", methods=["DELETE"])
def delete_region(region_id: str):
    try:
        rid = normalize_region_id(region_id)
    except RosterError as exc:
        return _err(exc)

    def mutator(payload: dict[str, Any]):
        payload.setdefault("regions", {}).pop(rid, None)
        return _region_view(payload, rid)

    region = mutate_store(mutator)
    return jsonify({"ok": True, **region})


@bp.route("/roster/<region_id>/contacts", methods=["POST"])
def add_contact(region_id: str):
    try:
        rid = normalize_region_id(region_id)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise RosterError("invalid_contacts")
        incoming = _contact_from_body(body)
    except RosterError as exc:
        return _err(exc)

    conflict = {"hit": False}

    def mutator(payload: dict[str, Any]):
        region = payload.setdefault("regions", {}).get(rid) or empty_region(rid)
        contacts = list(region.get("contacts") or [])
        key = digits_only(incoming["phone"])
        if any(digits_only(c.get("phone") or "") == key for c in contacts if isinstance(c, dict)):
            conflict["hit"] = True
            return _region_view(payload, rid)
        contacts.append(incoming)
        return _write_region(payload, rid, contacts)

    region = mutate_store(mutator)
    if conflict["hit"]:
        return jsonify({"ok": False, "error": "duplicate_phone", **region}), 409
    return jsonify({"ok": True, "contact": incoming, **region}), 201


@bp.route("/roster/<region_id>/import", methods=["POST"])
def import_contacts(region_id: str):
    try:
        rid = normalize_region_id(region_id)
        incoming = _contacts_from_request()
        if incoming is None:
            raise RosterError("invalid_contacts")
    except RosterError as exc:
        return _err(exc)

    def mutator(payload: dict[str, Any]):
        region = payload.setdefault("regions", {}).get(rid) or empty_region(rid)
        existing = list(region.get("contacts") or [])
        return _write_region(payload, rid, existing + incoming)

    region = mutate_store(mutator)
    return jsonify({"ok": True, **region})


@bp.route("/roster/<region_id>/contacts/<contact_id>", methods=["PATCH", "PUT"])
def update_contact(region_id: str, contact_id: str):
    try:
        rid = normalize_region_id(region_id)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise RosterError("invalid_contacts")
    except RosterError as exc:
        return _err(exc)

    missing = {"hit": False}
    duplicate = {"hit": False}
    updated = {"contact": None}

    def mutator(payload: dict[str, Any]):
        region = payload.setdefault("regions", {}).get(rid) or empty_region(rid)
        contacts = [dict(c) for c in (region.get("contacts") or []) if isinstance(c, dict)]
        target = next((c for c in contacts if c.get("id") == contact_id), None)
        if target is None:
            missing["hit"] = True
            return _region_view(payload, rid)
        if "phone" in body or "number" in body:
            target["phone"] = normalize_phone(str(body.get("phone") or body.get("number") or ""))
        if "label" in body or "name" in body:
            target["label"] = normalize_label(body.get("label") if "label" in body else body.get("name"))
        if "email" in body:
            target["email"] = normalize_email(body.get("email"))
        key = digits_only(target["phone"])
        if sum(1 for c in contacts if digits_only(c.get("phone") or "") == key) > 1:
            duplicate["hit"] = True
            return _region_view(payload, rid)
        updated["contact"] = dict(target)
        return _write_region(payload, rid, contacts)

    try:
        region = mutate_store(mutator)
    except RosterError as exc:
        return _err(exc)
    if missing["hit"]:
        return jsonify({"ok": False, "error": "contact_not_found"}), 404
    if duplicate["hit"]:
        return jsonify({"ok": False, "error": "duplicate_phone"}), 409
    return jsonify({"ok": True, "contact": updated["contact"], **region})


@bp.route("/roster/<region_id>/contacts/<contact_id>", methods=["DELETE"])
def delete_contact(region_id: str, contact_id: str):
    try:
        rid = normalize_region_id(region_id)
    except RosterError as exc:
        return _err(exc)

    missing = {"hit": False}

    def mutator(payload: dict[str, Any]):
        region = payload.setdefault("regions", {}).get(rid) or empty_region(rid)
        contacts = [c for c in (region.get("contacts") or []) if isinstance(c, dict)]
        kept = [c for c in contacts if c.get("id") != contact_id]
        if len(kept) == len(contacts):
            missing["hit"] = True
            return _region_view(payload, rid)
        return _write_region(payload, rid, kept)

    region = mutate_store(mutator)
    if missing["hit"]:
        return jsonify({"ok": False, "error": "contact_not_found"}), 404
    return jsonify({"ok": True, **region})
