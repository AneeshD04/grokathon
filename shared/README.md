# shared/

Cross-lane contracts (API types, event names, env keys).

**No drive-by edits.** Open a `lane:shared` Task, `@mention` every lane that consumes the contract, wait for a `CLAIM`.

Issue **#8** holds the exclusive lock on this directory. Schemas are JSON Schema draft 2020-12, one file per record.

## Schemas

### [alert.schema.json](alert.schema.json)

Stored alert. Required: `id`, `ts`, `geofence_id`, `title`, `summary`, `evidence`, `dedupe_key`, plus `source`, `severity`, `lat`, `lon`.

`source` is `camera | nws | usgs | x | model | news | places | transtar`. `severity` is `info | watch | warning | critical`.

`evidence.thumb_url` is an optional http(s) URL. `evidence.raw` is an open object (at most 32 keys). Optional model fields on `evidence`: `model`, `endpoint`, `max_prob`, `threshold`, `inputs`, `latency`, `synthetic`, `trained`. Optional `impacted_businesses[]` items require `place_id`, `name`, `types`, `lat`, `lon`.

`POST /api/alerts` omits `id` and may omit `ts`. The bus mints both. This file describes the stored record.

### [camera.schema.json](camera.schema.json)

Required: `id`, `name`, `lat`, `lon`, `still_url`, `source`. Optional: `hls_url`, `geofence_id`.

`source` is the feed: `transtar | fl511 | ndbc | webcoos | usgs`. That list is not the alert `source` enum.

### [watch.schema.json](watch.schema.json)

Stored watch. Required: `id`, `geofence_id`, `sources` (at least one), `camera_ids` (may be empty), `created_at`. At least one of `bbox` or `county`. `bbox` is `[minLon, minLat, maxLon, maxLat]`.

`sources` uses the alert `source` enum, including `transtar`. An empty `camera_ids` list means every camera on that watch.

### [org.schema.json](org.schema.json)

Notify roster contact. Required: `name`, `type`, `county`, `email`, `phone`. `email` and `phone` are nullable. `type` is `county_em | nws | uscg | 311`. These contacts are display-only.

### [business.schema.json](business.schema.json)

Places result used by `POST /api/businesses/nearby`. Required: `place_id`, `name`, `lat`, `lon`, `phone`, `website`, `types`, `maps_url`. `phone` and `website` are nullable. The field is `phone`, not `formatted_phone_number`.

### [resident.schema.json](resident.schema.json)

One opted-in resident. Required: `id`, `name`. Optional: `phone`, `email`, `lat`, `lon`, `geofence_id`. A region's list may be empty.

### [notify-log.schema.json](notify-log.schema.json)

Dry-run send log. Required: `timestamp`, `mode` (`dry-run-logged` only), `ipaws_stub`, `recipients` (`businesses`, `residents`, `orgs`), `drafts`. `additionalProperties` is false. The approval PIN is not a field and must not be stored on the log.

## TranStar

`transtar` is a legal `alert.source` and a legal watch `sources` value. Roadway flood warnings are that source.

`bots/camwatch/flood.py` still posts `source=usgs` with `evidence.raw.feed` set to `transtar-flood-warning` until that watcher switches. The sidecar `Source` enum in `backend/app/models.py` does not include `transtar` yet. Both of those files belong to other claims.
