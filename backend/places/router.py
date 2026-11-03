"""POST /api/businesses/nearby. Lookup only."""

from fastapi import APIRouter, HTTPException

from places.models import NearbyRequest, NearbyResponse
from places.service import PlacesError, lookup

router = APIRouter()


@router.post("/api/businesses/nearby", response_model=NearbyResponse)
def nearby(body: NearbyRequest) -> NearbyResponse:
    try:
        return lookup(body)
    except PlacesError as exc:
        raise HTTPException(status_code=502, detail="Places lookup failed") from exc
