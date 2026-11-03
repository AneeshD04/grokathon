/* Camera pins on the Flood/Drought Google map.
   Houston–Galveston TranStar stills from GET /api/cameras for the current
   map bbox (Galveston default). No Florida 511 filmstrip. Click a pin or a
   compact overlay thumb to open a refreshing still. */
(function safetyCameraPins() {
  "use strict";

  var GALVESTON_BBOX = [-95.1544, 29.0668, -94.3684, 29.5931];
  var CAMERA_BLUE = "#2563eb";
  var CAMERA_STROKE = "#1e3a8a";
  var OVERLAY_LIMIT = 4;

  var mapRef = null;
  var markers = [];
  var openInfoWindow = null;
  var refreshTimer = null;
  var regionListenerBound = false;
  var lastCameras = [];

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

  function catalogStill(id) {
    return "/api/cameras/" + encodeURIComponent(id) + "/still";
  }

  /** Houston–Galveston demo set when GET /api/cameras is unavailable. */
  var FIXTURE_CAMERAS = [
    {
      id: "transtar-180",
      name: "Galveston Ferry @ Galveston Ferry Landing",
      lat: 29.326965,
      lon: -94.772842,
      source: "transtar",
    },
    {
      id: "transtar-181",
      name: "Bolivar Ferry @ French Town Rd.",
      lat: 29.36452,
      lon: -94.7747,
      source: "transtar",
    },
    {
      id: "transtar-173",
      name: "45 GULF @ 61ST (W)",
      lat: 29.288568,
      lon: -94.838279,
      source: "transtar",
    },
    {
      id: "transtar-164",
      name: "45 GULF @ CAUSEWAY (N)",
      lat: 29.30133,
      lon: -94.89771,
      source: "transtar",
    },
    {
      id: "transtar-129",
      name: "45 Gulf @ Bay Area Blvd",
      lat: 29.54079,
      lon: -95.14238,
      source: "transtar",
    },
    {
      id: "transtar-1816",
      name: "NASA 1 @ SH-146",
      lat: 29.563873,
      lon: -95.025773,
      source: "transtar",
    },
  ].map(function (row) {
    return {
      id: row.id,
      name: row.name,
      lat: row.lat,
      lon: row.lon,
      still_url: catalogStill(row.id),
      source: row.source,
    };
  });

  function tearDownFilmstrip() {
    ["camera-demo-strip", "camera-demo-feed"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.remove();
    });
  }

  function ensureOverlayStyles() {
    if (document.getElementById("camera-map-overlay-styles")) return;
    var style = document.createElement("style");
    style.id = "camera-map-overlay-styles";
    style.textContent =
      "#camera-demo-strip,#camera-demo-feed{display:none!important}" +
      ".map-panel{position:relative}" +
      ".camera-map-overlay{position:absolute;left:12px;bottom:56px;z-index:5;" +
      "display:flex;flex-direction:column;gap:6px;width:148px;max-height:42%;" +
      "overflow:auto;padding:8px;background:rgba(15,23,42,.9);border-radius:10px;" +
      "border:1px solid rgba(255,255,255,.14);box-shadow:0 8px 24px rgba(0,0,0,.28)}" +
      ".camera-map-overlay-label{font:11px/1.2 system-ui,sans-serif;color:#cbd5e1;" +
      "letter-spacing:.04em;text-transform:uppercase}" +
      ".camera-map-overlay button{flex:0 0 auto;padding:0;border:0;border-radius:8px;" +
      "overflow:hidden;background:#0f172a;color:#e7eef6;text-align:left;cursor:pointer}" +
      ".camera-map-overlay img{display:block;width:100%;height:72px;object-fit:cover;background:#0f172a}" +
      ".camera-map-overlay figcaption,.camera-map-overlay .camera-map-overlay-cap{" +
      "display:block;padding:5px 7px;font:11px/1.3 system-ui,sans-serif;color:#e2e8f0;" +
      "white-space:nowrap;overflow:hidden;text-overflow:ellipsis}";
    document.head.appendChild(style);
  }

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

  function bboxSpanLon(bbox) {
    return Math.abs(Number(bbox[2]) - Number(bbox[0]));
  }

  function isTexasGulf(bbox) {
    if (!bbox || bbox.length !== 4) return false;
    var midLon = (Number(bbox[0]) + Number(bbox[2])) / 2;
    var midLat = (Number(bbox[1]) + Number(bbox[3])) / 2;
    return midLon < -90 && midLon > -100 && midLat > 25 && midLat < 34;
  }

  function isFloridaBbox(bbox) {
    if (!bbox || bbox.length !== 4) return false;
    var midLon = (Number(bbox[0]) + Number(bbox[2])) / 2;
    var midLat = (Number(bbox[1]) + Number(bbox[3])) / 2;
    return midLon > -88 && midLon < -79 && midLat > 24 && midLat < 32;
  }

  function preferLocalCameras(cameras, bbox) {
    if (isFloridaBbox(bbox)) return cameras;
    var local = (cameras || []).filter(function (cam) {
      return String(cam.source || "").toLowerCase() !== "fl511";
    });
    return local.length ? local : cameras;
  }

  function stillSrc(camera, bust) {
    if (!camera) return "";
    var url = "";
    if (camera.still_url && String(camera.still_url).indexOf("data:") === 0) {
      return camera.still_url;
    }
    if (camera.id) {
      url = catalogStill(camera.id);
    } else if (camera.still_url) {
      url = camera.still_url;
    }
    if (bust && url && String(url).indexOf("data:") !== 0) {
      url += (url.indexOf("?") >= 0 ? "&" : "?") + "t=" + Date.now();
    }
    return url;
  }

  function normalizeCamera(raw) {
    if (!raw) return null;
    var lat = Number(raw.lat);
    var lon = raw.lon != null ? Number(raw.lon) : Number(raw.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    var name = raw.name || raw.id || "Camera";
    var id = String(raw.id != null ? raw.id : name);
    return {
      id: id,
      name: name,
      lat: lat,
      lon: lon,
      still_url: raw.still_url || catalogStill(id),
      source: raw.source || "catalog",
    };
  }

  function stopRefresh() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  function buildInfoWindowContent(camera, bust) {
    var name = escapeHtml(camera.name);
    var src = escapeHtml(stillSrc(camera, bust));
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
      '" width="300" height="169" style="display:block;width:100%;max-width:300px;height:auto;border-radius:6px;background:#0f172a;" />' +
      (source
        ? '<div style="font-size:11px;color:#6b7280;margin-top:6px;">Source: ' + source + "</div>"
        : "") +
      "</div>"
    );
  }

  function clearMarkers() {
    stopRefresh();
    markers.forEach(function (entry) {
      if (entry.marker) entry.marker.setMap(null);
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

  function openCamera(entry) {
    if (!mapRef || !entry) return;
    stopRefresh();
    if (openInfoWindow) openInfoWindow.close();
    var camera = entry.camera;
    var info = entry.info;
    function tick() {
      info.setContent(buildInfoWindowContent(camera, true));
    }
    tick();
    if (entry.marker) {
      info.open({ map: mapRef, anchor: entry.marker });
    } else {
      info.setPosition({ lat: camera.lat, lng: camera.lon });
      info.open(mapRef);
    }
    openInfoWindow = info;
    refreshTimer = setInterval(tick, 5000);
    google.maps.event.addListenerOnce(info, "closeclick", stopRefresh);
  }

  function mountOverlay(cameras) {
    tearDownFilmstrip();
    ensureOverlayStyles();
    var old = document.getElementById("camera-map-overlay");
    if (old) old.remove();
    var host = document.querySelector(".map-panel") || document.getElementById("map");
    if (!host || !cameras.length) return;
    var overlay = document.createElement("div");
    overlay.id = "camera-map-overlay";
    overlay.className = "camera-map-overlay";
    overlay.setAttribute("aria-label", "Live cameras");
    var label = document.createElement("div");
    label.className = "camera-map-overlay-label";
    label.textContent = "Cameras";
    overlay.appendChild(label);
    cameras.slice(0, OVERLAY_LIMIT).forEach(function (camera) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.title = camera.name;
      var img = document.createElement("img");
      img.alt = camera.name;
      img.src = stillSrc(camera, false) || placeholderStill(camera.name);
      img.addEventListener("error", function () {
        img.src = placeholderStill(camera.name);
      });
      var cap = document.createElement("span");
      cap.className = "camera-map-overlay-cap";
      cap.textContent = camera.name;
      btn.append(img, cap);
      btn.addEventListener("click", function () {
        var hit = markers.filter(function (row) {
          return row.camera.id === camera.id;
        })[0];
        if (hit && mapRef && typeof mapRef.panTo === "function") {
          mapRef.panTo({ lat: camera.lat, lng: camera.lon });
        }
        openCamera(hit || { camera: camera, marker: null, info: new google.maps.InfoWindow() });
      });
      overlay.appendChild(btn);
    });
    host.appendChild(overlay);
  }

  function renderCameras(map, cameras) {
    clearMarkers();
    lastCameras = cameras.slice();
    cameras.forEach(function (camera) {
      var marker = new google.maps.Marker({
        map: map,
        position: { lat: camera.lat, lng: camera.lon },
        title: camera.name,
        icon: cameraIcon(),
        zIndex: google.maps.Marker.MAX_ZINDEX + 1,
      });
      var info = new google.maps.InfoWindow({
        content: buildInfoWindowContent(camera, false),
      });
      var entry = { camera: camera, marker: marker, info: info };
      marker.addListener("click", function () {
        openCamera(entry);
      });
      markers.push(entry);
    });
    mountOverlay(cameras);
  }

  function fetchCameras(bbox) {
    var query = bbox
      .map(function (n) {
        return Number(n);
      })
      .join(",");
    return fetch("/api/cameras?bbox=" + encodeURIComponent(query))
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        var list = Array.isArray(data) ? data : data && data.cameras;
        if (!Array.isArray(list) || !list.length) throw new Error("empty catalog");
        return preferLocalCameras(list.map(normalizeCamera).filter(Boolean), bbox);
      })
      .catch(function () {
        return filterCamerasInBbox(FIXTURE_CAMERAS, bbox);
      });
  }

  function currentSafetyBbox() {
    var sr = window.SafetyRegion;
    if (!sr || !sr.bbox) return null;
    return bboxFromRegionDetail({
      bbox: sr.bbox,
      minLon: sr.bbox.minLon,
      minLat: sr.bbox.minLat,
      maxLon: sr.bbox.maxLon,
      maxLat: sr.bbox.maxLat,
    });
  }

  function bboxFromMap(map) {
    if (!map || typeof map.getBounds !== "function") return null;
    var b = map.getBounds();
    if (!b) return null;
    var sw = b.getSouthWest();
    var ne = b.getNorthEast();
    return [sw.lng(), sw.lat(), ne.lng(), ne.lat()];
  }

  function usableBbox(bbox) {
    return bbox && bbox.length === 4 && bboxSpanLon(bbox) <= 3 && (isTexasGulf(bbox) || isFloridaBbox(bbox));
  }

  function resolveBbox(map) {
    var region = currentSafetyBbox();
    if (usableBbox(region)) return region;
    var view = bboxFromMap(map);
    if (usableBbox(view)) return view;
    return GALVESTON_BBOX.slice();
  }

  function loadAndRender(bbox) {
    var box = bbox && bbox.length === 4 ? bbox : GALVESTON_BBOX.slice();
    if (!usableBbox(box)) box = GALVESTON_BBOX.slice();
    fetchCameras(box).then(function (cameras) {
      if (!mapRef) return;
      var shown = filterCamerasInBbox(preferLocalCameras(cameras, box), box);
      if (!shown.length) shown = filterCamerasInBbox(FIXTURE_CAMERAS, GALVESTON_BBOX);
      renderCameras(mapRef, shown);
    });
  }

  function onRegionEvent(event) {
    if (!mapRef) return;
    var bbox = bboxFromRegionDetail(event && event.detail);
    loadAndRender(bbox || resolveBbox(mapRef));
  }

  function bindRegionListener() {
    if (regionListenerBound) return;
    regionListenerBound = true;
    window.addEventListener("safety:region", onRegionEvent);
  }

  function loadViewport(map) {
    loadAndRender(resolveBbox(map));
    return true;
  }

  function attach(map) {
    tearDownFilmstrip();
    ensureOverlayStyles();
    if (!map || typeof google === "undefined" || !google.maps) return;
    mapRef = map;
    window.floodMap = map;
    window.__floodMap = map;
    bindRegionListener();
    if (bboxFromMap(map) || currentSafetyBbox()) {
      loadViewport(map);
      return;
    }
    if (google.maps.event) {
      google.maps.event.addListenerOnce(map, "idle", function () {
        loadViewport(map);
      });
    }
    loadAndRender(GALVESTON_BBOX.slice());
  }

  function openByCamera(cam) {
    var normalized = normalizeCamera(cam);
    if (!normalized) return;
    var hit = markers.filter(function (row) {
      return row.camera.id === normalized.id;
    })[0];
    if (hit) {
      openCamera(hit);
      return;
    }
    if (!mapRef || typeof google === "undefined") return;
    var info = new google.maps.InfoWindow({
      position: { lat: normalized.lat, lng: normalized.lon },
      content: buildInfoWindowContent(normalized, true),
    });
    openCamera({ camera: normalized, marker: null, info: info });
  }

  window.SafetyCameraPins = {
    attach: attach,
    open: openByCamera,
    load: function () {
      return Promise.resolve(lastCameras.slice());
    },
    filterCamerasInBbox: filterCamerasInBbox,
    buildInfoWindowContent: buildInfoWindowContent,
    bboxFromRegionDetail: bboxFromRegionDetail,
  };

  tearDownFilmstrip();
  ensureOverlayStyles();

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
