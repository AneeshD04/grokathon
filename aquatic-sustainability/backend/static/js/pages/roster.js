(function safetyRoster() {
  var DISPLAY_CAP = 50;
  var EMPTY_COPY = "no list uploaded — public SMS skipped";
  var PHONE_HEADER = { phone: 1, phones: 1, mobile: 1, cell: 1, number: 1, e164: 1 };
  var LABEL_HEADER = { label: 1, name: 1, contact: 1, resident: 1 };
  var REGION_ID_RE = /^[a-z0-9][a-z0-9.-]{0,63}$/;

  var state = {
    regionId: null,
    contacts: [],
    loading: false,
    error: null,
    status: null,
  };
  var mountedPanels = [];

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function slugCountyName(name) {
    var text = String(name || "")
      .trim()
      .toLowerCase()
      .replace(/_/g, "-")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "");
    return REGION_ID_RE.test(text) ? text : null;
  }

  function regionFromDetail(detail) {
    if (!detail || detail.bbox === null) return null;
    if (detail.region_id && REGION_ID_RE.test(detail.region_id)) return detail.region_id;
    if (detail.county && detail.county.id) return detail.county.id;
    if (typeof detail.county === "string") {
      var byName = slugCountyName(detail.county);
      if (byName) return byName;
    }
    if (detail.watch && detail.watch.geofence_id && REGION_ID_RE.test(detail.watch.geofence_id)) {
      return detail.watch.geofence_id;
    }
    return null;
  }

  function resolveRegionId() {
    var sr = window.SafetyRegion;
    if (sr) {
      if (sr.region_id && REGION_ID_RE.test(sr.region_id)) return sr.region_id;
      if (sr.county && sr.county.id) return sr.county.id;
      if (typeof sr.county === "string") {
        var slug = slugCountyName(sr.county);
        if (slug) return slug;
      }
      if (sr.watch && sr.watch.geofence_id && REGION_ID_RE.test(sr.watch.geofence_id)) {
        return sr.watch.geofence_id;
      }
    }
    return null;
  }

  function parseCsvText(text) {
    var raw = String(text || "").trim();
    if (!raw) return [];
    var sample = raw.slice(0, 2048);
    var delimiter = sample.indexOf("\t") >= 0 && sample.indexOf(",") < 0 ? "\t" : ",";
    var rows = raw.split(/\r?\n/).map(function (line) {
      var out = [];
      var cell = "";
      var inQuotes = false;
      for (var i = 0; i < line.length; i++) {
        var ch = line[i];
        if (ch === '"') {
          if (inQuotes && line[i + 1] === '"') {
            cell += '"';
            i++;
          } else {
            inQuotes = !inQuotes;
          }
          continue;
        }
        if (!inQuotes && ch === delimiter) {
          out.push(cell);
          cell = "";
          continue;
        }
        cell += ch;
      }
      out.push(cell);
      return out.map(function (c) {
        return c.trim();
      });
    });
    rows = rows.filter(function (row) {
      return row.some(function (cell) {
        return String(cell).trim();
      });
    });
    if (!rows.length) return [];

    var header = rows[0].map(function (c) {
      return c.toLowerCase();
    });
    var hasHeader = header.some(function (cell) {
      return PHONE_HEADER[cell] || LABEL_HEADER[cell];
    });
    var parsed = [];

    function pushRow(phoneRaw, labelRaw) {
      if (!String(phoneRaw || "").trim()) return;
      parsed.push({
        phone: String(phoneRaw).trim(),
        label: labelRaw != null && String(labelRaw).trim() ? String(labelRaw).trim() : null,
      });
    }

    if (hasHeader) {
      var idx = {};
      header.forEach(function (name, i) {
        idx[name] = i;
      });
      function col(names) {
        var keys = Object.keys(names);
        for (var k = 0; k < keys.length; k++) {
          if (idx[keys[k]] != null) return idx[keys[k]];
        }
        return null;
      }
      var phoneI = col(PHONE_HEADER);
      var labelI = col(LABEL_HEADER);
      if (phoneI == null) phoneI = 0;
      for (var r = 1; r < rows.length; r++) {
        var row = rows[r];
        pushRow(row[phoneI], labelI != null ? row[labelI] : null);
      }
    } else {
      rows.forEach(function (row) {
        pushRow(row[0], row.length > 1 ? row[1] : null);
      });
    }
    return parsed;
  }

  function panelStyles() {
    return (
      "margin-top:12px;padding:12px;border-radius:8px;" +
      "background:var(--card-bg,#1e293b);color:var(--text,#e2e8f0);" +
      "border:1px solid rgba(148,163,184,0.25);font-size:13px;line-height:1.45;"
    );
  }

  function buildShell(container, panelRef) {
    container.innerHTML =
      '<div class="safety-roster-panel" style="' +
      panelStyles() +
      '">' +
      '<div style="font-weight:600;margin-bottom:6px;">Opt-in resident roster</div>' +
      '<div data-roster-region style="color:var(--muted,#94a3b8);margin-bottom:8px;"></div>' +
      '<div data-roster-empty style="color:var(--muted,#94a3b8);margin-bottom:8px;"></div>' +
      '<label style="display:block;color:var(--muted,#94a3b8);margin-bottom:4px;">Paste CSV or one phone per line (optional label after comma)</label>' +
      '<textarea data-roster-paste rows="4" style="width:100%;box-sizing:border-box;margin-bottom:8px;' +
      "background:rgba(15,23,42,0.6);color:var(--text,#e2e8f0);border:1px solid rgba(148,163,184,0.35);" +
      'border-radius:6px;padding:8px;resize:vertical;"></textarea>' +
      '<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:8px;">' +
      '<input type="file" accept=".csv,text/csv,text/plain" data-roster-file />' +
      '<button type="button" data-roster-import style="padding:6px 10px;border-radius:6px;border:0;' +
      'background:#2563eb;color:#fff;cursor:pointer;">Import (merge)</button>' +
      '<button type="button" data-roster-replace style="padding:6px 10px;border-radius:6px;border:1px solid rgba(148,163,184,0.45);' +
      'background:transparent;color:var(--text,#e2e8f0);cursor:pointer;">Replace list</button>' +
      '<button type="button" data-roster-refresh style="padding:6px 10px;border-radius:6px;border:1px solid rgba(148,163,184,0.45);' +
      'background:transparent;color:var(--text,#e2e8f0);cursor:pointer;">Refresh</button>' +
      "</div>" +
      '<div data-roster-status style="min-height:18px;margin-bottom:8px;color:var(--muted,#94a3b8);"></div>' +
      '<ul data-roster-list style="list-style:none;margin:0;padding:0;max-height:220px;overflow:auto;"></ul>' +
      "</div>";

    var panel = $(".safety-roster-panel", container);
    panel.querySelector("[data-roster-import]").addEventListener("click", function () {
      uploadCsv(panel, "merge");
    });
    panel.querySelector("[data-roster-replace]").addEventListener("click", function () {
      uploadCsv(panel, "replace");
    });
    panel.querySelector("[data-roster-refresh]").addEventListener("click", refreshList);
    panel.querySelector("[data-roster-file]").addEventListener("change", function (ev) {
      onFileSelected(panel, ev);
    });
    panel.querySelector("[data-roster-paste]").addEventListener("input", function () {
      updatePreviewHint(panel);
    });
    panelRef.current = panel;
    return panel;
  }

  function renderAllPanels() {
    mountedPanels.forEach(function (panel) {
      renderAll(panel);
    });
  }

  function setStatusAll(text, isError) {
    mountedPanels.forEach(function (panel) {
      setStatus(panel, text, isError);
    });
  }

  function setStatus(panelRoot, text, isError) {
    if (!panelRoot) return;
    var el = panelRoot.querySelector("[data-roster-status]");
    el.textContent = text || "";
    el.style.color = isError ? "#f87171" : "var(--muted,#94a3b8)";
  }

  function renderRegionLine(panelRoot) {
    if (!panelRoot) return;
    var el = panelRoot.querySelector("[data-roster-region]");
    if (!state.regionId) {
      el.textContent =
        "No county region selected. Choose Galveston or Harris to manage the opt-in phone list (drawn boxes do not get a roster id).";
      return;
    }
    el.textContent = "Region: " + state.regionId;
  }

  function renderEmptyLine(panelRoot) {
    if (!panelRoot) return;
    var el = panelRoot.querySelector("[data-roster-empty]");
    if (!state.regionId) {
      el.textContent = "";
      return;
    }
    if (state.loading) {
      el.textContent = "Loading roster…";
      return;
    }
    if (!state.contacts.length) {
      el.textContent = EMPTY_COPY;
      return;
    }
    var total = state.contacts.length;
    var shown = Math.min(total, DISPLAY_CAP);
    el.textContent =
      total + " contact" + (total === 1 ? "" : "s") + " on file" + (total > DISPLAY_CAP ? " (showing first " + shown + ")" : "");
  }

  function renderList(panelRoot) {
    if (!panelRoot) return;
    var list = panelRoot.querySelector("[data-roster-list]");
    list.innerHTML = "";
    if (!state.regionId) return;

    var slice = state.contacts.slice(0, DISPLAY_CAP);
    slice.forEach(function (contact) {
      var li = document.createElement("li");
      li.style.cssText =
        "display:flex;justify-content:space-between;gap:8px;align-items:center;" +
        "padding:6px 0;border-bottom:1px solid rgba(148,163,184,0.15);";
      var label = contact.label ? " · " + escapeHtml(contact.label) : "";
      li.innerHTML =
        '<span><code style="font-size:12px;">' +
        escapeHtml(contact.phone) +
        "</code>" +
        label +
        "</span>" +
        '<button type="button" data-id="' +
        escapeHtml(contact.id) +
        '" style="padding:2px 8px;font-size:12px;border-radius:4px;border:0;background:#475569;color:#fff;cursor:pointer;">Remove</button>';
      li.querySelector("button").addEventListener("click", function () {
        deleteContact(panelRoot, contact.id);
      });
      list.appendChild(li);
    });
  }

  function renderAll(panelRoot) {
    renderRegionLine(panelRoot);
    renderEmptyLine(panelRoot);
    renderList(panelRoot);
  }

  function updatePreviewHint(panelRoot) {
    if (!panelRoot || !state.regionId) return;
    var text = panelRoot.querySelector("[data-roster-paste]").value;
    if (!text.trim()) return;
    var rows = parseCsvText(text);
    if (rows.length) {
      setStatus(panelRoot, "Preview: " + rows.length + " row(s) ready to upload.");
    }
  }

  function readPayloadText(panelRoot) {
    var text = panelRoot.querySelector("[data-roster-paste]").value.trim();
    if (text) return text;
    return null;
  }

  function onFileSelected(panelRoot, ev) {
    var file = ev.target.files && ev.target.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () {
      panelRoot.querySelector("[data-roster-paste]").value = String(reader.result || "");
      updatePreviewHint(panelRoot);
    };
    reader.readAsText(file);
    ev.target.value = "";
  }

  function apiUrl(path) {
    return path;
  }

  function loadRegion(regionId) {
    state.regionId = regionId;
    state.error = null;
    renderAllPanels();
    if (!regionId) {
      state.contacts = [];
      renderAllPanels();
      return Promise.resolve();
    }
    state.loading = true;
    renderAllPanels();
    return fetch(apiUrl("/api/roster/" + encodeURIComponent(regionId)))
      .then(function (res) {
        return res.json().then(function (body) {
          if (!res.ok || !body.ok) {
            throw new Error((body && body.error) || "HTTP " + res.status);
          }
          return body;
        });
      })
      .then(function (body) {
        state.contacts = Array.isArray(body.contacts) ? body.contacts : [];
        state.loading = false;
        if (body.empty || !state.contacts.length) {
          setStatusAll(EMPTY_COPY);
        } else {
          setStatusAll("");
        }
        renderAllPanels();
      })
      .catch(function (err) {
        state.loading = false;
        state.contacts = [];
        setStatusAll(err && err.message ? err.message : "Could not load roster.", true);
        renderAllPanels();
      });
  }

  function refreshList() {
    var rid = resolveRegionId();
    return loadRegion(rid);
  }

  function uploadCsv(panelRoot, mode) {
    if (!state.regionId) {
      setStatusAll("Select Galveston or Harris before uploading.", true);
      return;
    }
    var text = readPayloadText(panelRoot);
    var rows = text ? parseCsvText(text) : [];
    if (!rows.length) {
      setStatus(panelRoot, "Add pasted CSV/text or choose a file first.", true);
      return;
    }
    var path =
      mode === "replace"
        ? "/api/roster/" + encodeURIComponent(state.regionId)
        : "/api/roster/" + encodeURIComponent(state.regionId) + "/import";
    var method = mode === "replace" ? "PUT" : "POST";
    setStatusAll("Uploading…");
    fetch(apiUrl(path), {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csv: text }),
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { res: res, body: body };
        });
      })
      .then(function (result) {
        var body = result.body;
        if (!result.res.ok || !body.ok) {
          throw new Error((body && body.error) || "HTTP " + result.res.status);
        }
        state.contacts = Array.isArray(body.contacts) ? body.contacts : [];
        mountedPanels.forEach(function (panel) {
          var paste = panel.querySelector("[data-roster-paste]");
          if (paste) paste.value = "";
        });
        setStatusAll(
          (mode === "replace" ? "List replaced" : "Imported") +
            " — " +
            state.contacts.length +
            " contact(s)."
        );
        renderAllPanels();
      })
      .catch(function (err) {
        setStatusAll(err && err.message ? err.message : "Upload failed.", true);
      });
  }

  function deleteContact(panelRoot, contactId) {
    if (!state.regionId || !contactId) return;
    setStatusAll("Removing…");
    fetch(
      apiUrl(
        "/api/roster/" +
          encodeURIComponent(state.regionId) +
          "/contacts/" +
          encodeURIComponent(contactId)
      ),
      { method: "DELETE" }
    )
      .then(function (res) {
        return res.json().then(function (body) {
          return { res: res, body: body };
        });
      })
      .then(function (result) {
        var body = result.body;
        if (!result.res.ok || !body.ok) {
          throw new Error((body && body.error) || "HTTP " + result.res.status);
        }
        state.contacts = Array.isArray(body.contacts) ? body.contacts : [];
        if (!state.contacts.length) {
          setStatusAll(EMPTY_COPY);
        } else {
          setStatusAll("Contact removed.");
        }
        renderAllPanels();
      })
      .catch(function (err) {
        setStatusAll(err && err.message ? err.message : "Delete failed.", true);
      });
  }

  function onRegionEvent(ev) {
    var rid = regionFromDetail(ev && ev.detail) || resolveRegionId();
    loadRegion(rid);
  }

  var regionListenerBound = false;

  function attach(container) {
    if (!container) return;
    var panelRef = { current: null };
    buildShell(container, panelRef);
    if (panelRef.current) mountedPanels.push(panelRef.current);
    if (!regionListenerBound) {
      window.addEventListener("safety:region", onRegionEvent);
      regionListenerBound = true;
    }
    renderAll(panelRef.current);
    if (mountedPanels.length === 1) {
      refreshList();
    } else {
      renderAllPanels();
    }
  }

  window.SafetyRoster = {
    attach: attach,
    parseCsvText: parseCsvText,
    resolveRegionId: resolveRegionId,
    EMPTY_COPY: EMPTY_COPY,
  };

  ["oem-watch", "region-picker"].forEach(function (id) {
    var host = document.getElementById(id);
    if (!host) return;
    if (host.querySelector("[data-safety-roster-root]")) return;
    var mount = document.createElement("div");
    mount.setAttribute("data-safety-roster-root", "1");
    host.appendChild(mount);
    attach(mount);
  });
})();
