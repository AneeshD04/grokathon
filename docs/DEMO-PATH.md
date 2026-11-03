# Judge demo path — old predictive tool vs new Safety Agent

**60 seconds. No rebuild.** Same Flask process: `python run.py` from `aquatic-sustainability/backend/`.

The original BDBI **Flood / Drought** page stays intact. There is **no** `/safety` site and no second chrome. The new work is overlays on `/flood-drought` (county mark, live pins, alert feed, PIN-gated dry-run notify).

## 0–20s — old tool (BDBI predictive)

1. Open `/flood-drought` (same navbar / `styles.css` as the rest of Aquatic).
2. Click the map (Houston–Galveston). Say: this is the **original DualCNN-LSTM** flood-risk click (`POST /api/flood-risk`, NASA GPM + SMAP, delayed). Dummy drought polygons are **not** that model.
3. Optional: `/coral-bleaching` is the original GBR CSV bundle. Skip oil-spill (dummy JS).

## 20–45s — new tool (county OEM agent, same page)

4. Stay on `/flood-drought`. Mark **Galveston County** (or draw the box). That subscribes ModelWatch + watchers. Do **not** navigate to a new app.
5. Show whatever is live on that map: camera pins, NWS/USGS pins, alert feed. Persona: **county OEM / local government**, not a consumer chat toy.
6. If you need a camera class-change without Grok: from `bots/`

   ```bash
   copy camwatch\fixtures\flooded-road.jpg camwatch\fixtures\inbox\
   python -m camwatch --once --sink file
   ```

   That posts `Water over roadway` / `cam:buffalo-1:water_over_road`. (`--sink http` if the Flask bus is up.)

7. If you need a government pin without a live storm: from `aquatic-sustainability/backend/`

   ```bash
   python -m govwatch --once --sink file
   ```

   Replays a recorded Texas Flash Flood Warning + a Dickinson USGS gauge above stage onto `POST /api/alerts` (or JSONL). No API key. No Grok.

## 45–60s — confirm, do not send

8. **Notify impacted businesses** / Send alerts → confirm modal → **wrong PIN fails**. Correct approval PIN (see [`SAFETY-AGENT-DESIGN.md`](SAFETY-AGENT-DESIGN.md#demo-send-gate-dry-run--approval-pin)) logs intended recipients only.
9. Say out loud: **no Twilio**, no WEA blast, dummy drought is not DualCNN-LSTM, Places phones are not a dial list.

## Do not

- Rebuild, switch to `frontend/safety/`, or open a sidecar UI.
- Burn Grok on a dry-run notify or a second camera loop.
- Claim we texted the county.
