(function recenterGalveston() {
  var LAT = 29.3;
  var LNG = -94.8;
  var ZOOM = 11;
  var POLL_MS = 8000;
  var mounted = false;

  function getMap() {
    return window.__floodMap || window.floodMap || null;
  }

  function recenter() {
    var map = getMap();
    if (!map || typeof map.setCenter !== "function") return;
    map.setCenter({ lat: LAT, lng: LNG });
    if (typeof map.setZoom === "function") map.setZoom(ZOOM);
  }

  function createButton() {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "toggle-btn";
    btn.textContent = "Recenter Galveston";
    btn.addEventListener("click", recenter);
    return btn;
  }

  function mountInto(host) {
    if (mounted || !host) return;
    var wrap = document.createElement("div");
    wrap.className = "recenter-galveston-wrap";
    wrap.style.marginTop = "8px";
    wrap.appendChild(createButton());
    host.appendChild(wrap);
    mounted = true;
  }

  function mountFixed() {
    if (mounted) return;
    var wrap = document.createElement("div");
    wrap.id = "recenter-galveston-fixed";
    wrap.style.cssText =
      "position:fixed;z-index:55;left:12px;bottom:72px;padding:4px;background:rgba(15,23,42,.92);border-radius:8px;border:1px solid rgba(255,255,255,.12);";
    wrap.appendChild(createButton());
    document.body.appendChild(wrap);
    mounted = true;
  }

  function pollOemWatch() {
    if (mounted) return;
    var started = Date.now();
    var timer = setInterval(function () {
      var host = document.getElementById("oem-watch");
      if (host) {
        clearInterval(timer);
        mountInto(host);
        return;
      }
      if (Date.now() - started >= POLL_MS) {
        clearInterval(timer);
        mountFixed();
      }
    }, 200);
  }

  window.RecenterGalveston = {
    mount: function mount(host) {
      if (host) mountInto(host);
      else pollOemWatch();
    },
    recenter: recenter,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      window.RecenterGalveston.mount();
    });
  } else {
    window.RecenterGalveston.mount();
  }
})();
