# Places nearby

**Product path is Flask**, not this sidecar.

```bash
cd aquatic-sustainability/backend
python run.py
# POST http://127.0.0.1:5001/api/businesses/nearby
```

Implementation: `aquatic-sustainability/backend/app/places.py`. Lookup only — it does not send SMS. Unset Maps/Places key returns Galveston fixtures with no phone numbers.

Do not extend this FastAPI process.
