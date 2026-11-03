(function copyDraft() {
  var ROOT_ATTR = "data-copy-draft-root";
  var POLL_MS = 8000;
  var MAX_TRIES = 40;

  var FALLBACK =
    "Demo only. Galveston coastal surge and ship-channel oil release. Not a live NWS product. Nothing was sent.";

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function isVisible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    var style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
      return false;
    }
    var rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function nodeText(el) {
    if (!el) return "";
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      return String(el.value || "").trim();
    }
    return String(el.textContent || "").trim();
  }

  function matchesDraftHint(text) {
    var lower = text.toLowerCase();
    return lower.indexOf("severity") !== -1 || lower.indexOf("galveston") !== -1;
  }

  function findVisibleDraftText() {
    var draftEl = document.getElementById("notifyDraftText");
    if (draftEl && isVisible(draftEl)) {
      var fromModal = nodeText(draftEl);
      if (fromModal) return fromModal;
    }

    var textareas = document.querySelectorAll("textarea");
    for (var i = 0; i < textareas.length; i += 1) {
      var ta = textareas[i];
      if (!isVisible(ta)) continue;
      var taVal = nodeText(ta);
      if (taVal) return taVal;
    }

    var nodes = document.querySelectorAll("div, p, span, pre, li, td, .value");
    for (var j = 0; j < nodes.length; j += 1) {
      var node = nodes[j];
      if (!isVisible(node)) continue;
      var text = nodeText(node);
      if (text.length < 12) continue;
      if (matchesDraftHint(text)) return text;
    }

    return FALLBACK;
  }

  function hiddenTextareaFallback(text) {
    var ta = document.getElementById("copy-draft-hidden-fallback");
    if (!ta) {
      ta = document.createElement("textarea");
      ta.id = "copy-draft-hidden-fallback";
      ta.setAttribute("aria-hidden", "true");
      ta.setAttribute("readonly", "readonly");
      ta.tabIndex = -1;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      ta.style.top = "0";
      ta.style.width = "1px";
      ta.style.height = "1px";
      document.body.appendChild(ta);
    }
    ta.value = text;
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, text.length);
    try {
      document.execCommand("copy");
    } catch (err) {
      // clipboard API or user gesture may be required
    }
  }

  function copyDraftText() {
    var text = findVisibleDraftText();
    hiddenTextareaFallback(text);
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      navigator.clipboard.writeText(text).catch(function () {
        hiddenTextareaFallback(text);
      });
    }
    return text;
  }

  function ensureStyles() {
    if (document.getElementById("copy-draft-styles")) return;
    var style = document.createElement("style");
    style.id = "copy-draft-styles";
    style.textContent =
      "#oem-watch .copy-draft-wrap{margin-top:10px;padding-top:10px;border-top:1px solid var(--border)}" +
      "#oem-watch .copy-draft-btn{width:100%}" +
      "#oem-watch .copy-draft-status{margin:6px 0 0;font-size:12px;color:var(--muted);min-height:1.2em}";
    document.head.appendChild(style);
  }

  function renderControl(host) {
    if (!host || host.querySelector("[" + ROOT_ATTR + "]")) return;

    ensureStyles();

    var root = document.createElement("div");
    root.className = "copy-draft-wrap";
    root.setAttribute(ROOT_ATTR, "1");

    root.innerHTML =
      '<button type="button" class="toggle-btn copy-draft-btn" id="copyDraftBtn">Copy draft</button>' +
      '<p class="copy-draft-status" id="copyDraftStatus" aria-live="polite"></p>';

    host.appendChild(root);

    var btn = root.querySelector("#copyDraftBtn");
    var status = root.querySelector("#copyDraftStatus");
    if (btn) {
      btn.addEventListener("click", function () {
        var copied = copyDraftText();
        if (status) {
          status.textContent =
            "Copied " +
            copied.length +
            " character" +
            (copied.length === 1 ? "" : "s") +
            " (demo — nothing sent).";
        }
      });
    }
  }

  function mount(host) {
    var el = host || document.getElementById("oem-watch");
    if (!el) return false;
    renderControl(el);
    return !!el.querySelector("[" + ROOT_ATTR + "]");
  }

  window.CopyDraft = {
    mount: mount,
    findVisibleDraftText: findVisibleDraftText,
    copyDraftText: copyDraftText,
  };

  if (mount()) return;

  var tries = 0;
  var timer = setInterval(function () {
    tries += 1;
    if (mount() || tries >= MAX_TRIES) {
      clearInterval(timer);
    }
  }, POLL_MS);
})();
