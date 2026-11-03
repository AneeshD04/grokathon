(function demoSteps() {
  var ROOT_ATTR = "data-demo-steps-root";
  var POLL_MS = 200;
  var MAX_TRIES = 40;

  var STEPS = [
    { n: 1, label: "Mark Galveston County" },
    { n: 2, label: "Camera pin" },
    { n: 3, label: "Business pin" },
    { n: 4, label: "Inject demo scenario" },
    { n: 5, label: "Send alerts — dry-run only" },
  ];

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function ensureStyles() {
    if (document.getElementById("demo-steps-styles")) return;
    var style = document.createElement("style");
    style.id = "demo-steps-styles";
    style.textContent =
      "#oem-watch .demo-steps{margin-bottom:10px;padding:10px;border:1px solid var(--border);border-radius:8px;background:rgba(255,255,255,0.03)}" +
      "#oem-watch .demo-steps-kicker{font-size:11px;text-transform:uppercase;letter-spacing:0.04em;color:var(--accent);font-weight:600;margin:0 0 4px}" +
      "#oem-watch .demo-steps-title{margin:0 0 6px;font-size:13px;font-weight:600}" +
      "#oem-watch .demo-steps-disclaimer{margin:0 0 10px;font-size:12px;line-height:1.35;color:var(--muted)}" +
      "#oem-watch .demo-steps-list{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px}" +
      "#oem-watch .demo-steps-item{display:flex;align-items:flex-start;gap:8px;font-size:12px;line-height:1.35}" +
      "#oem-watch .demo-steps-num{flex:0 0 22px;height:22px;border-radius:50%;border:1px solid var(--border);display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--accent)}" +
      "#oem-watch .demo-steps-label{flex:1;padding-top:2px}";
    document.head.appendChild(style);
  }

  function renderStrip(host) {
    if (!host || host.querySelector("[" + ROOT_ATTR + "]")) return;

    ensureStyles();

    var root = document.createElement("div");
    root.className = "demo-steps";
    root.setAttribute(ROOT_ATTR, "1");

    var itemsHtml = STEPS.map(function (step) {
      return (
        '<li class="demo-steps-item">' +
        '<span class="demo-steps-num" aria-hidden="true">' +
        escapeHtml(step.n) +
        "</span>" +
        '<span class="demo-steps-label">' +
        escapeHtml(step.label) +
        "</span>" +
        "</li>"
      );
    }).join("");

    root.innerHTML =
      '<p class="demo-steps-kicker">Judge demo</p>' +
      '<p class="demo-steps-title">5-step Safety Agent walkthrough</p>' +
      '<p class="demo-steps-disclaimer">This panel is a demo script only — not a live Wireless Emergency Alert (WEA) and no real SMS is sent.</p>' +
      '<ol class="demo-steps-list" aria-label="Demo steps">' +
      itemsHtml +
      "</ol>";

    host.insertBefore(root, host.firstChild);
  }

  function mount(host) {
    var el = host || document.getElementById("oem-watch");
    if (!el) return false;
    renderStrip(el);
    return !!el.querySelector("[" + ROOT_ATTR + "]");
  }

  window.DemoSteps = {
    mount: mount,
  };

  var tries = 0;
  var timer = setInterval(function () {
    tries += 1;
    if (mount() || tries >= MAX_TRIES) {
      clearInterval(timer);
    }
  }, POLL_MS);
})();
