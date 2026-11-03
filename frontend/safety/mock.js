/* Same JSON shapes as the aquatic Flask routes and the safety endpoints.
   Not a live watcher. Empty API_BASE in api.js selects this file. */
(function () {
  const alerts = [];

  function stillUrl(name) {
    const label = String(name).replace(/[<>&"]/g, "");
    const svg =
      "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'>" +
      "<rect width='100%' height='100%' fill='#102033'/>" +
      "<text x='28' y='180' fill='#e8eef7' font-size='28' font-family='sans-serif'>" + label + "</text>" +
      "</svg>";
    return "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(svg);
  }

  function cam(id, name, lat, lon, source, hls) {
    return {
      id: id,
      name: name,
      lat: lat,
      lon: lon,
      still_url: stillUrl(name),
      hls_url: hls ? "https://example.com/demo/" + id + "/index.m3u8" : null,
      source: source,
    };
  }

  const CATALOG = [
    cam("galveston-ferry", "Galveston Ferry Landing", 29.3102, -94.793, "Houston TranStar", true),
    cam("bolivar-ferry", "Bolivar Ferry Landing", 29.3648, -94.765, "Houston TranStar", false),
    cam("broadway", "Broadway / Seawall", 29.299, -94.789, "Houston TranStar", false),
    cam("texas-city-dike", "Texas City Dike", 29.389, -94.885, "Houston TranStar", false),
    cam("causeway", "I-45 Galveston Causeway", 29.296, -94.878, "Houston TranStar", false),
    cam("sh-146", "SH 146 Texas City", 29.398, -94.929, "Houston TranStar", false),
    cam("league-city", "League City FM 518", 29.499, -95.095, "Houston TranStar", false),
    cam("san-luis", "San Luis Pass", 29.083, -95.122, "Houston TranStar", false),
    cam("bay-area", "Bay Area Blvd", 29.543, -95.129, "Houston TranStar", false),
    cam("buffalo-speedway", "Buffalo Speedway", 29.737, -95.428, "Houston TranStar", false),
    cam("shepherd", "Shepherd / Buffalo Bayou", 29.76, -95.408, "Houston TranStar", false),
  ];

  function inside(lat, lon, bbox) {
    return lon >= bbox.west && lon <= bbox.east && lat >= bbox.south && lat <= bbox.north;
  }

  function riskWord(p) {
    if (p >= 0.75) return "high";
    if (p >= 0.5) return "warning";
    if (p >= 0.3) return "medium";
    return "low";
  }

  function overlapsGulf(bbox) {
    const g = window.SafetyCounties.galveston.bbox;
    return !(bbox.east < g.west || bbox.west > g.east || bbox.north < g.south || bbox.south > g.north);
  }

  window.SafetyMock = {
    stillUrl: stillUrl,
    floodRisk: function (lat, lon) {
      const base = Math.abs(Math.sin(lat * 0.17) * Math.cos(lon * 0.09));
      const points = [];
      for (let i = 0; i < 8; i += 1) {
        const prob = Math.min(0.97, Math.max(0.04, base * 0.85 + (i - 3) * 0.05));
        points.push({
          lat: lat + (i - 3.5) * 0.2,
          lon: lon + ((i % 3) - 1) * 0.2,
          prob: prob,
          risk: riskWord(prob),
        });
      }
      return {
        status: "finished",
        cached: false,
        result: {
          center: { lat: lat, lon: lon },
          points: points,
        },
      };
    },
    news: function () {
      return {
        articles: [
          {
            title: "Coastal flood watch covers several basins",
            excerpt: "Fixture item in the GET /api/news article shape. Not a live NewsAPI call.",
            source: "Safety fixture",
            date: "2026-11-02T18:00:00Z",
            url: "https://example.com/flood-watch",
            read_time: "2 min read",
            category: "flood",
          },
          {
            title: "Drought desks report low reservoirs inland",
            excerpt: "Second fixture article so the agent panel has a news list after a box is drawn.",
            source: "Safety fixture",
            date: "2026-11-02T15:30:00Z",
            url: "https://example.com/drought-desk",
            read_time: "2 min read",
            category: "drought",
          },
          {
            title: "Reef heat stress stays elevated this week",
            excerpt: "Third fixture article. The real route returns this same set of fields.",
            source: "Safety fixture",
            date: "2026-11-01T12:00:00Z",
            url: "https://example.com/reef-heat",
            read_time: "3 min read",
            category: "coral",
          },
        ],
      };
    },
    watches: {
      create: function (input) {
        const bbox = input.bbox;
        const id = "w_" + Date.now().toString(36);
        return {
          id: id,
          geofence_id: id,
          bbox: [
            Math.round(bbox.west * 10000) / 10000,
            Math.round(bbox.south * 10000) / 10000,
            Math.round(bbox.east * 10000) / 10000,
            Math.round(bbox.north * 10000) / 10000,
          ],
          county: bbox.name || null,
          sources: ["camera", "nws", "x"],
          camera_ids: [],
          created_at: new Date().toISOString(),
        };
      },
    },
    cameras: {
      inBbox: function (bbox) {
        return CATALOG.filter(function (row) {
          return inside(row.lat, row.lon, bbox);
        });
      },
    },
    alerts: {
      subscribe: function () {
        return function () {};
      },
      list: function () {
        return alerts.slice();
      },
    },
    chat: {
      send: function (text, bbox) {
        if (!bbox) {
          return {
            reply: "No region is selected. Draw a box anywhere on the map. I will not guess a location.",
          };
        }
        return {
          reply:
            "Incident officer. Watching " + (bbox.name || "the drawn box") +
            ". West " + bbox.west.toFixed(4) +
            ", south " + bbox.south.toFixed(4) +
            ", east " + bbox.east.toFixed(4) +
            ", north " + bbox.north.toFixed(4) +
            ". I am citing the flood model and the news feed for that center, not a live gauge. You asked: " + text,
        };
      },
    },
    routes: {
      impact: function (bbox) {
        if (!overlapsGulf(bbox)) return { segments: [] };
        return {
          segments: [
            {
              road: "I-45 Galveston Causeway",
              likelihood: 0.62,
              reason: "flood zone",
              delay_min: 18,
              normal_eta_min: 22,
              impacted_eta_min: 40,
            },
          ],
        };
      },
    },
  };
})();
