"""
Pydantic models for the Integration+Frontend backend.

Response shape (AttributionResult and its nested models) is a direct mirror of
`attribution_result.json` as defined in /backend/schemas.md — do not drift from
that file. If you need to change a field here, update schemas.md first per the
Orchestration Playbook §6 schema-change protocol, then update this file.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# /pipeline/run request
# ---------------------------------------------------------------------------

class LocationInput(BaseModel):
    """Slick location, WGS84 lon/lat — mirrors the `centroid` convention used
    throughout schemas.md ([lon, lat])."""

    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude, WGS84.")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude, WGS84.")


# Either a path/URI to a slick_detection.geojson file on disk (Detection runs
# offline on Kaggle and writes this artifact — it never calls this endpoint
# itself), or the GeoJSON object inlined directly in the request.
SlickGeojsonRef = Union[str, Dict[str, Any]]


class PipelineRunRequest(BaseModel):
    """Input to POST /pipeline/run.

    Detection does NOT run inside this request — it runs offline on Kaggle
    per the repo design (execution doc §0) and produces
    `slick_detection.geojson` as a flat file. This endpoint consumes that
    already-computed output; it does not accept a raw SAR image and does not
    trigger detection. `slick_geojson_ref` carries a reference to that file
    (a path/URI) or the GeoJSON content inlined directly — either is valid at
    this contract level, same pattern schemas.md already uses for
    `forward_hypotheses[].shape_overlap_score` (rigorous-or-fallback, both
    valid).
    """

    spill_id: str = Field(..., min_length=1, description="Join key propagated across all pipeline artifacts (schemas.md, Cross-cutting rule 1).")
    location: LocationInput
    detected_at: datetime = Field(..., description="ISO8601 UTC detection timestamp.")
    slick_geojson_ref: Optional[SlickGeojsonRef] = Field(
        None,
        description="Path/URI to a slick_detection.geojson file, or the GeoJSON object inlined directly. If omitted and image_path is provided, live detection is executed.",
    )
    image_path: Optional[str] = Field(
        None,
        description="Path/URI to a raw Sentinel-1 SAR TIFF scene on disk for live inference.",
    )


class DetectionPredictRequest(BaseModel):
    image_path: str = Field(..., description="Path to raw Sentinel-1 SAR TIFF image on disk.")


# ---------------------------------------------------------------------------
# attribution_result.json response contract (schemas.md §3)
# ---------------------------------------------------------------------------

class EvidenceTrace(BaseModel):
    proximity_score: float = 0.0
    confession_match_score: float = 0.0
    anomaly_score: float = 0.0
    vessel_type_prior: Optional[float] = None
    dominant_factor: str = "none"


DataProvenance = Literal["real_gfw", "real_aisstream_live", "synthetic_fallback"]


class Candidate(BaseModel):
    vessel_id: str = Field(..., description="MMSI where real.")
    vessel_name: Optional[str] = Field(None, description="From GFW Vessels API where resolvable.")
    last_known_position: Optional[List[float]] = Field(None, min_length=2, max_length=2, description="[lon, lat] coordinate of candidate vessel where available from GFW or AISstream.")
    suspicion_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    confidence_interval: Optional[List[float]] = Field(None, min_length=2, max_length=2)
    evidence_trace: EvidenceTrace
    data_provenance: DataProvenance = Field(
        ...,
        description="Mandatory per-candidate (schemas.md §3 field notes) — never omitted, never silently defaulted.",
    )


class TopKRecovery(BaseModel):
    k: int = 3
    recovered: Optional[bool] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class AttributionResult(BaseModel):
    spill_id: str
    candidates: List[Candidate]
    dark_vessel_alert: bool
    top_k_recovery: TopKRecovery
    origin_ensemble: Optional[Dict[str, Any]] = None
    trajectories: Optional[List[Dict[str, Any]]] = None
