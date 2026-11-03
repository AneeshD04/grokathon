# OWNERSHIP.md — who may edit what

Agents **must not** edit another lane's paths unless a `lane:shared` issue `@mentions` them and they `CLAIM` those files.

## Product root (binding)

**Build on `aquatic-sustainability/`** — the current BDBI Flask app (see `aquatic-sustainability/UPSTREAM.md`).

New work is **additive** on that tree: Safety Agent, cameras, X, gov alerts. Do **not** rewrite the product from scratch in repo-root `/frontend` or empty `/backend`.

| Path | Owner | GitHub |
| --- | --- | --- |
| `AGENTS.md`, `OWNERSHIP.md`, `TEAM.md` | Conductor | `@AneeshD04` |
| `agents/` | Conductor | `@AneeshD04` |
| `.cursor/` | Conductor | `@AneeshD04` |
| `.github/` | Conductor | `@AneeshD04` |
| `docs/`, `README.md`, `scripts/` | Conductor | `@AneeshD04` |
| `aquatic-sustainability/backend/` except `static/` | Backend / API | `@DevanshuShahs` |
| `aquatic-sustainability/backend/static/` | Frontend / UI | `@buzzkabir` |
| `bots/` | Grok Bot watchers + demo glue that **plug into** the Flask app | Athithan (handle in `TEAM.md`; ping `@AneeshD04` until invited) |
| `aquatic-sustainability/` research + deploy (`coral-reef-model/`, Docker, …) | Conductor unless a task `@mentions` you | `@AneeshD04` |
| `shared/` | Shared contracts | **all** — `lane:shared` issue required |
| repo-root `backend/` | **Stub only. Not the app.** Lane marker | `@DevanshuShahs` — do not implement product APIs here |
| repo-root `frontend/` | **Stub only. Not the app.** Lane marker | `@buzzkabir` — do not implement product UI here |

If a file is not listed, treat it as `shared/` and open a `type:decision` issue before adding it.

## Locking

The open `CLAIM` comment on an issue is the lock. Two open claims on the same path = conflict. Ping `@AneeshD04`.
