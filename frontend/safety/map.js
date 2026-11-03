/* World map. Behavior mirrored from aquatic-sustainability Google Maps pages,
   which do not lock the camera to one city:
   - backend/static/pages/flood-drought.html initMap (zoom 4.5, center lat 8 lng 110,
     mapTypeId "terrain", default Map/Satellite control, pan and zoom unrestricted)
   - backend/static/pages/oil-spill.html initMap (zoom 4, center lat 32 lng -80)
   - backend/static/js/mapInit.js (mapTypeId "terrain")
   No Google key is available (GET /api/config/maps-key). Leaflet stands in:
   Map = OSM, Satellite = Esri World Imagery. Drag-pan is on. Draw box, or
   Shift-drag, selects a region anywhere. */
(function () {
  const RECT = {
    color: "#38bdf8",
    weight: 2,
    fillColor: "#38bdf8",
    fillOpacity: 0.22,
  };

  let map;
  let osm;
  let satellite;
  let committed = null;
  let preview = null;
  let alertMarker = null;
  let current = null;
  let drawing = false;
  let drawMode = false;
  let startLatLng = null;

  function normalize(raw) {
    const west = Math.min(raw.west, raw.east);
    const east = Math.max(raw.west, raw.east);
    const south = Math.min(raw.south, raw.north);
    const north = Math.max(raw.south, raw.north);
    return {
      west: west,
      south: south,
      east: east,
      north: north,
      center: { lat: (south + north) / 2, lon: (west + east) / 2 },
      name: raw.name || "Drawn box",
    };
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  }

  function paintReadout(bbox, watch) {
    const hint = document.getElementById("bbox-hint");
    if (hint) hint.hidden = true;
    setText("bbox-name", bbox.name);
    setText("bbox-west", bbox.west.toFixed(4));
    setText("bbox-south", bbox.south.toFixed(4));
    setText("bbox-east", bbox.east.toFixed(4));
    setText("bbox-north", bbox.north.toFixed(4));
    setText("bbox-center", bbox.center.lat.toFixed(4) + ", " + bbox.center.lon.toFixed(4));
    const arr = watch && Array.isArray(watch.bbox)
      ? watch.bbox
      : [bbox.west, bbox.south, bbox.east, bbox.north];
    setText("bbox-watch", (watch && watch.id ? watch.id : "…") + " · [" + arr.map(function (n) {
      return Number(n).toFixed(4);
    }).join(", ") + "]");
    map.getContainer().dataset.bbox = arr.join(",");
  }

  async function loadRegion(bbox) {
    current = { bbox: bbox, watch: null };
    paintReadout(bbox, null);
    const pack = await Promise.all([
      SafetyAPI.watches.create({ bbox: bbox }),
      SafetyAPI.cameras.inBbox(bbox),
      SafetyAPI.floodRisk(bbox.center.lat, bbox.center.lon),
      SafetyAPI.news(),
      SafetyAPI.routes.impact(bbox),
    ].map(function (p) {
      return p.catch(function (err) { return { error: String(err && err.message || err) }; });
    }));
    const region = {
      bbox: bbox,
      watch: pack[0],
      cameras: Array.isArray(pack[1]) ? pack[1] : [],
      flood: pack[2],
      news: pack[3],
      impact: pack[4],
    };
    current.watch = region.watch;
    paintReadout(bbox, region.watch && region.watch.id ? region.watch : null);
    SafetyBus.emit("region", region);
  }

  function replaceShape(layer) {
    if (preview) {
      map.removeLayer(preview);
      preview = null;
    }
    if (committed) map.removeLayer(committed);
    committed = layer.addTo(map);
  }

  function setBasemap(name) {
    const useSat = name === "satellite";
    if (useSat) {
      if (map.hasLayer(osm)) map.removeLayer(osm);
      if (!map.hasLayer(satellite)) satellite.addTo(map);
    } else {
      if (map.hasLayer(satellite)) map.removeLayer(satellite);
      if (!map.hasLayer(osm)) osm.addTo(map);
    }
    map.getContainer().dataset.basemap = useSat ? "satellite" : "map";
    document.getElementById("basemap-map").classList.toggle("is-active", !useSat);
    document.getElementById("basemap-satellite").classList.toggle("is-active", useSat);
    document.getElementById("basemap-map").setAttribute("aria-pressed", String(!useSat));
    document.getElementById("basemap-satellite").setAttribute("aria-pressed", String(useSat));
  }

  function setDrawMode(on) {
    drawMode = on;
    map.getContainer().classList.toggle("is-drawing", on);
    if (on) map.dragging.disable();
    else map.dragging.enable();
    const button = document.getElementById("draw-box");
    button.classList.toggle("is-active", on);
    button.setAttribute("aria-pressed", String(on));
  }

  function ignoredTarget(target) {
    return Boolean(target.closest(".leaflet-control, .leaflet-marker-icon, .leaflet-popup, .camera-pin"));
  }

  function onDown(ev) {
    const armed = drawMode || ev.shiftKey;
    if (!armed || ev.button !== 0 || ignoredTarget(ev.target)) return;
    ev.stopPropagation();
    ev.preventDefault();
    map.dragging.disable();
    drawing = true;
    startLatLng = map.mouseEventToLatLng(ev);
    preview = L.rectangle(L.latLngBounds(startLatLng, startLatLng), RECT).addTo(map);
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  function onMove(ev) {
    if (!drawing || !preview) return;
    preview.setBounds(L.latLngBounds(startLatLng, map.mouseEventToLatLng(ev)));
  }

  function onUp(ev) {
    if (!drawing) return;
    drawing = false;
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    if (!drawMode) map.dragging.enable();
    const cur = map.mouseEventToLatLng(ev);
    const moved = map.latLngToContainerPoint(startLatLng).distanceTo(map.latLngToContainerPoint(cur));
    if (!preview || moved < 8) {
      if (preview) map.removeLayer(preview);
      preview = null;
      return;
    }
    if (committed) map.removeLayer(committed);
    committed = preview;
    preview = null;
    const bounds = committed.getBounds();
    loadRegion(normalize({
      west: bounds.getWest(),
      south: bounds.getSouth(),
      east: bounds.getEast(),
      north: bounds.getNorth(),
      name: "Drawn box",
    }));
  }

  function useCounty() {
    const county = SafetyCounties.galveston;
    const b = county.bbox;
    const bounds = L.latLngBounds([b.south, b.west], [b.north, b.east]);
    replaceShape(L.rectangle(bounds, RECT));
    map.fitBounds(bounds, { paddingTopLeft: [280, 24], paddingBottomRight: [380, 24], maxZoom: 9 });
    loadRegion(normalize({
      west: b.west,
      south: b.south,
      east: b.east,
      north: b.north,
      name: county.name,
    }));
  }

  function init() {
    if (!window.L) {
      document.getElementById("bbox-readout").textContent = "Map library failed to load.";
      return;
    }
    map = L.map("map", {
      dragging: true,
      boxZoom: false,
      worldCopyJump: true,
      minZoom: 2,
      zoomControl: false,
    }).setView([26.5, -90], 4);

    L.control.zoom({ position: "bottomleft" }).addTo(map);
    osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap",
    });
    satellite = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 19, attribution: "Tiles &copy; Esri" }
    );
    osm.addTo(map);
    map.getContainer().dataset.basemap = "map";
    map.getContainer().addEventListener("mousedown", onDown, true);
    document.getElementById("basemap-map").addEventListener("click", function () { setBasemap("map"); });
    document.getElementById("basemap-satellite").addEventListener("click", function () { setBasemap("satellite"); });
    document.getElementById("draw-box").addEventListener("click", function () { setDrawMode(!drawMode); });
    document.getElementById("galveston-preset").addEventListener("click", useCounty);

    window.SafetyMap = {
      setBasemap: setBasemap,
      setDrawMode: setDrawMode,
      getBbox: function () { return current && current.bbox; },
      getWatch: function () { return current && current.watch; },
      getMap: function () { return map; },
      flyTo: function (lat, lon) {
        map.flyTo([lat, lon], Math.max(map.getZoom(), 6), { duration: 0.7 });
        if (alertMarker) map.removeLayer(alertMarker);
        alertMarker = L.circleMarker([lat, lon], {
          radius: 11,
          color: "#fb923c",
          weight: 2,
          fillColor: "#fb923c",
          fillOpacity: 0.9,
        }).addTo(map);
        map.once("moveend", function () {
          map.getContainer().dataset.center = Number(lat).toFixed(4) + "," + Number(lon).toFixed(4);
        });
      },
    };
  }

  init();
})();
