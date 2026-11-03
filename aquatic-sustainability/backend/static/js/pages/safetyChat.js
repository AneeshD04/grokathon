(function safetyChat() {
  var CHAT_URL = "/api/safety/chat";
  var RETRY_MS = 250;
  var RETRY_BUDGET_MS = 8000;

  function ensureStyles() {
    if (document.getElementById("safety-chat-styles")) return;
    var style = document.createElement("style");
    style.id = "safety-chat-styles";
    style.textContent =
      ".safety-chat{margin-top:12px;padding-top:12px;border-top:1px solid var(--border,rgba(148,163,184,0.35))}" +
      ".safety-chat h4{margin:0 0 4px;font-size:14px;font-weight:600}" +
      ".safety-chat .safety-chat-hint{margin:0 0 8px;font-size:12px;color:var(--muted,#94a3b8)}" +
      ".safety-chat-log{max-height:220px;overflow-y:auto;padding:8px;border-radius:8px;" +
      "background:rgba(15,23,42,0.35);border:1px solid rgba(148,163,184,0.2);margin-bottom:8px}" +
      ".safety-chat-msg{margin:0 0 8px;font-size:13px;line-height:1.45;white-space:pre-wrap;word-break:break-word}" +
      ".safety-chat-msg:last-child{margin-bottom:0}" +
      ".safety-chat-msg--user{color:var(--accent,#38bdf8)}" +
      ".safety-chat-msg--officer{color:var(--text,#e2e8f0)}" +
      ".safety-chat-msg--system{color:var(--muted,#94a3b8);font-size:12px;font-style:italic}" +
      ".safety-chat-form{display:flex;gap:8px;align-items:flex-end}" +
      ".safety-chat-form textarea{flex:1;min-height:52px;max-height:120px;resize:vertical;" +
      "padding:8px;border-radius:8px;border:1px solid rgba(148,163,184,0.35);background:rgba(15,23,42,0.5);color:inherit;font:inherit}" +
      ".safety-chat-form button{flex-shrink:0;padding:8px 14px;border-radius:8px;border:0;" +
      "background:var(--accent,#0ea5e9);color:#0f172a;font-weight:600;cursor:pointer}" +
      ".safety-chat-form button:disabled{opacity:0.55;cursor:not-allowed}";
    document.head.appendChild(style);
  }

  function currentBbox() {
    var sr = window.SafetyRegion;
    if (!sr) return null;
    var box = typeof sr.getBbox === "function" ? sr.getBbox() : sr.bbox;
    if (!box || typeof box !== "object") return null;
    var minLon = Number(box.minLon);
    var minLat = Number(box.minLat);
    var maxLon = Number(box.maxLon);
    var maxLat = Number(box.maxLat);
    if (![minLon, minLat, maxLon, maxLat].every(Number.isFinite)) return null;
    return { minLon: minLon, minLat: minLat, maxLon: maxLon, maxLat: maxLat };
  }

  function regionLabel() {
    var sr = window.SafetyRegion;
    if (!sr) return "the map viewport";
    if (sr.county && typeof sr.county === "object" && sr.county.name) return sr.county.name;
    if (typeof sr.county === "string" && sr.county.trim()) return sr.county.trim();
    if (sr.watch && sr.watch.geofence_id) return sr.watch.geofence_id;
    return "the selected watch area";
  }

  function bboxSummary(bbox) {
    if (!bbox) return "No geofence bbox is published yet — set Galveston/Harris or draw a box on the map.";
    return (
      "Active bbox: west " +
      bbox.minLon.toFixed(3) +
      ", south " +
      bbox.minLat.toFixed(3) +
      ", east " +
      bbox.maxLon.toFixed(3) +
      ", north " +
      bbox.maxLat.toFixed(3) +
      "."
    );
  }

  function replyFromPayload(data) {
    if (!data || typeof data !== "object") return "";
    if (typeof data.reply === "string" && data.reply.trim()) return data.reply.trim();
    if (typeof data.message === "string" && data.message.trim()) return data.message.trim();
    if (typeof data.content === "string" && data.content.trim()) return data.content.trim();
    return "";
  }

  function offlineOfficerReply(userText) {
    var bbox = currentBbox();
    var area = regionLabel();
    var lines = [
      "County OEM incident officer (local demo — not 911, not NWS, and no SMS was sent).",
      "The Safety Agent chat proxy is not connected from this browser session, so I cannot run Grok tools or pull live bus data.",
      bboxSummary(bbox),
      "For " + area + ", treat your note as situational awareness only until the proxy responds.",
    ];
    if (userText && userText.trim()) {
      lines.push('You wrote: "' + userText.trim().replace(/"/g, "'") + '".');
    }
    lines.push("Next step on your side: confirm watches/alerts on the map feed, then use the notify flow only after human PIN approval — nothing auto-sends.");
    return lines.join("\n\n");
  }

  function attach(container) {
    if (!container || container.nodeType !== 1) return;
    ensureStyles();
    if (container.querySelector("[data-safety-chat-panel]")) return;

    var root = document.createElement("div");
    root.className = "safety-chat";
    root.setAttribute("data-safety-chat-panel", "1");
    root.innerHTML =
      "<h4>Safety Agent chat</h4>" +
      '<p class="safety-chat-hint">County OEM console — drafts and tools only. Never claims 911 or outbound SMS.</p>' +
      '<div class="safety-chat-log" data-safety-chat-log aria-live="polite"></div>' +
      '<form class="safety-chat-form" data-safety-chat-form>' +
      '<textarea data-safety-chat-input rows="2" placeholder="Ask about flood risk, cameras, or alerts in the watch…" aria-label="Safety Agent message"></textarea>' +
      '<button type="submit" data-safety-chat-send>Send</button>' +
      "</form>";

    container.appendChild(root);

    var logEl = root.querySelector("[data-safety-chat-log]");
    var formEl = root.querySelector("[data-safety-chat-form]");
    var inputEl = root.querySelector("[data-safety-chat-input]");
    var sendBtn = root.querySelector("[data-safety-chat-send]");
    var busy = false;

    function scrollLog() {
      logEl.scrollTop = logEl.scrollHeight;
    }

    function appendMessage(role, text) {
      var p = document.createElement("p");
      p.className = "safety-chat-msg safety-chat-msg--" + role;
      p.textContent = text;
      logEl.appendChild(p);
      scrollLog();
    }

    appendMessage(
      "system",
      "Type a question about the watch. Messages POST to " + CHAT_URL + " with the current SafetyRegion bbox."
    );

    function setBusy(on) {
      busy = on;
      sendBtn.disabled = on;
      inputEl.disabled = on;
    }

    function sendUserText(text) {
      var trimmed = String(text || "").trim();
      if (!trimmed || busy) return;
      appendMessage("user", trimmed);
      inputEl.value = "";
      setBusy(true);

      var payload = { text: trimmed, bbox: currentBbox() };

      fetch(CHAT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      })
        .then(function (response) {
          return response
            .json()
            .catch(function () {
              return {};
            })
            .then(function (data) {
              if (response.ok) {
                var reply = replyFromPayload(data);
                appendMessage(
                  "officer",
                  reply ||
                    "The chat proxy responded but returned no reply text. Try again or check the server log."
                );
                return;
              }
              appendMessage("officer", offlineOfficerReply(trimmed));
            });
        })
        .catch(function () {
          appendMessage("officer", offlineOfficerReply(trimmed));
        })
        .finally(function () {
          setBusy(false);
          inputEl.focus();
        });
    }

    formEl.addEventListener("submit", function (ev) {
      ev.preventDefault();
      sendUserText(inputEl.value);
    });

    inputEl.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        sendUserText(inputEl.value);
      }
    });
  }

  function mountWhenReady() {
    var elapsed = 0;

    function attempt() {
      var host = document.getElementById("oem-watch");
      if (host && !host.querySelector("[data-safety-chat-root]")) {
        var mount = document.createElement("div");
        mount.setAttribute("data-safety-chat-root", "1");
        host.appendChild(mount);
        attach(mount);
        return;
      }
      elapsed += RETRY_MS;
      if (elapsed < RETRY_BUDGET_MS) {
        window.setTimeout(attempt, RETRY_MS);
      }
    }

    attempt();
  }

  window.SafetyChat = {
    attach: attach,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountWhenReady);
  } else {
    mountWhenReady();
  }
})();
