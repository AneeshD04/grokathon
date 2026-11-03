# agent-devanshu

- Human: Devanshu Shah
- GitHub: `@DevanshuShahs`
- Grok Bot name: `Grokathon Backend`
- Owns: `aquatic-sustainability/backend/` except `static/` (the BDBI Flask API)
- Does **not** own: empty repo-root `backend/` (stub marker only — do not implement product APIs there)
- Reads: `shared/` (changes only via `lane:shared`)

## You do

- Sync to latest `origin/main` before you edit or push (`git fetch origin && git pull --ff-only` or rebase). Product lives in `aquatic-sustainability/`.
- **Build on the existing Flask app** in `aquatic-sustainability/backend/`. Additive endpoints (cameras, watches, alerts, Safety Agent proxy). Do not rewrite DualCNN-LSTM or start a new server in `/backend`.
- Env for backend secrets: copy repo-root `.env.example` → `aquatic-sustainability/backend/.env` (gitignored).
- Publish contracts into `shared/` only after a `lane:shared` issue `@mentions` `@buzzkabir` (and Athithan if bots consume it).
- Reply on issues when `@DevanshuShahs` is pinged — even to say "claimed" or "not me".

## You never

- Edit `aquatic-sustainability/backend/static/` (Kabir) or `bots/` or rewrite `AGENTS.md`.
- Start a feature that already has an open Task. Comment instead.

## How others ping you

```
@DevanshuShahs HANDOFF
need: <endpoint / schema>
done-when: <contract + tests or a curl example>
files: aquatic-sustainability/backend/...
```
