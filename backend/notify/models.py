"""Request and response shapes for POST /api/notify."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Severity(str, Enum):
    info = "info"
    watch = "watch"
    warning = "warning"
    critical = "critical"


class OrgType(str, Enum):
    county_em = "county_em"
    nws = "nws"
    uscg = "uscg"
    city_311 = "311"


class NotifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geofence: str = Field(min_length=1)
    severity: Severity
    summary: str = Field(min_length=1)

    @field_validator("geofence", "summary")
    @classmethod
    def strip_required(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be blank")
        return text


class Draft(BaseModel):
    body: str
    source: str


class Delivery(BaseModel):
    channel: str = "sms"
    to: str


class OrgRecord(BaseModel):
    name: str
    type: OrgType
    county: str
    email: str | None = None
    phone: str | None = None


class RosterOrg(OrgRecord):
    would_notify: bool = True


class NotifyResponse(BaseModel):
    id: str
    severity: Severity
    geofence: str
    matched: bool
    draft: Draft
    delivered: list[Delivery]
    sandbox_only: bool = True
    roster: list[RosterOrg]
