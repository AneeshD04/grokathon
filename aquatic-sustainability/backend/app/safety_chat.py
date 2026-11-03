"""POST /api/safety/chat — one Grok tool loop for the county OEM console.

Tools call the alert bus and notify sidecars over HTTP. Flood risk uses the
same in-process job as POST /api/flood-risk. list_cameras stays empty until
the cameras claim lands. This module does not send Twilio or call Grok from
inside a tool.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from flask import Blueprint, jsonify, request

bp = Blueprint("safety_chat", __name__)

API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_MODEL = "grok-4"
MAX_TOOL_ROUNDS = 4
DEFAULT_BUS_URL = "http://127.0.0.1:8000"
DEFAULT_NOTIFY_URL = "http://127.0.0.1:8001"

SYSTEM_PROMPT = (
    "You are an incident officer for county OEM / local government, not a consumer chatbot. "
    "Cite source and time. Never invent gauges, lab water-quality, oil CNN, or affordability. "
    "Distinguish real DualCNN-LSTM and GBR coral CSVs from dummy drought/flood polygons. "
    "If evidence.synthetic or vision is uncertain, say so. Never impersonate 911/NWS/IPAWS. "
    "Never send without PIN. Never treat Places numbers or opt-in phones as a live blast list. "
    "Never claim you WEA-blasted a county."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_watch",
            "description": "Create a watch on the alert bus for a county and/or bbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "county": {"type": "string"},
                    "bbox": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                        "description": "[minLon, minLat, maxLon, maxLat]",
                    },
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                },
                "required": ["sources"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_alerts",
            "description": "List alerts on the bus. Optional since is an ISO-8601 timestamp.",
            "parameters": {
                "type": "object",
                "properties": {"since": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_flood_risk",
            "description": "Run the existing flood-risk model for one lat/lon.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                },
                "required": ["lat", "lon"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_cameras",
            "description": "Cameras inside a bbox. Empty until the cameras API is merged.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bbox": {"type": "array", "items": {"type": "number"}},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notify_orgs",
            "description": "Dry-run notify via the notify sidecar. Requires an approval PIN. Does not call Grok.",
            "parameters": {
                "type": "object",
                "properties": {
                    "geofence": {"type": "string"},
                    "severity": {"type": "string"},
                    "summary": {"type": "string"},
                    "approval_pin": {"type": "string"},
                },
                "required": ["geofence", "severity", "summary", "approval_pin"],
            },
        },
    },
]


class MissingKey(Exception):
    """XAI_API_KEY is unset. Never carries a key value."""


def api_key() -> str:
    return os.environ.get("XAI_API_KEY", "").strip()


def http_json(method: str, url: str, payload: dict | None = None, headers: dict | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read().decode() or "null"
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        return {"error": detail or str(exc.reason), "status": exc.code}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"error": exc.__class__.__name__, "status": None}


def _default_flood(lat: float, lon: float) -> Any:
    from .tasks import run_flood_job

    return run_flood_job(lat, lon)


flood_runner = _default_flood


def complete(messages: list[dict], tools: list[dict]) -> dict:
    key = api_key()
    if not key:
        raise MissingKey()
    model = os.environ.get("XAI_MODEL", "").strip() or DEFAULT_MODEL
    payload = {
        "model": model,
        "temperature": 0,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())


def _bus_url() -> str:
    return os.environ.get("ALERT_BUS_URL", DEFAULT_BUS_URL).strip().rstrip("/") or DEFAULT_BUS_URL


def _notify_url() -> str:
    return os.environ.get("NOTIFY_URL", DEFAULT_NOTIFY_URL).strip().rstrip("/") or DEFAULT_NOTIFY_URL


def _bus_headers() -> dict[str, str]:
    token = os.environ.get("ALERT_BUS_TOKEN", "").strip()
    if not token:
        return {}
    return {"X-Alert-Bus-Token": token}


def _args(call: dict) -> dict:
    raw = (call.get("function") or {}).get("arguments") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def run_tool(name: str, arguments: dict) -> Any:
    if name == "set_watch":
        return set_watch(arguments)
    if name == "get_alerts":
        return get_alerts(arguments)
    if name == "get_flood_risk":
        return get_flood_risk(arguments)
    if name == "list_cameras":
        return {"cameras": []}
    if name == "notify_orgs":
        return notify_orgs(arguments)
    return {"error": "unknown tool"}


def set_watch(arguments: dict) -> Any:
    sources = arguments.get("sources")
    if isinstance(sources, str):
        sources = [sources]
    if not isinstance(sources, list) or not sources:
        return {"error": "sources is required"}
    county = (arguments.get("county") or "").strip()
    bbox = arguments.get("bbox")
    if not county and not isinstance(bbox, list):
        return {"error": "county or bbox is required"}
    body: dict[str, Any] = {"sources": sources}
    if county:
        body["county"] = county
    if isinstance(bbox, list):
        body["bbox"] = bbox
    return http_json("POST", f"{_bus_url()}/api/watches", body, _bus_headers())


def get_alerts(arguments: dict) -> Any:
    since = (arguments.get("since") or "").strip()
    url = f"{_bus_url()}/api/alerts"
    if since:
        url = f"{url}?since={urllib.request.quote(since)}"
    return http_json("GET", url, None, _bus_headers())


def get_flood_risk(arguments: dict) -> Any:
    try:
        lat = float(arguments["lat"])
        lon = float(arguments["lon"])
    except (KeyError, TypeError, ValueError):
        return {"error": "lat and lon are required"}
    try:
        return flood_runner(lat, lon)
    except Exception as exc:
        return {"error": exc.__class__.__name__}


def notify_orgs(arguments: dict) -> Any:
    body = {
        "geofence": arguments.get("geofence"),
        "severity": arguments.get("severity"),
        "summary": arguments.get("summary"),
        "approval_pin": arguments.get("approval_pin"),
    }
    if not all(isinstance(value, str) and value.strip() for value in body.values()):
        return {"error": "geofence, severity, summary, and approval_pin are required"}
    return http_json("POST", f"{_notify_url()}/api/notify", body, None)


def _user_messages(payload: Any) -> list[dict] | None:
    if not isinstance(payload, dict):
        return None
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    cleaned: list[dict] = []
    for item in messages:
        if not isinstance(item, dict):
            return None
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            return None
        cleaned.append({"role": role, "content": content})
    if not any(item["role"] == "user" for item in cleaned):
        return None
    return cleaned


def run_chat(messages: list[dict]) -> dict:
    transcript: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
    used: list[dict] = []
    for _ in range(MAX_TOOL_ROUNDS):
        data = complete(transcript, TOOLS)
        message = (data.get("choices") or [{}])[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return {"reply": message.get("content") or "", "tools": used}
        transcript.append(
            {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": tool_calls,
            }
        )
        for call in tool_calls:
            name = (call.get("function") or {}).get("name") or ""
            arguments = _args(call)
            result = run_tool(name, arguments)
            used.append({"name": name, "arguments": arguments, "result": result})
            transcript.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result),
                }
            )
    return {"reply": "", "tools": used}


@bp.route("/safety/chat", methods=["POST"])
def safety_chat():
    if not api_key():
        return jsonify({"error": "XAI_API_KEY is not set"}), 503
    messages = _user_messages(request.get_json(silent=True))
    if messages is None:
        return jsonify({"error": "messages must include a user turn"}), 400
    try:
        return jsonify(run_chat(messages))
    except MissingKey:
        return jsonify({"error": "XAI_API_KEY is not set"}), 503
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return jsonify({"error": "xAI request failed"}), 502
