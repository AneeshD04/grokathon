# Upstream snapshot

Vendored from [gt-big-data/aquatic-sustainability](https://github.com/gt-big-data/aquatic-sustainability).

| Field | Value |
| --- | --- |
| SHA | [`23606826fca4f1001e0ba7c6e29b9a0d98435bfb`](https://github.com/gt-big-data/aquatic-sustainability/commit/23606826fca4f1001e0ba7c6e29b9a0d98435bfb) |
| Ref | `main` (HEAD was identical to this SHA when imported) |
| Message | `Merge pull request #37 from gt-big-data/alexis` |
| Live demo | https://aquatic-sustainability-834508815183.us-east1.run.app |
| BDBI leads | Rick Lee, Michael Xu |

This directory **is the product**. Team agents extend this Flask app in place. Do not fork it into empty repo-root `backend/` or `frontend/`.

## Included

All app code, production models, static UI, Docker/Cloud Run files, and research dirs that exist on current `main`:

- `backend/` — Flask API, DualCNN-LSTM V3 weights, coral CSVs, vanilla JS UI in `backend/static/`
- `coral reef analysis/`, `coral-reef-model/`, `xgboost-model/`, `Time Series Models/`
- `database/`, `images/`, `webpage/`, Docker/Cloud Build, `DummyData.csv`, docs at this root

## Excluded (on purpose)

| Path | Why |
| --- | --- |
| `keras classifier/` | ~5,637 training JPEGs, **67.1 MB**. Oil-spill CNN is **not** wired to the live API. Pull from upstream if you train vision. |
| `backend/new_model/elevation_asia_7_5arc.tif` | Git LFS object **~468 MB**. GitHub rejects blobs over 100 MB. Experimental V9 DEM, unused by the Flask app. Fetch from upstream LFS if needed. |
| `.git/` | Nested git history stripped; this is a snapshot, not a submodule. |
| `.idea/`, `.vscode/` | Upstream editor junk. |
| `.ipynb_checkpoints/` | Notebook cache. |
| `backend/.venv/`, `backend/.env` | Local only. Copy `../../.env.example` → `backend/.env`. Never commit. |

Upstream tracks `*.pt` / `*.tif` / `*.pkl` with Git LFS. This copy stores the **usable** blobs in git (V3 flood weights are 2.2 MB). The 468 MB DEM is the only LFS object too large to vendor.

To refresh later:

```bash
git fetch https://github.com/gt-big-data/aquatic-sustainability.git main
# compare SHA in this file; copy working tree excluding the rows above
```
