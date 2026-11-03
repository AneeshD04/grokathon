"""Draft a short sandbox SMS. Grok when XAI_API_KEY is set, otherwise a template."""

import os

import httpx

from notify.models import Draft

XAI_URL = "https://api.x.ai/v1/chat/completions"
SMS_LIMIT = 320

SYSTEM_PROMPT = (
    "You draft one SMS for a sandbox incident drill. "
    "Use only the severity, place, and summary you are given. "
    "Do not invent measurements, locations, or sources. "
    "Do not tell the recipient to call 911 or contact any emergency service. "
    "Reply with the SMS text only."
)


def template_body(severity: str, geofence: str, summary: str) -> str:
    return f"{severity.upper()} for {geofence}: {summary}"[:SMS_LIMIT]


def _grok_text(payload: dict) -> str:
    return str(payload["choices"][0]["message"]["content"]).strip()


def draft_sms(
    severity: str,
    geofence: str,
    summary: str,
    client: httpx.Client | None = None,
) -> Draft:
    fallback = Draft(body=template_body(severity, geofence, summary), source="template")
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return fallback

    own_client = client is None
    http = client or httpx.Client(timeout=15.0)
    try:
        response = http.post(
            XAI_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.environ.get("XAI_MODEL", "grok-4").strip() or "grok-4",
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"severity: {severity}\nplace: {geofence}\nsummary: {summary}"
                        ),
                    },
                ],
            },
        )
        response.raise_for_status()
        text = _grok_text(response.json())
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return fallback
    finally:
        if own_client:
            http.close()

    if not text or "911" in text:
        return fallback
    return Draft(body=text[:SMS_LIMIT], source="grok")
