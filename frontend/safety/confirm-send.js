/* Notify impacted businesses. Approval PIN gated dry-run.

   Hackathon default matches DEMO_APPROVAL_PIN in docs/SAFETY-AGENT-DESIGN.md.
   Rotate before any real deployment. Wrong PIN logs nothing.
   POST {NOTIFY_BASE}/api/notify when that sidecar is up.
   HTTP 403 invalid_approval_pin is a reject. If the sidecar is down, the
   same success log stays on the page. This file never calls Twilio. */
(function () {
  const NOTIFY_BASE = "http://127.0.0.1:8001";
  const DEMO_APPROVAL_PIN = "3408";

  const ORGS = [
    "Galveston County Office of Emergency Management",
    "National Weather Service Houston/Galveston",
    "U.S. Coast Guard Sector Houston-Galveston",
    "City of Galveston 311",
  ];

  let businesses = [];
  let lastLog = null;

  function draftText() {
    return (
      "WARNING for Galveston County. DualCNN-LSTM flood model flags elevated flood " +
      "probability on this polygon. NASA GPM precipitation and SMAP soil moisture " +
      "are the model inputs. Numeric probability is not attached until the model " +
      "poller is connected. Evacuate or avoid low roads near the listed businesses. " +
      "This draft is a dry-run. It is not a water-quality lab result, and it was not sent."
    );
  }

  function $(id) {
    return document.getElementById(id);
  }

  function setHidden(id, hidden) {
    const node = $(id);
    if (node) node.hidden = hidden;
  }

  function renderOrgs() {
    const list = $("org-list");
    list.textContent = "";
    ORGS.forEach(function (name) {
      const item = document.createElement("li");
      item.textContent = name;
      list.appendChild(item);
    });
  }

  function renderNames(listId, rows) {
    const list = $(listId);
    list.textContent = "";
    rows.forEach(function (name) {
      const item = document.createElement("li");
      item.textContent = name;
      list.appendChild(item);
    });
  }

  function showError(text) {
    const node = $("pin-error");
    node.hidden = false;
    node.textContent = text;
  }

  function clearError() {
    const node = $("pin-error");
    node.hidden = true;
    node.textContent = "";
  }

  function writeLog(entry) {
    lastLog = entry;
    const panel = $("send-log");
    panel.hidden = false;
    $("log-status").textContent = entry.status;
    $("log-mode").textContent = entry.mode;
    $("log-when").textContent = entry.at;
    $("log-ipaws").textContent = entry.ipaws ? "IPAWS stub checked (not connected, not sent)" : "IPAWS stub not checked";
    $("log-residents").textContent = "no list uploaded — public SMS skipped";
    renderNames("log-businesses", entry.businesses);
    renderNames("log-orgs", ORGS);
  }

  function open(nextBusinesses) {
    businesses = nextBusinesses || [];
    $("draft-message").textContent = draftText();
    $("business-count").textContent = String(businesses.length);
    renderNames(
      "modal-businesses",
      businesses.map(function (biz) { return biz.name; })
    );
    $("resident-line").textContent = "no list uploaded — public SMS skipped";
    $("ipaws-stub").checked = false;
    $("approval-pin").value = "";
    clearError();
    setHidden("confirm-modal", false);
    $("approval-pin").focus();
  }

  function closeWithoutLog() {
    setHidden("confirm-modal", true);
    clearError();
    $("approval-pin").value = "";
  }

  async function submit() {
    const pin = $("approval-pin").value.trim();
    const ipaws = $("ipaws-stub").checked;
    if (pin !== DEMO_APPROVAL_PIN) {
      showError("Approval PIN rejected. Nothing was logged.");
      return;
    }

    const summary = draftText();
    let mode = "dry-run-logged";
    let status = "Logged as sent. No SMS, email, call, or WEA was transmitted.";
    try {
      const res = await fetch(NOTIFY_BASE + "/api/notify", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          geofence: "galveston-county",
          severity: "warning",
          summary: summary,
          approval_pin: pin,
        }),
      });
      if (res.status === 403) {
        showError("Approval PIN rejected. Nothing was logged.");
        return;
      }
      if (!res.ok) throw new Error("notify " + res.status);
      const data = await res.json();
      if (data && data.mode) mode = data.mode;
      status = "Logged as sent. The notify service returned " + mode + ". Nothing was transmitted from this page.";
    } catch (err) {
      mode = "dry-run-logged";
      status = "Logged as sent on this page. The notify service was unreachable. No SMS, email, call, or WEA was transmitted.";
    }

    writeLog({
      status: status,
      mode: mode,
      at: new Date().toISOString(),
      ipaws: ipaws,
      businesses: businesses.map(function (biz) { return biz.name; }),
    });
    setHidden("confirm-modal", true);
    $("approval-pin").value = "";
  }

  function init() {
    renderOrgs();
    $("confirm-cancel").addEventListener("click", closeWithoutLog);
    $("confirm-submit").addEventListener("click", function () {
      submit();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && !$("confirm-modal").hidden) closeWithoutLog();
    });
    window.SafetyConfirmSend = { open: open };
  }

  init();
})();
