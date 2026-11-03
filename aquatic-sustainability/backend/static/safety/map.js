/* County / bbox picker. Leaflet stands in for the Google map on the flood
   page (no maps key on this route). Map = OSM, Satellite = Esri imagery.
   Galveston County or a dragged rectangle becomes POST /api/watches. */
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
    const arr = watch && Array.isArray(watch.bbox)
      ? watch.bbox
      : [bbox.west, bbox.south, bbox.east, bbox.north];
    const id = watch && watch.id ? watch.id : "…";
    setText("bbox-watch", id + " · [" + arr.map(function (n) {
      return Number(n).toFixed(4);
    }).join(", ") + "]");
    map.getContainer().dataset.bbox = arr.join(",");
  }

  async function loadRegion(bbox) {
    current = { bbox: bbox, watch: null };
    paintReadout(bbox, null);
    const watch = await SafetyAPI.watches.create({ bbox: bbox });
    current.watch = watch;
    paintReadout(bbox, watch);
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

  function onDown(ev) {
    const armed = drawMode || ev.shiftKey;
    if (!armed || ev.button !== 0) return;
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
    map.fitBounds(bounds, { padding: [24, 24], maxZoom: 10 });
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
      setText("bbox-name", "Map library failed to load.");
      return;
    }
    map = L.map("map", {
      dragging: true,
      boxZoom: false,
      worldCopyJump: true,
      minZoom: 2,
      zoomControl: true,
    }).setView([29.3, -94.8], 6);

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
    document.addEventListener("navbar:loaded", function () { map.invalidateSize(); });
    window.addEventListener("resize", function () { map.invalidateSize(); });

    window.SafetyMap = {
      getBbox: function () { return current && current.bbox; },
      getWatch: function () { return current && current.watch; },
      useCounty: useCounty,
    };
  }

  init();
})();
