(function safetyAlerts() {
  const listEl = document.getElementById("oemAlertList");
  const statusEl = document.getElementById("oemAlertStatus");
  const injectBtn = document.getElementById("oemInjectAlert");
  if (!listEl || !statusEl) return;

  const STREAM_URLS = [
    "/api/alerts/stream",
    "http://127.0.0.1:8000/api/alerts/stream",
    "http://localhost:8000/api/alerts/stream",
  ];
  const LIST_URLS = [
    "/api/alerts",
    "http://127.0.0.1:8000/api/alerts",
    "http://localhost:8000/api/alerts",
  ];

  const GALVESTON = { lat: 29.3013, lng: -94.7977 };
  const state = {
    alerts: [],
    markers: new Map(),
    selectedId: null,
    map: null,
  };

  window.SafetyOem = window.SafetyOem || {};
  window.SafetyOem.getSelectedAlert = function getSelectedAlert() {
    return state.alerts.find((item) => item.id === state.selectedId) || state.alerts[0] || null;
  };
  window.SafetyOem.getAlerts = function getAlerts() {
    return state.alerts.slice();
  };

  function setStatus(text) {
    statusEl.textContent = text;
  }

  function visionClass(alert) {
    const raw = alert && alert.evidence && alert.evidence.raw;
    if (!raw || typeof raw !== "object") return "";
    return raw.vision_class || raw.filename || "";
  }

  function evidenceThumb(alert) {
    const url = alert && alert.evidence && alert.evidence.thumb_url;
    return typeof url === "string" && /^https?:\/\//i.test(url) ? url : null;
  }

  function upsertAlert(alert) {
    if (!alert || !alert.id) return null;
    const index = state.alerts.findIndex(
      (item) => item.id === alert.id || (alert.dedupe_key && item.dedupe_key === alert.dedupe_key)
    );
    if (index >= 0) {
      state.alerts[index] = Object.assign({}, state.alerts[index], alert);
      return state.alerts[index];
    }
    state.alerts.unshift(alert);
    return alert;
  }

  function whenMapReady(callback) {
    if (state.map) {
      callback(state.map);
      return;
    }
    const timer = setInterval(function () {
      const map = window.map;
      if (map && window.google && google.maps && google.maps.Marker) {
        clearInterval(timer);
        state.map = map;
        callback(map);
      }
    }, 250);
  }

  function markerFor(alert) {
    if (!state.map || !window.google || !google.maps) return null;
    const existing = state.markers.get(alert.id);
    if (existing) return existing;
    const lat = Number(alert.lat);
    const lng = Number(alert.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    const marker = new google.maps.Marker({
      position: { lat: lat, lng: lng },
      map: state.map,
      title: alert.title || "Alert",
    });
    marker.addListener("click", function () {
      selectAlert(alert.id, { fly: true });
    });
    state.markers.set(alert.id, marker);
    return marker;
  }

  function flyTo(alert) {
    whenMapReady(function (map) {
      const lat = Number(alert.lat);
      const lng = Number(alert.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
      const pos = { lat: lat, lng: lng };
      map.setCenter(pos);
      map.setZoom(12);
      const marker = markerFor(alert);
      const thumb = evidenceThumb(alert);
      const klass = visionClass(alert);
      const lines = [
        "<div style=\"padding:8px;max-width:240px\">",
        "<strong>" + escapeHtml(alert.title || "Alert") + "</strong><br>",
        escapeHtml(alert.summary || ""),
      ];
      if (!thumb && klass) {
        lines.push("<br><span class=\"muted\">" + escapeHtml(klass) + "</span>");
      }
      if (thumb) {
        lines.push(
          "<br><img src=\"" +
            escapeHtml(thumb) +
            "\" alt=\"\" style=\"margin-top:8px;max-width:220px;border-radius:8px\">"
        );
      }
      lines.push("</div>");
      const info = new google.maps.InfoWindow({ content: lines.join("") });
      info.open(map, marker || undefined);
      if (!marker) info.setPosition(pos);
    });
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function selectAlert(id, options) {
    const alert = state.alerts.find((item) => item.id === id);
    if (!alert) return;
    state.selectedId = id;
    renderList();
    if (options && options.fly) flyTo(alert);
    document.dispatchEvent(new CustomEvent("safety:alert-selected", { detail: alert }));
  }

  function renderList() {
    listEl.textContent = "";
    if (!state.alerts.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No live alerts yet. Inject one to demo without a refresh.";
      listEl.appendChild(empty);
      return;
    }
    state.alerts.forEach(function (alert) {
      const item = document.createElement("div");
      item.className = "modal-info-item";
      item.setAttribute("role", "button");
      item.tabIndex = 0;
      item.setAttribute("aria-selected", alert.id === state.selectedId ? "true" : "false");

      const label = document.createElement("label");
      label.textContent = [alert.source || "alert", alert.severity || ""].filter(Boolean).join(" · ");
      item.appendChild(label);

      const title = document.createElement("div");
      title.className = "value";
      title.textContent = alert.title || "Untitled alert";
      item.appendChild(title);

      const summary = document.createElement("div");
      summary.className = "modal-map-coords";
      const thumb = evidenceThumb(alert);
      const klass = visionClass(alert);
      const bits = [];
      if (alert.summary) bits.push(alert.summary);
      if (!thumb && klass) bits.push(klass);
      summary.textContent = bits.join(" · ");
      item.appendChild(summary);

      if (thumb) {
        const img = document.createElement("img");
        img.src = thumb;
        img.alt = "";
        img.style.cssText = "margin-top:8px;max-width:100%;border-radius:8px";
        item.appendChild(img);
      }

      item.addEventListener("click", function () {
        selectAlert(alert.id, { fly: true });
      });
      item.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectAlert(alert.id, { fly: true });
        }
      });
      listEl.appendChild(item);
      markerFor(alert);
    });
  }

  function addAlert(alert, options) {
    const stored = upsertAlert(alert);
    if (!stored) return;
    if (!state.selectedId) state.selectedId = stored.id;
    setStatus(state.alerts.length + " alert" + (state.alerts.length === 1 ? "" : "s"));
    renderList();
    if (options && options.fly) {
      selectAlert(stored.id, { fly: true });
    }
  }

  function fakeAlert() {
    const stamp = Date.now();
    return {
      id: "inject-" + stamp,
      ts: new Date().toISOString(),
      source: "camera",
      severity: "warning",
      lat: GALVESTON.lat,
      lon: GALVESTON.lng,
      geofence_id: "galveston-county",
      title: "Standing water on Broadway",
      summary: "Judge inject: standing water covering two lanes near Seawall.",
      evidence: {
        thumb_url: null,
        raw: {
          vision_class: "standing_water",
          filename: "judge-inject.jpg",
        },
      },
      dedupe_key: "inject-" + stamp,
    };
  }

  function connectStream(index) {
    if (index >= STREAM_URLS.length) {
      setStatus(state.alerts.length ? state.alerts.length + " alerts (bus offline)" : "Alert bus offline — inject still works");
      return;
    }
    let source;
    try {
      source = new EventSource(STREAM_URLS[index]);
    } catch (err) {
      connectStream(index + 1);
      return;
    }
    let opened = false;
    source.addEventListener("alert", function (event) {
      try {
        addAlert(JSON.parse(event.data), { fly: false });
      } catch (err) {
        console.warn("safety-alerts: bad SSE payload", err);
      }
    });
    source.onopen = function () {
      opened = true;
      if (!state.alerts.length) setStatus("Listening for alerts");
    };
    source.onerror = function () {
      source.close();
      if (!opened) connectStream(index + 1);
    };
  }

  async function loadExisting() {
    for (let i = 0; i < LIST_URLS.length; i += 1) {
      try {
        const response = await fetch(LIST_URLS[i]);
        if (!response.ok) continue;
        const payload = await response.json();
        const rows = Array.isArray(payload) ? payload : payload.alerts || [];
        rows.forEach(function (row) {
          addAlert(row, { fly: false });
        });
        if (rows.length) setStatus(state.alerts.length + " alert" + (state.alerts.length === 1 ? "" : "s"));
        return;
      } catch (err) {
        // try next origin
      }
    }
  }

  if (injectBtn) {
    injectBtn.addEventListener("click", function () {
      addAlert(fakeAlert(), { fly: true });
    });
  }

  if (window.location.hash === "#oem-alerts") {
    var panel = document.getElementById("oem-alerts");
    if (panel && panel.scrollIntoView) panel.scrollIntoView({ block: "nearest" });
  }

  whenMapReady(function () {
    state.alerts.forEach(markerFor);
  });
  renderList();
  loadExisting();
  connectStream(0);
})();
