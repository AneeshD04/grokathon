/* Connection: API_BASE "" means same-origin (Flask at /safety).
   Set it only if the page is hosted on a different origin.
   Served copy: aquatic-sustainability/backend/static/safety/
   Keep frontend/safety/ identical to that directory. Do not change call shapes.
   floodRisk(lat, lon)     POST /api/flood-risk          {lat, lon}
   news()                  GET  /api/news
   watches.create({bbox})  POST /api/watches             bbox [west,south,east,north]
   cameras.inBbox(bbox)    GET  /api/cameras?bbox=west,south,east,north
   alerts.subscribe(fn)    SSE  /api/alerts/stream       event "alert"; GET /api/alerts
   chat.send(text, bbox)   POST /api/safety/chat
   routes.impact(bbox)     GET  /api/routes/impact?bbox=west,south,east,north
   Flood and news always hit Flask. The other calls 404 until those lanes land;
   the page catches that and still shows the box, flood result, and news.
*/
let API_BASE = "";

function apiUrl(path) {
  return API_BASE.replace(/\/$/, "") + path;
}

function boxArray(bbox) {
  return [bbox.west, bbox.south, bbox.east, bbox.north];
}

function boxQuery(bbox) {
  return boxArray(bbox).join(",");
}

async function readJson(res, label) {
  if (!res.ok) throw new Error(label + " failed (" + res.status + ")");
  return res.json();
}

window.SafetyAPI = {
  get API_BASE() {
    return API_BASE;
  },
  set API_BASE(value) {
    API_BASE = value || "";
  },
  async floodRisk(lat, lon) {
    const res = await fetch(apiUrl("/api/flood-risk"), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ lat: lat, lon: lon }),
    });
    return readJson(res, "POST /api/flood-risk");
  },
  async news() {
    const res = await fetch(apiUrl("/api/news"));
    return readJson(res, "GET /api/news");
  },
  watches: {
    async create(input) {
      const bbox = input.bbox || input;
      const body = {
        bbox: boxArray(bbox),
        sources: ["camera", "nws", "x", "model"],
      };
      if (bbox.name) body.county = bbox.name;
      const res = await fetch(apiUrl("/api/watches"), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      return readJson(res, "POST /api/watches");
    },
  },
  cameras: {
    async inBbox(bbox) {
      const res = await fetch(apiUrl("/api/cameras?bbox=" + encodeURIComponent(boxQuery(bbox))));
      const data = await readJson(res, "GET /api/cameras");
      if (Array.isArray(data)) return data;
      return data.cameras || [];
    },
  },
  alerts: {
    subscribe(onAlert) {
      let closed = false;
      let stream = null;
      fetch(apiUrl("/api/alerts"))
        .then(function (res) {
          if (!res.ok) return null;
          return res.json();
        })
        .then(function (data) {
          if (closed || !data) return;
          const rows = Array.isArray(data) ? data : (data.alerts || []);
          rows.forEach(onAlert);
          stream = new EventSource(apiUrl("/api/alerts/stream"));
          stream.addEventListener("alert", function (ev) {
            if (closed) return;
            try { onAlert(JSON.parse(ev.data)); } catch (err) { /* ignore malformed */ }
          });
        })
        .catch(function () {});
      return function () {
        closed = true;
        if (stream) stream.close();
      };
    },
  },
  chat: {
    async send(text, bbox) {
      const res = await fetch(apiUrl("/api/safety/chat"), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: text, bbox: bbox || null }),
      });
      return readJson(res, "POST /api/safety/chat");
    },
  },
  routes: {
    async impact(bbox) {
      const res = await fetch(apiUrl("/api/routes/impact?bbox=" + encodeURIComponent(boxQuery(bbox))));
      return readJson(res, "GET /api/routes/impact");
    },
  },
};
