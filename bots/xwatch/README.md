# XWatch (`bots/xwatch/`)

Issue #18. Fixture / RSS social watcher. **No live X API. No Grok swarm.**

`X_BEARER_TOKEN` is ignored even if present. Mock tweets come from
`fixtures/galveston-flood.json`. Optional `--rss` reads a local RSS file
or a non-X http(s) feed. Matching flood/surge items in the Houston–Galveston
geofence are posted onto the #11 alert bus (`POST /api/alerts`).

A fixture tweet about Galveston flooding uses `source: x`, severity
`critical` (storm surge / water over roadway), and
`dedupe_key: x:fixture-galveston-flood-1`. RSS items use `source: news`.

## Run

From `bots/`:

```bash
# Demo inject. File sink does not need the sidecar:
python -m xwatch --once --sink file --out /tmp/xwatch-alerts.jsonl --ignore-watches

# Same fixture onto the alert bus (sidecar on :8000):
python -m xwatch --once --ignore-watches

# RSS fixture instead of (or with) JSON:
python -m xwatch --once --no-fixture --rss xwatch/fixtures/galveston-flood.rss --sink file --out /tmp/xwatch-alerts.jsonl --ignore-watches
```

`--sink http` (default) posts to `$ALERTS_BASE_URL/api/alerts`. If the
registry is up and no watch lists source `x` or `news`, nothing is posted.
Pass `--ignore-watches` for the demo inject.

## Proof

```bash
python -m unittest tests.test_xwatch_fixture -v
```
