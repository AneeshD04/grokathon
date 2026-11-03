(function travelDelayPanel() {
  var POLL_MS = 8000;
  var ROOT_ATTR = "data-travel-delay-root";
  var API_PATHS = ["/api/roads", "/api/travel-delay"];
  var DEMO_NOTE =
    "Demo travel estimate for planning only — not a dispatch order or official routing.";

  var FIXTURE = [
    {
      road: "I-45 causeway",
      detail: "+25 min vs normal route",
      delay_minutes: 25,
    },
    {
      road: "Seawall Blvd",
      detail: "Closed at 61st",
      status: "closed",
    },
    {
      road: "SH-87 ferry",
      detail: "Ferry delayed",
      status: "delayed",
    },
  ];

  var panels = [];
  var pollTimer = null;
  var inflight = false;

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function rowFromObject(item) {
    if (!item || typeof item !== "object") return null;
    var road =
      item.road ||
      item.name ||
      item.segment ||
      item.route ||
      item.label ||
      "";
    if (!String(road).trim()) return null;
    var detail =
      item.detail ||
      item.reason ||
      item.status ||
      item.description ||
      "";
    if (item.delay_minutes != null && !detail) {
      detail = "+" + item.delay_minutes + " min";
    } else if (item.delayMinutes != null && !detail) {
      detail = "+" + item.delayMinutes + " min";
    } else if (item.extra_minutes != null && !detail) {
      detail = "+" + item.extra_minutes + " min";
    }
    return {
      road: String(road).trim(),
      detail: String(detail || "").trim() || "Impact reported",
    };
  }

  function normalizeRows(data) {
    var list = [];
    if (Array.isArray(data)) list = data;
    else if (data && typeof data === "object") {
      list =
        data.items ||
        data.roads ||
        data.delays ||
        data.segments ||
        data.routes ||
        [];
    }
    if (!Array.isArray(list)) return [];
    return list.map(rowFromObject).filter(Boolean);
  }

  function fetchLive() {
    var chain = Promise.resolve(null);
    API_PATHS.forEach(function (path) {
      chain = chain.then(function (found) {
        if (found) return found;
        return fetch(path, { credentials: "same-origin" })
          .then(function (res) {
            if (!res.ok) return null;
            return res.json().then(function (data) {
              var rows = normalizeRows(data);
              if (!rows.length) return null;
              return { rows: rows, source: "live", path: path };
            });
          })
          .catch(function () {
            return null;
          });
      });
    });
    return chain;
  }

  function ensureStyles() {
    if (document.getElementById("travel-delay-styles")) return;
    var style = document.createElement("style");
    style.id = "travel-delay-styles";
    style.textContent =
      "[data-travel-delay-root]{margin-top:12px;padding-top:12px;border-top:1px solid var(--border,rgba(148,163,184,.25))}" +
      "[data-travel-delay-root] .travel-delay-list{list-style:none;margin:8px 0 0;padding:0}" +
      "[data-travel-delay-root] .travel-delay-row{" +
      "display:flex;justify-content:space-between;gap:10px;align-items:flex-start;" +
      "padding:6px 0;border-bottom:1px solid rgba(148,163,184,.15);font-size:13px;line-height:1.35}" +
      "[data-travel-delay-root] .travel-delay-road{font-weight:600}" +
      "[data-travel-delay-root] .travel-delay-detail{color:var(--muted,#94a3b8);text-align:right;flex:0 1 auto}";
    document.head.appendChild(style);
  }

  function buildShell(host) {
    ensureStyles();
    var root = document.createElement("div");
    root.setAttribute(ROOT_ATTR, "1");
    root.innerHTML =
      '<div class="filter-title">First-responder travel</div>' +
      '<p class="muted" style="margin:4px 0 0;font-size:12px;">' +
      escapeHtml(DEMO_NOTE) +
      "</p>" +
      '<p class="muted" data-travel-delay-status style="margin:6px 0 0;font-size:12px;">Loading…</p>' +
      '<ul class="travel-delay-list" data-travel-delay-list></ul>';
    host.appendChild(root);
    panels.push(root);
    return root;
  }

  function setStatus(root, text) {
    var el = root.querySelector("[data-travel-delay-status]");
    if (el) el.textContent = text || "";
  }

  function renderList(root, rows) {
    var list = root.querySelector("[data-travel-delay-list]");
    if (!list) return;
    list.innerHTML = "";
    rows.forEach(function (row) {
      var li = document.createElement("li");
      li.className = "travel-delay-row";
      li.innerHTML =
        '<span class="travel-delay-road">' +
        escapeHtml(row.road) +
        "</span>" +
        '<span class="travel-delay-detail">' +
        escapeHtml(row.detail) +
        "</span>";
      list.appendChild(li);
    });
  }

  function refreshAll() {
    if (inflight) return;
    inflight = true;
    fetchLive()
      .then(function (result) {
        var rows = result ? result.rows : FIXTURE.slice();
        var status = result
          ? "Live from " + result.path + " · updated " + new Date().toLocaleTimeString()
          : "Demo fixture (API unavailable) · updated " + new Date().toLocaleTimeString();
        panels.forEach(function (root) {
          renderList(root, rows);
          setStatus(root, status);
        });
      })
      .finally(function () {
        inflight = false;
      });
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(refreshAll, POLL_MS);
  }

  function mount(host) {
    host = host || document.getElementById("oem-watch");
    if (!host) return false;
    if (host.querySelector("[" + ROOT_ATTR + "]")) return true;
    buildShell(host);
    refreshAll();
    startPolling();
    return true;
  }

  window.TravelDelay = { mount: mount };

  function tryAutoMount() {
    mount(document.getElementById("oem-watch"));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", tryAutoMount);
  } else {
    tryAutoMount();
  }
})();
