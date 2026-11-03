(function safetyRoster() {
  var DISPLAY_CAP = 50;
  var EMPTY_COPY = "no list uploaded — public SMS skipped";
  var ROSTER_API_DOWN = "Roster API is down. No numbers were contacted.";
  var BAD_CSV_COPY =
    "Could not read phone numbers from this CSV. Use a phone/mobile column or one number per line.";
  var PHONE_HEADER = { phone: 1, phones: 1, mobile: 1, cell: 1, number: 1, e164: 1 };
  var LABEL_HEADER = { label: 1, name: 1, contact: 1, resident: 1 };
  var REGION_ID_RE = /^[a-z0-9][a-z0-9.-]{0,63}$/;

  var ERROR_COPY = {
    invalid_phone: "That phone number does not look valid. Use 10 digits, e.g. 713 555 0142.",
    emergency_number: "Emergency numbers like 911 cannot go on the list.",
    invalid_email: "That email address does not look valid.",
    invalid_contacts: "Nothing usable to add. Check the numbers and try again.",
    invalid_region_id: "Pick Galveston or Harris County first.",
    duplicate_phone: "That number is already on the list.",
    contact_not_found: "That contact was already removed. Refresh the list.",
  };
  var loadSeq = 0;

  var state = {
    regionId: null,
    contacts: [],
    loading: false,
    error: null,
    status: null,
    apiDown: false,
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
      '<div style="font-weight:500;margin-bottom:4px;">Add one contact</div>' +
      '<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px;">' +
      '<input type="tel" data-roster-add-phone placeholder="Phone, e.g. 713 555 0142" autocomplete="off" ' +
      'style="flex:1 1 140px;min-width:0;box-sizing:border-box;background:rgba(15,23,42,0.6);color:var(--text,#e2e8f0);' +
      'border:1px solid rgba(148,163,184,0.35);border-radius:6px;padding:6px 8px;" />' +
      '<input type="text" data-roster-add-label placeholder="Name (optional)" autocomplete="off" ' +
      'style="flex:1 1 120px;min-width:0;box-sizing:border-box;background:rgba(15,23,42,0.6);color:var(--text,#e2e8f0);' +
      'border:1px solid rgba(148,163,184,0.35);border-radius:6px;padding:6px 8px;" />' +
      '<button type="button" data-roster-add style="padding:6px 10px;border-radius:6px;border:0;' +
      'background:#2563eb;color:#fff;cursor:pointer;">Add contact</button>' +
      "</div>" +
      '<label style="display:block;color:var(--muted,#94a3b8);margin-bottom:4px;">Or paste CSV or one phone per line (optional label after comma)</label>' +
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
    panel.querySelector("[data-roster-add]").addEventListener("click", function () {
      addContact(panel);
    });
    ["[data-roster-add-phone]", "[data-roster-add-label]"].forEach(function (sel) {
      panel.querySelector(sel).addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") {
          ev.preventDefault();
          addContact(panel);
        }
      });
    });
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
    var enabled = !!state.regionId;
    ["[data-roster-add-phone]", "[data-roster-add-label]", "[data-roster-add]", "[data-roster-import]", "[data-roster-replace]"].forEach(
      function (sel) {
        var node = panelRoot.querySelector(sel);
        if (!node) return;
        node.disabled = !enabled;
        node.style.opacity = enabled ? "" : "0.5";
        node.style.cursor = enabled ? "pointer" : "not-allowed";
      }
    );
    if (!state.regionId) {
      el.textContent =
        "No county region selected. Choose Galveston or Harris to manage the opt-in phone list (drawn boxes do not get a roster id).";
      return;
    }
    var county = window.oemCountyById && window.oemCountyById(state.regionId);
    el.textContent = "Region: " + (county ? county.name : state.regionId);
  }

  // Resolve with the parsed JSON body, or reject with a user-facing message.
  // Network failures and 5xx mean the API is down; 4xx carries a real reason.
  function api(path, options) {
    return fetch(apiUrl(path), options).then(
      function (res) {
        return res.json().then(
          function (body) {
            if (res.ok && body && body.ok) return body;
            var code = body && body.error;
            var err = new Error(
              res.status >= 500 ? ROSTER_API_DOWN : ERROR_COPY[code] || "Request failed (" + res.status + ")."
            );
            err.apiDown = res.status >= 500;
            err.code = code;
            throw err;
          },
          function () {
            var err = new Error(ROSTER_API_DOWN);
            err.apiDown = true;
            throw err;
          }
        );
      },
      function () {
        var err = new Error(ROSTER_API_DOWN);
        err.apiDown = true;
        throw err;
      }
    );
  }

  function addContact(panelRoot) {
    if (!state.regionId) {
      setStatusAll("Select Galveston or Harris before adding a contact.", true);
      return;
    }
    var phoneEl = panelRoot.querySelector("[data-roster-add-phone]");
    var labelEl = panelRoot.querySelector("[data-roster-add-label]");
    var phone = phoneEl.value.trim();
    if (!phone) {
      setStatus(panelRoot, "Enter a phone number first.", true);
      phoneEl.focus();
      return;
    }
    var label = labelEl.value.trim();
    setStatusAll("Adding…");
    api("/api/roster/" + encodeURIComponent(state.regionId) + "/contacts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: phone, label: label || null }),
    })
      .then(function (body) {
        state.contacts = Array.isArray(body.contacts) ? body.contacts : [];
        state.apiDown = false;
        mountedPanels.forEach(function (panel) {
          panel.querySelector("[data-roster-add-phone]").value = "";
          panel.querySelector("[data-roster-add-label]").value = "";
        });
        setStatusAll("Added " + ((body.contact && body.contact.phone) || phone) + ".");
        renderAllPanels();
        phoneEl.focus();
      })
      .catch(function (err) {
        if (err.apiDown) state.apiDown = true;
        setStatusAll(err.message, true);
        renderAllPanels();
      });
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
      return;
    }
    setStatus(panelRoot, BAD_CSV_COPY, true);
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
    var seq = ++loadSeq;
    state.loading = true;
    state.apiDown = false;
    renderAllPanels();
    return api("/api/roster/" + encodeURIComponent(regionId))
      .then(function (body) {
        if (seq !== loadSeq) return;
        state.contacts = Array.isArray(body.contacts) ? body.contacts : [];
        state.loading = false;
        state.apiDown = false;
        setStatusAll(state.contacts.length ? "" : EMPTY_COPY);
        renderAllPanels();
      })
      .catch(function () {
        if (seq !== loadSeq) return;
        state.loading = false;
        state.contacts = [];
        state.apiDown = true;
        setStatusAll(ROSTER_API_DOWN, true);
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
      setStatus(
        panelRoot,
        text ? BAD_CSV_COPY : "Add pasted CSV/text or choose a file first.",
        true
      );
      return;
    }
    var path =
      mode === "replace"
        ? "/api/roster/" + encodeURIComponent(state.regionId)
        : "/api/roster/" + encodeURIComponent(state.regionId) + "/import";
    var method = mode === "replace" ? "PUT" : "POST";
    setStatusAll("Uploading…");
    api(path, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csv: text }),
    })
      .then(function (body) {
        state.contacts = Array.isArray(body.contacts) ? body.contacts : [];
        state.apiDown = false;
        mountedPanels.forEach(function (panel) {
          var paste = panel.querySelector("[data-roster-paste]");
          if (paste) paste.value = "";
        });
        setStatusAll(
          (mode === "replace" ? "List replaced" : "Imported") +
            " - " +
            state.contacts.length +
            " contact(s)."
        );
        renderAllPanels();
      })
      .catch(function (err) {
        if (err.apiDown) state.apiDown = true;
        setStatusAll(err.message, true);
        renderAllPanels();
      });
  }

  function deleteContact(panelRoot, contactId) {
    if (!state.regionId || !contactId) return;
    setStatusAll("Removing…");
    api(
      "/api/roster/" + encodeURIComponent(state.regionId) + "/contacts/" + encodeURIComponent(contactId),
      { method: "DELETE" }
    )
      .then(function (body) {
        state.contacts = Array.isArray(body.contacts) ? body.contacts : [];
        setStatusAll(state.contacts.length ? "Contact removed." : EMPTY_COPY);
        renderAllPanels();
      })
      .catch(function (err) {
        setStatusAll(err.message || "Delete failed.", true);
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

  function publicContacts() {
    if (state.apiDown || state.loading || !state.regionId) return [];
    return state.contacts.slice();
  }

  window.SafetyRoster = {
    attach: attach,
    parseCsvText: parseCsvText,
    resolveRegionId: resolveRegionId,
    EMPTY_COPY: EMPTY_COPY,
    ROSTER_API_DOWN: ROSTER_API_DOWN,
    isApiDown: function () {
      return !!state.apiDown;
    },
    getContacts: publicContacts,
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
