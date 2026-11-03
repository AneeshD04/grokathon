# Places nearby

`POST /api/businesses/nearby` is mounted on the port-8000 app. It lists businesses inside a bbox or polygon. It does not send SMS or email.

`GOOGLE_MAPS_API_KEY` calls Google Places Nearby (New), one request, at most 20 results, types `hospital`, `school`, `lodging`, `supermarket`, `gas_station`, and `pharmacy`. If the key is unset, the route returns a Galveston fixture list and does not invent phone numbers. Points outside the ring are dropped.

```bash
curl -s -X POST localhost:8000/api/businesses/nearby \
  -H 'content-type: application/json' \
  -d '{"bbox":[-95.0,29.2,-94.7,29.4]}'
```

`polygon` is `[[lon, lat], ...]` and wins when both fields are sent. `limit` defaults to 20.
