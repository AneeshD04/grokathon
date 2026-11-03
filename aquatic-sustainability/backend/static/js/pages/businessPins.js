(function businessPinsLayer() {
  if (window.__safetyBusinessPinsLoaded) {
    return;
  }
  window.__safetyBusinessPinsLoaded = true;

  var BUS_URL =
    window.ALERT_BUS_URL ||
    (typeof localStorage !== "undefined" && localStorage.getItem("ALERT_BUS_URL")) ||
    "http://127.0.0.1:8000";
  var NEARBY_LIMIT = 20;

  /** Matches backend/places/fixtures.py when Places is unavailable. */
  var FIXTURE_BUSINESSES = [
    {
      place_id: "fixture-utmb",
      name: "Fixture UTMB Health",
      lat: 29.3106,
      lon: -94.7774,
      phone: null,
      website: null,
      types: ["hospital"],
      maps_url: "https://maps.google.com/?q=place_id:fixture-utmb",
    },
    {
      place_id: "fixture-school",
      name: "Fixture Ball High School",
      lat: 29.2905,
      lon: -94.8094,
      phone: null,
      website: null,
      types: ["school"],
      maps_url: "https://maps.google.com/?q=place_id:fixture-school",
    },
    {
      place_id: "fixture-lodging",
      name: "Fixture Seawall Lodging",
      lat: 29.2722,
      lon: -94.815,
      phone: null,
      website: null,
      types: ["lodging"],
      maps_url: "https://maps.google.com/?q=place_id:fixture-lodging",
    },
  ];

  var map = null;
  var markers = [];
  var activeInfoWindow = null;
  var currentBbox = null;
  var loadToken = 0;

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function bboxFromDetail(detail) {
    if (!detail) return null;
    if (detail.bbox === null) return null;
    if (Array.isArray(detail.bbox) && detail.bbox.length === 4) {
      return detail.bbox.slice();
    }
    if (
      typeof detail.minLon === "number" &&
      typeof detail.minLat === "number" &&
      typeof detail.maxLon === "number" &&
      typeof detail.maxLat === "number"
    ) {
      return [detail.minLon, detail.minLat, detail.maxLon, detail.maxLat];
    }
    return null;
  }

  function bboxFromSafetyRegion() {
    if (!window.SafetyRegion || typeof window.SafetyRegion.getBbox !== "function") {
      return null;
    }
    var box = window.SafetyRegion.getBbox();
    if (!box) return null;
    if (Array.isArray(box) && box.length === 4) return box.slice();
    if (
      typeof box.minLon === "number" &&
      typeof box.minLat === "number" &&
      typeof box.maxLon === "number" &&
      typeof box.maxLat === "number"
    ) {
      return [box.minLon, box.minLat, box.maxLon, box.maxLat];
    }
    return null;
  }

  function filterInsideBbox(businesses, bbox) {
    var minLon = bbox[0];
    var minLat = bbox[1];
    var maxLon = bbox[2];
    var maxLat = bbox[3];
    return businesses.filter(function (row) {
      return (
        row.lon >= minLon &&
        row.lon <= maxLon &&
        row.lat >= minLat &&
        row.lat <= maxLat
      );
    });
  }

  function fixtureFallback(bbox) {
    return {
      businesses: filterInsideBbox(FIXTURE_BUSINESSES, bbox),
      truncated: false,
      source: "fixture",
    };
  }

  function fetchNearby(bbox) {
    var body = JSON.stringify({ bbox: bbox, limit: NEARBY_LIMIT });
    var endpoints = [
      "/api/businesses/nearby",
      String(BUS_URL).replace(/\/$/, "") + "/api/businesses/nearby",
    ];

    function tryNext(i) {
      if (i >= endpoints.length) {
        return Promise.resolve({ payload: fixtureFallback(bbox), fromFixture: true });
      }
      return fetch(endpoints[i], {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body,
      })
        .then(function (res) {
          if (!res.ok) return tryNext(i + 1);
          return res.json().then(function (payload) {
            if (!payload || !Array.isArray(payload.businesses)) {
              return tryNext(i + 1);
            }
            return { payload: payload, fromFixture: payload.source === "fixture" };
          });
        })
        .catch(function () {
          return tryNext(i + 1);
        });
    }

    return tryNext(0);
  }

  function diamondIcon() {
    return {
      path: "M 0,-9 L 9,0 L 0,9 L -9,0 Z",
      fillColor: "#c026d3",
      fillOpacity: 0.95,
      strokeColor: "#581c87",
      strokeWeight: 1.5,
      scale: 1,
    };
  }

  function squareIcon() {
    return {
      path: "M -7,-7 L 7,-7 L 7,7 L -7,7 Z",
      fillColor: "#ea580c",
      fillOpacity: 0.95,
      strokeColor: "#7c2d12",
      strokeWeight: 1.5,
      scale: 1,
    };
  }

  function businessIcon(index) {
    return index % 2 === 0 ? diamondIcon() : squareIcon();
  }

  function infoContent(business) {
    var types =
      business.types && business.types.length
        ? business.types.join(", ")
        : "business";
    var phoneLine = business.phone
      ? escapeHtml(business.phone)
      : "no phone on file";
    var websiteBlock = "";
    if (business.website) {
      var safeUrl = escapeHtml(business.website);
      websiteBlock =
        '<div style="margin-top:6px;font-size:12px;">' +
        '<a href="' +
        safeUrl +
        '" target="_blank" rel="noopener noreferrer">' +
        safeUrl +
        "</a></div>";
    } else {
      websiteBlock =
        '<div style="margin-top:6px;font-size:12px;color:#6b7280;">No website listed</div>';
    }
    return (
      '<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;max-width:260px;padding:2px;">' +
      '<div style="font-size:14px;font-weight:700;color:#111827;margin-bottom:6px;">' +
      escapeHtml(business.name) +
      "</div>" +
      '<div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em;">Impacted business</div>' +
      '<div style="margin-top:8px;font-size:12px;color:#374151;"><strong>Types:</strong> ' +
      escapeHtml(types) +
      "</div>" +
      websiteBlock +
      '<div style="margin-top:6px;font-size:12px;color:#374151;"><strong>Phone:</strong> ' +
      phoneLine +
      "</div>" +
      '<div style="margin-top:8px;font-size:10px;color:#9ca3af;">Display only — demo does not dial.</div>' +
      "</div>"
    );
  }

  function clearMarkers() {
    markers.forEach(function (marker) {
      marker.setMap(null);
    });
    markers = [];
    if (activeInfoWindow) {
      activeInfoWindow.close();
      activeInfoWindow = null;
    }
  }

  function drawBusinesses(businesses) {
    if (!map || !window.google || !google.maps) return;
    clearMarkers();
    businesses.forEach(function (business, index) {
      var marker = new google.maps.Marker({
        map: map,
        position: { lat: business.lat, lng: business.lon },
        title: business.name,
        icon: businessIcon(index),
        zIndex: google.maps.Marker.MAX_ZINDEX + 10,
      });
      marker.addListener("click", function () {
        if (activeInfoWindow) activeInfoWindow.close();
        activeInfoWindow = new google.maps.InfoWindow({
          content: infoContent(business),
        });
        activeInfoWindow.open({ map: map, anchor: marker });
      });
      markers.push(marker);
    });
  }

  function redraw() {
    if (!map || !currentBbox) {
      clearMarkers();
      return;
    }
    var token = ++loadToken;
    fetchNearby(currentBbox).then(function (result) {
      if (token !== loadToken) return;
      drawBusinesses(result.payload.businesses || []);
    });
  }

  function onRegionEvent(event) {
    var bbox = bboxFromDetail(event && event.detail);
    if (bbox === null && event && event.detail && event.detail.bbox === null) {
      currentBbox = null;
      clearMarkers();
      return;
    }
    if (!bbox) return;
    currentBbox = bbox;
    redraw();
  }

  function attach(nextMap) {
    if (!nextMap) return;
    map = nextMap;
    if (!currentBbox) {
      currentBbox = bboxFromSafetyRegion();
    }
    redraw();
  }

  window.SafetyBusinessPins = {
    attach: attach,
    redraw: redraw,
    filterInsideBbox: filterInsideBbox,
    fixtureFallback: fixtureFallback,
    FIXTURE_BUSINESSES: FIXTURE_BUSINESSES,
  };

  window.addEventListener("safety:region", onRegionEvent);

  function bootstrap() {
    var existing = window.floodMap || window.__floodMap;
    if (existing) {
      attach(existing);
      return;
    }
    window.addEventListener(
      "flood-map-ready",
      function (event) {
        if (event.detail && event.detail.map) {
          attach(event.detail.map);
        }
      },
      { once: true }
    );
  }

  bootstrap();
})();
