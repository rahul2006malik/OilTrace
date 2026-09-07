/**
 * OilTrace Canonical Data Contract (v2)
 *
 * Single Source of Truth for all entity schemas across Backend (Python/Pydantic)
 * and Frontend (TypeScript/React).
 *
 * CI and pre-demo checks enforce exact parity using scripts/check_contract_sync.py.
 * Every field carries a verified _source and provenance discipline.
 */

// ============================================================================
// 1. SLICK DETECTION
// ============================================================================

export interface SlickDetection {
  spill_id: string;
  detected_at: string;              // ISO8601 UTC — from real SAR product metadata
  geometry: {
    type: 'Polygon' | 'MultiPolygon';
    coordinates: number[][][] | number[][][][];
  };                                // _source: real segmenter output, never invented
  centroid: [number, number];       // [lon, lat], computed from geometry
  area_km2: number;                 // _source: geodesic area of geometry
  elongation_ratio: number;
  oil_confidence: number;           // 0-1, _source: classifier_prob * mean_seg_prob
  thickness_class: 'sheen' | 'thin' | 'thick';
  source_scene_id: string;
  lookalike_suppressed: boolean;
  data_provenance: 'real_detector' | 'real_uploaded_fixture';  // NEVER 'synthetic' for this object
}

// ============================================================================
// 2. DRIFT ENSEMBLE & SIMULATION
// ============================================================================

export interface DriftEnsembleMember {
  member_id: number;
  windage_coefficient: number;      // _source: sampled per-member, real value used in that run
  current_scale: number;
  backward_track: { lon: number; lat: number; t: string }[];  // full subsampled path, not just endpoint
}

export interface DriftRun {
  spill_id: string;
  forcing: {
    current_dataset: string;        // e.g. "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m"
    wind_dataset: string;           // e.g. "ERA5 reanalysis-era5-single-levels"
    window_start: string;
    window_end: string;
  };
  ensemble_size: number;
  members_complete: number;         // honest — how many of ensemble_size actually finished full duration
  members_dropped: number;
  members: DriftEnsembleMember[];   // real per-member data for the Physics Inspector, not just KDE output
  origin_zone: {
    p50: { type: 'Polygon'; coordinates: number[][][] };
    p75: { type: 'Polygon'; coordinates: number[][][] };
    p90: { type: 'Polygon'; coordinates: number[][][] };
    estimated_onset_time: string;
    estimated_onset_spread_hours: number;
    age_method: 'fay_spreading_inversion';   // always disclose the method
  };
}

// ============================================================================
// 3. ATTRIBUTION, RECONSTRUCTION & EVIDENCE
// ============================================================================

export interface EvidenceTrace {
  proximity_score: number;
  path_match_score: number;         // 4D ray-trace score (route_reconstruction.py)
  confession_match_score: number;   // forward-sim IoU
  anomaly_score: number;
  vessel_type_prior: number | null;
  dominant_factor: string;
  shap_explanation: Record<string, number> | null;
  counterfactuals: string[];
  narrative: string;                // generated ONLY from real fields, never hand-templated by score bucket
}

export interface Candidate {
  vessel_id: string;                // MMSI
  vessel_name: string | null;
  imo: string | null;
  flag_country: string | null;
  vessel_type: string | null;
  last_known_position: [number, number] | null;
  ais_positions: {
    timestamp: string;
    lat: number;
    lon: number;
    sog: number;
    cog: number;
    is_reconstructed: boolean;
  }[];
  route_reconstruction: {
    intersects_50pct: boolean;
    intersects_75pct: boolean;
    intersects_90pct: boolean;
    min_distance_km: number;
    ray_trace_score: number;
  } | null;
  suspicion_score: number | null;
  confidence_interval: [number, number] | null;
  confidence_interval_method: string;   // e.g. "placeholder_width_pending_bootstrap" — DISCLOSE, don't hide
  evidence_trace: EvidenceTrace;
  proximate_but_absent_at_origin: boolean;
  data_provenance: 'real_gfw' | 'real_aisstream_live' | 'synthetic_fallback';  // mandatory, rendered as badge
}

export interface AttributionResult {
  spill_id: string;
  candidates: Candidate[];
  dark_vessel_alert: boolean;
  top_k_recovery: {
    k: number;
    recovered: boolean | null;
    confidence: number | null;
  };
  real_vessel_fraction: number;     // e.g. 0.87 — computed, shown honestly in UI header
}

// ============================================================================
// 4. EVIDENCE DOSSIER (CRYPTOGRAPHIC EXPORT)
// ============================================================================

export interface EvidenceDossier {
  spill_id: string;
  generated_at: string;
  payload_sha256: string;           // COMPUTED from the actual JSON payload at export time — never a constant
  detection: SlickDetection;
  drift: DriftRun;
  attribution: AttributionResult;
}

// ============================================================================
// 5. DRIFT PHYSICS AT POINT (HUD CARD)
// ============================================================================

export interface PhysicsAtPoint {
  query: {
    lon: number;
    lat: number;
    time: string;
  };
  current: {
    u: number;                      // m/s east-west
    v: number;                      // m/s north-south
    speed_ms: number;               // velocity magnitude
    speed_knots: number;
    direction_deg: number;          // nautical ocean current bearing (towards)
    source_dataset: string;
  };
  wind: {
    u10: number;                    // m/s
    v10: number;                    // m/s
    speed_ms: number;
    direction_deg: number;          // meteorological wind direction
    source_dataset: string;
  };
  particle_velocity: {
    u_net: number;
    v_net: number;
    speed_ms: number;
    bearing_deg: number;
    windage_coefficient_used: number; // sampled alpha (e.g. 0.030)
  };
}
