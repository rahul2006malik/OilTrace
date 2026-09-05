# SIH26143 — Data Contracts (schemas.md)

**Status:** v1 — initial contract, established before deep implementation in any subsystem.
**Owner:** Integration+Frontend thread. Any change to this file follows the schema-change
protocol (Orchestration Playbook, Section 6) — propose in the Orchestrator thread, check
downstream impact, update this file, ping affected threads before they build further
against the old shape.

This file is the single source of truth for the three handoff artifacts between
subsystems. Every subsystem builds and tests against a **mocked upstream file** matching
these shapes from hour one — no subsystem should be blocked waiting on another to finish.

Pipeline: `Detection → Drift → Attribution → Frontend`

---

## 1. `slick_detection.geojson`

**Producer:** Detection
**Consumers:** Drift, Attribution

```json
{
  "spill_id": "string",
  "detected_at": "ISO8601 UTC",
  "geometry": "GeoJSON Polygon (WGS84)",
  "centroid": [0.0, 0.0],
  "area_km2": 0.0,
  "elongation_ratio": 0.0,
  "oil_confidence": 0.0,
  "lookalike_suppressed": false,
  "thickness_class": "sheen | thin | thick",
  "source_scene_id": "string"
}
```

**Field notes:**
- `centroid` is `[lon, lat]`.
- `oil_confidence` is a float in `[0, 1]`.
- `thickness_class` is an enum: `sheen | thin | thick` — proxy from VV/VH damping ratio, not full polarimetric decomposition (Project Doc §5.5).
- `source_scene_id` is the Sentinel-1 product identifier — as of mid-2026 this is an **S1C/S1D** scene, not S1A (retired 29–30 Jun 2026). Don't hardcode S1A anywhere.
- `elongation_ratio` feeds Drift's forward-hypothesis routing and Attribution's baseline scorer (long/linear vs. blob-shaped).

---

## 2. `origin_ensemble.json` + `forward_cone.geojson`

**Producer:** Drift
**Consumer:** Attribution

```json
{
  "spill_id": "string",
  "origin_probability_cone": "GeoJSON polygon set with probability levels",
  "age_estimate_hours": {"value": 0.0, "confidence_range": [0.0, 0.0]},
  "ensemble_members": [{"lon": 0.0, "lat": 0.0, "time": "ISO8601"}],
  "forward_hypotheses": [
    {"vessel_id": "string", "simulated_footprint": "GeoJSON polygon", "shape_overlap_score": 0.0}
  ]
}
```

**Field notes:**
- `spill_id` must match the `slick_detection.geojson` it was derived from — this is the join key across all three artifacts.
- `origin_probability_cone` is a KDE-rendered polygon set (`scipy.stats.gaussian_kde` over ensemble endpoints), not a single point or line. A single-point/single-line cone is a contract violation, not a simplification.
- `age_estimate_hours` is a heuristic (area/perimeter growth trends), **not** derived from the backward run itself — backward drift gives position, not age (Project Doc §6.2/§6.3).
- `forward_hypotheses[].shape_overlap_score` is the "confession simulation" match — IoU between simulated particle-density raster and the observed mask (rigorous), or centroid-distance + area-ratio + orientation (fast fallback). Either is valid at this contract level; Attribution should not assume which one was used.

---

## 3. `attribution_result.json`

**Producer:** Attribution
**Consumer:** Frontend / Integration

```json
{
  "spill_id": "string",
  "candidates": [
    {
      "vessel_id": "string (MMSI where real)",
      "vessel_name": "string, from GFW Vessels API where resolvable",
      "last_known_position": [0.0, 0.0],
      "suspicion_score": 0.0,
      "confidence_interval": [0.0, 0.0],
      "evidence_trace": {
        "proximity_score": 0.0,
        "confession_match_score": 0.0,
        "anomaly_score": 0.0,
        "vessel_type_prior": 0.0,
        "dominant_factor": "string"
      },
      "data_provenance": "real_gfw | real_aisstream_live | synthetic_fallback"
    }
  ],
  "dark_vessel_alert": false,
  "top_k_recovery": {"k": 3, "recovered": false, "confidence": 0.0}
}
```

