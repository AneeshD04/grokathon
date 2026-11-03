# Progress vs untouched BDBI

Snapshot: **2026-11-02 evening ET** (`origin/main` at `dfcc343`, after PRs #22, #29, #31).  
Upstream: [gt-big-data/aquatic-sustainability](https://github.com/gt-big-data/aquatic-sustainability) `main` (`23606826`, as vendored on PR #41).  
Local tree: untracked `aquatic-sustainability/` — the Flask app + models, **not** on `main`.

This is an honesty check, not a pitch. Analysis is still the old BDBI models. Safety Agent, cameras, and notify are mostly issues + docs, not shipped product code.

## 1) What the original product already did

BDBI *Hydrological Disasters And Disparities* is a Flask + Google Maps site. README ambition (affordability, oil/algal CNN, Chrome extension) is broader than what is wired.

| Surface | Upstream reality |
| --- | --- |
| `/flood-drought` | **Real** DualCNN-LSTM `POST /api/flood-risk` (NASA GPM + SMAP) **plus** hardcoded Georgia dummy pins. `GET /api/drought` / `GET /api/flood` are dummy polygons. |
| `/coral-bleaching` | **Real** weekly LSTM + XGBoost CSV bundle for GBR centroids. |
| `/oil-spill` | Dummy JS pins. Keras oil/algal classifier is **not** on the API. |
| `/news` | NewsAPI or placeholders. |
| `/login` `/register` | Supabase if keys exist. |
| `/water` | Route 404; affordability **not implemented**. |
| Maps | Maps JS key from `GET /api/config/maps-key`. |
| Watchers / chat / cameras / Places fan-out | **None.** |

We did **not** retrain or replace DualCNN-LSTM, coral CSVs, or the dummy oil/drought paths. Inventory: [`BDBI-AQUATIC-SUSTAINABILITY.md`](BDBI-AQUATIC-SUSTAINABILITY.md).

## 2) What we planned (issue bus)

Product call [#7](https://github.com/AneeshD04/grokathon/issues/7): real-time **Safety Agent** on top of that app (county OEM marks a region → ModelWatch + cameras/NWS/X → human confirm → dry-run fan-out). Design: [`SAFETY-AGENT-DESIGN.md`](SAFETY-AGENT-DESIGN.md).

| Slice | Issues | Intended owner |
| --- | --- | --- |
| Vendor the Flask app as the product root | [#6](https://github.com/AneeshD04/grokathon/issues/6) | Aneesh |
| Shared alert/watch/camera JSON | [#8](https://github.com/AneeshD04/grokathon/issues/8) | shared |
| Alert bus + SSE | [#11](https://github.com/AneeshD04/grokathon/issues/11) | Devanshu |
| Notify (later: PIN-gated dry-run) | [#13](https://github.com/AneeshD04/grokathon/issues/13) [#27](https://github.com/AneeshD04/grokathon/issues/27) | Devanshu / docs |
| Safety Agent chat proxy | [#12](https://github.com/AneeshD04/grokathon/issues/12) | Devanshu |
| County picker, camera pins, chat drawer | [#14](https://github.com/AneeshD04/grokathon/issues/14) [#15](https://github.com/AneeshD04/grokathon/issues/15) [#16](https://github.com/AneeshD04/grokathon/issues/16) | Kabir |
| Cameras-in-bbox API + Houston catalog | [#10](https://github.com/AneeshD04/grokathon/issues/10) [#9](https://github.com/AneeshD04/grokathon/issues/9) | Devanshu / Aneesh |
| CamWatch / X / NWS+USGS | [#17](https://github.com/AneeshD04/grokathon/issues/17) [#18](https://github.com/AneeshD04/grokathon/issues/18) [#19](https://github.com/AneeshD04/grokathon/issues/19) | Athithan (forward) / Aneesh |
| Places businesses + confirm UI + tools | [#24](https://github.com/AneeshD04/grokathon/issues/24) [#25](https://github.com/AneeshD04/grokathon/issues/25) [#26](https://github.com/AneeshD04/grokathon/issues/26) | Devanshu / Kabir / Aneesh |
| ModelWatch glue (poll existing flood/coral APIs) | [#34](https://github.com/AneeshD04/grokathon/issues/34) [#35](https://github.com/AneeshD04/grokathon/issues/35) [#38](https://github.com/AneeshD04/grokathon/issues/38) | docs / Devanshu |
| Opt-in resident roster | [#39](https://github.com/AneeshD04/grokathon/issues/39) [#40](https://github.com/AneeshD04/grokathon/issues/40) [#32](https://github.com/AneeshD04/grokathon/issues/32) | Devanshu / Kabir |

## 3) What is actually merged (`origin/main`)

`aquatic-sustainability/` is **not** on `main`. Repo-root `frontend/` and `bots/` are stub READMEs. `shared/` is a stub README (contracts still [#8](https://github.com/AneeshD04/grokathon/issues/8)).

| Merged | What it is | What it is not |
| --- | --- | --- |
| [#22](https://github.com/AneeshD04/grokathon/pull/22) | Sync-before-edit protocol | Product |
| Docs on `main` (`90eca5e`) | How BDBI works, missing keys, early Safety Agent design, camera *source list* | No Safety UI, no camera API, no watchers |
| [#29](https://github.com/AneeshD04/grokathon/pull/29) / [#11](https://github.com/AneeshD04/grokathon/issues/11) | In-memory **sidecar** alert bus (`backend/` :8000, SSE) | Not inside the Flask aquatic app. No ModelWatch publisher. |
| [#31](https://github.com/AneeshD04/grokathon/pull/31) / [#13](https://github.com/AneeshD04/grokathon/issues/13) | **Sidecar** notify (`backend/notify/` :8001). Twilio only to `NOTIFY_SANDBOX_PHONES`; roster/911 never dialed | Not wired to the map. Later PIN + always-dry-run design is **docs/PRs only**, not this merge. |

Open PRs (not merged at snapshot): [#41](https://github.com/AneeshD04/grokathon/pull/41) vendor aquatic; [#36](https://github.com/AneeshD04/grokathon/pull/36) / [#37](https://github.com/AneeshD04/grokathon/pull/37) OEM/Places **docs**; [#43](https://github.com/AneeshD04/grokathon/pull/43) Places nearby **code** (still open); [#44](https://github.com/AneeshD04/grokathon/pull/44) Grok quota docs; [#45](https://github.com/AneeshD04/grokathon/pull/45) conductor-no-impl. Athithan `#17` camwatch branch exists; no PR.

## 4) Local `aquatic-sustainability/` vs `main`

The local folder is a vendor of current BDBI `main` (same SHA as PR #41). It has the **original** flood/coral/oil/news pages and DualCNN-LSTM weights. It does **not** contain Safety Agent chat, camera pins, Places fan-out, ModelWatch, or notify glued into Flask.

So: judges running local Flask see the **untouched predictive app**. The Grokathon layer is protocol + design docs + two sidecars on empty `/backend`, plus open issues/PRs.

## 5) Honest score

| Capability | Status |
| --- | --- |
| BDBI flood DualCNN-LSTM / coral CSVs / dummy oil+drought | Unchanged. Local + PR #41 only; **not on `main`** |
| Safety Agent chat / Grok tools | Issues + design doc. No shipped proxy ([#12](https://github.com/AneeshD04/grokathon/issues/12)) |
| Cameras on the map / CamWatch vision | Catalog notes in [`CAMERA-SOURCES.md`](CAMERA-SOURCES.md). [#15](https://github.com/AneeshD04/grokathon/issues/15) [#17](https://github.com/AneeshD04/grokathon/issues/17) not merged |
| County picker / alert drawer | [#14](https://github.com/AneeshD04/grokathon/issues/14) [#16](https://github.com/AneeshD04/grokathon/issues/16) claimed; not on `main` |
| Notify / Places / OEM PIN | Sidecar SMS sandbox is merged; Places + PIN dry-run + “notify impacted businesses” are issues/docs (and open #43), not in the aquatic UI |
| ModelWatch | Docs in flight ([#34](https://github.com/AneeshD04/grokathon/issues/34)); poller [#35](https://github.com/AneeshD04/grokathon/issues/35) unstarted on `main` |

Do not tell judges we shipped a live camera Safety Agent. We planned it, documented it, and merged plumbing sidecars. The predictive models are still BDBI’s.
