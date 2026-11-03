/* Business pins. Diamonds, not the camera circle markers from #15.
   Phone is text only. No tel: link. */
(function () {
  let layer = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function icon() {
    return L.divIcon({
      className: "business-pin",
      html: "<span class='business-pin-shape' aria-hidden='true'></span>",
      iconSize: [18, 18],
      iconAnchor: [9, 9],
      popupAnchor: [0, -12],
    });
  }

  function popupHtml(biz) {
    const types = (biz.types || []).join(", ") || "business";
    const phone = biz.phone ? escapeHtml(biz.phone) : "no phone on file";
    const website = biz.website
      ? "<a href='" + escapeHtml(biz.website) + "' target='_blank' rel='noopener noreferrer'>website</a>"
      : "no website on file";
    const maps = biz.maps_url
      ? "<a href='" + escapeHtml(biz.maps_url) + "' target='_blank' rel='noopener noreferrer'>map</a>"
      : "";
    return (
      "<strong>" + escapeHtml(biz.name) + "</strong>" +
      "<div class='biz-popup-types'>" + escapeHtml(types) + "</div>" +
      "<div>Phone (display only): " + phone + "</div>" +
      "<div>" + website + (maps ? " · " + maps : "") + "</div>" +
      "<div class='biz-popup-note'>Not a dial list. This number is not texted or called.</div>"
    );
  }

  function draw(map, businesses) {
    if (layer) map.removeLayer(layer);
    layer = L.layerGroup();
    businesses.forEach(function (biz) {
      if (typeof biz.lat !== "number" || typeof biz.lon !== "number") return;
      const marker = L.marker([biz.lat, biz.lon], { icon: icon(), keyboard: true, title: biz.name });
      marker.bindPopup(popupHtml(biz));
      marker.on("click", function (ev) {
        L.DomEvent.stopPropagation(ev);
      });
      layer.addLayer(marker);
    });
    layer.addTo(map);
  }

  window.SafetyBusinessPins = {
    draw: draw,
  };
})();
