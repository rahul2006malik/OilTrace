/**
 * OilTrace Canonical Data Contract (v2.0)
 *
 * Single Source of Truth TypeScript interfaces matching contracts/schema.ts.
 * Enforced strictly by scripts/check_contract_sync.py.
 */

// ============================================================================
// 1. SLICK DETECTION (§1)
// ============================================================================

export type ThicknessClass = 'sheen' | 'thin' | 'thick';
export type DetectionProvenance = 'real_detector' | 'real_uploaded_fixture';

export interface SlickDetection {
  spill_id: string;
  detected_at: string;              // ISO8601 UTC
  geometry: {
    type: 'Polygon' | 'MultiPolygon';
    coordinates: number[][][] | number[][][][];
  };
  centroid: [number, number];       // [lon, lat]
  area_km2: number;                 // Geodesic area in km²
  elongation_ratio: number;
  oil_confidence: number;           // 0.0 to 1.0
  thickness_class: ThicknessClass;
  source_scene_id: string;
  lookalike_suppressed: boolean;
  data_provenance: DetectionProvenance;
}

// ============================================================================
// 2. DRIFT RUN & ENSEMBLE (§2)
// ============================================================================

export interface DriftTrackPoint {
  lon: number;
  lat: number;
  t: string;
}

export interface DriftEnsembleMember {
  member_id: number;
  windage_coefficient: number;
  current_scale: number;
  backward_track: DriftTrackPoint[];
}

export interface DriftOriginZone {
  p50: { type: 'Polygon'; coordinates: number[][][] };
  p75: { type: 'Polygon'; coordinates: number[][][] };
  p90: { type: 'Polygon'; coordinates: number[][][] };
  estimated_onset_time: string;
  estimated_onset_spread_hours: number;
  age_method: 'fay_spreading_inversion';
}

export interface DriftRun {
  spill_id: string;
  forcing: {
    current_dataset: string;
    wind_dataset: string;
    window_start: string;
    window_end: string;
  };
  ensemble_size: number;
  members_complete: number;
  members_dropped: number;
  members: DriftEnsembleMember[];
  origin_zone: DriftOriginZone;
}

// ============================================================================
// 3. ATTRIBUTION, RECONSTRUCTION & CANDIDATES (§3)
// ============================================================================

export type CandidateProvenance = 'real_gfw' | 'real_aisstream_live' | 'synthetic_fallback';

export interface EvidenceTrace {
  proximity_score: number;
  path_match_score: number;
  confession_match_score: number;
  anomaly_score: number;
  vessel_type_prior: number | null;
  dominant_factor: string;
  shap_explanation: Record<string, number> | null;
  counterfactuals: string[];
  narrative: string;
}

export interface AisPosition {
  timestamp: string;
  lat: number;
  lon: number;
  sog: number;
  cog: number;
  is_reconstructed: boolean;
}

export interface RouteReconstruction {
  intersects_50pct: boolean;
  intersects_75pct: boolean;
  intersects_90pct: boolean;
  min_distance_km: number;
  ray_trace_score: number;
}

export interface VoyageMilestone {
  label: string;
  timestamp: string;
  coordinates: [number, number];
  type: 'departure' | 'blackout_start' | 'blackout_end' | 'spill_intersect' | 'current_position';
  note?: string;
}

export interface SogProfilePoint {
  timestamp: string;
  sog_knots: number;
  is_discharge_window: boolean;
}

export interface Candidate {
  vessel_id: string;                // MMSI
  vessel_name: string | null;
  imo: string | null;
  flag_country: string | null;
  flag_state?: string | null;
  vessel_type: string | null;
  last_known_position: [number, number] | null;
  ais_positions: AisPosition[];
  route_reconstruction: RouteReconstruction | null;
  suspicion_score: number | null;
  confidence_interval: [number, number] | null;
  confidence_interval_method: string;
  evidence_trace: EvidenceTrace;
  proximate_but_absent_at_origin: boolean;
  data_provenance: CandidateProvenance;
  departure_port?: string | null;
  destination_port?: string | null;
  voyage_status?: string | null;
  voyage_milestones?: VoyageMilestone[] | null;
  sog_profile?: SogProfilePoint[] | null;
}

