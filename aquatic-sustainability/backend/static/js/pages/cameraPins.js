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
    const center = map.getCenter && map.getCenter();
    const stillDefault = !center || (Math.abs(center.lat() - 8) < 1 && Math.abs(center.lng() - 110) < 1);
    if (stillDefault) map.fitBounds(bounds, 48);
  }
  function showStrip(cameras) {
    if (!cameras.length || document.getElementById("camera-demo-strip")) return;
    const bar = document.createElement("div");
    bar.id = "camera-demo-strip";
    bar.style.cssText = "position:fixed;z-index:50;left:12px;right:12px;bottom:12px;display:flex;gap:8px;overflow:auto;padding:8px;background:rgba(15,23,42,.94);border-radius:12px;border:1px solid rgba(255,255,255,.12);";
    cameras.slice(0, 6).forEach(function (cam) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.style.cssText = "flex:0 0 180px;padding:0;border:0;border-radius:8px;overflow:hidden;background:#0f172a;color:#e7eef6;text-align:left;cursor:pointer;";
      const img = document.createElement("img");
      img.alt = cam.name;
      img.src = cam.still_url;
      img.style.cssText = "display:block;width:100%;height:90px;object-fit:cover;background:#111;";
      img.addEventListener("error", function () { btn.remove(); });
      const cap = document.createElement("div");
      cap.textContent = cam.name;
      cap.style.cssText = "padding:6px 8px;font:12px/1.3 system-ui,sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
      btn.append(img, cap);
      btn.addEventListener("click", function () { showFeed(cam); });
      bar.appendChild(btn);
    });
    document.body.appendChild(bar);
  }
  function showFeed(cam) {
    const old = document.getElementById("camera-demo-feed");
    if (old) old.remove();
    stop();
    const wrap = document.createElement("div");
    wrap.id = "camera-demo-feed";
    wrap.style.cssText = "position:fixed;z-index:60;left:50%;bottom:132px;transform:translateX(-50%);width:min(420px,calc(100% - 24px));background:#fff;color:#0f172a;border-radius:12px;padding:12px;box-shadow:0 12px 40px rgba(0,0,0,.35);";
    const title = document.createElement("strong");
    title.textContent = cam.name;
    const meta = document.createElement("div");
    meta.style.cssText = "color:#475569;margin:2px 0 8px;font:13px/1.35 system-ui,sans-serif;";
    meta.textContent = [cam.county, cam.highway, cam.alertEvent, "Live still"].filter(Boolean).join(" · ");
    const img = document.createElement("img");
    img.alt = cam.name;
    img.style.cssText = "display:block;width:100%;height:220px;object-fit:cover;background:#0f172a;border-radius:8px;";
    function tick() {
      const url = new URL(cam.still_url);
      url.searchParams.set("t", String(Date.now()));
      img.src = url.toString();
    }
    tick();
    timer = setInterval(tick, 5000);
    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "Close";
    close.style.cssText = "margin-top:8px;";
    close.addEventListener("click", function () { stop(); wrap.remove(); });
    wrap.append(title, meta, img, close);
    document.body.appendChild(wrap);
  }
  window.SafetyCameraPins = { attach: attach, load: load };
  if (window.__floodMap) attach(window.__floodMap);
  load().then(showStrip).catch(function () {});
})();

