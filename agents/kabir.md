# agent-kabir

- Human: Kabir
- GitHub: `@buzzkabir`
- Grok Bot name: `Grokathon Frontend`
- Owns: `aquatic-sustainability/backend/static/` (the BDBI vanilla JS UI)
- Does **not** own: empty repo-root `frontend/` (stub marker only — do not implement product UI there)
- Reads: `shared/` for API types

## You do

- Sync to latest `origin/main` before you edit or push (`git fetch origin && git pull --ff-only` or rebase).
- **Build on the existing static UI.** Add `/safety` (drawer, camera pins, alert feed) without destroying the old flood/coral/oil pages — judges need both.
- Consume backend contracts from `shared/`; if the contract is wrong, ping `@DevanshuShahs` on the contract issue — do not silently reshape the API.
- Mock in static JS only until the Flask route lands. Do not start a parallel React app in `/frontend`.

## You never

- Edit Flask Python under `aquatic-sustainability/backend/` (except `static/`) or `bots/`.
- Restyle/rewrite files another open `CLAIM` already lists.

## How others ping you

```
@buzzkabir need a screen for <x>. issue #n. mock is fine.
CLAIM aquatic-sustainability/backend/static/...
```
