"""Single-frame Grok vision labels for flood cameras.

Loads XAI_API_KEY from the environment, or from /workspace/grokathon/.env
when the variable is unset. Never logs the key or the Authorization header.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

ENV_PATH = Path("/workspace/grokathon/.env")
API_URL = "https://api.x.ai/v1/chat/completions"
# xAI image-understanding docs use grok-4.7 for image input (checked 2026).
DEFAULT_MODEL = "grok-4.7"
# Longest first so "standing water" wins over a shorter token inside it.
LABELS = (
    "people in water",
    "standing water",
    "impassable",
    "dry",
    "wet",
)

_LABEL_RE = re.compile(
    "|".join(rf"(?<![a-z]){re.escape(label)}(?![a-z])" for label in LABELS)
)


class GrokClientError(Exception):
    """Missing key or a failed vision call. Never carries the API key."""


def classify_frame(jpeg_bytes: bytes, camera_name: str) -> str:
    """Return one flood label for a JPEG frame.

    Labels: dry, wet, standing water, impassable, people in water.
    Raises GrokClientError when the key is missing or the API call fails.
    """
    if not isinstance(jpeg_bytes, (bytes, bytearray)) or not jpeg_bytes:
        raise GrokClientError("jpeg_bytes must be a non-empty JPEG")

    api_key = _load_api_key()
    if not api_key:
        raise GrokClientError(
            "XAI_API_KEY is not set in the environment or /workspace/grokathon/.env"
        )

    model = (os.environ.get("XAI_VISION_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    name = " ".join(str(camera_name).split()) or "unknown camera"
    encoded = base64.standard_b64encode(bytes(jpeg_bytes)).decode("ascii")
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encoded}",
                            "detail": "low",
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Camera: {name}. "
                            "Classify this frame for flood safety. "
                            "Reply with exactly one of these labels and no other text: "
                            "dry, wet, standing water, impassable, people in water."
                        ),
                    },
                ],
            }
        ],
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Drop the urllib error: its request object holds the bearer token.
        raise GrokClientError(f"xAI vision HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise GrokClientError(f"xAI vision request failed: {exc.reason}") from None
    except TimeoutError:
        raise GrokClientError("xAI vision request timed out") from None
    except json.JSONDecodeError:
        raise GrokClientError("xAI vision returned invalid JSON") from None

    try:
        content = payload["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError) as exc:
        raise GrokClientError("xAI vision response missing message content") from exc
    text = _content_text(content)
    if not text:
        raise GrokClientError("xAI vision returned empty content")
    return _extract_label(text)


def _load_api_key() -> str:
    existing = (os.environ.get("XAI_API_KEY") or "").strip()
    if existing:
        return existing
    if not ENV_PATH.is_file():
        return ""
    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise GrokClientError(f"could not read {ENV_PATH}") from exc
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() != "XAI_API_KEY":
            continue
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ["XAI_API_KEY"] = value
        return value
    return ""


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _extract_label(text: str) -> str:
    cleaned = text.strip().lower()
    exact = cleaned.strip("`\"'").strip().rstrip(".").strip()
    if exact in LABELS:
        return exact
    match = _LABEL_RE.search(cleaned)
    if match:
        return match.group(0)
    raise GrokClientError("xAI vision returned an unrecognized label")