**Field notes:**
- `last_known_position` is `[lon, lat]` where available from GFW presence or AISstream transponder pings, enabling exact point-marker rendering on the nautical chart without approximating from forward dispersion footprints.
- `data_provenance` is **mandatory per-candidate**, not a global disclaimer — this is the field that answers "is this real data?" live, on demand (Project Doc §7.4, §13.2). Never omit it and never default it silently.
- `dark_vessel_alert: true` is a first-class output state, not an error/empty state — when true, `candidates` may still contain scored-but-below-threshold entries; the frontend renders the dark-vessel state distinctly either way.
- `confidence_interval` comes from bootstrap resampling of the drift ensemble members (Project Doc §7.4) — reusing Subsystem 2's ensemble, not a separately fabricated interval.
- `top_k_recovery` is only meaningful for **constructed validation scenarios** where the true test vessel is known (Project Doc §11.2) — in a live/unknown scenario this object should be present but `recovered` is not applicable and should be treated as `null`/omitted by consumers, not coerced to `false`.

---

## 4. `POST /pipeline/run` request contract

**Consumer:** Integration (this is the request body Integration's `/pipeline/run`
endpoint accepts — distinct from the three producer→consumer artifacts above,
but part of this contract for the same reason: it's what lets Drift/Attribution
build against a stable shape without Detection's real service existing.)

```json
{
  "spill_id": "string",
  "location": {"lon": 0.0, "lat": 0.0},
  "detected_at": "ISO8601 UTC",
  "slick_geojson_ref": "string (path/URI) OR inline slick_detection.geojson object",
  "image_path": "optional string (path/URI to raw Sentinel-1 SAR TIFF for live detection)"
}
```

**Field notes:**
- **Live Detection support**: When `image_path` is provided, the backend can invoke live cascade detection (`POST /detection/predict` or inline) to dynamically extract the slick geometry and metrics in real time (~3.5 seconds) rather than loading a precomputed file.
- `slick_geojson_ref` is either a path/URI to an already-written
  `slick_detection.geojson`, or that same object inlined directly in the
  request body. Both are valid at this contract level — same pattern as
  `forward_hypotheses[].shape_overlap_score` in Section 2 (rigorous-or-fallback
  computation method, either valid downstream). Whichever form is used, the
  content must still satisfy the `slick_detection.geojson` shape in Section 1
  once resolved.
- `location` and `detected_at` are carried at the top level (not solely
  inside the resolved GeoJSON) so `/pipeline/run` can validate/route a request
  before it has to open or fetch `slick_geojson_ref` at all.
- `spill_id` here must match the `spill_id` inside the resolved
  `slick_detection.geojson` — same join-key rule as Cross-cutting rule 1. A
  mismatch is a validation error, not a silent overwrite in either direction.

---

## Cross-cutting rules

1. **`spill_id` is the join key** across all three artifacts end-to-end. Every producer must propagate the exact `spill_id` it received/generated; never regenerate a new one mid-pipeline.
2. **No silent synthetic substitution.** Any field ultimately sourced from `synthetic_fallback` data must carry that tag at the point it enters `attribution_result.json`. If a subsystem's mocked-upstream testing data leaks into a real run, that's a bug, not a variant.
3. **`/pipeline/run` (Integration) validates each artifact against this file before passing it downstream** and raises a specific, named-field error on mismatch — no silent broken frontend state (Project Doc §8.3).
4. **Changing this file:** Maintain backward compatibility with downstream modules (Detection -> Drift -> Attribution -> UI). Confirm downstream impact before altering data structures.

---

*v1.2 — [September 4, 2026]. Log subsequent changes below.*

## Changelog
- v1: Initial data contract specification.
- v1.1: added Section 4, `POST /pipeline/run` request contract — `slick_geojson_ref`
  (path or inline `slick_detection.geojson`) added alongside `spill_id` +
  `location` + `detected_at`. Clarifies Detection runs offline on Kaggle and
  never calls this endpoint directly; its contract obligation ends at producing
  `slick_detection.geojson`. No change to the three producer→consumer artifact
  shapes (Sections 1–3).
- v1.2: Added `last_known_position: [lon, lat]` to Section 3 `Candidate` contract,
  enabling exact nautical map plotting from real GFW/AISstream pings. Added optional
  `image_path` to Section 4 `POST /pipeline/run` and added live `POST /detection/predict`
  route specification for real-time SAR radar detection.
