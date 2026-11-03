(function layerLegend() {
  var ROOT_ATTR = "data-layer-legend-root";

  function row(swatchHtml, label) {
    var item = document.createElement("div");
    item.style.cssText =
      "display:flex;align-items:center;gap:8px;margin:4px 0;color:var(--text);";
    item.innerHTML =
      swatchHtml +
      '<span style="font-size:12px;line-height:1.3;color:var(--muted);">' +
      label +
      "</span>";
    return item;
  }

  function buildLegendEl() {
    var root = document.createElement("div");
    root.setAttribute(ROOT_ATTR, "1");
    root.setAttribute("aria-label", "Map pin legend");
    root.style.cssText =
      "margin-top:8px;padding:8px 10px;background:var(--card-bg);" +
      "border:1px solid var(--border);border-radius:8px;" +
      "--legend-camera:#3b82f6;--legend-business:#c026d3;--legend-alert:#ea580c;";

    var title = document.createElement("div");
    title.textContent = "Map pins";
    title.style.cssText =
      "font-size:11px;font-weight:600;letter-spacing:0.02em;" +
      "text-transform:uppercase;color:var(--muted);margin-bottom:4px;";
    root.appendChild(title);

    var cameraSwatch =
      '<span style="display:inline-block;width:12px;height:12px;border-radius:50%;' +
      "background:var(--legend-camera);border:1px solid var(--border);" +
      'flex-shrink:0;"></span>';
    root.appendChild(row(cameraSwatch, "Camera"));

    var businessSwatch =
      '<span style="display:inline-block;width:10px;height:10px;transform:rotate(45deg);' +
      "background:var(--legend-business);border:1px solid #581c87;" +
      'flex-shrink:0;margin:0 1px;"></span>';
    root.appendChild(row(businessSwatch, "Business"));

    var alertSwatch =
      '<span style="display:inline-block;width:12px;height:12px;border-radius:50%;' +
      "background:var(--legend-alert);border:1px solid #7c2d12;" +
      'flex-shrink:0;"></span>';
    root.appendChild(row(alertSwatch, "Alert"));

    return root;
  }

  function mountInto(host, fixed) {
    if (!host || host.querySelector("[" + ROOT_ATTR + "]")) return;
    var legend = buildLegendEl();
    if (fixed) {
      legend.style.cssText +=
        "position:fixed;top:12px;left:12px;z-index:1000;margin-top:0;" +
        "box-shadow:0 2px 10px color-mix(in srgb, var(--text) 12%, transparent);";
    }
    host.appendChild(legend);
  }

  function mount() {
    var host = document.getElementById("oem-watch");
    if (host) {
      mountInto(host, false);
      return;
    }
    setTimeout(function () {
      if (document.querySelector("[" + ROOT_ATTR + "]")) return;
      var panel = document.getElementById("oem-watch");
      if (panel) {
        mountInto(panel, false);
        return;
      }
      mountInto(document.body, true);
    }, 1000);
  }

  window.LayerLegend = { mount: mount };
})();
