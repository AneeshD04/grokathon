/* Alert feed. Rows appear only from alerts.subscribe (SSE / snapshot). */
(function () {
  const seen = new Set();
  const rows = [];

  function render() {
    const list = document.getElementById("alert-list");
    list.innerHTML = "";
    if (!rows.length) {
      const empty = document.createElement("li");
      empty.className = "alert-empty";
      empty.textContent = "No alerts.";
      list.appendChild(empty);
      return;
    }
    rows.forEach(function (alert) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "alert-row";
      button.dataset.severity = alert.severity || "info";
      const title = document.createElement("strong");
      title.textContent = alert.title || "Alert";
      const meta = document.createElement("span");
      meta.textContent = (alert.severity || "info") + " · " + (alert.source || "") + " · " + (alert.ts || "");
      button.appendChild(title);
      button.appendChild(meta);
      button.addEventListener("click", function () {
        if (typeof alert.lat === "number" && typeof alert.lon === "number") {
          SafetyMap.flyTo(alert.lat, alert.lon);
        }
        const figure = document.getElementById("evidence");
        const img = document.getElementById("evidence-thumb");
        const caption = document.getElementById("evidence-caption");
        const thumb = alert.evidence && alert.evidence.thumb_url;
        if (thumb) {
          figure.hidden = false;
          img.src = thumb;
          img.alt = (alert.title || "Alert") + " evidence";
          caption.textContent = alert.summary || "";
        } else {
          figure.hidden = true;
        }
      });
      item.appendChild(button);
      list.appendChild(item);
    });
  }

  function onAlert(alert) {
    if (!alert || seen.has(alert.id)) return;
    if (alert.id) seen.add(alert.id);
    rows.unshift(alert);
    render();
  }

  render();
  SafetyAPI.alerts.subscribe(onAlert);
})();
