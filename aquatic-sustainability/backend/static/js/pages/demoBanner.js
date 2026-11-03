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
      // In flow (body is a flex column on this page) so it pushes the sticky
      // header and map down instead of painting over the brand and nav.
      "position:relative;flex:0 0 auto;width:100%;z-index:50;" +
      "margin:0;padding:6px 12px;" +
      "font:12px/1.35 system-ui,-apple-system,sans-serif;" +
      "text-align:center;color:#fef3c7;" +
      "background:#78350f;border-bottom:1px solid rgba(255,255,255,.15);" +
      "box-sizing:border-box;";
    document.body.prepend(bar);
  }

  window.DemoBanner = { mount: mount };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
