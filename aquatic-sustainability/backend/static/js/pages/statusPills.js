/** Demo API health: alerts, cameras, places. Same-origin probes only. */
(function statusPillsModule() {
  var CAMERAS_BBOX = "-95.2,29.0,-94.4,29.6";
  /** Small Galveston island box for POST /api/businesses/nearby. */
  var PLACES_BBOX = [-94.82, 29.28, -94.78, 29.32];
  var POLL_MS = 8000;
  var STYLE_ID = "demo-status-pills-styles";
  var ROOT_CLASS = "demo-status-pills";

  var mountedHost = null;
  var rootEl = null;
  var pollTimer = null;

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent =
      "." +
      ROOT_CLASS +
      "{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;font-size:12px;line-height:1.2}" +
      "." +
      ROOT_CLASS +
      " .demo-status-pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;border:1px solid var(--border,#ccc);background:var(--surface,#f8f9fa)}" +
      "." +
      ROOT_CLASS +
      " .demo-status-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}" +
      "." +
      ROOT_CLASS +
      " .demo-status-pill[data-state='up'] .demo-status-dot{background:#2e7d32}" +
      "." +
      ROOT_CLASS +
      " .demo-status-pill[data-state='down'] .demo-status-dot{background:#c62828}" +
      "." +
      ROOT_CLASS +
      " .demo-status-pill[data-state='pending'] .demo-status-dot{background:#9e9e9e}";
    document.head.appendChild(style);
  }

  function pingAlerts() {
    return fetch("/api/alerts")
      .then(function (res) {
        return res.ok;
      })
      .catch(function () {
        return false;
      });
  }

  function pingCameras() {
    return fetch("/api/cameras?bbox=" + encodeURIComponent(CAMERAS_BBOX))
      .then(function (res) {
        return res.ok;
      })
      .catch(function () {
        return false;
      });
  }

  function pingPlaces() {
    return fetch("/api/businesses/nearby", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bbox: PLACES_BBOX }),
    })
      .then(function (res) {
        return res.ok;
      })
      .catch(function () {
        return false;
      });
  }

  function pillHtml(key, label, up) {
    var state = up === null ? "pending" : up ? "up" : "down";
    var statusText = up === null ? "checking" : up ? "up" : "down";
    return (
      '<span class="demo-status-pill" data-key="' +
      key +
      '" data-state="' +
      state +
      '">' +
      '<span class="demo-status-dot" aria-hidden="true"></span>' +
      "<span>" +
      label +
      ": " +
      statusText +
      "</span>" +
      "</span>"
    );
  }

  function renderPending(container) {
    container.innerHTML =
      pillHtml("alerts", "Alerts", null) +
      pillHtml("cameras", "Cameras", null) +
      pillHtml("places", "Places", null);
  }

  function applyStatus(container, statuses) {
    ["alerts", "cameras", "places"].forEach(function (key) {
      var pill = container.querySelector('.demo-status-pill[data-key="' + key + '"]');
      if (!pill) return;
      var up = statuses[key];
      var state = up ? "up" : "down";
      pill.setAttribute("data-state", state);
      var text = pill.querySelector("span:last-child");
      if (text) {
        text.textContent =
          (key === "alerts" ? "Alerts" : key === "cameras" ? "Cameras" : "Places") +
          ": " +
          (up ? "up" : "down");
      }
    });
  }

  function refresh(container) {
    renderPending(container);
    return Promise.all([pingAlerts(), pingCameras(), pingPlaces()]).then(function (results) {
      applyStatus(container, {
        alerts: results[0],
        cameras: results[1],
        places: results[2],
      });
    });
  }

  function findHost() {
    return document.getElementById("oem-watch") || document.body;
  }

  function mount(host) {
    ensureStyles();
    var target = host || findHost();
    if (!target) target = document.body;

    if (mountedHost === target && rootEl && rootEl.parentNode === target) {
      return refresh(rootEl).then(function () {
        return rootEl;
      });
    }

    if (rootEl && rootEl.parentNode) {
      rootEl.parentNode.removeChild(rootEl);
    }

    rootEl = document.createElement("div");
    rootEl.className = ROOT_CLASS;
    rootEl.setAttribute("role", "status");
    rootEl.setAttribute("aria-live", "polite");
    rootEl.setAttribute("aria-label", "Demo API status");
    target.appendChild(rootEl);
    mountedHost = target;
    return refresh(rootEl).then(function () {
      return rootEl;
    });
  }

  function pollForHost() {
    var host = findHost();
    if (host !== mountedHost) {
      mount(host);
    } else if (rootEl) {
      refresh(rootEl);
    }
  }

  window.StatusPills = window.StatusPills || {};
  window.StatusPills.mount = mount;

  function onReady() {
    mount(findHost());
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollForHost, POLL_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }
})();
