# Grokathon

Georgia Tech **BDBI × SpaceXSI Grokathon** team repo.

Team: Aneesh, Devanshu, Athithan, Kabir.

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
agents/      collaboration briefs + Grok Bot prompts
backend/    Devanshu
frontend/    Kabir
bots/        Athithan (Grok Bot integration, demo)
shared/      cross-lane contracts (issue required)
.cursor/     Cursor rules every agent loads
.github/     issue/PR templates
```

## Commands

```bash
gh issue list --state open
gh issue develop <n> --name "agent/<handle>/#<n>-slug"   # optional
```

Do not push straight to `main`. One issue → one branch → one PR.
