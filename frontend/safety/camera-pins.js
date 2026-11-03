/* Camera pins for whatever cameras.inBbox returned with the region. */
(function () {
  let layer = null;

  function style(active) {
    return {
      radius: 8,
      color: active ? "#fb923c" : "#0f172a",
      weight: 2,
      fillColor: active ? "#fb923c" : "#38bdf8",
      fillOpacity: 0.95,
      className: "camera-pin",
    };
  }

  function draw(cameras) {
    if (!window.SafetyMap || !window.L) return;
    const map = SafetyMap.getMap();
    if (layer) map.removeLayer(layer);
    layer = L.layerGroup();
    cameras.forEach(function (cam) {
      const marker = L.circleMarker([cam.lat, cam.lon], style(false));
      marker.on("click", function (ev) {
        L.DomEvent.stopPropagation(ev);
        layer.eachLayer(function (other) {
          other.setStyle(style(other === marker));
        });
        if (window.SafetyCameras) SafetyCameras.focus(cam);
      });
      marker.bindTooltip(cam.name, { direction: "top" });
      layer.addLayer(marker);
    });
    layer.addTo(map);
  }

  SafetyBus.on("region", function (region) {
    const cameras = region.cameras || [];
    draw(cameras);
    if (window.SafetyCameras) SafetyCameras.render(cameras);
  });

  SafetyBus.on("camera", function (cam) {
    if (!layer) return;
    layer.eachLayer(function (marker) {
      const latlng = marker.getLatLng();
      const hit = Math.abs(latlng.lat - cam.lat) < 1e-6 && Math.abs(latlng.lng - cam.lon) < 1e-6;
      marker.setStyle(style(hit));
    });
  });
})();
