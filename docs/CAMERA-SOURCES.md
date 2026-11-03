# Live camera sources we can actually use

Demo region default: **Houston–Galveston coastal / Harris County** (flood + cameras + TranStar flood-warning JSON). Secondary: **Florida Atlantic/Gulf coast** (FL511 ArcGIS camera layer).

These are public, geolocated feeds we can list on a map, click to preview, and attach a watcher to. Prefer **still JPEG** for Grok vision (cheaper than HLS). Respect ToS; server-side fetch only.

## Tier 1 — use for the demo (JSON + lat/lon)

| Source | What | How to query | Click-to-view |
| --- | --- | --- | --- |
| **Houston TranStar cameras** | Hundreds of freeway / street / **ferry** cams including Galveston & Bolivar landings | [Camera viewer](https://traffic.houstontranstar.org/cameras/) + still image URLs used by that page | Popup `<img>` of latest still |
| **Houston TranStar roadway flood warnings** | Not a camera — live flood-warning points | [JSON flood warning feed](https://traffic.houstontranstar.org/api/api_doc.aspx) | Map pins |
| **FL511 traffic cameras** | Statewide DOT cams, coastal bbox works | ArcGIS: `https://services.arcgis.com/3wFbqsFPLeKqOlIK/arcgis/rest/services/FL511_Traffic_Cameras/FeatureServer/0/query?f=json&outFields=*&where=1%3D1` | `image` / stream fields on features |
| **NOAA NDBC BuoyCAMs** | Daylight stills from ocean buoys | [BuoyCAM map](https://www.ndbc.noaa.gov/buoycams.shtml) — station pages serve latest JPEG | Station still |
| **WebCOOS / SECOORA** | Coastal science cams (shoreline, flooding, rip current). IOOS, ~60+ national | API: `https://app.webcoos.org/webcoos/api/v1/assets/` (needs free token). Site: [webcoos.org/cameras](https://www.webcoos.org/cameras/) | HLS + still products |
| **USGS CoastCams** | ~55 coastal hazard webcams (Madeira Beach FL, etc.) | [USGS CMHRP webcams](https://www.usgs.gov/programs/cmhrp/multimedia/webcams) | Time-averaged + latest still |

## Tier 2 — add if time

| Source | Notes |
| --- | --- |
| NOAA PORTS / Harbor cams | Port of Houston / Savannah style marine traffic |
| GDOT 511 | Georgia inland + some coastal approaches |
| TxDOT district CCTV | Overlaps TranStar in Houston |
| YouTube live “beach cam” | Last resort; scrape is fragile — only if we have a stable embed URL |
| Road511 aggregator | Paid API wrapping state 511 cams — skip unless we have a key |

## Watcher contract

When the user draws a county/area:

1. Geocode → bbox (or county FIPS).
2. `GET /api/cameras?bbox=minLon,minLat,maxLon,maxLat` returns cameras from a **catalog JSON** we ship in `shared/cameras/`.
3. Map markers. Click → latest JPEG (and HLS if present).
4. Spawn one **CamWatch** sub-agent per selected camera (cap **8** for demo). Each samples every 15–30s → Grok vision → alert if water/overtop/debris/crowd.

Seed the catalog by hand for Houston+Galveston (10–20 cams) plus FL511 query for Florida counties. Do not try to ingest every DOT camera in the US tonight.

## Demo seed list (fill URLs in implementation)

Houston / Galveston (TranStar names we can resolve on their camera page):

- Galveston Landing (ferry)
- Bolivar Landing (ferry)
- Broadway (Galveston)
- Bay Area Blvd
- SH-35
- Old Galveston Road
- Buffalo Speedway
- Shepherd / Buffalo Bayou corridor

Florida (FL511 feature query, filter `LATITUDE/LONGITUDE` in Miami-Dade, Pinellas, Duval).