export interface TopKRecovery {
  k: number;
  recovered: boolean | null;
  confidence: number | null;
}

export interface NavalInterceptAdvisory {
  jurisdiction_zone: string;
  sovereign_state: string;
  statutory_authority: string;
  operational_directive: string;
  // B10 FIX: coordinating_command was missing in some pipeline responses, make it optional
  coordinating_command?: string;
  tactical_urgency: 'IMMEDIATE' | 'STANDARD' | 'ROUTINE';
  admiralty_evidence_hash: string;
}

export interface AttributionResult {
  spill_id: string;
  candidates: Candidate[];
  dark_vessel_alert: boolean;
  top_k_recovery: TopKRecovery;
  real_vessel_fraction: number;     // 0.0 to 1.0
  origin_ensemble?: any;
  trajectories?: any[];
  naval_intercept_advisory?: NavalInterceptAdvisory;
  dark_vessel_intelligence?: any;
  comparative_baseline?: any;
}

// ============================================================================
// 4. EVIDENCE DOSSIER (CRYPTOGRAPHIC EXPORT §4)
// ============================================================================

export interface EvidenceDossier {
  spill_id: string;
  generated_at: string;
  payload_sha256: string;
  detection: SlickDetection;
  drift: DriftRun;
  attribution: AttributionResult;
}

// ============================================================================
// 5. DRIFT PHYSICS AT POINT (§5)
// ============================================================================

export interface MetoceanVector {
  u: number;
  v: number;
  speed_ms: number;
  speed_knots: number;
  direction_deg: number;
  source_dataset: string;
}

export interface WindVector {
  u10: number;
  v10: number;
  speed_ms: number;
  direction_deg: number;
  source_dataset: string;
}

export interface ParticleVelocityVector {
  u_net: number;
  v_net: number;
  speed_ms: number;
  bearing_deg: number;
  windage_coefficient_used: number;
}

export interface PhysicsAtPoint {
  query: {
    lon: number;
    lat: number;
    time: string;
  };
  current: MetoceanVector;
  wind: WindVector;
  particle_velocity: ParticleVelocityVector;
}

// ============================================================================
// 6. SYSTEM HEALTH
// ============================================================================

export interface SystemHealth {
  status: 'ok' | 'degraded' | 'error';
  subsystems: {
    detection_available: boolean;
    drift_available: boolean;
    attribution_available: boolean;
  };
  cache_dir: string;
}

// ============================================================================
// 7. SCENARIO & UI NAVIGATION
// ============================================================================

export type ScreenType = 'overview' | 'scenarios' | 'detection' | 'simulation' | 'surveillance' | 'analysis' | 'vessels' | 'reports' | 'governance' | 'login';

export interface ScenarioItem {
  scenario_id: string;
  name: string;
  spill_id: string;
  bbox: [number, number, number, number];
  detected_at: string;
  has_drift_ensemble: boolean;
  has_real_gfw: boolean;
  description?: string;
  location_name?: string;
  // B10 FIX: Add region field used by TacticalMap.tsx cursor HUD label
  region?: string;
  spill_area_km2?: number;
  suspect_count?: number;
  tags?: string[];
  slick_geojson?: SlickDetection;
}

// ============================================================================
// 8. METOCEAN GRID & SATELLITE PASSES
// ============================================================================

export interface MetoceanGridPoint {
  lon: number;
  lat: number;
  u_wind: number;
  v_wind: number;
  wind_speed: number;
  wind_deg: number;
  u_curr: number;
  v_curr: number;
  curr_speed: number;
  curr_deg: number;
}

export interface MetoceanGridResponse {
  status: string;
  count: number;
  bbox: number[];
  points: MetoceanGridPoint[];
}

export interface SatellitePassItem {
  satellite_name: string;
  sensor_band: string;
  acquisition_time_utc: string;
  elevation_deg: number;
  swath_overlap_pct: number;
  status: string;
}

export interface SatellitePassesResponse {
  spill_id: string;
  target_centroid: [number, number];
  scheduled_passes: SatellitePassItem[];
}

