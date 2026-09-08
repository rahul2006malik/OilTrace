"""
Pydantic models for the Integration+Frontend backend.

Canonical Data Contract (v2.0) — Single Source of Truth matching:
  - contracts/schema.ts
  - schemas.md
Enforced strictly by scripts/check_contract_sync.py.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# /pipeline/run request & input models
# ---------------------------------------------------------------------------

class LocationInput(BaseModel):
    """Slick location, WGS84 lon/lat — mirrors the `centroid` convention used
    throughout schemas.md ([lon, lat])."""
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude, WGS84.")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude, WGS84.")


SlickGeojsonRef = Union[str, Dict[str, Any]]


class PipelineRunRequest(BaseModel):
    """Input to POST /pipeline/run."""
    spill_id: str = Field(..., min_length=1, description="Join key propagated across all pipeline artifacts.")
    location: LocationInput
    detected_at: datetime = Field(..., description="ISO8601 UTC detection timestamp.")
    slick_geojson_ref: Optional[SlickGeojsonRef] = Field(
        None,
        description="Path/URI to a slick_detection.geojson file, or the GeoJSON object inlined directly.",
    )
    image_path: Optional[str] = Field(
        None,
        description="Path/URI to a raw Sentinel-1 SAR TIFF scene on disk for live inference.",
    )


class DetectionPredictRequest(BaseModel):
    image_path: str = Field(..., description="Path to raw Sentinel-1 SAR TIFF image on disk.")


# ---------------------------------------------------------------------------
# 1. SlickDetection (Detection Contract §1)
# ---------------------------------------------------------------------------

ThicknessClass = Literal["sheen", "thin", "thick"]
DetectionProvenance = Literal["real_detector", "real_uploaded_fixture"]


class SlickDetection(BaseModel):
    spill_id: str
    detected_at: str
    geometry: Dict[str, Any]
    centroid: List[float] = Field(..., min_length=2, max_length=2)
    area_km2: float
    elongation_ratio: float
    oil_confidence: float
    thickness_class: ThicknessClass
    source_scene_id: str
    lookalike_suppressed: bool
    data_provenance: DetectionProvenance

    @model_validator(mode="before")
    @classmethod
    def _normalize_detection(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Canonical thickness class normalization
            tc = str(data.get("thickness_class", "sheen")).lower()
            if tc in ("none", "negligible"):
                data["thickness_class"] = "sheen"
            elif tc in ("rainbow", "metallic"):
                data["thickness_class"] = "thin"
            elif tc in ("true_color", "discontinuous_true_color"):
                data["thickness_class"] = "thick"
            elif tc not in ("sheen", "thin", "thick"):
                data["thickness_class"] = "sheen"

            # Strict provenance validation
            dp = str(data.get("data_provenance", "real_detector"))
            if dp not in ("real_detector", "real_uploaded_fixture"):
                data["data_provenance"] = "real_detector"

            # Strict [lon, lat] coordinate range validation
            centroid = data.get("centroid")
            if isinstance(centroid, (list, tuple)) and len(centroid) >= 2:
                lon = max(-180.0, min(180.0, float(centroid[0])))
                lat = max(-90.0, min(90.0, float(centroid[1])))
                data["centroid"] = [lon, lat]

            # Enforce oil_confidence clamp [0.0, 1.0]
            if "oil_confidence" in data and data["oil_confidence"] is not None:
                data["oil_confidence"] = max(0.0, min(1.0, float(data["oil_confidence"])))

            # Enforce area_km2 >= 0.0
            if "area_km2" in data and data["area_km2"] is not None:
                data["area_km2"] = max(0.0, float(data["area_km2"]))
        return data


# ---------------------------------------------------------------------------
# 2. Drift Models (Drift Contract §2)
# ---------------------------------------------------------------------------

class DriftTrackPoint(BaseModel):
    lon: float
    lat: float
    t: str


class DriftEnsembleMember(BaseModel):
    member_id: int
    windage_coefficient: float
    current_scale: float
    backward_track: List[Dict[str, Any]] = Field(default_factory=list)


class DriftForcingMeta(BaseModel):
    current_dataset: str
    wind_dataset: str
    window_start: str
    window_end: str


class DriftOriginZone(BaseModel):
    p50: Dict[str, Any]
    p75: Dict[str, Any]
    p90: Dict[str, Any]
    estimated_onset_time: str
    estimated_onset_spread_hours: float
    age_method: Literal["fay_spreading_inversion"] = "fay_spreading_inversion"


class DriftRun(BaseModel):
    spill_id: str
    forcing: Dict[str, Any]
    ensemble_size: int
    members_complete: int
    members_dropped: int
    members: List[DriftEnsembleMember]
    origin_zone: Dict[str, Any]


# ---------------------------------------------------------------------------
# 3. Attribution & Candidate Models (Attribution Contract §3)
# ---------------------------------------------------------------------------

class EvidenceTrace(BaseModel):
    proximity_score: float = 0.0
    path_match_score: float = 0.0
    confession_match_score: float = 0.0
    anomaly_score: float = 0.0
    vessel_type_prior: Optional[float] = None
    dominant_factor: str = "none"
    shap_explanation: Optional[Dict[str, Any]] = None
    counterfactuals: List[str] = Field(default_factory=list)
    narrative: str = ""
    cpa_distance_km: Optional[float] = None
    cpa_time_diff_hours: Optional[float] = None
    causal_veto: bool = False
    spatiotemporal_cpa_match: Optional[bool] = None


DataProvenance = Literal["real_gfw", "real_aisstream_live", "synthetic_fallback"]


class AisPosition(BaseModel):
    timestamp: str
    lat: float
    lon: float
    sog: float
    cog: float
    is_reconstructed: bool = False


class RouteReconstruction(BaseModel):
    intersects_50pct: bool = False
    intersects_75pct: bool = False
    intersects_90pct: bool = False
    min_distance_km: float = 0.0
    ray_trace_score: float = 0.0
    cpa_distance_km: float = 0.0
    cpa_time_diff_hours: float = 0.0
    cpa_timestamp: Optional[str] = None
    causal_veto: bool = False
    speed_summary: Optional[Dict[str, Any]] = None


class Candidate(BaseModel):
    vessel_id: str = Field(..., description="MMSI where real.")
    vessel_name: Optional[str] = Field(None, description="From GFW Vessels API where resolvable.")
    imo: Optional[str] = Field(None, description="IMO number where resolvable.")
    flag_country: Optional[str] = Field(None, description="Flag state ISO code.")
    vessel_type: Optional[str] = Field(None, description="Vessel category / ship type.")
    last_known_position: Optional[List[float]] = Field(None, min_length=2, max_length=2)
    ais_positions: List[Dict[str, Any]] = Field(default_factory=list)
    route_reconstruction: Optional[Dict[str, Any]] = None
    suspicion_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    confidence_interval: Optional[List[float]] = Field(None, min_length=2, max_length=2)
    confidence_interval_method: str = "placeholder_width_pending_bootstrap"
    evidence_trace: EvidenceTrace
    proximate_but_absent_at_origin: bool = False
    cpa_distance_km: Optional[float] = None
    cpa_time_diff_hours: Optional[float] = None
    causal_veto: bool = False
    data_provenance: DataProvenance = Field(
        ...,
        description="Mandatory per-candidate: real_gfw, real_aisstream_live, or synthetic_fallback.",
    )
    # Optional operational metadata for deep forensic review
    departure_port: Optional[str] = None
    destination_port: Optional[str] = None
    voyage_status: Optional[str] = None
    voyage_milestones: Optional[List[Dict[str, Any]]] = None
    sog_profile: Optional[List[Dict[str, Any]]] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_candidate(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "flag_country" not in data and "flag_state" in data:
                data["flag_country"] = data["flag_state"]
            if "flag_country" not in data and "flag" in data:
                data["flag_country"] = data["flag"]
            if "confidence_interval_method" not in data or not data["confidence_interval_method"]:
                data["confidence_interval_method"] = "placeholder_width_pending_bootstrap"
            # Clamping suspicion_score to [0.0, 1.0]
            if "suspicion_score" in data and data["suspicion_score"] is not None:
                data["suspicion_score"] = max(0.0, min(1.0, float(data["suspicion_score"])))
            # Coordinate bounds for last_known_position [lon, lat]
            lkp = data.get("last_known_position")
            if isinstance(lkp, (list, tuple)) and len(lkp) >= 2:
                lon = max(-180.0, min(180.0, float(lkp[0])))
                lat = max(-90.0, min(90.0, float(lkp[1])))
                data["last_known_position"] = [lon, lat]
        return data


class TopKRecovery(BaseModel):
    k: int = 3
    recovered: Optional[bool] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class AttributionResult(BaseModel):
    spill_id: str
    candidates: List[Candidate]
    dark_vessel_alert: bool
    top_k_recovery: TopKRecovery
    real_vessel_fraction: float = 1.0
    origin_ensemble: Optional[Dict[str, Any]] = None
    trajectories: Optional[List[Dict[str, Any]]] = None
    naval_intercept_advisory: Optional[Dict[str, Any]] = None
    dark_vessel_intelligence: Optional[Dict[str, Any]] = None
    comparative_baseline: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 4. Evidence Dossier (Cryptographic Export §4)
# ---------------------------------------------------------------------------

class EvidenceDossier(BaseModel):
    spill_id: str
    generated_at: str
    payload_sha256: str
    detection: SlickDetection
    drift: DriftRun
    attribution: AttributionResult


# ---------------------------------------------------------------------------
# 5. Physics Inspector Point Lookup (§5)
# ---------------------------------------------------------------------------

class MetoceanVector(BaseModel):
    u: float
    v: float
    speed_ms: float
    speed_knots: float
    direction_deg: float
    source_dataset: str


class WindVector(BaseModel):
    u10: float
    v10: float
    speed_ms: float
    direction_deg: float
    source_dataset: str


class ParticleVelocityVector(BaseModel):
    u_net: float
    v_net: float
    speed_ms: float
    bearing_deg: float
    windage_coefficient_used: float


class PhysicsAtPoint(BaseModel):
    query: Dict[str, Any]
    current: MetoceanVector
    wind: WindVector
    particle_velocity: ParticleVelocityVector


class AnalystFeedbackRequest(BaseModel):
    spill_id: str
    vessel_id: str
    action: Literal["verify", "dismiss", "override"]
    analyst_id: str = Field("ANALYST-IN-CHARGE", description="Identity or badge ID of the forensic analyst.")
    notes: Optional[str] = None
