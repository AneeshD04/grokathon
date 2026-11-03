# Grokathon

Georgia Tech **BDBI × SpaceXSI Grokathon** team repo.

Team: Aneesh, Devanshu, Athithan, Kabir.

Hackathon product: a **county OEM / emergency-manager Safety Agent** on BDBI **[Aquatic Sustainability](https://github.com/gt-big-data/aquatic-sustainability)** — mark a county, watch live cameras/NWS/X, then PIN-gated **dry-run** fan-out to local businesses (Google Places) and opted-in residents. We do **not** WEA-blast the public (IPAWS stub only).

**Rule for every agent:** build on [`aquatic-sustainability/`](aquatic-sustainability/) (current upstream `main`). Additive work only. Do not rewrite the app in empty `/backend` or `/frontend`. Snapshot notes: [`aquatic-sustainability/UPSTREAM.md`](aquatic-sustainability/UPSTREAM.md).

Read: [`docs/BDBI-AQUATIC-SUSTAINABILITY.md`](docs/BDBI-AQUATIC-SUSTAINABILITY.md) · [`docs/MISSING-KEYS.md`](docs/MISSING-KEYS.md) · [`docs/SAFETY-AGENT-DESIGN.md`](docs/SAFETY-AGENT-DESIGN.md) · [`docs/CAMERA-SOURCES.md`](docs/CAMERA-SOURCES.md)

We build with **Cursor** and **Grok Bot**. Multiple humans and their agents ship in parallel **without writing over each other**. GitHub Issues is the messaging bus — agents `@mention`, claim files, and hand off work there.

## Start here

| You are | Read |
| --- | --- |
| Any human or agent | [`AGENTS.md`](AGENTS.md) (law), [`OWNERSHIP.md`](OWNERSHIP.md), [`TEAM.md`](TEAM.md) |
| Setting up a Grok Bot | [`agents/GROKBOTS.md`](agents/GROKBOTS.md) |
| Aneesh / conductor | [`agents/aneesh.md`](agents/aneesh.md) |
| Devanshu | [`agents/devanshu.md`](agents/devanshu.md) |
| Kabir | [`agents/kabir.md`](agents/kabir.md) |
| Athithan | [`agents/athithan.md`](agents/athithan.md) |

Issue templates: **Task**, **Ping**, **Handoff**, **Blocker**.

## Layout

```
aquatic-sustainability/          PRODUCT ROOT — BDBI Flask app (extend this)
  backend/                       Devanshu (@DevanshuShahs) — API
  backend/static/                Kabir (@buzzkabir) — UI
bots/                            Athithan — watchers that plug into that app
docs/ agents/                    Aneesh — protocol + design
backend/ frontend/               empty stubs — not the app; do not build here
shared/                          cross-lane contracts (lane:shared issue required)
```

Run the app: copy [`.env.example`](.env.example) → `aquatic-sustainability/backend/.env`, then `python run.py` from `aquatic-sustainability/backend/` (see `docs/BDBI-AQUATIC-SUSTAINABILITY.md`). Never commit `.env` or `.venv`.

## Commands

```bash
git fetch origin && git pull --ff-only
gh issue list --state open
gh issue develop <n> --name "agent/<handle>/#<n>-slug"   # optional
```

Do not push straight to `main`. One issue → one branch → one PR.
