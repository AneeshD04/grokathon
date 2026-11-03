(function demoBanner() {
  const BANNER_ID = "demo-only-banner";
  const TEXT =
    "Demo only. Not a live NWS product. Send alerts does not text anyone or submit WEA.";

  function mount() {
    if (document.getElementById(BANNER_ID)) return;
    const bar = document.createElement("div");
    bar.id = BANNER_ID;
    bar.setAttribute("role", "status");
    bar.textContent = TEXT;
    bar.style.cssText =
      "position:fixed;top:0;left:0;right:0;z-index:10000;" +
      "margin:0;padding:6px 12px;" +
      "font:12px/1.35 system-ui,-apple-system,sans-serif;" +
      "text-align:center;color:#fef3c7;" +
      "background:#78350f;border-bottom:1px solid rgba(255,255,255,.15);" +
      "box-sizing:border-box;pointer-events:none;";
    document.body.prepend(bar);
  }

  window.DemoBanner = { mount: mount };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
