/* Galveston County, Texas. GEOID 48167.
   Bounding box from the US Census Bureau TIGERweb State_County layer
   (BASENAME='Galveston', STATE='48'), Web Mercator extent converted to WGS84,
   queried 2026-11-02:
   https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1
   west -95.2331, south 29.0627, east -94.3694, north 29.5983.
   The ring is the same layer generalized at maxAllowableOffset=0.012 degrees
   (outSR 4326). The shortcut uses the extent above, not this ring, so the
   numbers match the Census extent. */
window.SafetyCounties = {
  galveston: {
    id: "48167",
    name: "Galveston County",
    bbox: {
      west: -95.2331,
      south: 29.0627,
      east: -94.3694,
      north: 29.5983,
    },
  },
};
