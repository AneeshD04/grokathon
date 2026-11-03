/* Still panel for cameras returned by SafetyAPI.cameras.inBbox.
   Empty until GET /api/cameras exists. Pins are camera-pins.js. */
(function () {
  const LIST_CAP = 8;
  let selectedId = null;

  function panel() {
    return document.getElementById("camera-panel");
  }

  function render(cameras) {
    const root = panel();
    if (!root) return;
    root.hidden = false;
    root.innerHTML = "";
    if (!cameras.length) {
      const empty = document.createElement("p");
      empty.className = "camera-caption";
      empty.textContent = "No cameras in this box.";
      root.appendChild(empty);
      return;
    }

    const shown = cameras.slice(0, LIST_CAP);
    const extra = cameras.length - shown.length;
    const head = document.createElement("div");
    head.className = "camera-head";
    head.textContent = cameras.length + (cameras.length === 1 ? " camera" : " cameras") + " in this box";
    root.appendChild(head);

    const still = document.createElement("img");
    still.id = "camera-still";
    still.alt = "";
    still.hidden = true;
    root.appendChild(still);

    const caption = document.createElement("p");
    caption.id = "camera-caption";
    caption.className = "camera-caption";
    caption.textContent = "Click a pin or a name to watch the still.";
    root.appendChild(caption);

    const list = document.createElement("ul");
    list.id = "camera-list";
    shown.forEach(function (cam) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "camera-row";
      button.dataset.cameraId = cam.id;
      button.textContent = cam.name;
      button.addEventListener("click", function () {
        window.SafetyCameras.focus(cam);
      });
      item.appendChild(button);
      list.appendChild(item);
    });
    root.appendChild(list);

    if (extra > 0) {
      const more = document.createElement("p");
      more.className = "camera-more";
      more.textContent = "Showing " + LIST_CAP + " of " + cameras.length + " in the list. All " + cameras.length + " are on the map.";
      root.appendChild(more);
    }

    if (selectedId) {
      const match = cameras.find(function (cam) { return cam.id === selectedId; });
      if (match) focus(match);
    }
  }

  function focus(cam) {
    selectedId = cam.id;
    const still = document.getElementById("camera-still");
    const caption = document.getElementById("camera-caption");
    if (!still) return;
    still.hidden = false;
    still.src = cam.still_url;
    still.alt = cam.name + " still";
    const hls = cam.hls_url ? " · HLS listed, still shown" : "";
    caption.textContent = cam.name + " · " + (cam.source || "") + hls;
    document.querySelectorAll(".camera-row").forEach(function (row) {
      row.classList.toggle("is-active", row.dataset.cameraId === cam.id);
    });
    if (window.SafetyBus) SafetyBus.emit("camera", cam);
  }

  window.SafetyCameras = {
    render: render,
    focus: focus,
  };
})();
