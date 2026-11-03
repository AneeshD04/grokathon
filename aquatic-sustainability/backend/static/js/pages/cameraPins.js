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
      '" width="300" height="169" style="display:block;width:100%;max-width:300px;height:auto;border-radius:6px;background:#0f172a;" />' +
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

  window.SafetyCameraPins = {
    attach: attach,
    filterCamerasInBbox: filterCamerasInBbox,
    buildInfoWindowContent: buildInfoWindowContent,
    bboxFromRegionDetail: bboxFromRegionDetail,
  };

  if (window.floodMap) {
    attach(window.floodMap);
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
