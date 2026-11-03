/* At-risk cameras for the safety map.

   Live NWS flood and coastal-flood alerts choose the area. Florida 511
   cameras inside those polygons are the pins. Shoreline roads sort ahead
   of interstate cameras in the same warning. If no alert contains a
   camera, the shoreline set is shown so the map is not empty.

   A drawn region limits that set to the box. Mock stills from mock.js
   are not plotted. GET /api/cameras is used when SafetyAPI.API_BASE is
   set and that response includes real image URLs. */
(function () {
  const FL511 = "https://services.arcgis.com/3wFbqsFPLeKqOlIK/arcgis/rest/services/FL511_Traffic_Cameras/FeatureServer/0/query";
  const NWS = "https://api.weather.gov/alerts/active?area=FL";
  const ALERT_RANK = {
    "Flash Flood Warning": 1,
    "Flood Warning": 2,
    "Storm Surge Warning": 3,
    "Coastal Flood Warning": 4,
    "Flood Watch": 5,
    "Storm Surge Watch": 6,
    "Coastal Flood Advisory": 7,
    "Flood Advisory": 8,
    "Coastal Flood Statement": 9,
  };
  const COAST_ROAD_WHERE = "(HIGHWAY IN ('A1A','US-1','SR-A1A') OR DESCRIPT LIKE '%Causeway%' OR DESCRIPT LIKE '%Overseas%' OR DESCRIPT LIKE '%Beach%')";
  const INTERSTATE_WHERE = "HIGHWAY IN ('I-95','I-4','I-75','I-10')";
  const COAST_WHERE = "COUNTY IN ('Miami-Dade','Broward','Palm Beach','Monroe','Brevard','Martin','St. Lucie','Indian River','Duval','Pinellas') AND " + COAST_ROAD_WHERE;
  const COASTAL_RE = /A1A|\bUS-?\s?1\b|CAUSEWAY|OVERSEAS|BEACH|CARD SOUND|BAYSHORE|RICKENBACKER|MACARTHUR|VENETIAN/i;
  const SHORE = [
    [-81.39, 30.29], [-81.02, 29.85], [-80.83, 29.23], [-80.60, 28.39],
    [-80.45, 27.98], [-80.32, 27.47], [-80.07, 26.93], [-80.10, 26.35],
    [-80.12, 26.12], [-80.12, 25.78], [-80.16, 25.49], [-80.38, 25.18],
    [-81.38, 24.71], [-81.78, 24.55], [-82.64, 27.77], [-82.83, 27.98],
  ];

  let cache = null;
  let pending = null;

  function pointInRing(lon, lat, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0];
      const yi = ring[i][1];
      const xj = ring[j][0];
      const yj = ring[j][1];
      const intersect = (yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / ((yj - yi) || 1e-12) + xi;
      if (intersect) inside = !inside;
    }
    return inside;
  }

  function outerRings(geom) {
    if (!geom) return [];
    if (geom.type === "Polygon") return geom.coordinates.length ? [geom.coordinates[0]] : [];
    if (geom.type === "MultiPolygon") return geom.coordinates.map(function (poly) { return poly[0]; }).filter(Boolean);
    return [];
  }

  function contains(lon, lat, geom) {
    return outerRings(geom).some(function (ring) { return pointInRing(lon, lat, ring); });
  }

  function boundsOf(geom) {
    let minLon = Infinity;
    let minLat = Infinity;
    let maxLon = -Infinity;
    let maxLat = -Infinity;
    outerRings(geom).forEach(function (ring) {
      ring.forEach(function (pair) {
        minLon = Math.min(minLon, pair[0]);
        maxLon = Math.max(maxLon, pair[0]);
        minLat = Math.min(minLat, pair[1]);
        maxLat = Math.max(maxLat, pair[1]);
      });
    });
    if (!isFinite(minLon)) return null;
    return { minLon: minLon, minLat: minLat, maxLon: maxLon, maxLat: maxLat };
  }

  function haversineKm(lat1, lon1, lat2, lon2) {
    const r = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
    return 2 * r * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  function shoreKm(lat, lon) {
    let best = Infinity;
    SHORE.forEach(function (pair) {
      best = Math.min(best, haversineKm(lat, lon, pair[1], pair[0]));
    });
    return best;
  }

  function httpUrl(value) {
    if (!value) return "";
    try {
      const url = new URL(String(value), window.location.href);
      if (url.protocol === "https:" || url.protocol === "http:") return url.toString();
    } catch (err) {
      return "";
    }
    return "";
  }

  function decorate(cam) {
    cam.shoreKm = shoreKm(cam.lat, cam.lon);
    cam.coastal = COASTAL_RE.test((cam.highway || "") + " " + (cam.name || ""));
    return cam;
  }

  function fromFl511(attr, alert) {
    const lat = Number(attr.LATITUDE);
    const lon = Number(attr.LONGITUDE);
    const still = httpUrl(attr.IMAGE);
    if (!isFinite(lat) || !isFinite(lon) || !still) return null;
    return decorate({
      id: "fl511-" + attr.ID,
      name: attr.DESCRIPT || attr.HIGHWAY || ("Camera " + attr.ID),
      lat: lat,
      lon: lon,
      still_url: still,
      hls_url: null,
      source: "fl511",
      county: attr.COUNTY || "",
      highway: attr.HIGHWAY || "",
      alertEvent: alert ? alert.event : "",
      alertRank: alert ? alert.rank : 99,
    });
  }

  function fromContract(row, alert) {
    const lat = Number(row.lat);
    const lon = Number(row.lon);
    const still = httpUrl(row.still_url);
    if (!row.id || !isFinite(lat) || !isFinite(lon) || !still) return null;
    if (still.indexOf("data:") === 0) return null;
    return decorate({
      id: String(row.id),
      name: row.name || String(row.id),
      lat: lat,
      lon: lon,
      still_url: still,
      hls_url: httpUrl(row.hls_url) || null,
      source: row.source || "fl511",
      county: row.county || "",
      highway: row.highway || "",
      alertEvent: alert ? alert.event : (row.alertEvent || ""),
      alertRank: alert ? alert.rank : 99,
    });
  }

  function inBbox(cam, bbox) {
    if (!bbox) return true;
    return cam.lon >= bbox.west && cam.lon <= bbox.east && cam.lat >= bbox.south && cam.lat <= bbox.north;
  }

  function probeStill(url) {
    return new Promise(function (resolve) {
      const img = new Image();
      const timer = setTimeout(function () { resolve(false); }, 5000);
      img.onload = function () {
        clearTimeout(timer);
        resolve(img.naturalWidth > 0);
      };
      img.onerror = function () {
        clearTimeout(timer);
        resolve(false);
      };
      img.src = url;
    });
  }

  async function keepLive(list) {
    const sorted = list.slice().sort(function (a, b) { return a.shoreKm - b.shoreKm; });
    const coastal = sorted.filter(function (cam) { return cam.coastal; }).slice(0, 20);
    const seen = {};
    coastal.forEach(function (cam) { seen[cam.id] = true; });
    const inland = sorted.filter(function (cam) { return !seen[cam.id]; }).slice(0, 12);
    const probed = await mapPool(coastal.concat(inland), 6, async function (cam) {
      cam.stillOk = await probeStill(cam.still_url);
      return cam;
    });
    return pick(probed.filter(function (cam) { return cam.stillOk; }));
  }

  function pick(list) {
    const sorted = list.slice().sort(function (a, b) { return a.shoreKm - b.shoreKm; });
    const coastal = sorted.filter(function (cam) { return cam.coastal; }).slice(0, 14);
    const seen = {};
    coastal.forEach(function (cam) { seen[cam.id] = true; });
    const inland = sorted.filter(function (cam) { return !seen[cam.id]; }).slice(0, 6);
    return coastal.concat(inland);
  }

  async function mapPool(items, limit, fn) {
    const out = new Array(items.length);
    let cursor = 0;
    async function worker() {
      for (;;) {
        const index = cursor++;
        if (index >= items.length) return;
        out[index] = await fn(items[index]);
      }
    }
    await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
    return out;
  }

  async function queryFl511(params) {
    const url = new URL(FL511);
    Object.keys(params).forEach(function (key) { url.searchParams.set(key, params[key]); });
    const res = await fetch(url.toString());
    if (!res.ok) throw new Error("Florida 511 returned " + res.status);
    const data = await res.json();
    if (data.error) throw new Error(data.error.message || "Florida 511 query failed");
    return data.features || [];
  }

  async function fetchAlerts() {
    const res = await fetch(NWS, { headers: { Accept: "application/geo+json" } });
    if (!res.ok) throw new Error("Weather alerts returned " + res.status);
    const data = await res.json();
    const alerts = [];
    (data.features || []).forEach(function (feature) {
      const props = feature.properties || {};
      const rank = ALERT_RANK[props.event];
      const box = boundsOf(feature.geometry);
      if (!rank || !box) return;
      alerts.push({ event: props.event, rank: rank, geometry: feature.geometry, box: box });
    });
    alerts.sort(function (a, b) { return a.rank - b.rank; });
    return alerts.slice(0, 12);
  }

  function groupByBox(alerts) {
    const groups = [];
    const index = {};
    alerts.forEach(function (alert) {
      const box = alert.box;
      const key = [box.minLon, box.minLat, box.maxLon, box.maxLat].map(function (n) { return n.toFixed(2); }).join(",");
      if (!index[key]) {
        index[key] = { box: box, alerts: [] };
        groups.push(index[key]);
      }
      index[key].alerts.push(alert);
    });
    return groups;
  }

  async function featuresInBox(box, where) {
    try {
      return await queryFl511({
        f: "json",
        where: where,
        geometry: [box.minLon, box.minLat, box.maxLon, box.maxLat].join(","),
        geometryType: "esriGeometryEnvelope",
        inSR: "4326",
        spatialRel: "esriSpatialRelIntersects",
        outFields: "ID,DESCRIPT,COUNTY,HIGHWAY,LATITUDE,LONGITUDE,IMAGE",
        returnGeometry: "false",
        resultRecordCount: "200",
      });
    } catch (err) {
      return [];
    }
  }

  async function camerasInGroup(group) {
    const batches = await Promise.all([
      featuresInBox(group.box, COAST_ROAD_WHERE),
      featuresInBox(group.box, INTERSTATE_WHERE),
    ]);
    const seenFeature = {};
    const features = [];
    batches.forEach(function (list) {
      list.forEach(function (feature) {
        const id = (feature.attributes || {}).ID;
        if (id == null || seenFeature[id]) return;
        seenFeature[id] = true;
        features.push(feature);
      });
    });
    const found = [];
    features.forEach(function (feature) {
      const attr = feature.attributes || {};
      const lat = Number(attr.LATITUDE);
      const lon = Number(attr.LONGITUDE);
      if (!isFinite(lat) || !isFinite(lon)) return;
      let best = null;
      group.alerts.forEach(function (alert) {
        if (!contains(lon, lat, alert.geometry)) return;
        if (!best || alert.rank < best.rank) best = alert;
      });
      if (!best) return;
      const cam = fromFl511(attr, best);
      if (cam) found.push(cam);
    });
    return found;
  }

  async function coastalFallback() {
    const features = await queryFl511({
      f: "json",
      where: COAST_WHERE,
      outFields: "ID,DESCRIPT,COUNTY,HIGHWAY,LATITUDE,LONGITUDE,IMAGE",
      returnGeometry: "false",
      resultRecordCount: "80",
    });
    return keepLive(features.map(function (feature) { return fromFl511(feature.attributes || {}, null); }).filter(Boolean));
  }

  function remember(bucket, cam) {
    const prev = bucket[cam.id];
    if (!prev || cam.alertRank < prev.alertRank) bucket[cam.id] = cam;
  }

  async function fetchAtRisk() {
    const forceFallback = new URLSearchParams(window.location.search).has("cameraFallback");
    const alerts = forceFallback ? [] : await fetchAlerts();
    const bucket = {};
    if (alerts.length) {
      const groups = groupByBox(alerts);
      const batches = await mapPool(groups, 4, camerasInGroup);
      batches.forEach(function (list) {
        (list || []).forEach(function (cam) { remember(bucket, cam); });
      });
    }
    let cameras = await keepLive(Object.keys(bucket).map(function (id) { return bucket[id]; }));
    let mode = "alert";
    if (!cameras.length) {
      cameras = await coastalFallback();
      mode = "coastal-fallback";
    }
    return { cameras: cameras, alerts: alerts, mode: mode };
  }

  function summaryFor(cameras, meta, bbox) {
    if (bbox && !cameras.length) return "No at-risk cameras in this region.";
    if (!cameras.length) return "No at-risk cameras to show.";
    if (meta.mode === "coastal-fallback") {
      return cameras.length + " shoreline cameras. No live flood alert contained a road camera, so these are the coastal roads.";
    }
    const events = [];
    let coastal = 0;
    cameras.forEach(function (cam) {
      if (cam.coastal) coastal += 1;
      if (cam.alertEvent && events.indexOf(cam.alertEvent) === -1) events.push(cam.alertEvent);
    });
    const eventText = events.length ? " · " + events.join(", ") : "";
    let pins = " These are interstate cameras inside the warning.";
    if (coastal && coastal < cameras.length) pins = " Teal pins are shoreline roads. Gray pins are interstate cameras in the same warning.";
    else if (coastal) pins = " These are shoreline roads inside the warning.";
    return cameras.length + " cameras in live flood alerts" + eventText + "." + pins;
  }

  function realApiCameras(rows) {
    if (!window.SafetyAPI || SafetyAPI.API_BASE === "") return [];
    return (rows || []).map(function (row) { return fromContract(row); }).filter(Boolean);
  }

  async function load(options) {
    const bbox = options && options.bbox;
    const apiCameras = realApiCameras(options && options.apiCameras);
    if (!pending) {
      pending = fetchAtRisk().then(function (result) {
        cache = result;
        return result;
      }).catch(function (err) {
        pending = null;
        throw err;
      });
    }
    const meta = await pending;
    let cameras;
    let mode = meta.mode;
    if (apiCameras.length) {
      cameras = pick(apiCameras.filter(function (cam) { return inBbox(cam, bbox); }));
      mode = "api";
    } else {
      cameras = meta.cameras.filter(function (cam) { return inBbox(cam, bbox); });
    }
    return {
      cameras: cameras,
      mode: mode,
      summary: summaryFor(cameras, { mode: mode, alerts: meta.alerts }, bbox),
    };
  }

  window.SafetyCameras = {
    load: load,
    focus: function (cam) {
      if (window.SafetyCameraPins) SafetyCameraPins.open(cam);
    },
  };
})();
