/* Business lookup for the #25 preview.

   POST {PLACES_BASE}/api/businesses/nearby
   body { bbox: [minLon, minLat, maxLon, maxLat], limit }
   Response { businesses, truncated, source } from #24.

   If that route is down, the three Galveston fixtures are used.
   Those rows have phone: null. Do not invent numbers. */
(function () {
  const PLACES_BASE = "http://127.0.0.1:8000";

  const GALVESTON = {
    name: "Galveston County",
    west: -95.2331,
    south: 29.0627,
    east: -94.3694,
    north: 29.5983,
  };

  const FIXTURES = [
    {
      place_id: "fixture-utmb",
      name: "Fixture UTMB Health",
      lat: 29.3106,
      lon: -94.7774,
      phone: null,
      website: null,
      types: ["hospital"],
      maps_url: "https://maps.google.com/?q=place_id:fixture-utmb",
    },
    {
      place_id: "fixture-school",
      name: "Fixture Ball High School",
      lat: 29.2905,
      lon: -94.8094,
      phone: null,
      website: null,
      types: ["school"],
      maps_url: "https://maps.google.com/?q=place_id:fixture-school",
    },
    {
      place_id: "fixture-lodging",
      name: "Fixture Seawall Lodging",
      lat: 29.2722,
      lon: -94.815,
      phone: null,
      website: null,
      types: ["lodging"],
      maps_url: "https://maps.google.com/?q=place_id:fixture-lodging",
    },
  ];

  function bboxArray(bbox) {
    return [bbox.west, bbox.south, bbox.east, bbox.north];
  }

  async function nearby(bbox) {
    try {
      const res = await fetch(PLACES_BASE + "/api/businesses/nearby", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ bbox: bboxArray(bbox), limit: 20 }),
      });
      if (!res.ok) throw new Error("nearby " + res.status);
      const data = await res.json();
      if (!data || !Array.isArray(data.businesses)) throw new Error("nearby shape");
      return {
        businesses: data.businesses,
        truncated: Boolean(data.truncated),
        source: data.source === "google" ? "google" : "fixture",
      };
    } catch (err) {
      return {
        businesses: FIXTURES.map(function (row) {
          return Object.assign({}, row, { types: row.types.slice() });
        }),
        truncated: false,
        source: "fixture",
      };
    }
  }

  window.SafetyBusinesses = {
    galveston: GALVESTON,
    nearby: nearby,
  };
})();
