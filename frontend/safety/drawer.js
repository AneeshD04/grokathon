/* Safety Agent drawer. One surface: flood model, news, route delay, alerts, chat.
   Other issues add adapter methods, not new buttons. */
(function () {
  const root = document.getElementById("safety-drawer");
  root.innerHTML =
    '<header class="drawer-head">' +
      '<p class="eyebrow">Safety Agent</p>' +
      '<h1>Region brief</h1>' +
    '</header>' +
    '<section class="drawer-section" id="agent-brief">' +
      '<p id="brief-empty">Draw a box anywhere on the map. This brief uses that bbox.</p>' +
      '<p id="flood-line" hidden></p>' +
      '<ul id="news-list"></ul>' +
      '<p id="route-line" hidden></p>' +
    '</section>' +
    '<section class="drawer-section">' +
      '<h2>Alerts</h2>' +
      '<ul id="alert-list"></ul>' +
      '<figure id="evidence" hidden>' +
        '<img id="evidence-thumb" alt="Alert evidence" />' +
        '<figcaption id="evidence-caption"></figcaption>' +
      '</figure>' +
    '</section>' +
    '<section class="drawer-section">' +
      '<h2>Chat</h2>' +
      '<div id="transcript"></div>' +
      '<form id="chat-form">' +
        '<input id="chat-text" type="text" placeholder="Ask about this box" autocomplete="off" />' +
        '<button type="submit">Send</button>' +
      '</form>' +
    '</section>';

  function addLine(role, text) {
    const line = document.createElement("p");
    line.className = "chat-line " + role;
    line.textContent = text;
    document.getElementById("transcript").appendChild(line);
  }

  addLine("officer", "Incident officer standing by. Pan the globe, draw a box, then ask about that area.");

  function meanProb(flood) {
    const points = flood && flood.result && flood.result.points;
    if (!points || !points.length) return null;
    const sum = points.reduce(function (acc, point) { return acc + Number(point.prob || 0); }, 0);
    return sum / points.length;
  }

  function renderRegion(region) {
    document.getElementById("brief-empty").hidden = true;
    const floodLine = document.getElementById("flood-line");
    const newsList = document.getElementById("news-list");
    const routeLine = document.getElementById("route-line");
    const flood = region.flood;
    const avg = meanProb(flood);
    floodLine.hidden = false;
    if (avg == null || !flood.result || !flood.result.center) {
      floodLine.textContent = "Flood model: no points returned.";
    } else {
      const center = flood.result.center;
      floodLine.textContent =
        "Flood model at " + center.lat.toFixed(2) + ", " + center.lon.toFixed(2) +
        ": " + Math.round(avg * 100) + "% mean across " + flood.result.points.length + " points.";
    }

    newsList.innerHTML = "";
    const articles = (region.news && region.news.articles) || [];
    articles.forEach(function (article) {
      const li = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = article.title || "Untitled";
      const meta = document.createElement("span");
      meta.textContent = (article.source || "Unknown") + " · " + (article.date || "");
      const excerpt = document.createElement("span");
      excerpt.textContent = article.excerpt || "";
      li.appendChild(title);
      li.appendChild(meta);
      li.appendChild(excerpt);
      newsList.appendChild(li);
    });

    const segments = region.impact && region.impact.segments;
    if (segments && segments.length) {
      const first = segments[0];
      routeLine.hidden = false;
      routeLine.textContent =
        "First responder delay: +" + first.delay_min + " minutes on " + first.road +
        " (" + first.normal_eta_min + " → " + first.impacted_eta_min + " min).";
    } else {
      routeLine.hidden = true;
      routeLine.textContent = "";
    }

    const bbox = region.bbox;
    addLine(
      "officer",
      "Watching " + bbox.name + ". Center " + bbox.center.lat.toFixed(2) + ", " + bbox.center.lon.toFixed(2) +
      ". " + (avg == null ? "No flood points." : "Flood mean " + Math.round(avg * 100) + "%.") +
      " " + articles.length + " news items."
    );
  }

  SafetyBus.on("region", renderRegion);

  document.getElementById("chat-form").addEventListener("submit", async function (ev) {
    ev.preventDefault();
    const input = document.getElementById("chat-text");
    const text = input.value.trim();
    if (!text) return;
    addLine("user", text);
    input.value = "";
    try {
      const res = await SafetyAPI.chat.send(text, SafetyMap.getBbox());
      addLine("officer", res.reply || "No reply.");
    } catch (err) {
      addLine("officer", "Chat proxy is not connected.");
    }
  });
})();
