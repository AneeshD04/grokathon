# agent-athithan

- Human: Athithan
- GitHub: **invite pending** — put the handle in `TEAM.md` then replace every `@Athithan` note
- Grok Bot name: `Grokathon Bots`
- Owns: `bots/` — Grok Bot wiring, CamWatch / X / gov watchers, live demo script
- Watchers **plug into** `aquatic-sustainability/` (call its `/api/*`, publish onto the alert bus). They do not replace the Flask app.
- Until invited: `@AneeshD04` is the relay. Agents still file `lane:athithan` issues.

## You do

- Sync to latest `origin/main` before you edit or push (`git fetch origin && git pull --ff-only` or rebase). Product lives in `aquatic-sustainability/`.
- Grok Bot routines and demo glue that sit **on top of** the BDBI app.
- Coordinate with `@buzzkabir` for `/safety` surfaces and `@DevanshuShahs` for `/api/watches` + `/api/alerts`.

## You never

- Drive-by edits in `aquatic-sustainability/backend/static/` or Flask Python.
- Create a second frontend or API outside `bots/` / the claimed Flask routes.

## How others ping you

Until the handle exists:

```
@AneeshD04 please forward to Athithan: <ask>
lane:athithan
files: bots/...
```

After invite:

```
@<athithan-handle> HANDOFF
need: <bot / demo step>
files: bots/...
```
