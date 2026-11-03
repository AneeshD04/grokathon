"""Houston–Galveston org roster. Contacts are display-only and never dialed."""

import json
import os
from pathlib import Path

from notify.models import OrgRecord

DEMO_COUNTY = "galveston"
CANONICAL_GEOFENCE = "galveston-county"

# Normalized geofence text -> demo county key.
ALIASES = {
    "galveston": DEMO_COUNTY,
    "houston galveston": DEMO_COUNTY,
    "houston demo": DEMO_COUNTY,
}


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
    return Path(__file__).resolve().parent / "data" / "orgs.json"


def load_orgs() -> list[OrgRecord]:
    payload = json.loads(roster_path().read_text())
    return [OrgRecord.model_validate(item) for item in payload]


def match_geofence(geofence: str) -> tuple[str | None, list[OrgRecord]]:
    county = ALIASES.get(normalize(geofence))
    if county is None:
        return None, []
    orgs = [org for org in load_orgs() if normalize(org.county) == county]
    return CANONICAL_GEOFENCE, orgs
