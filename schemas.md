# OilTrace — Canonical Data Contract v2 (schemas.md)

**Status:** v2.0 — Canonical Single Source of Truth for Project OilTrace (SIH26143 — NTRO Problem Statement).  
**Enforcement:** Verified across Python Pydantic models (`backend/app/models.py`) and TypeScript interfaces (`frontend/src/types/index.ts`, `contracts/schema.ts`) via `scripts/check_contract_sync.py`.

---

## 1. `slick_detection.geojson` (Detection Output)

**Producer:** Detection / Segmentation Cascade  
**Consumers:** Drift, Attribution, Command Center UI

```json
{
  "spill_id": "string",
  "detected_at": "ISO8601 UTC (from real SAR product metadata)",
  "geometry": {
    "type": "Polygon | MultiPolygon",
    "coordinates": "[[[lon, lat], ...]]"
  },
  "centroid": [0.0, 0.0],
  "area_km2": 0.0,
  "elongation_ratio": 0.0,
  "oil_confidence": 0.0,
  "thickness_class": "sheen | thin | thick",
  "source_scene_id": "string (Sentinel-1C/1D product ID)",
  "lookalike_suppressed": false,
  "data_provenance": "real_detector | real_uploaded_fixture"
}
```

**Field Notes:**
- `centroid` is `[lon, lat]`.
- `area_km2` is the true geodesic area computed on WGS84 spheroid.
- `oil_confidence` is float in `[0, 1]` (`classifier_prob * mean_seg_prob`).
- `data_provenance` is strictly `'real_detector' | 'real_uploaded_fixture'` (never `'synthetic'`).

---

## 2. `origin_ensemble.json` (Drift Output)

**Producer:** Drift Subsystem (OpenDrift / backward_ensemble.py)  
**Consumers:** Attribution, Physics Inspector, Command Center Map

```json
{
  "spill_id": "string",
  "forcing": {
    "current_dataset": "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
    "wind_dataset": "ERA5 reanalysis-era5-single-levels",
    "window_start": "ISO8601 UTC",
    "window_end": "ISO8601 UTC"
  },
  "ensemble_size": 25,
  "members_complete": 25,
  "members_dropped": 0,
  "members": [
    {
      "member_id": 0,
      "windage_coefficient": 0.032,
      "current_scale": 1.0,
      "backward_track": [
        {"lon": 71.61, "lat": 18.42, "t": "2026-08-25T03:45:00Z"}
      ]
    }
  ],
  "origin_zone": {
    "p50": {"type": "Polygon", "coordinates": "[[[lon, lat], ...]]"},
    "p75": {"type": "Polygon", "coordinates": "[[[lon, lat], ...]]"},
    "p90": {"type": "Polygon", "coordinates": "[[[lon, lat], ...]]"},
    "estimated_onset_time": "ISO8601 UTC",
    "estimated_onset_spread_hours": 3.5,
    "age_method": "fay_spreading_inversion"
  }
}
```

**Field Notes:**
- `members` contains the complete subsampled trajectory of each ensemble member (powers the Physics Inspector build-up).
- `members_complete` and `members_dropped` transparently disclose ensemble completion health.
- `age_method` discloses `'fay_spreading_inversion'` (heuristic inversion, never claimed as direct observation).

---

## 3. `attribution_result.json` (Attribution Output)

**Producer:** Attribution Subsystem (scorer.py, route_reconstruction.py, gfw_client.py)  
**Consumers:** Backend API, Leaderboard, Evidence Dossier, PDF Exporter

```json
{
  "spill_id": "string",
  "candidates": [
    {
      "vessel_id": "string (MMSI where real)",
      "vessel_name": "string | null",
      "imo": "string | null",
      "flag_country": "string | null",
      "vessel_type": "string | null",
      "last_known_position": [0.0, 0.0],
      "ais_positions": [
        {
          "timestamp": "ISO8601 UTC",
          "lat": 0.0,
          "lon": 0.0,
          "sog": 0.0,
          "cog": 0.0,
          "is_reconstructed": false
        }
      ],
      "route_reconstruction": {
        "intersects_50pct": false,
        "intersects_75pct": false,
        "intersects_90pct": true,
        "min_distance_km": 1.2,
        "ray_trace_score": 0.88
      },
      "suspicion_score": 0.89,
      "confidence_interval": [0.82, 0.94],
      "confidence_interval_method": "placeholder_width_pending_bootstrap",
      "evidence_trace": {
        "proximity_score": 0.92,
        "path_match_score": 0.88,
        "confession_match_score": 0.84,
        "anomaly_score": 0.91,
        "vessel_type_prior": 0.85,
        "dominant_factor": "path_match_score",
        "shap_explanation": {"lane_deviation": 0.31, "dark_gap_duration": 0.28},
        "counterfactuals": ["AIS gap during reverse drift transit window"],
        "narrative": "Vessel exhibited an unannounced AIS gap intersecting the 90% drift origin zone."
      },
      "proximate_but_absent_at_origin": false,
      "data_provenance": "real_gfw | real_aisstream_live | synthetic_fallback"
    }
  ],
  "dark_vessel_alert": false,
  "top_k_recovery": {
    "k": 3,
    "recovered": true,
    "confidence": 0.89
  },
  "real_vessel_fraction": 0.87
}
```

**Field Notes:**
- `data_provenance` is strictly mandatory per candidate: `'real_gfw'`, `'real_aisstream_live'`, or `'synthetic_fallback'`.
- `real_vessel_fraction` is computed dynamically: `count(real_*) / len(candidates)`.
- `narrative` is generated algorithmically from real evidence factors — never templated by score bucket.

---

## 4. `EvidenceDossier` & Cryptographic Export

```json
{
  "spill_id": "string",
  "generated_at": "ISO8601 UTC",
  "payload_sha256": "64-character lowercase hex string",
  "detection": "SlickDetection object",
  "drift": "DriftRun object",
  "attribution": "AttributionResult object"
}
```

**Cryptographic Integrity Rule:**
- `payload_sha256` is computed by the server or export generator over the canonical JSON payload (`SHA-256`). Hardcoded hashes are strictly prohibited.
