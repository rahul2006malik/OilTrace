# SIH26143 — Backend (Integration+Frontend thread)

**Status: stub.** One endpoint, `POST /pipeline/run`, returns a hardcoded
placeholder shaped exactly like `attribution_result.json` (see `schemas.md`
in this directory). Detection, Drift, and Attribution are **not** called yet.
What's real here is the request/response *contract* and the validation
behavior — that's the point of building this now, before there's real logic
to plug in.

## Run it

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Interactive docs at `http://127.0.0.1:8000/docs`.

## Endpoints

- `GET /health` — liveness check.
- `POST /pipeline/run` — the stub. See below.

## `POST /pipeline/run`

**Request:**

```json
{
  "spill_id": "spill_001",
  "location": {"lon": 72.4865, "lat": 18.7715},
  "detected_at": "2026-08-27T10:00:00Z"
}
```

**Response (200)** — shape-identical to `attribution_result.json`, values
hardcoded, `data_provenance` honestly tagged `synthetic_fallback` since
nothing here is computed yet:

```json
{
  "spill_id": "spill_001",
  "candidates": [
    {
      "vessel_id": "STUB-000000000",
      "vessel_name": "Placeholder Vessel (stub — no attribution run yet)",
      "suspicion_score": 0.0,
      "confidence_interval": [0.0, 0.0],
      "evidence_trace": {
        "proximity_score": 0.0,
        "confession_match_score": 0.0,
        "anomaly_score": 0.0,
        "vessel_type_prior": 0.0,
        "dominant_factor": "none — stub response, subsystems not wired in yet"
      },
      "data_provenance": "synthetic_fallback"
    }
  ],
  "dark_vessel_alert": false,
  "top_k_recovery": {"k": 3, "recovered": null, "confidence": 0.0}
}
```

**Malformed request (422)** — named-field errors, per schemas.md's
"no silent broken frontend state" rule:

```bash
curl -s -X POST http://127.0.0.1:8000/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"location": {"lon": 72.4865, "lat": 18.7715}, "detected_at": "2026-08-27T10:00:00Z"}'
```

```json
{
  "error": "validation_failed",
  "detail": "Input did not match the /pipeline/run contract. See 'fields' for exactly what failed.",
  "fields": [
    {"field": "spill_id", "message": "Field required", "type": "missing"}
  ]
}
```

Tested cases: missing required field, out-of-range lat/lon, and an
unparseable timestamp all produce a 422 naming the exact offending field —
never a generic 500, never a silently-defaulted value.

## Next steps (not in this stub)

Wire `run_pipeline()` in `app/main.py` to actually call Detection → Drift →
Attribution once those modules exist, validating each intermediate artifact
against `schemas.md` before passing it downstream (Cross-cutting rule 3) and
raising the same kind of named-field error on a contract mismatch as this
stub does for a bad request. Don't change the response shape without going
through the Orchestration Playbook §6 schema-change protocol first.
