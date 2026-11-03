"""Galveston stand-ins used when GOOGLE_MAPS_API_KEY is unset. No phone numbers."""

from places.models import Business

FIXTURE_BUSINESSES: list[Business] = [
    Business(
        place_id="fixture-utmb",
        name="Fixture UTMB Health",
        lat=29.3106,
        lon=-94.7774,
        phone=None,
        website=None,
        types=["hospital"],
        maps_url="https://maps.google.com/?q=place_id:fixture-utmb",
    ),
    Business(
        place_id="fixture-school",
        name="Fixture Ball High School",
        lat=29.2905,
        lon=-94.8094,
        phone=None,
        website=None,
        types=["school"],
        maps_url="https://maps.google.com/?q=place_id:fixture-school",
    ),
    Business(
        place_id="fixture-lodging",
        name="Fixture Seawall Lodging",
        lat=29.2722,
        lon=-94.815,
        phone=None,
        website=None,
        types=["lodging"],
        maps_url="https://maps.google.com/?q=place_id:fixture-lodging",
    ),
]
