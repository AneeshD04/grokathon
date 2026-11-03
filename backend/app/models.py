"""Alert and watch shapes from docs/SAFETY-AGENT-DESIGN.md.

shared/ is owned by issue #8. These models match that design doc until the
contract files land.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class Source(str, Enum):
    camera = "camera"
    nws = "nws"
    usgs = "usgs"
    x = "x"
    model = "model"
    news = "news"


class Severity(str, Enum):
    info = "info"
    watch = "watch"
    warning = "warning"
    critical = "critical"


class WatchCreate(BaseModel):
    bbox: list[float] | None = None
    county: str | None = None
    sources: list[Source] = Field(min_length=1)
    camera_ids: list[str] = Field(default_factory=list)
    geofence_id: str | None = None

    @model_validator(mode="after")
    def require_geofence(self) -> "WatchCreate":
        county = (self.county or "").strip()
        self.county = county or None
        if self.bbox is None and self.county is None:
            raise ValueError("bbox or county is required")
        if self.bbox is not None:
            if len(self.bbox) != 4:
                raise ValueError("bbox must be [minLon, minLat, maxLon, maxLat]")
            min_lon, min_lat, max_lon, max_lat = self.bbox
            if not (min_lon < max_lon and min_lat < max_lat):
                raise ValueError("bbox min must be less than max")
            if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
                raise ValueError("longitude out of range")
            if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
                raise ValueError("latitude out of range")
        return self


class Watch(BaseModel):
    id: str
    geofence_id: str
    bbox: list[float] | None = None
    county: str | None = None
    sources: list[Source]
    camera_ids: list[str]
    created_at: str


class Evidence(BaseModel):
    thumb_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class AlertCreate(BaseModel):
    source: Source
    severity: Severity
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    geofence_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence: Evidence = Field(default_factory=Evidence)
    dedupe_key: str = Field(min_length=1)
    ts: str | None = None

    @field_validator("ts")
    @classmethod
    def ts_must_be_iso(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parse_iso(value)
        return value


class Alert(BaseModel):
    id: str
    ts: str
    source: Source
    severity: Severity
    lat: float
    lon: float
    geofence_id: str
    title: str
    summary: str
    evidence: Evidence
    dedupe_key: str


class AlertPostResponse(BaseModel):
    alert: Alert
    deduped: bool


def parse_iso(value: str):
    from datetime import datetime

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("ts must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("ts must include a timezone")
    return parsed
