(function regionPicker() {
  var DEFAULT_SOURCES = ["model", "camera", "nws"];
  var GALVESTON_BBOX = [-95.1544, 29.0668, -94.3684, 29.5931];
  var BUS_URL =
    window.ALERT_BUS_URL ||
    localStorage.getItem("ALERT_BUS_URL") ||
    "http://127.0.0.1:8000";

  var map = null;
  var overlay = null;
  var pixelProbe = null;
  var dragStart = null;
  var dragOriginPx = null;
  var drawing = false;
  var current = {
    county: null,
    bbox: null,
    watch: null,
    mocked: false,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function round4(n) {
    return Math.round(n * 10000) / 10000;
  }

  function bboxFromPath(path) {
    var minLon = Infinity;
    var minLat = Infinity;
    var maxLon = -Infinity;
    var maxLat = -Infinity;
    path.forEach(function (pt) {
      minLon = Math.min(minLon, pt.lng);
      minLat = Math.min(minLat, pt.lat);
      maxLon = Math.max(maxLon, pt.lng);
      maxLat = Math.max(maxLat, pt.lat);
    });
    return [round4(minLon), round4(minLat), round4(maxLon), round4(maxLat)];
  }

  function mockWatch(payload) {
    var geofenceId = payload.county
      ? payload.county.toLowerCase().split(/\s+/).join("-")
      : "bbox:" + payload.bbox.join(",");
    return {
      id: "local-" + Date.now(),
      geofence_id: geofenceId,
      bbox: payload.bbox,
      county: payload.county || null,
      sources: payload.sources,
      camera_ids: [],
      created_at: new Date().toISOString(),
    };
  }

  function createWatch(payload) {
    var endpoints = ["/api/watches", String(BUS_URL).replace(/\/$/, "") + "/api/watches"];
    var lastError = null;

    function tryNext(i) {
      if (i >= endpoints.length) {
        return Promise.resolve({ watch: mockWatch(payload), mocked: true, error: lastError });
      }
      return fetch(endpoints[i], {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          if (!res.ok) {
            lastError = "HTTP " + res.status;
            return tryNext(i + 1);
          }
          return res.json().then(function (watch) {
            return { watch: watch, mocked: false };
          });
        })
        .catch(function (err) {
          lastError = err && err.message ? err.message : "network";
          return tryNext(i + 1);
        });
    }

    return tryNext(0);
  }

  function publishRegion() {
    var bbox = current.bbox;
    var detail = {
      minLon: bbox[0],
      minLat: bbox[1],
      maxLon: bbox[2],
      maxLat: bbox[3],
      bbox: bbox.slice(),
      county: current.county,
      watch: current.watch,
      mocked: current.mocked,
      sources: DEFAULT_SOURCES.slice(),
    };
    window.SafetyRegion = {
      bbox: {
        minLon: detail.minLon,
        minLat: detail.minLat,
        maxLon: detail.maxLon,
        maxLat: detail.maxLat,
      },
      county: current.county,
      watch: current.watch,
      sources: DEFAULT_SOURCES.slice(),
      getBbox: function () {
        return window.SafetyRegion.bbox;
      },
    };
    window.dispatchEvent(new CustomEvent("safety:region", { detail: detail }));
  }

  function setStatus(text, subscribed) {
    var el = $("oemWatchStatus");
    if (!el) return;
    el.textContent = "";
    var line = document.createElement("div");
    line.textContent = text;
    el.appendChild(line);
    if (subscribed) {
      var badge = document.createElement("div");
      badge.className = "oem-subscribed";
      badge.textContent = "Subscribed to BDBI analysis";
      el.appendChild(badge);
    }
  }

  function setCountyButtons(activeId) {
    ["watchGalveston", "watchHarris"].forEach(function (id) {
      var btn = $(id);
      if (!btn) return;
      var on =
        (id === "watchGalveston" && activeId === "galveston-county") ||
        (id === "watchHarris" && activeId === "harris-county");
      btn.classList.toggle("flood-active", on);
    });
    var drawBtn = $("drawWatchBox");
    if (drawBtn) drawBtn.classList.toggle("flood-active", drawing);
  }

  function clearOverlay() {
    if (overlay) {
      overlay.setMap(null);
      overlay = null;
    }
  }

  function showPath(path, color) {
    if (!map || !window.google || !google.maps) return;
    clearOverlay();
    overlay = new google.maps.Polygon({
      paths: path,
      strokeColor: color || "#1a73e8",
      strokeOpacity: 0.95,
      strokeWeight: 2,
      fillColor: color || "#1a73e8",
      fillOpacity: 0.18,
      map: map,
      clickable: false,
    });
    var bounds = new google.maps.LatLngBounds();
    path.forEach(function (pt) {
      bounds.extend(pt);
    });
    map.fitBounds(bounds, 48);
  }

  function stopDrawing() {
    drawing = false;
    dragStart = null;
    dragOriginPx = null;
    if (map) {
      map.setOptions({ draggable: true, gestureHandling: "auto", draggableCursor: null });
    }
    setCountyButtons(current.county ? current.county.id : null);
  }

  function latLngFromMouse(ev) {
    if (!map || !pixelProbe) return null;
    var projection = pixelProbe.getProjection();
    if (!projection) return null;
    var rect = map.getDiv().getBoundingClientRect();
    return projection.fromContainerPixelToLatLng(
      new google.maps.Point(ev.clientX - rect.left, ev.clientY - rect.top)
    );
  }

  function paintDrag(a, b) {
    var sw = new google.maps.LatLng(Math.min(a.lat(), b.lat()), Math.min(a.lng(), b.lng()));
    var ne = new google.maps.LatLng(Math.max(a.lat(), b.lat()), Math.max(a.lng(), b.lng()));
    var bounds = new google.maps.LatLngBounds(sw, ne);
    if (!overlay || typeof overlay.setBounds !== "function") {
      clearOverlay();
      overlay = new google.maps.Rectangle({
        bounds: bounds,
        strokeColor: "#60a5fa",
        strokeOpacity: 0.95,
        strokeWeight: 2,
        fillColor: "#60a5fa",
        fillOpacity: 0.18,
        map: map,
        clickable: false,
      });
    } else {
      overlay.setBounds(bounds);
    }
    return bounds;
  }

  function restoreCommitted() {
    if (!current.bbox) {
      clearOverlay();
      return;
    }
    showPath([
      { lat: current.bbox[1], lng: current.bbox[0] },
      { lat: current.bbox[1], lng: current.bbox[2] },
      { lat: current.bbox[3], lng: current.bbox[2] },
      { lat: current.bbox[3], lng: current.bbox[0] },
    ]);
  }

  function onDragDown(ev) {
    if (!drawing || ev.button !== 0) return;
    var node = ev.target;
    if (node && node.closest && node.closest(".gm-bundled-control, .gm-style-mtc, .gmnoprint, .filter-overlay")) return;
    ev.preventDefault();
    ev.stopPropagation();
    var start = latLngFromMouse(ev);
    if (!start) return;
    dragStart = start;
    dragOriginPx = { x: ev.clientX, y: ev.clientY };

    function onMove(moveEv) {
      var cur = latLngFromMouse(moveEv);
      if (!cur || !dragStart) return;
      paintDrag(dragStart, cur);
    }

    function onUp(upEv) {
      document.removeEventListener("mousemove", onMove, true);
      document.removeEventListener("mouseup", onUp, true);
      var origin = dragStart;
      var originPx = dragOriginPx;
      var cur = latLngFromMouse(upEv);
      dragStart = null;
      dragOriginPx = null;
      var moved = originPx ? Math.hypot(upEv.clientX - originPx.x, upEv.clientY - originPx.y) : 0;
      if (!origin || !cur || moved < 8) {
        restoreCommitted();
        setStatus(moved < 8 ? "Drag a wider rectangle." : "Map is still loading.");
        return;
      }
      var bounds = paintDrag(origin, cur);
      var sw = bounds.getSouthWest();
      var ne = bounds.getNorthEast();
      var path = [
        { lat: sw.lat(), lng: sw.lng() },
        { lat: sw.lat(), lng: ne.lng() },
        { lat: ne.lat(), lng: ne.lng() },
        { lat: ne.lat(), lng: sw.lng() },
      ];
      stopDrawing();
      applyRegion({ path: path, bbox: bboxFromPath(path), county: null });
    }

    document.addEventListener("mousemove", onMove, true);
    document.addEventListener("mouseup", onUp, true);
  }

  function applyRegion(opts) {
    var path = opts.path;
    var bbox = opts.bbox || (path ? bboxFromPath(path) : null);
    var county = opts.county || null;
    if (!bbox || bbox[0] >= bbox[2] || bbox[1] >= bbox[3]) {
      setStatus("Need a box with width and height.");
      return;
    }
    if (map && path) {
      showPath(path);
    } else if (!county) {
      setStatus("Map still loading…");
      return;
    }
    current.county = county;
    current.bbox = bbox;
    setCountyButtons(county ? county.id : null);

    var payload = {
      bbox: bbox,
      sources: DEFAULT_SOURCES.slice(),
    };
    if (county) payload.county = county.name;

    setStatus("Saving watch…");
    createWatch(payload).then(function (result) {
      current.watch = result.watch;
      current.mocked = result.mocked;
      var label = county ? county.name : "Drawn box";
      var bboxText =
        "bbox [" + bbox[0] + ", " + bbox[1] + ", " + bbox[2] + ", " + bbox[3] + "]";
      var extra = result.mocked ? " (local mock — alert bus not reached)" : "";
      setStatus(label + " · " + bboxText + extra, true);
      publishRegion();
    });
  }

  function watchCounty(id) {
    stopDrawing();
    var county = window.oemCountyById ? window.oemCountyById(id) : null;
    if (!county && id === "galveston-county") {
      county = {
        id: id,
        name: "Galveston County",
        bbox: GALVESTON_BBOX.slice(),
        path: [
          { lat: GALVESTON_BBOX[1], lng: GALVESTON_BBOX[0] },
          { lat: GALVESTON_BBOX[1], lng: GALVESTON_BBOX[2] },
          { lat: GALVESTON_BBOX[3], lng: GALVESTON_BBOX[2] },
          { lat: GALVESTON_BBOX[3], lng: GALVESTON_BBOX[0] },
        ],
      };
    }
    if (!county) {
      setStatus("Unknown county.");
      return;
    }
    applyRegion({ county: county, path: county.path, bbox: county.bbox.slice() });
  }

  function startDraw() {
    if (!map) {
      setStatus("Map still loading…");
      return;
    }
    drawing = !drawing;
    if (!drawing) {
      stopDrawing();
      setStatus(current.bbox ? "Draw cancelled. Previous watch kept." : "No watch yet.");
      return;
    }
    current.county = null;
    setCountyButtons(null);
    map.setOptions({ draggable: false, gestureHandling: "none", draggableCursor: "crosshair" });
    setStatus("Drag a rectangle on the map.");
    var drawBtn = $("drawWatchBox");
    if (drawBtn) drawBtn.classList.add("flood-active");
  }

  function clearWatch() {
    stopDrawing();
    clearOverlay();
    current = { county: null, bbox: null, watch: null, mocked: false };
    setCountyButtons(null);
    setStatus("No watch yet.");
    window.SafetyRegion = {
      bbox: null,
      county: null,
      watch: null,
      sources: DEFAULT_SOURCES.slice(),
      getBbox: function () {
        return null;
      },
    };
    window.dispatchEvent(new CustomEvent("safety:region", { detail: { bbox: null } }));
  }

  function ensureStyles() {
    if ($("oem-watch-styles")) return;
    var style = document.createElement("style");
    style.id = "oem-watch-styles";
    style.textContent =
      "#oem-watch{margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}" +
      "#oem-watch .toggle-buttons{margin-top:8px}" +
      "#oem-watch .oem-subscribed{color:var(--accent);font-weight:600;margin-top:4px}";
    document.head.appendChild(style);
  }

  function ensurePanel() {
    if ($("oem-watch")) return;
    var overlayEl = document.querySelector(".filter-overlay");
    if (!overlayEl) return;

    var panel = document.createElement("div");
    panel.id = "oem-watch";
    panel.className = "filter-section";
    panel.innerHTML =
      '<div class="filter-title">County OEM watch</div>' +
      '<p class="muted">Mark Galveston or Harris, or draw a box. ModelWatch uses this geofence.</p>' +
      '<div class="toggle-buttons">' +
      '<button type="button" class="toggle-btn" id="watchGalveston">Galveston</button>' +
      '<button type="button" class="toggle-btn" id="watchHarris">Harris</button>' +
      "</div>" +
      '<div class="toggle-buttons">' +
      '<button type="button" class="toggle-btn" id="drawWatchBox">Draw box</button>' +
      '<button type="button" class="toggle-btn" id="clearWatchBox">Clear</button>' +
      "</div>" +
      '<p class="muted" id="oemWatchStatus">No watch yet.</p>';
    overlayEl.appendChild(panel);
  }

  function bind() {
    var galveston = $("watchGalveston");
    var harris = $("watchHarris");
    var drawBtn = $("drawWatchBox");
    var clearBtn = $("clearWatchBox");
    if (galveston) {
      galveston.addEventListener("click", function () {
        watchCounty("galveston-county");
      });
    }
    if (harris) {
      harris.addEventListener("click", function () {
        watchCounty("harris-county");
      });
    }
    if (drawBtn) drawBtn.addEventListener("click", startDraw);
    if (clearBtn) clearBtn.addEventListener("click", clearWatch);
    if (window.location.hash === "#oem-watch") {
      var panel = $("oem-watch");
      if (panel && panel.scrollIntoView) panel.scrollIntoView({ block: "nearest" });
    }
  }

  function attachMap(nextMap) {
    if (!nextMap || map === nextMap) return;
    map = nextMap;
    window.floodMap = nextMap;
    window.__floodMap = nextMap;
    pixelProbe = new google.maps.OverlayView();
    pixelProbe.onAdd = function () {};
    pixelProbe.draw = function () {};
    pixelProbe.setMap(map);
    map.getDiv().addEventListener("mousedown", onDragDown, true);
    if (current.bbox && current.county) {
      showPath(current.county.path);
    } else if (current.bbox) {
      restoreCommitted();
    }
  }

  function hookGoogleMap() {
    if (!window.google || !google.maps || typeof google.maps.Map !== "function") return false;
    if (google.maps.Map.__oemHooked) return true;
    var Original = google.maps.Map;
    function HookedMap(el, opts) {
      var instance = new Original(el, opts);
      if (el && el.id === "map") {
        window.floodMap = instance;
        window.__floodMap = instance;
        window.dispatchEvent(new CustomEvent("flood-map-ready", { detail: { map: instance } }));
      }
      return instance;
    }
    HookedMap.prototype = Original.prototype;
    HookedMap.__oemHooked = true;
    google.maps.Map = HookedMap;
    return true;
  }

  function waitForMap() {
    hookGoogleMap();
    var existing = window.floodMap || window.__floodMap;
    if (existing) {
      window.floodMap = existing;
      window.__floodMap = existing;
      attachMap(existing);
      return;
    }
    setTimeout(waitForMap, 50);
  }

  window.SafetyRegion = {
    bbox: null,
    county: null,
    watch: null,
    sources: DEFAULT_SOURCES.slice(),
    getBbox: function () {
      return null;
    },
  };

  ensureStyles();
  ensurePanel();
  bind();
  window.addEventListener("flood-map-ready", function (event) {
    attachMap(event.detail && event.detail.map);
  });
  waitForMap();
})();
