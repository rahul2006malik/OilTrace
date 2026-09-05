"""
SIH26143 — Integration+Frontend backend orchestrator.

Coordinates the full end-to-end pipeline:
  Detection (input GeoJSON) -> Drift (OpenDrift backward/forward) -> Attribution (GFW/Isolation Forest) -> Frontend.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from shapely.geometry import Point, shape

from .errors import validation_exception_handler
from .models import (
    AttributionResult,
    Candidate,
    DetectionPredictRequest,
    EvidenceTrace,
    PipelineRunRequest,
    TopKRecovery,
)

logger = logging.getLogger("oiltrace_backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Ensure project root is in sys.path
import sys
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Subsystem imports (robust against offline/missing dependencies)
try:
    from detection import OilSpillDetector
    DETECTION_AVAILABLE = True
except ImportError as e:
    logger.warning("Detection subsystem not importable: %s", e)
    DETECTION_AVAILABLE = False

try:
    from drift.pipeline import run_drift_backward
    from drift.forward_simulation import run_forward_confession_simulation
    from drift.fetch_forcing import fetch_currents, fetch_winds
    DRIFT_AVAILABLE = True
except ImportError as e:
    logger.warning("Drift subsystem not importable: %s", e)
    DRIFT_AVAILABLE = False

try:
    from attribution.scorer import score_vessels, fuse_candidate_scores
    from attribution.feature_engineering import build_features, discover_aisstream_files, VesselFeatures
    from attribution.project_paths import CACHE_DIR, AISSTREAM_CAPTURE_DIR
    from attribution.gfw_client import resolve_vessel_identity
    ATTRIBUTION_AVAILABLE = True
except ImportError as e:
    logger.warning("Attribution subsystem not importable: %s", e)
    ATTRIBUTION_AVAILABLE = False

app = FastAPI(
    title="OilTrace Integration Backend (SIH26143)",
    version="1.0.0",
    description="Orchestration service for Marine Oil Spill Detection & Attribution. "
                "Executes ocean drift hindcasting and vessel attribution against real GFW/AIS data.",
)

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)


def _get_project_cache_dir() -> Path:
    curr = Path(__file__).resolve().parent
    for parent in [curr, curr.parent, curr.parent.parent]:
        candidate = parent / "data" / "cache"
        if candidate.parent.exists():
            return candidate
    return Path("data/cache")


def _get_scenario_forcing_paths(
    bbox: list[float],
    start_dt: datetime,
    end_dt: datetime,
    cache_dir: Path,
) -> tuple[Optional[str], Optional[str]]:
    """
    Resolves exact scenario-matching NetCDFs from data/cache/forcing/ via fetch_currents / fetch_winds.
    fetch_currents/fetch_winds check for the exact expected filename on disk and skip download if found.
    """
    forcing_dir = str(cache_dir / "forcing")
    try:
        currents_path = fetch_currents(bbox, start_dt, end_dt, out_dir=forcing_dir)
        winds_path = fetch_winds(bbox, start_dt, end_dt, out_dir=forcing_dir)
        return currents_path, winds_path
    except Exception as e:
        logger.warning("[pipeline] Could not resolve matching forcing files for bbox=%s (%s): %s", bbox, start_dt, e)
        import glob
        cached_currents = sorted(glob.glob(os.path.join(forcing_dir, "glorys_currents_*.nc")), reverse=True)
        cached_winds = sorted(glob.glob(os.path.join(forcing_dir, "era5_wind_*.nc")), reverse=True)
        c_p = cached_currents[0] if cached_currents else None
        w_p = cached_winds[0] if cached_winds else None
        return c_p, w_p


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _compute_drift_proximity_by_vessel(
    candidates: list[dict],
    drift_result: Optional[dict],
    default_origin_lon: float,
    default_origin_lat: float,
) -> dict[str, float]:
    """
    Computes real per-vessel spatial proximity from the Drift origin cone or spill centroid.
    Uses point-in-polygon checks across 50%, 75%, 90% KDE contours, and exponential spatial distance decay.
    """
    polygons_by_prob: list[tuple[float, Any]] = []
    if drift_result and "origin_probability_cone" in drift_result:
        features = drift_result["origin_probability_cone"].get("features", [])
        for f in features:
            prob = f.get("properties", {}).get("probability", 1.0)
            geom = f.get("geometry")
            if geom:
                try:
                    poly = shape(geom)
                    polygons_by_prob.append((float(prob), poly))
                except Exception:
                    pass
        polygons_by_prob.sort(key=lambda x: x[0])

    prox_by_vessel = {}
    for cand in candidates:
        vid = cand.get("vessel_id", "")
        v_lon = cand.get("lon")
        v_lat = cand.get("lat")

        # If candidate has no position, do not default to spill center
        if v_lon is None or v_lat is None:
            prox_by_vessel[vid] = 0.02
            continue

        pt = Point(v_lon, v_lat)
        matched_contour = False

        if polygons_by_prob:
            for prob, poly in polygons_by_prob:
                if poly.contains(pt):
                    if prob <= 0.50:
                        score = 0.95
                    elif prob <= 0.75:
                        score = 0.75
                    else:
                        score = 0.50
                    matched_contour = True
                    break

            if not matched_contour:
                # Spatial distance decay from the outer contour centroid
                outer_poly = polygons_by_prob[-1][1]
                dist_km = _haversine_km(v_lon, v_lat, outer_poly.centroid.x, outer_poly.centroid.y)
                score = max(0.005, math.exp(-dist_km / 25.0) * 0.40)
        else:
            # Baseline direct spatial distance from detection centroid
            dist_km = _haversine_km(v_lon, v_lat, default_origin_lon, default_origin_lat)
            score = max(0.005, math.exp(-dist_km / 25.0) * 0.85)

        prox_by_vessel[vid] = round(score, 4)

    return prox_by_vessel


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "subsystems": {
            "detection_available": DETECTION_AVAILABLE,
            "drift_available": DRIFT_AVAILABLE,
            "attribution_available": ATTRIBUTION_AVAILABLE,
        },
        "cache_dir": str(_get_project_cache_dir()),
    }


@app.post("/detection/predict")
async def predict_spill(payload: DetectionPredictRequest) -> dict:
    """
    Executes live two-stage cascade detection (ResNet34 classifier gate + wide-decoder U-Net segmenter)
    on a raw Sentinel-1 SAR TIFF scene. Returns schemas.md-compliant GeoJSON in ~3.5 seconds.
    """
    if not DETECTION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Detection subsystem is not available.")

    img_p = Path(payload.image_path)
    if not img_p.is_absolute():
        curr = Path(__file__).resolve().parent
        for parent in [curr, curr.parent, curr.parent.parent]:
            candidate = parent / img_p
            if candidate.exists():
                img_p = candidate
                break

    if not img_p.exists():
        raise HTTPException(status_code=404, detail=f"Image file not found: {payload.image_path}")

    try:
        detector = OilSpillDetector()
        res = detector.predict(str(img_p))
        return {
            "has_oil": bool(res.get("has_oil", False)),
            "oil_confidence": float(res.get("oil_confidence", 0.0)),
            "geojson": res.get("geojson"),
            "execution_time_seconds": round(float(res.get("execution_time_seconds", 0.0)), 2),
        }
    except Exception as e:
        logger.error("Live detection failed on %s: %s", payload.image_path, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Detection inference error: {e}")


@app.get("/scenarios")
async def list_scenarios() -> dict:
    """List pre-cached demo scenarios available for offline judging."""
    cache_dir = _get_project_cache_dir()
    scenarios = []
    
    # Check for Mumbai-Gulf corridor scenario
    origin_file = cache_dir / "origin_ensemble.json"
    if origin_file.exists():
        scenarios.append({
            "scenario_id": "mumbai_gulf_flagship",
            "name": "Mumbai-Gulf Commercial Corridor (Arabian Sea)",
            "spill_id": "SPILL-2026-ARABIAN-001",
            "bbox": [60.0, 15.0, 73.0, 22.0],
            "detected_at": "2026-08-25T06:00:00Z",
            "has_drift_ensemble": True,
            "has_real_gfw": True,
        })
    return {"scenarios": scenarios}


@app.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str) -> dict:
    """Retrieve pre-cached scenario artifacts (drift cone, candidates, slick, attribution)."""
    cache_dir = _get_project_cache_dir()
    origin_file = cache_dir / "origin_ensemble.json"
    traj_file = cache_dir / "origin_ensemble.trajectories.json"
    slick_file = cache_dir / "flagship_slick_detection.geojson"
    attr_file = cache_dir / "attribution_result.json"
    
    if not origin_file.exists():
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found in cache.")
    
    origin_data = json.loads(origin_file.read_text(encoding="utf-8"))
    traj_data = json.loads(traj_file.read_text(encoding="utf-8")) if traj_file.exists() else {}
    slick_data = json.loads(slick_file.read_text(encoding="utf-8")) if slick_file.exists() else None
    attr_data = json.loads(attr_file.read_text(encoding="utf-8")) if attr_file.exists() else None
    
    return {
        "scenario_id": scenario_id,
        "origin_ensemble": origin_data,
        "trajectories": traj_data.get("trajectories", []),
        "slick": slick_data,
        "attribution": attr_data,
    }


@app.post("/pipeline/run", response_model=AttributionResult)
async def run_pipeline(payload: PipelineRunRequest) -> AttributionResult:
    """
    Executes full pipeline orchestration:
      1. Parses slick detection metadata.
      2. Runs or retrieves Drift backward ensemble simulation -> origin probability cone.
      3. Gathers real GFW/AIS vessel features for the spatio-temporal window.
      4. Runs Isolation Forest behavior anomaly scoring.
      5. Runs forward confession simulations for top candidate vessels using real logged coordinates.
      6. Fuses evidence traces and returns schema-conformant AttributionResult.
    """
    spill_id = payload.spill_id
    lon = payload.location.lon
    lat = payload.location.lat
    detected_at_dt = payload.detected_at
    if detected_at_dt.tzinfo is not None:
        detected_at_dt = detected_at_dt.replace(tzinfo=None)
    detected_at_str = detected_at_dt.isoformat()
    cache_dir = _get_project_cache_dir()

    # If slick_geojson_ref is omitted but image_path provided, run live detection
    if payload.slick_geojson_ref is None and payload.image_path:
        img_p = Path(payload.image_path)
        if not img_p.is_absolute():
            curr = Path(__file__).resolve().parent
            for parent in [curr, curr.parent, curr.parent.parent]:
                candidate = parent / img_p
                if candidate.exists():
                    img_p = candidate
                    break
        if img_p.exists() and DETECTION_AVAILABLE:
            logger.info("[pipeline] Triggering live Detection cascade on raw SAR TIFF: %s", img_p)
            try:
                detector = OilSpillDetector()
                det_res = detector.predict(str(img_p))
                if det_res.get("detected") and det_res.get("geojson"):
                    g = det_res["geojson"]
                    lon, lat = g.get("centroid", [lon, lat])
                    spill_id = g.get("spill_id", spill_id)
            except Exception as e:
                logger.warning("[pipeline] Live detection on image failed: %s", e)

    # Step 1: Load precomputed Drift backward simulation if spill_id matches, otherwise run live
    drift_result = None
    origin_cache = cache_dir / "origin_ensemble.json"
    if origin_cache.exists():
        try:
            cached_data = json.loads(origin_cache.read_text(encoding="utf-8"))
            if cached_data.get("spill_id") == spill_id:
                drift_result = cached_data
                logger.info("[pipeline] Loaded precomputed drift origin cone for spill_id=%s", spill_id)
            else:
                logger.info("[pipeline] Cached origin_ensemble spill_id '%s' != requested '%s' — will execute live drift",
                            cached_data.get("spill_id"), spill_id)
        except Exception as e:
            logger.warning("[pipeline] Error reading cached origin_ensemble: %s", e)
            drift_result = None

    if drift_result is None and DRIFT_AVAILABLE:
        try:
            logger.info("[pipeline] Running live OpenDrift backward ensemble for spill_id=%s at (%s, %s)", spill_id, lon, lat)
            drift_result = run_drift_backward(
                spill_id=spill_id,
                lon=lon,
                lat=lat,
                detected_at=detected_at_str,
                backward_hours=24,
                n_members=15,
                write_files=False,
            )
        except Exception as e:
            logger.warning("[pipeline] Live drift backward run failed: %s: %s", type(e).__name__, e, exc_info=True)

    # Step 2: Extract or load vessel candidate population
    raw_candidates = []
    provenance = "synthetic_fallback"

    # Search for cached GFW presence in cache directory
    presence_files = list(cache_dir.glob("ais_presence_*.json"))
    gap_files = list(cache_dir.glob("gap_events_*.json"))
    loitering_files = list(cache_dir.glob("loitering_events_*.json"))
    encounter_files = list(cache_dir.glob("encounter_events_*.json"))
    ais_files = discover_aisstream_files() if ATTRIBUTION_AVAILABLE else []

    if ATTRIBUTION_AVAILABLE and presence_files:
        try:
            p_data = json.loads(presence_files[0].read_text(encoding="utf-8"))
            g_data = json.loads(gap_files[0].read_text(encoding="utf-8")) if gap_files else {}
            l_data = json.loads(loitering_files[0].read_text(encoding="utf-8")) if loitering_files else {}
            e_data = json.loads(encounter_files[0].read_text(encoding="utf-8")) if encounter_files else {}

            entries = p_data.get("entries", [])
            gap_ev = g_data.get("events", [])
            loit_ev = l_data.get("events", [])
            enc_ev = e_data.get("events", [])

            features = build_features(
                presence_entries=entries,
                gap_events=gap_ev,
                loitering_events=loit_ev,
                encounter_events=enc_ev,
                aisstream_jsonl_paths=ais_files,
            )
            if features:
                raw_candidates = score_vessels(features)
                provenance = "real_gfw"
                logger.info("[pipeline] Extracted %d real candidates from GFW/AIS caches", len(raw_candidates))
        except Exception as e:
            logger.warning("[pipeline] Feature extraction failed: %s", e, exc_info=True)

    # Fallback population if no live/cached GFW files present
    if not raw_candidates:
        default_pop = {
            "412000001": VesselFeatures(vessel_key="412000001", presence_hours=32.5, gap_count=2, gap_duration_hours=18.4, loitering_count=1, last_lon=lon+0.04, last_lat=lat+0.02),
            "636019002": VesselFeatures(vessel_key="636019002", presence_hours=44.0, gap_count=0, gap_duration_hours=0.0, loitering_count=0, last_lon=lon+0.08, last_lat=lat+0.05),
            "354000003": VesselFeatures(vessel_key="354000003", presence_hours=12.0, gap_count=1, gap_duration_hours=6.2, loitering_count=0, last_lon=lon-0.03, last_lat=lat-0.02),
        }
        if ATTRIBUTION_AVAILABLE:
            raw_candidates = score_vessels(default_pop)
        provenance = "synthetic_fallback"
        logger.info("[pipeline] Using synthetic fallback population (%d vessels)", len(raw_candidates))

    # Step 3: Compute real Drift proximity per candidate
    drift_prox_by_vessel = _compute_drift_proximity_by_vessel(
        raw_candidates,
        drift_result=drift_result,
        default_origin_lon=lon,
        default_origin_lat=lat,
    )

    # Step 4: Run forward confession simulations for top candidate vessels using real coordinates
    fwd_hypotheses = []
    pad_deg = 2.0
    forcing_bbox = [lon - pad_deg, lat - pad_deg, lon + pad_deg, lat + pad_deg]
    start_dt = detected_at_dt - timedelta(hours=30)
    end_dt = detected_at_dt + timedelta(hours=6)
    currents_path, winds_path = _get_scenario_forcing_paths(forcing_bbox, start_dt, end_dt, cache_dir)

    if DRIFT_AVAILABLE and raw_candidates and currents_path and winds_path:
        try:
            cand_inputs = []
            for c in raw_candidates[:5]:
                c_lon = c.get("lon")
                c_lat = c.get("lat")
                if c_lon is not None and c_lat is not None:
                    # Pass real release_time if available, or None to trigger honest fallback tagging in forward_simulation.py
                    cand_inputs.append({
                        "vessel_id": c["vessel_id"],
                        "lon": c_lon,
                        "lat": c_lat,
                        "release_time": c.get("release_time"),
                    })

            if cand_inputs:
                logger.info("[pipeline] Running forward confession simulations for %d candidates", len(cand_inputs))
                fwd_hypotheses = run_forward_confession_simulation(
                    candidates=cand_inputs,
                    observed_lon=lon,
                    observed_lat=lat,
                    detected_at=detected_at_dt,
                    currents_path=currents_path,
                    winds_path=winds_path,
                )
        except Exception as e:
            logger.warning("[pipeline] Forward confession simulation failed: %s: %s", type(e).__name__, e, exc_info=True)
            fwd_hypotheses = []

    # Step 5: Fuse scores into final candidate contracts
    if ATTRIBUTION_AVAILABLE and raw_candidates:
        fused_cands = fuse_candidate_scores(
            raw_candidates,
            drift_proximity_by_vessel=drift_prox_by_vessel if drift_prox_by_vessel else None,
            forward_hypotheses=fwd_hypotheses if fwd_hypotheses else None,
        )
    else:
        fused_cands = raw_candidates

    # Resolve vessel identities for top candidates if available
    if ATTRIBUTION_AVAILABLE:
        for cand in fused_cands[:8]:
            if not cand.get("vessel_name"):
                try:
                    ident = resolve_vessel_identity(cand["vessel_id"])
                    if ident.resolved:
                        cand["vessel_name"] = ident.shipname
                        if ident.shiptype:
                            cand["evidence_trace"]["vessel_type_prior"] = 0.85
                except Exception as e:
                    logger.debug("[pipeline] Identity lookup failed for %s: %s", cand["vessel_id"], e)

    # Ensure valid candidate data shapes with coordinates and stationary-rig filtering
    formatted_candidates = []
    for c in fused_cands:
        v_id = str(c["vessel_id"])
        v_name = c.get("vessel_name") or f"Vessel (MMSI: {v_id})"

        # Exclude permanent stationary offshore platforms / drilling rigs from transit suspect lists
        v_name_upper = v_name.upper()
        if "SAGAR SAMRAT" in v_name_upper or "MOPU" in v_name_upper or v_id == "419381000":
            logger.info("[pipeline] Filtered stationary platform %s (%s) from criminal transit rankings", v_name, v_id)
            continue

        v_lon = c.get("lon")
        v_lat = c.get("lat")
        last_pos = [round(float(v_lon), 4), round(float(v_lat), 4)] if (v_lon is not None and v_lat is not None) else None

        ev = c.get("evidence_trace", {})
        formatted_candidates.append(
            Candidate(
                vessel_id=v_id,
                vessel_name=v_name,
                last_known_position=last_pos,
                suspicion_score=c.get("suspicion_score"),
                confidence_interval=c.get("confidence_interval"),
                evidence_trace=EvidenceTrace(
                    proximity_score=float(ev.get("proximity_score", 0.0)),
                    confession_match_score=float(ev.get("confession_match_score", 0.0)),
                    anomaly_score=float(ev.get("anomaly_score", 0.0)),
                    vessel_type_prior=ev.get("vessel_type_prior"),
                    dominant_factor=str(ev.get("dominant_factor", "anomaly_score")),
                ),
                data_provenance=c.get("data_provenance", provenance),
            )
        )
        if len(formatted_candidates) >= 15:
            break

    # Determine Dark Vessel Alert
    top_score = formatted_candidates[0].suspicion_score if formatted_candidates and formatted_candidates[0].suspicion_score is not None else 0.0
    dark_vessel_alert = (top_score < 0.40)

    # Load trajectory streamlines if available in cache
    traj_data = []
    traj_cache = cache_dir / "origin_ensemble.trajectories.json"
    if traj_cache.exists():
        try:
            traj_data = json.loads(traj_cache.read_text(encoding="utf-8")).get("trajectories", [])
        except Exception:
            traj_data = []

    return AttributionResult(
        spill_id=spill_id,
        candidates=formatted_candidates,
        dark_vessel_alert=dark_vessel_alert,
        top_k_recovery=TopKRecovery(k=3, recovered=None, confidence=None),
        origin_ensemble=drift_result,
        trajectories=traj_data,
    )
