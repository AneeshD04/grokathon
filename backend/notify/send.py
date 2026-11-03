"""Twilio SMS restricted to NOTIFY_SANDBOX_PHONES. Roster numbers are never dialed."""

import os
from typing import Protocol

import httpx

EMERGENCY_DIGITS = {"911", "1911"}


class SandboxRejected(Exception):
    """A sandbox destination is an emergency number or a roster contact."""


class SmsSender(Protocol):
    def send(self, to: str, body: str) -> None: ...


def digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def is_emergency(value: str) -> bool:
    return digits(value) in EMERGENCY_DIGITS


def sandbox_numbers() -> list[str]:
    raw = os.environ.get("NOTIFY_SANDBOX_PHONES", "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def twilio_configured() -> bool:
    return all(
        os.environ.get(name, "").strip()
        for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER")
    )


def check_allowlist(numbers: list[str], forbidden: set[str]) -> None:
    blocked = {digits(number) for number in forbidden if digits(number)}
    for number in numbers:
        if is_emergency(number) or digits(number) in blocked:
            raise SandboxRejected(
                "Sandbox SMS cannot go to an emergency number or a roster contact"
            )


class TwilioSender:
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self._client = client

    def send(self, to: str, body: str) -> None:
        if is_emergency(to) or is_emergency(self.from_number):
            raise SandboxRejected(
                "Sandbox SMS cannot go to an emergency number or a roster contact"
            )
        url = (
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{self.account_sid}/Messages.json"
        )
        own_client = self._client is None
        http = self._client or httpx.Client(timeout=15.0)
        try:
            response = http.post(
                url,
                auth=(self.account_sid, self.auth_token),
                data={"To": to, "From": self.from_number, "Body": body},
            )
            response.raise_for_status()
        finally:
            if own_client:
                http.close()


def sender_from_env() -> TwilioSender | None:
    if not twilio_configured():
        return None
    return TwilioSender(
        os.environ["TWILIO_ACCOUNT_SID"].strip(),
        os.environ["TWILIO_AUTH_TOKEN"].strip(),
        os.environ["TWILIO_FROM_NUMBER"].strip(),
    )
