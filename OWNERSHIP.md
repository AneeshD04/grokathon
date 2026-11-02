# OWNERSHIP.md — who may edit what

Agents **must not** edit another lane's paths unless a `lane:shared` issue `@mentions` them and they `CLAIM` those files.

| Path | Owner | GitHub |
| --- | --- | --- |
| `AGENTS.md`, `OWNERSHIP.md`, `TEAM.md` | Conductor | `@AneeshD04` |
| `agents/` | Conductor | `@AneeshD04` |
| `.cursor/` | Conductor | `@AneeshD04` |
| `.github/` | Conductor | `@AneeshD04` |
| `backend/` | Backend | `@DevanshuShahs` |
| `frontend/` | Frontend | `@buzzkabir` |
| `bots/` | Grok Bot / demo | Athithan (handle in `TEAM.md`) |
| `shared/` | Shared contracts | **all** — `lane:shared` issue required |
| `scripts/` | Conductor + whoever is `@mentioned` | default `@AneeshD04` |
| `README.md` | Conductor, PRs welcome | `@AneeshD04` |

If a file is not listed, treat it as `shared/` and open a `type:decision` issue before adding it.

## Locking

The open `CLAIM` comment on an issue is the lock. Two open claims on the same path = conflict. Ping `@AneeshD04`.
