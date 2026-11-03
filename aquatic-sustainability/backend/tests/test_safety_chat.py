"""Safety chat tool loop. No live xAI, alert bus, notify sidecar, or flood model."""

import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask

BACKEND = Path(__file__).resolve().parents[1]
INIT_PY = BACKEND / "app" / "__init__.py"


def _load():
    path = BACKEND / "app" / "safety_chat.py"
    spec = importlib.util.spec_from_file_location("safety_chat_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


chat = _load()


def _client():
    app = Flask(__name__)
    app.register_blueprint(chat.bp, url_prefix="/api")
    return app.test_client()


def _tool_message(name: str, arguments: dict, call_id: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                }
            }
        ]
    }


def _text_message(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class SafetyChatTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("XAI_API_KEY")
        os.environ["XAI_API_KEY"] = "test-key"

    def tearDown(self):
        if self._env is None:
            os.environ.pop("XAI_API_KEY", None)
        else:
            os.environ["XAI_API_KEY"] = self._env

    def test_blueprint_is_registered_on_the_flask_app(self):
        source = INIT_PY.read_text()
        self.assertIn("from .safety_chat import bp as safety_chat_bp", source)
        self.assertIn('app.register_blueprint(safety_chat_bp, url_prefix="/api")', source)

    def test_missing_key_returns_503_without_calling_xai(self):
        os.environ.pop("XAI_API_KEY", None)

        def explode(*_args, **_kwargs):
            raise AssertionError("xAI was called")

        with mock.patch.object(chat, "complete", explode):
            response = _client().post("/api/safety/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "XAI_API_KEY is not set")

    def test_galveston_watch_then_reply_cites_the_alert(self):
        http_calls = []
        turns = {"n": 0}

        def fake_complete(_messages, _tools):
            turns["n"] += 1
            if turns["n"] == 1:
                return _tool_message(
                    "set_watch",
                    {"county": "Galveston County", "sources": ["nws", "camera"]},
                    "call-watch",
                )
            if turns["n"] == 2:
                return _tool_message("get_alerts", {}, "call-alerts")
            return _text_message("Alert alt-1 from camera at 2026-11-02T00:00:00Z: water over the roadway.")

        def fake_http(method, url, payload=None, headers=None):
            http_calls.append((method, url, payload, headers))
            if url.endswith("/api/watches"):
                return {
                    "id": "w1",
                    "geofence_id": "galveston-county",
                    "county": payload["county"],
                    "sources": payload["sources"],
                }
            if "/api/alerts" in url:
                return [
                    {
                        "id": "alt-1",
                        "source": "camera",
                        "ts": "2026-11-02T00:00:00Z",
                        "title": "Water over roadway",
                    }
                ]
            return {"error": "unexpected", "status": None}

        with (
            mock.patch.object(chat, "complete", fake_complete),
            mock.patch.object(chat, "http_json", fake_http),
        ):
            response = _client().post(
                "/api/safety/chat",
                json={"messages": [{"role": "user", "content": "Watch Galveston County"}]},
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn("alt-1", body["reply"])
        self.assertEqual([item["name"] for item in body["tools"]], ["set_watch", "get_alerts"])
        method, url, payload, _headers = http_calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/api/watches"))
        self.assertEqual(payload["county"], "Galveston County")
        self.assertEqual(payload["sources"], ["nws", "camera"])

    def test_list_cameras_is_empty_and_does_not_use_http(self):
        def fake_complete(_messages, _tools):
            if not getattr(fake_complete, "called", False):
                fake_complete.called = True
                return _tool_message("list_cameras", {"bbox": [-95.0, 29.2, -94.7, 29.4]}, "call-cams")
            return _text_message("No cameras are listed yet.")

        fake_complete.called = False

        def explode(*_args, **_kwargs):
            raise AssertionError("list_cameras used HTTP")

        with (
            mock.patch.object(chat, "complete", fake_complete),
            mock.patch.object(chat, "http_json", explode),
        ):
            response = _client().post(
                "/api/safety/chat",
                json={"messages": [{"role": "user", "content": "What cameras are in Galveston?"}]},
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["tools"][0]["result"], {"cameras": []})

    def test_notify_posts_pin_and_summary_without_grok_inside_the_tool(self):
        http_calls = []
        complete_calls = {"n": 0}

        def fake_complete(_messages, _tools):
            complete_calls["n"] += 1
            if complete_calls["n"] == 1:
                return _tool_message(
                    "notify_orgs",
                    {
                        "geofence": "galveston-county",
                        "severity": "warning",
                        "summary": "Standing water on the seawall.",
                        "approval_pin": "3408",
                    },
                    "call-notify",
                )
            return _text_message("Logged a dry-run notify for galveston-county.")

        def fake_http(method, url, payload=None, headers=None):
            http_calls.append((method, url, payload))
            return {"ok": True, "mode": "dry-run-logged", "id": "n1"}

        with (
            mock.patch.object(chat, "complete", fake_complete),
            mock.patch.object(chat, "http_json", fake_http),
        ):
            response = _client().post(
                "/api/safety/chat",
                json={"messages": [{"role": "user", "content": "Notify orgs about the seawall."}]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(complete_calls["n"], 2)
        method, url, payload = http_calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "http://127.0.0.1:8001/api/notify")
        self.assertEqual(payload["approval_pin"], "3408")
        self.assertEqual(payload["summary"], "Standing water on the seawall.")
