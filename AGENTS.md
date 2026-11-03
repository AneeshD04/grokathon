# AGENTS.md — Grokathon collaboration law

This file is **binding** for every human, Cursor agent, and Grok Bot on this repo.
If you skip it, you will overwrite teammates and duplicate work.

Repo: [AneeshD04/grokathon](https://github.com/AneeshD04/grokathon)  
Issue bus: [Issues](https://github.com/AneeshD04/grokathon/issues)

## Non-negotiables

1. **GitHub Issues is the only team chat.** Not Slack, not Discord, not a private Cursor thread for anything that another agent must see. If another agent needs it, it goes on an issue.
2. **No code without a claimed issue.** If there is no issue, or the issue is not assigned to you, you do not touch files.
3. **Never duplicate an issue.** Search first (`gh issue list`, GitHub search). Comment on the existing thread.
4. **Never write over another agent's claimed paths.** Ownership is in `OWNERSHIP.md`. Claimed files are listed on the issue.
5. **Talk with `@mentions`.** Ping the GitHub handle, not a nickname. The ping *is* the handoff.
6. **One agent, one claimed task.** Finish or hand off before claiming another P0/P1.
7. **Always sync before you edit or push.** `git fetch origin && git pull --ff-only` (or rebase onto latest `origin/main`) before the first file change. Pull again before you push; if behind, fast-forward or rebase, then push. Never force-push `main`. Product code lives in `aquatic-sustainability/` — build on current `main`, not a stale clone or empty `backend/` / `frontend/` stubs.
8. **Conductor files issues and reviews PRs.** `@AneeshD04` does not implement backend, frontend, or bots unless a lane owner `HANDOFF`s those paths.

## Roster (ping these)

| Human | GitHub | Agent id | Lane |
| --- | --- | --- | --- |
| Aneesh | `@AneeshD04` | `agent-aneesh` | Conductor, product, protocol, `agents/`, `docs/` |
| Devanshu | `@DevanshuShahs` | `agent-devanshu` | API: `aquatic-sustainability/backend/` (not empty `/backend`) |
| Kabir | `@buzzkabir` | `agent-kabir` | UI: `aquatic-sustainability/backend/static/` (not empty `/frontend`) |
| Athithan | **invite pending** — set handle in `TEAM.md` | `agent-athithan` | `bots/` + safety watchers that plug into that Flask app |

Until Athithan is a collaborator, ping `@AneeshD04` on `lane:athithan` issues and say `please forward to Athithan`.

**Product root:** `aquatic-sustainability/` is the BDBI app teammates extend. Additive features only (Safety Agent, cameras, X, gov alerts). Do not rewrite from scratch in `/frontend` or empty `/backend`.

Per-agent briefs live in [`agents/`](agents/). Grok Bot paste-prompts live in [`agents/GROKBOTS.md`](agents/GROKBOTS.md).

## Boot sequence (every session)

Run this **before** editing anything:

```bash
git fetch origin
git pull --ff-only
# already on a branch?  git fetch origin && git rebase origin/main
gh issue list --state open --limit 50
gh issue list --search "status:claimed OR status:in-progress" --state open
```

Then:

1. Confirm you are on latest `origin/main` (or rebased onto it). Do not edit a stale tree.
2. Read this file, `OWNERSHIP.md`, and **your** file in `agents/`.
3. Search issues for the work you are about to do.
4. If a matching open issue exists → comment + `@mention` the assignee. Do not open a second issue.
5. If none exists → open the right template (`task` / `ping` / `handoff` / `blocker`).
6. Claim it (below) **before** the first file edit.
7. Branch from `main`: `agent/<github-handle>/#<issue>-short-slug`.

## Claiming work

On the issue, post **exactly** this (fill the fields):

```
CLAIM
assignee: @YourHandle
files:
- path/to/file-or-dir
locks: exclusive
```

Then:

- Assign the issue to yourself.
- Add `status:claimed` and your `lane:*` label.
- List **every path you will edit**. If you need a new path, comment an updated `CLAIM` first.

**Conflict rule:** if any listed path already appears in another open `CLAIM`, you **stop**. Comment on both issues and ping `@AneeshD04`. Do not "just be careful."

Release a claim when you hand off, close, or drop the work:

```
UNCLAIM
assignee: @YourHandle
reason: handed-off | done | dropped
```

## Messaging and delegation

Issues replace chat. Use them like this:

| Intent | How |
| --- | --- |
| Ask a teammate / their bot | Comment `@Handle` on the relevant issue. One question per comment when you need a reply. |
| Start a new conversation | Open a **ping** issue. Title: `ping(@Handle): <topic>`. Body is the message. |
| Delegate | Open a **handoff** issue *or* convert the current issue: `UNCLAIM`, assign them, comment `HANDOFF @Handle` with context, paths, and definition of done. |
| Blocked | Add `status:blocked`, open/comment a **blocker**, `@mention` whoever can unblock. |
| Decision needed | Label `type:decision`, ping `@AneeshD04` plus anyone affected. Do not fork the codebase waiting. |

**Mention rules**

- `@AneeshD04` — conductor, conflicts, product calls, Athithan forwarding.
- `@DevanshuShahs` — API contracts, server, data.
- `@buzzkabir` — UI, client state, demo screens.
- Athithan — Grok Bot wiring, live demo script (handle in `TEAM.md`).
- Ping **the human GitHub handle**. Their Grok Bot / Cursor agent is expected to watch assignments and `@mentions`.
- Never `@mention` someone just to FYI-dump. If they must act, say what you need them to do in the same comment.

Handoff comment shape:

```
HANDOFF @TheirHandle
why: <one sentence>
done-when: <bullet definition of done>
files:
- ...
context: <what you already tried / links to commits>
please: <the actual ask>
```

## File ownership

See `OWNERSHIP.md`. Short version:

- Edit **only** your lane unless the issue is `lane:shared` **and** you were `@mentioned`.
- Product code is `aquatic-sustainability/`. Claim paths under that tree.
- `agents/`, `AGENTS.md`, `.cursor/rules/` → Aneesh unless he hands off.
- Shared contracts (`shared/`) need a `type:decision` or `lane:shared` issue before changing.

## Git workflow

- Default branch: `main`.
- **Before edit:** `git fetch origin && git pull --ff-only`. If you already have a branch, rebase onto latest `origin/main`.
- **Before push:** fetch/pull again. If behind, fast-forward or rebase, then push. Never force-push `main`.
- Product code lives in `aquatic-sustainability/` on current `main`. Do not implement against a stale snapshot or empty `backend/` / `frontend/` stubs.
- No direct pushes to `main` except a documented conductor hotfix pinged on an issue.
- One issue ↔ one branch ↔ one PR.
- PR title: `#<issue> <what>` and link the issue (`Fixes #n` or `Refs #n`).
- `@mention` the other lanes you touched in the PR body.
- Do not force-push shared branches. Do not rewrite history on `main`.

## Duplicate and overlap defense

Before creating an issue, search titles **and** body for the feature words.

If two agents started the same work:

1. Stop coding.
2. Comment on both issues with `OVERLAP` and `@AneeshD04`.
3. Conductor picks a surviving issue; the other is closed as duplicate with a pointer.
4. The losing branch is abandoned, not merged.

## Status labels (source of truth)

`inbox` → `claimed` → `in-progress` → `review` → closed (`done`).  
`blocked` can sit on top of `claimed` / `in-progress`.

If labels and the last `CLAIM` comment disagree, **the latest CLAIM comment wins**. Fix labels in the same comment.

## What Grok Bots must do

Each teammate runs a Grok Bot using the prompt in `agents/GROKBOTS.md`.

Bots:

- Poll / watch GitHub issues for `@their-human` and assignments.
- Reply **on the issue**, not in a side channel.
- Sync to latest `origin/main` before edit or push. Never force-push `main`.
- Delegate by `HANDOFF @Handle`, never by silently editing another lane.
- Refuse to implement if the claim/lock check fails.

Humans stay accountable for merges.

## Definition of done for any task

- Issue has a `CLAIM` (or a closed `UNCLAIM` + merged PR).
- Paths in the claim match the diff.
- PR reviewed or explicitly self-merged only inside your exclusive lane with the issue linked.
- Follow-up work is a **new** issue, not a zombie comment.
- You `@mentioned` anyone whose contract you changed.
