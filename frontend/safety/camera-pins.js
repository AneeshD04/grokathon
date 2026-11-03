/* Camera pins. A click opens the live feed in the marker popup.
   Teal pins are shoreline roads. Gray pins are interstate cameras in the same warning. */
(function () {
  let layer = null;
  let markers = {};
  let stopFeed = null;
  let onPopupClose = null;
  let requestId = 0;

  function view() {
    return window.SafetyMap && SafetyMap.getMap();
  }

  function style(cam, active) {
    return {
      radius: cam.coastal ? 8 : 6,
      color: active ? "#fb923c" : "#0f172a",
      weight: 2,
      fillColor: active ? "#fb923c" : (cam.coastal ? "#14b8a6" : "#64748b"),
      fillOpacity: 0.95,
      className: "camera-pin",
    };
  }

  function setStatus(text) {
    let el = document.getElementById("camera-risk-status");
    if (!el) {
      el = document.createElement("div");
      el.id = "camera-risk-status";
      el.setAttribute("role", "status");
      el.style.cssText = "position:fixed;z-index:650;top:14px;left:280px;right:370px;text-align:center;pointer-events:none;";
      const inner = document.createElement("p");
      inner.id = "camera-risk-status-text";
      inner.style.cssText = "display:inline-block;margin:0;padding:8px 12px;border-radius:999px;background:rgba(15,23,42,.92);color:#e7eef6;border:1px solid rgba(255,255,255,.14);font:13px/1.35 system-ui,sans-serif;";
      el.appendChild(inner);
      document.body.appendChild(el);
    }
    el.querySelector("#camera-risk-status-text").textContent = text;
  }

  function bust(url) {
    const next = new URL(url, window.location.href);
    next.searchParams.set("t", String(Date.now()));
    return next.toString();
  }

  function showStill(frame, meta, bits, cam, stops, note) {
    frame.textContent = "";
    const img = document.createElement("img");
    img.alt = cam.name + " live still";
    img.style.cssText = "display:block;width:100%;height:168px;object-fit:cover;background:#0f172a;border-radius:6px;";
    let lastGood = "";
    let failed = false;
    function tick() { img.src = bust(cam.still_url); }
    tick();
    const timer = setInterval(tick, 5000);
    stops.push(function () { clearInterval(timer); });
    img.addEventListener("load", function () {
      if (img.naturalWidth > 0) lastGood = img.src;
    });
    img.addEventListener("error", function () {
      if (lastGood && img.src !== lastGood) {
        img.src = lastGood;
        return;
      }
      if (failed) return;
      failed = true;
      meta.textContent = bits.concat(["still unavailable"]).join(" · ");
    });
    meta.textContent = bits.concat(note ? [note] : []).join(" · ");
    frame.appendChild(img);
  }

  function startVideo(video, url) {
    let hls = null;
    let stopped = false;
    const failed = new Promise(function (resolve) {
      function fail() { if (!stopped) resolve(); }
      if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = url;
        video.play().catch(fail);
        video.addEventListener("error", fail);
        return;
      }
      const existing = window.Hls;
      function attach() {
        if (stopped) return;
        if (!window.Hls || !window.Hls.isSupported()) {
          fail();
          return;
        }
        hls = new window.Hls();
        hls.loadSource(url);
        hls.attachMedia(video);
        hls.on(window.Hls.Events.ERROR, function (_event, data) {
          if (data && data.fatal) fail();
        });
      }
      if (existing) {
        attach();
        return;
      }
      const script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js";
      script.onload = attach;
      script.onerror = fail;
      document.head.appendChild(script);
    });
    return {
      failed: failed,
      stop: function () {
        stopped = true;
        if (hls) hls.destroy();
        video.pause();
        video.removeAttribute("src");
        video.load();
      },
    };
  }

  function buildFeed(cam) {
    const root = document.createElement("div");
    root.style.cssText = "width:280px;font:13px/1.35 system-ui,sans-serif;color:#0f172a;";
    const title = document.createElement("strong");
    title.textContent = cam.name;
    title.style.display = "block";
    const meta = document.createElement("div");
    meta.style.cssText = "color:#475569;margin:2px 0 8px;";
    const bits = [cam.county, cam.highway, cam.alertEvent].filter(Boolean);
    bits.push(cam.hls_url ? "Live video" : "Live still");
    const frame = document.createElement("div");
    const stops = [];
    if (cam.hls_url) {
      const video = document.createElement("video");
      video.controls = true;
      video.autoplay = true;
      video.muted = true;
      video.playsInline = true;
      video.style.cssText = "display:block;width:100%;height:168px;background:#0f172a;border-radius:6px;";
      frame.appendChild(video);
      meta.textContent = bits.join(" · ");
      const play = startVideo(video, cam.hls_url);
      stops.push(function () { play.stop(); });
      play.failed.then(function () {
        if (!stops.length) return;
        showStill(frame, meta, bits.filter(function (bit) { return bit !== "Live video"; }).concat(["Live still"]), cam, stops, "video unavailable");
      });
    } else {
      showStill(frame, meta, bits, cam, stops);
    }
    root.appendChild(title);
    root.appendChild(meta);
    root.appendChild(frame);
    return {
      el: root,
      stop: function () {
        const copy = stops.slice();
        stops.length = 0;
        copy.forEach(function (fn) { fn(); });
      },
    };
  }

  function highlight(id) {
    Object.keys(markers).forEach(function (key) {
      const entry = markers[key];
      entry.marker.setStyle(style(entry.cam, key === id));
    });
  }

  function showPopup(map, cam) {
    const feed = buildFeed(cam);
    const previous = stopFeed;
    stopFeed = feed.stop;
    if (previous) previous();
    if (onPopupClose) map.off("popupclose", onPopupClose);
    highlight(cam.id);
    L.popup({
      maxWidth: 320,
      minWidth: 280,
      autoPan: true,
      autoPanPaddingTopLeft: L.point(280, 48),
      autoPanPaddingBottomRight: L.point(380, 24),
      className: "camera-watch",
    }).setLatLng([cam.lat, cam.lon]).setContent(feed.el).openOn(map);
    onPopupClose = function () {
      if (stopFeed !== feed.stop) return;
      feed.stop();
      stopFeed = null;
    };
    map.on("popupclose", onPopupClose);
  }

  function draw(cameras) {
    const map = view();
    if (!map) return;
    if (layer) map.removeLayer(layer);
    if (stopFeed) {
      stopFeed();
      stopFeed = null;
    }
    markers = {};
    layer = L.layerGroup();
    cameras.forEach(function (cam) {
      const marker = L.circleMarker([cam.lat, cam.lon], style(cam, false));
      marker.on("click", function (ev) {
        L.DomEvent.stopPropagation(ev);
        showPopup(map, cam);
      });
      marker.bindTooltip(cam.name, { direction: "top" });
      layer.addLayer(marker);
      markers[cam.id] = { marker: marker, cam: cam };
    });
    layer.addTo(map);
  }

  function fit(cameras) {
    const map = view();
    if (!map || !cameras.length) return;
    map.fitBounds(L.latLngBounds(cameras.map(function (cam) { return [cam.lat, cam.lon]; })), {
      paddingTopLeft: [300, 56],
      paddingBottomRight: [400, 48],
      maxZoom: 12,
    });
  }

  async function show(bbox, apiCameras, shouldFit) {
    const ticket = ++requestId;
    setStatus("Looking for cameras inside live flood alerts…");
    try {
      const result = await SafetyCameras.load({ bbox: bbox, apiCameras: apiCameras });
      if (ticket !== requestId) return;
      draw(result.cameras);
      setStatus(result.summary);
      if (shouldFit) fit(result.cameras);
    } catch (err) {
      if (ticket !== requestId) return;
      draw([]);
      setStatus(err && err.message ? err.message : "Live camera search failed.");
    }
  }

  SafetyBus.on("region", function (region) {
    const bbox = region && region.bbox;
    show(bbox, region && region.cameras, false);
  });

  window.SafetyCameraPins = {
    open: function (cam) {
      const map = view();
      const entry = markers[cam.id];
      if (!map || !entry) return;
      showPopup(map, entry.cam);
    },
  };

  show(null, null, true);
})();
