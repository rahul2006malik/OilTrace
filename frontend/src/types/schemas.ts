/**
 * Data contracts for OilTrace.
 *
 * Source of truth: `schemas.md` v1.2 (Data Contracts) and `backend/app/models.py`
 * (Pydantic mirror of `attribution_result.json`). Do not drift from either —
 * if a field changes here, it must change there first per the Orchestration
 * Playbook §6 schema-change protocol. This file intentionally does not widen
 * any field to `any` beyond what schemas.md itself leaves open-ended
 * (`forward_hypotheses[].shape_overlap_score`'s computation method, etc).
 */

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

/** `[lon, lat]`, WGS84 — the convention used throughout schemas.md. */
export type LonLat = [number, number];

export type DataProvenance = "real_gfw" | "real_aisstream_live" | "synthetic_fallback";

// ---------------------------------------------------------------------------
// 1. slick_detection.geojson (Producer: Detection — schemas.md §1)
// ---------------------------------------------------------------------------

export type ThicknessClass = "sheen" | "thin" | "thick";

export interface SlickDetection {
  spill_id: string;
  /** ISO8601 UTC. */
  detected_at: string;
  /** GeoJSON Polygon, WGS84. */
  geometry: GeoJSON.Polygon;
  centroid: LonLat;
  area_km2: number;
  elongation_ratio: number;
  /** Float in [0, 1]. */
  oil_confidence: number;
  /** Proxy from VV/VH damping ratio, not full polarimetric decomposition (Project Doc §5.5). */
  thickness_class: ThicknessClass;
  lookalike_suppressed: boolean;
  /** Sentinel-1 product identifier. As of mid-2026 this is S1C/S1D — never hardcode S1A. */
  source_scene_id: string;
}

// ---------------------------------------------------------------------------
// 2. origin_ensemble.json + forward_cone.geojson (Producer: Drift — schemas.md §2)
// ---------------------------------------------------------------------------

export interface AgeEstimateHours {
  value: number;
  confidence_range: [number, number];
}

export interface EnsembleMember {
  lon: number;
  lat: number;
  /** ISO8601. */
  time: string;
}

export interface ForwardHypothesis {
  vessel_id: string;
  simulated_footprint: GeoJSON.Polygon;
  /**
   * "Confession simulation" match — either rigorous IoU between simulated
   * particle-density raster and observed mask, or a fast centroid-distance +
   * area-ratio + orientation fallback. Both are valid at this contract level;
   * the frontend must not assume which one produced the score.
   */
  shape_overlap_score: number;
}

export interface OriginEnsemble {
  spill_id: string;
  /** KDE-rendered polygon set with probability levels — never a single point or line. */
  origin_probability_cone: GeoJSON.FeatureCollection;
  age_estimate_hours: AgeEstimateHours;
  ensemble_members: EnsembleMember[];
  forward_hypotheses: ForwardHypothesis[];
}

/**
 * One backward-drift particle track, reshaped from `ensemble_members` for
 * polyline rendering on the tactical chart. Not a schemas.md artifact itself —
 * a frontend-local projection of Section 2's ensemble data.
 */
export interface TrajectoryMember {
  member: number;
  lons: number[];
  lats: number[];
}

// ---------------------------------------------------------------------------
// 3. attribution_result.json (Producer: Attribution — schemas.md §3 / models.py)
// ---------------------------------------------------------------------------

export interface EvidenceTrace {
  proximity_score: number;
  confession_match_score: number;
  anomaly_score: number;
  vessel_type_prior: number | null;
  dominant_factor: string;
}

export interface Candidate {
  /** MMSI where real. */
  vessel_id: string;
  /** From GFW Vessels API where resolvable. */
  vessel_name: string | null;
  last_known_position: LonLat | null;
  suspicion_score: number | null;
  confidence_interval: [number, number] | null;
  evidence_trace: EvidenceTrace;
  /** Mandatory per-candidate — never omitted, never silently defaulted. */
  data_provenance: DataProvenance;
}

export interface TopKRecovery {
  k: number;
  /** Only meaningful for constructed validation scenarios — null in live/unknown scenarios. */
  recovered: boolean | null;
  confidence: number | null;
}

export interface AttributionResult {
  spill_id: string;
  candidates: Candidate[];
  /** First-class output state, not an error/empty state. */
  dark_vessel_alert: boolean;
  top_k_recovery: TopKRecovery;
  origin_ensemble?: OriginEnsemble;
  trajectories?: TrajectoryMember[];
}

// ---------------------------------------------------------------------------
// 4. POST /pipeline/run request contract (schemas.md §4)
// ---------------------------------------------------------------------------

export interface LocationInput {
  lon: number;
  lat: number;
}

/** Path/URI to a slick_detection.geojson file, or the object inlined directly. */
export type SlickGeojsonRef = string | SlickDetection | Record<string, unknown>;

export interface PipelineRunRequest {
  spill_id: string;
  location: LocationInput;
  /** ISO8601 UTC. */
  detected_at: string;
  slick_geojson_ref?: SlickGeojsonRef;
  /** Path/URI to a raw Sentinel-1 SAR TIFF scene, for live detection. */
  image_path?: string;
}

export interface DetectionPredictRequest {
  image_path: string;
}

export interface DetectionPredictResponse {
  has_oil: boolean;
  oil_confidence: number;
  geojson?: SlickDetection | GeoJSON.FeatureCollection | Record<string, unknown>;
  execution_time_seconds: number;
}

// ---------------------------------------------------------------------------
// Scenario metadata (frontend/backend convenience wrapper, not a schemas.md artifact)
// ---------------------------------------------------------------------------

export interface ScenarioSummary {
  scenario_id: string;
  name: string;
  spill_id: string;
  /** [minLon, minLat, maxLon, maxLat]. */
  bbox: [number, number, number, number];
  /** ISO8601 UTC. */
  detected_at: string;
}

/** Full resolved payload for a single scenario, as returned by GET /scenarios/:id. */
export interface ScenarioData {
  scenario: ScenarioSummary;
  slick: SlickDetection;
  origin: OriginEnsemble;
  attribution: AttributionResult;
}

// ---------------------------------------------------------------------------
// Sandbox / what-if weighting (attribution scorer sliders, right-column UI)
// ---------------------------------------------------------------------------

export interface SandboxWeights {
  proximity: number;
  confession_match: number;
  anomaly: number;
  vessel_type_prior: number;
}
