(function regionPicker() {
  var DEFAULT_SOURCES = ["model", "camera", "nws"];
  var BUS_URL =
    window.ALERT_BUS_URL ||
    localStorage.getItem("ALERT_BUS_URL") ||
    "http://127.0.0.1:8000";

  var map = null;
  var overlay = null;
  var drawClicks = [];
  var drawMoveListener = null;
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

  function pathFromCorners(a, b) {
    var minLat = Math.min(a.lat(), b.lat());
    var maxLat = Math.max(a.lat(), b.lat());
    var minLon = Math.min(a.lng(), b.lng());
    var maxLon = Math.max(a.lng(), b.lng());
    return [
      { lat: minLat, lng: minLon },
      { lat: minLat, lng: maxLon },
      { lat: maxLat, lng: maxLon },
      { lat: maxLat, lng: minLon },
    ];
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
      county: current.county,
      watch: current.watch,
      mocked: current.mocked,
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
      badge.textContent = "Subscribed to BDBI analysis";
      badge.style.color = "var(--accent)";
      badge.style.fontWeight = "600";
      badge.style.marginTop = "4px";
      el.appendChild(badge);
    }
  }

  function setCountyButtons(activeId) {
    ["watchGalveston", "watchHarris"].forEach(function (id) {
      var btn = $(id);
      if (!btn) return;
      var on = (id === "watchGalveston" && activeId === "galveston-county") ||
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
    drawClicks = [];
    if (drawMoveListener) {
      google.maps.event.removeListener(drawMoveListener);
      drawMoveListener = null;
    }
    if (map) {
      map.setOptions({ draggableCursor: null });
    }
    setCountyButtons(current.county ? current.county.id : null);
  }

  function applyRegion(opts) {
    var path = opts.path;
    var bbox = opts.bbox || bboxFromPath(path);
    var county = opts.county || null;
    if (!map) {
      setStatus("Map still loading…");
      return;
    }
    if (bbox[0] >= bbox[2] || bbox[1] >= bbox[3]) {
      setStatus("Need a box with width and height.");
      return;
    }
    showPath(path);
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
    if (!county) {
      setStatus("Unknown county.");
      return;
    }
    applyRegion({ county: county, path: county.path, bbox: county.bbox.slice() });
  }

  function onMapClick(e) {
    if (!drawing) return;
    drawClicks.push(e.latLng);
    if (drawClicks.length === 1) {
      setStatus("Click the opposite corner.");
      drawMoveListener = map.addListener("mousemove", function (move) {
        showPath(pathFromCorners(drawClicks[0], move.latLng), "#60a5fa");
      });
      return;
    }
    var path = pathFromCorners(drawClicks[0], drawClicks[1]);
    stopDrawing();
    applyRegion({ path: path, bbox: bboxFromPath(path), county: null });
  }

  function startDraw() {
    if (!map) return;
    drawing = !drawing;
    drawClicks = [];
    if (!drawing) {
      stopDrawing();
      setStatus(current.bbox ? "Draw cancelled. Previous watch kept." : "No watch yet.");
      return;
    }
    current.county = null;
    setCountyButtons(null);
    map.setOptions({ draggableCursor: "crosshair" });
    setStatus("Click two corners to mark a watch box.");
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
      getBbox: function () {
        return null;
      },
    };
    window.dispatchEvent(new CustomEvent("safety:region", { detail: { bbox: null } }));
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
    map = nextMap;
    map.addListener("click", onMapClick);
  }

  window.SafetyRegion = {
    bbox: null,
    county: null,
    watch: null,
    getBbox: function () {
      return null;
    },
  };

  bind();
  if (window.floodMap) {
    attachMap(window.floodMap);
  } else {
    window.addEventListener(
      "flood-map-ready",
      function (event) {
        attachMap(event.detail.map);
      },
      { once: true }
    );
  }
})();
