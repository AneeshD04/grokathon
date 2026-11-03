(function demoBannerModule() {
  var BANNER_ID = "demo-only-banner";
  var MESSAGE =
    "Demo only. Not a live NWS product. Send alerts does not text anyone or submit WEA.";

  function mount() {
    var existing = document.getElementById(BANNER_ID);
    if (existing) return existing;

    var el = document.createElement("div");
    el.id = BANNER_ID;
    el.setAttribute("role", "status");
    el.textContent = MESSAGE;
    el.style.cssText = [
      "box-sizing:border-box",
      "width:100%",
      "margin:0",
      "padding:8px 12px",
      "font:600 13px/1.4 system-ui,-apple-system,Segoe UI,sans-serif",
      "text-align:center",
      "color:#1f2937",
      "background:#fef3c7",
      "border-bottom:1px solid #f59e0b",
      "position:relative",
      "z-index:10050",
    ].join(";");

    document.body.insertBefore(el, document.body.firstChild);
    return el;
  }

  window.DemoBanner = { mount: mount };

  function shouldMountHere() {
    var path = window.location.pathname.replace(/\/+$/, "") || "/";
    return path === "/flood-drought";
  }

  function maybeAutoMount() {
    if (shouldMountHere()) mount();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", maybeAutoMount);
  } else {
    maybeAutoMount();
  }
})();