(function safetyCameraPins() {
  "use strict";

  var CAMERA_BLUE = "#2563eb";
  var CAMERA_STROKE = "#1e3a8a";

  var mapRef = null;
  var markers = [];
  var openInfoWindow = null;
  var regionListenerBound = false;

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function placeholderStill(label) {
    var safe = escapeHtml(label || "Camera");
    var svg =
      "<svg xmlns='http://www.w3.org/2000/svg' width='320' height='180'>" +
      "<rect fill='#0f172a' width='100%' height='100%'/>" +
      "<circle cx='160' cy='72' r='28' fill='none' stroke='#60a5fa' stroke-width='3'/>" +
      "<rect x='148' y='60' width='24' height='18' rx='3' fill='#60a5fa'/>" +
      "<text x='160' y='130' fill='#93c5fd' font-family='system-ui,sans-serif' font-size='13' text-anchor='middle'>" +
      safe +
      "</text></svg>";
    return "data:image/svg+xml," + encodeURIComponent(svg);
  }

  /** Houston–Galveston demo set when GET /api/cameras is unavailable. */
  var FIXTURE_CAMERAS = [
    {
      id: "180",
      name: "Galveston Ferry @ Galveston Ferry Landing",
      lat: 29.326965,
      lon: -94.772842,
      source: "Houston TranStar",
    },
    {
      id: "181",
      name: "Bolivar Ferry @ French Town Rd.",
      lat: 29.36452,
      lon: -94.7747,
      source: "Houston TranStar",
    },
    {
      id: "173",
      name: "45 GULF @ 61ST (W)",
      lat: 29.288568,
      lon: -94.838279,
      source: "Houston TranStar",
    },
    {
      id: "164",
      name: "45 GULF @ CAUSEWAY (N)",
      lat: 29.30133,
      lon: -94.89771,
      source: "Houston TranStar",
    },
    {
      id: "129",
      name: "45 Gulf @ Bay Area Blvd",
      lat: 29.54079,
      lon: -95.14238,
      source: "Houston TranStar",
    },
    {
      id: "1816",
      name: "NASA 1 @ SH-146",
      lat: 29.563873,
      lon: -95.025773,
      source: "Houston TranStar",
    },
  ].map(function (row) {
    return {
      id: row.id,
      name: row.name,
      lat: row.lat,
      lon: row.lon,
      still_url: placeholderStill(row.name),
      source: row.source,
    };
  });

  /**
   * @param {CustomEvent['detail']} detail
   * @returns {[number, number, number, number] | null}
   */
  function bboxFromRegionDetail(detail) {
    if (!detail) return null;
    if (detail.bbox === null) return null;
    if (Array.isArray(detail.bbox) && detail.bbox.length === 4) {
      return detail.bbox.map(Number);
    }
    if (
      typeof detail.minLon === "number" &&
      typeof detail.minLat === "number" &&
      typeof detail.maxLon === "number" &&
      typeof detail.maxLat === "number"
    ) {
      return [detail.minLon, detail.minLat, detail.maxLon, detail.maxLat];
    }
    return null;
  }

  /**
   * @param {Array<{lat:number, lon?:number, lng?:number}>} cameras
   * @param {[number, number, number, number]} bbox [minLon, minLat, maxLon, maxLat]
   */
  function filterCamerasInBbox(cameras, bbox) {
    if (!bbox || bbox.length !== 4) return [];
    var minLon = bbox[0];
    var minLat = bbox[1];
    var maxLon = bbox[2];
    var maxLat = bbox[3];
    return (cameras || []).filter(function (cam) {
      var lat = Number(cam.lat);
      var lon = cam.lon != null ? Number(cam.lon) : Number(cam.lng);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
      return lon >= minLon && lon <= maxLon && lat >= minLat && lat <= maxLat;
    });
  }

  function normalizeCamera(raw) {
    if (!raw) return null;
    var lat = Number(raw.lat);
    var lon = raw.lon != null ? Number(raw.lon) : Number(raw.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    var name = raw.name || raw.id || "Camera";
    return {
      id: String(raw.id != null ? raw.id : name),
      name: name,
      lat: lat,
      lon: lon,
      still_url: raw.still_url || placeholderStill(name),
      source: raw.source || "catalog",
    };
  }

  function buildInfoWindowContent(camera) {
    var name = escapeHtml(camera.name);
    var src = escapeHtml(camera.still_url);
    var source = escapeHtml(camera.source || "");
    return (
      '<div class="safety-camera-popup" style="font-family:system-ui,sans-serif;max-width:320px;padding:4px 2px;">' +
      '<div style="font-weight:700;font-size:14px;margin-bottom:8px;color:#111827;">' +
      name +
      "</div>" +
      '<img src="' +
      src +
      '" alt="' +
      name +
      '" width="300" height="169" style="display:block;width:100%;max-width:300px;height:auto;border-radius:6px;background:#0f172a;" onerror="this.replaceWith(document.createTextNode(\'Still unavailable\'))" />' +
      (source
        ? '<div style="font-size:11px;color:#6b7280;margin-top:6px;">Source: ' + source + "</div>"
        : "") +
      "</div>"
    );
  }

  function clearMarkers() {
    markers.forEach(function (marker) {
      marker.setMap(null);
    });
    markers = [];
    if (openInfoWindow) {
      openInfoWindow.close();
      openInfoWindow = null;
    }
  }

  function cameraIcon() {
    return {
      path: google.maps.SymbolPath.CIRCLE,
      scale: 8,
      fillColor: CAMERA_BLUE,
      fillOpacity: 0.95,
      strokeColor: CAMERA_STROKE,
      strokeWeight: 2,
    };
  }

  function renderCameras(map, cameras) {
    clearMarkers();
    cameras.forEach(function (camera) {
      var marker = new google.maps.Marker({
        map: map,
        position: { lat: camera.lat, lng: camera.lon },
        title: camera.name,
        icon: cameraIcon(),
        zIndex: google.maps.Marker.MAX_ZINDEX + 1,
      });
      var info = new google.maps.InfoWindow({
        content: buildInfoWindowContent(camera),
      });
      marker.addListener("click", function () {
        if (openInfoWindow) openInfoWindow.close();
        info.open({ map: map, anchor: marker });
        openInfoWindow = info;
      });
      markers.push(marker);
    });
  }

  function fetchCameras(bbox) {
    var query = bbox.map(function (n) {
      return Number(n);
    }).join(",");
    return fetch("/api/cameras?bbox=" + encodeURIComponent(query))
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        var list = Array.isArray(data) ? data : data && data.cameras;
        if (!Array.isArray(list) || !list.length) throw new Error("empty catalog");
        return list.map(normalizeCamera).filter(Boolean);
      })
      .catch(function () {
        return filterCamerasInBbox(FIXTURE_CAMERAS, bbox);
      });
  }

  function onRegionEvent(event) {
    if (!mapRef) return;
    var bbox = bboxFromRegionDetail(event && event.detail);
    if (!bbox) {
      clearMarkers();
      return;
    }
    fetchCameras(bbox).then(function (cameras) {
      if (!mapRef) return;
      renderCameras(mapRef, filterCamerasInBbox(cameras, bbox));
    });
  }

  function bindRegionListener() {
    if (regionListenerBound) return;
    regionListenerBound = true;
    window.addEventListener("safety:region", onRegionEvent);
  }

  function currentSafetyBbox() {
    var sr = window.SafetyRegion;
    if (!sr || !sr.bbox) return null;
    return bboxFromRegionDetail({ bbox: sr.bbox, minLon: sr.bbox.minLon, minLat: sr.bbox.minLat, maxLon: sr.bbox.maxLon, maxLat: sr.bbox.maxLat });
  }

  function attach(map) {
    if (!map || typeof google === "undefined" || !google.maps) return;
    mapRef = map;
    bindRegionListener();
    var seed = currentSafetyBbox();
    if (seed) {
      onRegionEvent({ detail: { bbox: seed } });
    }
  }

  var livePins = window.SafetyCameraPins;
  window.SafetyCameraPins = {
    attach: function (map) {
      if (livePins && livePins.attach) livePins.attach(map);
      attach(map);
    },
    load: livePins && livePins.load,
    filterCamerasInBbox: filterCamerasInBbox,
    buildInfoWindowContent: buildInfoWindowContent,
    bboxFromRegionDetail: bboxFromRegionDetail,
  };

  var initialMap = window.floodMap || window.__floodMap;
  if (initialMap) {
    attach(initialMap);
  } else {
    window.addEventListener(
      "flood-map-ready",
      function (event) {
        attach(event.detail && event.detail.map);
      },
      { once: true }
    );
  }
})();
