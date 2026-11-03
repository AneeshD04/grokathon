(function safetyNotify() {
  const openBtn = document.getElementById("oemSendAlerts");
  const modal = document.getElementById("notifyModal");
  const body = document.getElementById("notifyModalBody");
  const closeBtn = modal ? modal.querySelector(".modal-close") : null;
  if (!openBtn || !modal || !body) return;

  // Hackathon default for DEMO_APPROVAL_PIN. Rotate before any real deployment.
  const DEMO_APPROVAL_PIN = "3408";
  const GEOFENCE_ID = "galveston-county";
  const ORG_ROSTER = [
    { name: "Galveston County Office of Emergency Management", channel: "voice" },
    { name: "National Weather Service Houston/Galveston", channel: "email" },
    { name: "U.S. Coast Guard Sector Houston-Galveston", channel: "voice" },
    { name: "City of Galveston 311", channel: "sms" },
  ];

  function pinsMatch(provided, expected) {
    if (typeof provided !== "string" || typeof expected !== "string") return false;
    if (provided.length !== expected.length) return false;
    let mismatch = 0;
    for (let i = 0; i < expected.length; i += 1) {
      mismatch |= provided.charCodeAt(i) ^ expected.charCodeAt(i);
    }
    return mismatch === 0;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function selectedAlert() {
    if (window.SafetyOem && typeof window.SafetyOem.getSelectedAlert === "function") {
      return window.SafetyOem.getSelectedAlert();
    }
    return null;
  }

  function draftMessage(alert) {
    if (alert && alert.summary) {
      const klass =
        alert.evidence && alert.evidence.raw && alert.evidence.raw.vision_class
          ? " Vision class: " + alert.evidence.raw.vision_class + "."
          : "";
      return (
        "County OEM draft for Galveston County. " +
        alert.summary +
        klass +
        " DualCNN-LSTM flood probability (NASA GPM + SMAP) is the model evidence — not a water-quality lab result. Confirm to log a sandbox fan-out."
      );
    }
    return (
      "County OEM draft for Galveston County. DualCNN-LSTM flood probability from NASA GPM + SMAP is the model evidence. " +
      "Confirm to log a sandbox fan-out to the uploaded public roster and org display list. Nothing is sent."
    );
  }

  function openModal() {
    const alert = selectedAlert();
    const residents = [];
    const businesses = [];
    const publicLine = residents.length
      ? residents.length + " opted-in resident" + (residents.length === 1 ? "" : "s")
      : "no list — public SMS skipped";
    const draft = draftMessage(alert);

    body.innerHTML =
      '<div class="modal-section">' +
      "<h3>Drafted message</h3>" +
      '<div class="modal-info-item"><div class="value" id="notifyDraftText">' +
      escapeHtml(draft) +
      "</div></div>" +
      "</div>" +
      '<div class="modal-section">' +
      "<h3>Intended recipients</h3>" +
      '<div class="modal-info-grid">' +
      '<div class="modal-info-item"><label>Public roster</label><div class="value" id="notifyPublicCount">' +
      escapeHtml(publicLine) +
      "</div></div>" +
      '<div class="modal-info-item"><label>Businesses</label><div class="value">' +
      businesses.length +
      " (Places list is #25)</div></div>" +
      '<div class="modal-info-item"><label>Org display roster</label><div class="value">' +
      ORG_ROSTER.length +
      " would notify</div></div>" +
      "</div>" +
      '<p class="muted" style="margin-top:12px">Would notify: ' +
      escapeHtml(ORG_ROSTER.map(function (org) { return org.name; }).join("; ")) +
      ". Contacts are display-only.</p>" +
      "</div>" +
      '<div class="modal-section">' +
      "<h3>IPAWS / WEA</h3>" +
      '<label class="checkbox"><input type="checkbox" id="notifyIpawsStub"> Would submit this polygon + message to IPAWS-OPEN (WEA). Not connected.</label>' +
      "</div>" +
      '<div class="modal-section">' +
      "<h3>Approval PIN</h3>" +
      '<div class="modal-info-item"><label for="notifyApprovalPin">County OEM confirm</label>' +
      '<input id="notifyApprovalPin" name="approval_pin" type="password" inputmode="numeric" autocomplete="off" maxlength="8">' +
      '<p class="notify-pin-error" id="notifyPinError" hidden></p></div>' +
      "</div>" +
      '<div class="cta-row">' +
      '<button type="button" class="btn" id="notifyConfirmBtn">Confirm notify</button>' +
      '<button type="button" class="btn btn-outline" id="notifyCancelBtn">Cancel</button>' +
      "</div>";

    modal.classList.add("active");
    const pinInput = document.getElementById("notifyApprovalPin");
    if (pinInput) pinInput.focus();
  }

  function closeModal() {
    modal.classList.remove("active");
    body.innerHTML = "";
  }

  function showError(message) {
    const errorEl = document.getElementById("notifyPinError");
    if (!errorEl) return;
    errorEl.hidden = false;
    errorEl.textContent = message;
  }

  function showSuccess(log) {
    const emailNote = log.intended.email.length
      ? "Email intended (logged only — no provider)."
      : "No email recipients on the roster.";
    body.innerHTML =
      '<div class="modal-section">' +
      "<h3>Sandbox result</h3>" +
      '<div class="modal-info-item"><div class="value highlight">Logged as if sent. Nothing was delivered.</div>' +
      '<div class="modal-map-coords">Mode: ' +
      escapeHtml(log.mode) +
      "</div></div>" +
      "</div>" +
      '<div class="modal-section">' +
      "<h3>Intended channels (not sent)</h3>" +
      '<div class="modal-info-grid">' +
      '<div class="modal-info-item"><label>SMS</label><div class="value">' +
      escapeHtml(log.public_sms) +
      "</div></div>" +
      '<div class="modal-info-item"><label>Voice</label><div class="value">' +
      escapeHtml(String(log.intended.voice.length)) +
      " intended</div></div>" +
      '<div class="modal-info-item"><label>Email</label><div class="value">' +
      escapeHtml(emailNote) +
      "</div></div>" +
      "</div>" +
      '<p class="muted" style="margin-top:12px">No SMS, voice, email, Twilio, Grok, or WEA blast went out. The IPAWS stub is not connected.</p>' +
      "</div>" +
      '<div class="cta-row"><button type="button" class="btn" id="notifyDoneBtn">Close</button></div>';
    const done = document.getElementById("notifyDoneBtn");
    if (done) done.addEventListener("click", closeModal);
  }

  function confirmNotify() {
    const pinInput = document.getElementById("notifyApprovalPin");
    const provided = pinInput ? pinInput.value : "";
    if (!pinsMatch(provided, DEMO_APPROVAL_PIN)) {
      showError("PIN rejected. Nothing was logged or sent.");
      if (pinInput) {
        pinInput.value = "";
        pinInput.focus();
      }
      return;
    }

    const alert = selectedAlert();
    const ipaws = Boolean(document.getElementById("notifyIpawsStub") && document.getElementById("notifyIpawsStub").checked);
    const draftEl = document.getElementById("notifyDraftText");
    const log = {
      ts: new Date().toISOString(),
      mode: "dry-run-logged",
      geofence_id: GEOFENCE_ID,
      alert_id: alert && alert.id ? alert.id : null,
      message: draftEl ? draftEl.textContent : draftMessage(alert),
      public_sms: "no list — public SMS skipped",
      businesses: 0,
      residents: 0,
      ipaws_stub: ipaws,
      sent: false,
      twilio: false,
      grok: false,
      intended: {
        sms: ORG_ROSTER.filter(function (org) { return org.channel === "sms"; }).map(function (org) { return org.name; }),
        voice: ORG_ROSTER.filter(function (org) { return org.channel === "voice"; }).map(function (org) { return org.name; }),
        email: ORG_ROSTER.filter(function (org) { return org.channel === "email"; }).map(function (org) { return org.name; }),
      },
    };

    console.info("[safety-notify sandbox] intended SMS/voice/email (not sent)", {
      ts: log.ts,
      mode: log.mode,
      geofence_id: log.geofence_id,
      alert_id: log.alert_id,
      public_sms: log.public_sms,
      ipaws_stub: log.ipaws_stub,
      intended: log.intended,
      sent: false,
    });
    try {
      const prior = JSON.parse(sessionStorage.getItem("safety_notify_log") || "[]");
      prior.push(log);
      sessionStorage.setItem("safety_notify_log", JSON.stringify(prior));
    } catch (err) {
      // ignore quota / private mode
    }
    showSuccess(log);
  }

  openBtn.addEventListener("click", openModal);
  if (closeBtn) closeBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", function (event) {
    if (event.target === modal) closeModal();
  });
  body.addEventListener("click", function (event) {
    const target = event.target;
    if (target && target.id === "notifyConfirmBtn") confirmNotify();
    if (target && target.id === "notifyCancelBtn") closeModal();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && modal.classList.contains("active")) {
      closeModal();
    }
  });
})();
