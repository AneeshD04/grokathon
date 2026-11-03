# Grokathon

Georgia Tech **BDBI × SpaceXSI Grokathon** team repo.

Team: Aneesh, Devanshu, Athithan, Kabir.

Hackathon product: improve BDBI **[Aquatic Sustainability](https://github.com/gt-big-data/aquatic-sustainability)** (hydrological disasters + disparities) with a **Safety Agent** and live watchers (gov feeds, cameras, optional X). The upstream app is vendored in `aquatic-sustainability/`.

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
aquatic-sustainability/   vendored BDBI app (Flask + models + UI)
docs/                     project explanation + Safety Agent design
agents/                   collab briefs + Grok Bot prompts
backend/ / frontend/ / bots/   new-lane work (do not fork the vendored app blindly)
shared/                   cross-lane contracts
```

## Commands

```bash
gh issue list --state open
gh issue develop <n> --name "agent/<handle>/#<n>-slug"   # optional
```

Do not push straight to `main`. One issue → one branch → one PR.
