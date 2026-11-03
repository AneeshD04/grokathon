"""Request and response shapes for POST /api/businesses/nearby."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class NearbyRequest(BaseModel):
    bbox: list[float] | None = None
    polygon: list[list[float]] | None = None
    limit: int = Field(default=20, ge=1, le=20)
    types: list[str] | None = None

    @field_validator("types")
    @classmethod
    def types_are_short(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if not value or len(value) > 10:
            raise ValueError("types must contain 1 to 10 entries")
        cleaned = []
        for item in value:
            text = item.strip()
            if not text or len(text) > 40:
                raise ValueError("invalid place type")
            cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def require_area(self) -> "NearbyRequest":
        if self.polygon is not None:
            if len(self.polygon) < 3:
                raise ValueError("polygon needs at least 3 points")
            for point in self.polygon:
                if len(point) != 2:
                    raise ValueError("polygon points are [lon, lat]")
                lon, lat = point
                _check_lon_lat(lon, lat)
            return self
        if self.bbox is None:
            raise ValueError("bbox or polygon is required")
        if len(self.bbox) != 4:
            raise ValueError("bbox must be [minLon, minLat, maxLon, maxLat]")
        min_lon, min_lat, max_lon, max_lat = self.bbox
        _check_lon_lat(min_lon, min_lat)
        _check_lon_lat(max_lon, max_lat)
        if not (min_lon < max_lon and min_lat < max_lat):
            raise ValueError("bbox min must be less than max")
        return self


class Business(BaseModel):
    place_id: str
    name: str
    lat: float
    lon: float
    phone: str | None = None
    website: str | None = None
    types: list[str]
    maps_url: str


class NearbyResponse(BaseModel):
    businesses: list[Business]
    truncated: bool
    source: Literal["google", "fixture"]


def _check_lon_lat(lon: float, lat: float) -> None:
    if not -180 <= lon <= 180:
        raise ValueError("longitude out of range")
    if not -90 <= lat <= 90:
        raise ValueError("latitude out of range")
