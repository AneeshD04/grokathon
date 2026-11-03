/* Camera pins on the existing Flood/Drought Google map.
   Click a pin to open a refreshing live still. Houston TranStar's public
   snapshot URLs currently return HTML, so the pictures are Florida 511
   cameras inside active NWS flood alerts. Same-origin GET /api/cameras
   wins when it returns real image URLs. */
(function () {
  const FL511 = "https://services.arcgis.com/3wFbqsFPLeKqOlIK/arcgis/rest/services/FL511_Traffic_Cameras/FeatureServer/0/query";
  const NWS = "https://api.weather.gov/alerts/active?area=FL";
  const RANK = {
    "Flash Flood Warning": 1, "Flood Warning": 2, "Storm Surge Warning": 3,
    "Coastal Flood Warning": 4, "Flood Watch": 5, "Storm Surge Watch": 6,
    "Coastal Flood Advisory": 7, "Flood Advisory": 8, "Coastal Flood Statement": 9
  };
  const COAST_WHERE = "(HIGHWAY IN ('A1A','US-1','SR-A1A') OR DESCRIPT LIKE '%Causeway%' OR DESCRIPT LIKE '%Overseas%' OR DESCRIPT LIKE '%Beach%')";
  const ROAD_WHERE = "(HIGHWAY IN ('I-95','I-4','I-75','I-10'))";
  const COASTAL_RE = /A1A|\bUS-?\s?1\b|CAUSEWAY|OVERSEAS|BEACH/i;
  let cache = null;
  let markers = [];
  let info = null;
  let timer = null;

  function rings(geom) {
    if (!geom) return [];
    if (geom.type === "Polygon") return geom.coordinates.length ? [geom.coordinates[0]] : [];
    if (geom.type === "MultiPolygon") return geom.coordinates.map(function (p) { return p[0]; });
    return [];
  }
  function inside(lon, lat, geom) {
    return rings(geom).some(function (ring) {
      let hit = false;
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const yi = ring[i][1], yj = ring[j][1];
        if ((yi > lat) !== (yj > lat) && lon < ((ring[j][0] - ring[i][0]) * (lat - yi)) / ((yj - yi) || 1e-12) + ring[i][0]) hit = !hit;
      }
      return hit;
    });
  }
  function boxOf(geom) {
    let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
    rings(geom).forEach(function (ring) {
      ring.forEach(function (p) {
        minLon = Math.min(minLon, p[0]); maxLon = Math.max(maxLon, p[0]);
        minLat = Math.min(minLat, p[1]); maxLat = Math.max(maxLat, p[1]);
      });
    });
    return isFinite(minLon) ? { minLon: minLon, minLat: minLat, maxLon: maxLon, maxLat: maxLat } : null;
  }
  function httpUrl(value) {
    try {
      const url = new URL(String(value));
      if (url.protocol === "https:" || url.protocol === "http:") return url.toString();
    } catch (e) {}
    return "";
  }
  async function fl511(params) {
    const url = new URL(FL511);
    Object.keys(params).forEach(function (k) { url.searchParams.set(k, params[k]); });
    const res = await fetch(url);
    if (!res.ok) throw new Error("Florida 511 " + res.status);
    const data = await res.json();
    return data.features || [];
  }
  function fromAttr(attr, eventName) {
    const lat = Number(attr.LATITUDE), lon = Number(attr.LONGITUDE), still = httpUrl(attr.IMAGE);
    if (!isFinite(lat) || !isFinite(lon) || !still) return null;
    const name = attr.DESCRIPT || attr.HIGHWAY || ("Camera " + attr.ID);
    return {
      id: "fl511-" + attr.ID, name: name, lat: lat, lon: lon, still_url: still,
      county: attr.COUNTY || "", highway: attr.HIGHWAY || "", alertEvent: eventName || "",
      coastal: COASTAL_RE.test((attr.HIGHWAY || "") + " " + name), source: "fl511"
    };
  }
  async function alerts() {
    const res = await fetch(NWS, { headers: { Accept: "application/geo+json" } });
    if (!res.ok) throw new Error("Weather alerts " + res.status);
    const data = await res.json();
    return (data.features || []).map(function (f) {
      const eventName = (f.properties || {}).event;
      const box = boxOf(f.geometry);
      if (!RANK[eventName] || !box) return null;
      return { event: eventName, rank: RANK[eventName], geometry: f.geometry, box: box };
    }).filter(Boolean).sort(function (a, b) { return a.rank - b.rank; }).slice(0, 8);
  }
  async function inAlerts(list) {
    const found = {};
    await Promise.all(list.map(async function (alert) {
      const geom = [alert.box.minLon, alert.box.minLat, alert.box.maxLon, alert.box.maxLat].join(",");
      const base = { f: "json", geometry: geom, geometryType: "esriGeometryEnvelope", inSR: "4326", spatialRel: "esriSpatialRelIntersects", outFields: "ID,DESCRIPT,COUNTY,HIGHWAY,LATITUDE,LONGITUDE,IMAGE", returnGeometry: "false", resultRecordCount: "80" };
      let features = [];
      try {
        const coast = await fl511(Object.assign({ where: COAST_WHERE }, base));
        const roads = await fl511(Object.assign({ where: ROAD_WHERE }, base));
        features = coast.concat(roads);
      } catch (e) { return; }
      features.forEach(function (feature) {
        const attr = feature.attributes || {};
        if (!inside(Number(attr.LONGITUDE), Number(attr.LATITUDE), alert.geometry)) return;
        const cam = fromAttr(attr, alert.event);
        if (!cam) return;
        if (!found[cam.id] || RANK[alert.event] < (found[cam.id].rank || 99)) {
          cam.rank = RANK[alert.event];
          found[cam.id] = cam;
        }
      });
    }));
    const cams = Object.keys(found).map(function (id) { return found[id]; });
    cams.sort(function (a, b) { return (a.coastal === b.coastal) ? 0 : (a.coastal ? -1 : 1); });
    return cams.filter(function (cam) { return cam.coastal; }).slice(0, 10).concat(cams.filter(function (cam) { return !cam.coastal; }).slice(0, 6));
  }
  async function fromApi(bbox) {
    const q = [bbox.minLon, bbox.minLat, bbox.maxLon, bbox.maxLat].join(",");
    try {
      const res = await fetch("/api/cameras?bbox=" + encodeURIComponent(q));
      if (!res.ok) return [];
      const data = await res.json();
      const rows = Array.isArray(data) ? data : (data.cameras || []);
      return rows.map(function (row) {
        const still = httpUrl(row.still_url);
        const lat = Number(row.lat), lon = Number(row.lon);
        if (!row.id || !still || !isFinite(lat) || !isFinite(lon)) return null;
        return { id: String(row.id), name: row.name || String(row.id), lat: lat, lon: lon, still_url: still, county: row.county || "", highway: row.highway || "", alertEvent: "", coastal: true, source: row.source || "api" };
      }).filter(Boolean);
    } catch (e) { return []; }
  }
  async function load() {
    if (cache) return cache;
    const live = await alerts();
    let cameras = live.length ? await inAlerts(live) : [];
    if (!cameras.length && live.length) {
      const b = live[0].box;
      cameras = await fromApi(b);
    }
    if (!cameras.length) {
      const features = await fl511({ f: "json", where: "COUNTY IN ('Broward','Palm Beach','Miami-Dade','Monroe') AND " + COAST_WHERE, outFields: "ID,DESCRIPT,COUNTY,HIGHWAY,LATITUDE,LONGITUDE,IMAGE", returnGeometry: "false", resultRecordCount: "20" });
      cameras = features.map(function (f) { return fromAttr(f.attributes || {}, ""); }).filter(Boolean).slice(0, 12);
    }
    cache = cameras;
    return cameras;
  }
  function stop() { if (timer) clearInterval(timer); timer = null; }
  function open(map, cam) {
    stop();
    if (!info) info = new google.maps.InfoWindow();
    const root = document.createElement("div");
    root.style.cssText = "width:280px;font:13px/1.35 system-ui,sans-serif;color:#0f172a;";
    const title = document.createElement("strong");
    title.textContent = cam.name;
    const meta = document.createElement("div");
    meta.style.cssText = "color:#475569;margin:2px 0 8px;";
    meta.textContent = [cam.county, cam.highway, cam.alertEvent, "Live still"].filter(Boolean).join(" · ");
    const img = document.createElement("img");
    img.alt = cam.name;
    img.style.cssText = "display:block;width:100%;height:168px;object-fit:cover;background:#0f172a;border-radius:6px;";
    function tick() {
      const url = new URL(cam.still_url);
      url.searchParams.set("t", String(Date.now()));
      img.src = url.toString();
    }
    tick();
    timer = setInterval(tick, 5000);
    img.addEventListener("error", function () { meta.textContent += " · still unavailable"; });
    root.append(title, meta, img);
    info.setContent(root);
    info.setPosition({ lat: cam.lat, lng: cam.lon });
    info.open(map);
    google.maps.event.addListenerOnce(info, "closeclick", stop);
  }
  async function attach(map) {
    const cameras = await load();
    markers.forEach(function (m) { m.setMap(null); });
    markers = [];
    if (!cameras.length) return;
    const bounds = new google.maps.LatLngBounds();
    cameras.forEach(function (cam) {
      const marker = new google.maps.Marker({
        position: { lat: cam.lat, lng: cam.lon },
        map: map,
        title: cam.name,
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: cam.coastal ? 8 : 6,
          fillColor: cam.coastal ? "#14b8a6" : "#64748b",
          fillOpacity: 1,
          strokeColor: "#0f172a",
          strokeWeight: 2
        }
      });
      marker.addListener("click", function () { open(map, cam); });
      markers.push(marker);
      bounds.extend(marker.getPosition());
    });
    map.fitBounds(bounds, 48);
  }
  window.SafetyCameraPins = { attach: attach, load: load };
  if (window.__floodMap) attach(window.__floodMap);
})();
