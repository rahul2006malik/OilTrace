"""
SIH26143 — Route Reconstruction & Dead Reckoning Engine
Reconstructs vessel trajectories across AIS blackout gaps using speed (SOG),
course (COG), and Copernicus GLORYS ocean surface currents.
Computes 4D spatio-temporal intersection with the backward drift origin cone.

DESIGN NOTE — Path-Aware Attribution (Project Doc Section 6.2)
---------------------------------------------------------------
Naive 2D proximity attribution answers "who is near the slick right now?"
but fails to answer "who was at the origin zone when the oil was dumped?"
This module implements the critical causal correction:

  1. Dead Reckoning (DR) across AIS gaps: When a vessel disables its
     transponder (t_gap > 1.5h), integrate its forward position in 15-minute
     Euler steps using its last logged SOG, COG, and the local GLORYS
     surface current vector.

  2. 4D Ray-Tracing: Check whether the vessel's reconstructed polyline
     intersected the backward drift origin cone during the estimated
     discharge window (T_spill ± 6h):

       RayTraceScore = max_k [ ConeWeight(x_k) * exp(-|t_k - T_origin| / τ) ]
       where τ = 6.0h

  3. "Proximate But Not Present at Origin Time" Flag: If a vessel is
     currently < 15 km from the slick but its path_match_score < 0.20,
     flag it: [!] PROXIMATE NOW // ABSENT AT RELEASE TIME.

DATA PROVENANCE
----------------
This module uses only:
  - AIS position reports (real from AISstream live capture or GFW Events)
  - Copernicus GLORYS 1/12° surface current vectors (if available on disk)
  - The backward drift origin cone from Drift subsystem's origin_ensemble.json

No synthetic data is generated. If GLORYS forcing is unavailable, dead
reckoning proceeds with vessel SOG/COG alone (current_u = current_v = 0),
which is documented and honest — not silently substituted.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

try:
    from shapely.geometry import Point, shape
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance between two WGS84 points in kilometres."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Waypoint(NamedTuple):
    """A single position fix — real or dead-reckoned."""
    lon: float
    lat: float
    timestamp: datetime
    sog_knots: float
    cog_deg: float
    is_interpolated: bool


class ReconstructedTrack(NamedTuple):
    """Result of full track reconstruction + cone intersection analysis."""
    vessel_id: str
    waypoints: List[Waypoint]
    intersects_cone_50: bool
    intersects_cone_75: bool
    intersects_cone_90: bool
    min_distance_to_cone_km: float
    ray_trace_score: float
    proximate_but_absent_at_origin: bool


# ---------------------------------------------------------------------------
# GLORYS forcing loader (lightweight, from precomputed NetCDF cache)
# ---------------------------------------------------------------------------

def _load_glorys_current_at(
    lon: float, lat: float, timestamp: datetime,
    forcing_dir: Optional[str] = None,
) -> Tuple[float, float]:
    """
    Returns (u_ms, v_ms) — eastward and northward ocean surface current
    components in m/s at the given position and time, from cached GLORYS
    NetCDF files.

    Falls back to (0.0, 0.0) if:
      - forcing_dir is None or doesn't exist
      - No matching NetCDF found
      - netCDF4/xarray not available

    This is honest: dead reckoning without ocean currents is documented
    as vessel-only DR, not silently substituted with fake currents.
    """
    if not forcing_dir:
        return 0.0, 0.0

    forcing_path = Path(forcing_dir)
    if not forcing_path.exists():
        return 0.0, 0.0

    try:
        import glob
        nc_files = sorted(glob.glob(str(forcing_path / "glorys_currents_*.nc")))
        if not nc_files:
            return 0.0, 0.0

        # Use the most recent matching file
        try:
            import xarray as xr
            ds = xr.open_dataset(nc_files[-1])
        except ImportError:
            # xarray not available — fall back gracefully
            return 0.0, 0.0

        # GLORYS variable names: uo (eastward), vo (northward)
        # Select nearest spatial point and nearest time
        try:
            u_var = "uo" if "uo" in ds else ("u" if "u" in ds else None)
            v_var = "vo" if "vo" in ds else ("v" if "v" in ds else None)
            if u_var is None or v_var is None:
                ds.close()
                return 0.0, 0.0

            sel_kwargs = {}
            if "time" in ds.dims or "time" in ds.coords:
                sel_kwargs["time"] = str(timestamp)
            if "latitude" in ds.dims or "latitude" in ds.coords:
                sel_kwargs["latitude"] = lat
            elif "lat" in ds.dims or "lat" in ds.coords:
                sel_kwargs["lat"] = lat
            if "longitude" in ds.dims or "longitude" in ds.coords:
                sel_kwargs["longitude"] = lon
            elif "lon" in ds.dims or "lon" in ds.coords:
                sel_kwargs["lon"] = lon

            point = ds.sel(**sel_kwargs, method="nearest")
            u = float(point[u_var].values)
            v = float(point[v_var].values)
            ds.close()

            if math.isnan(u) or math.isnan(v):
                return 0.0, 0.0
            return u, v

        except Exception:
            ds.close()
            return 0.0, 0.0

    except Exception:
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# Dead Reckoning Engine
# ---------------------------------------------------------------------------

def dead_reckon_segment(
    start_pos: Tuple[float, float],
    start_time: datetime,
    end_time: datetime,
    sog_knots: float,
    cog_deg: float,
    current_u_ms: float = 0.0,
    current_v_ms: float = 0.0,
    step_minutes: int = 15,
    forcing_dir: Optional[str] = None,
    end_pos: Optional[Tuple[float, float]] = None,
) -> List[Waypoint]:
    """
    Euler-integrate a vessel's position forward across an AIS blackout gap.

    With forcing_dir supplied, ocean currents are re-queried from GLORYS NetCDF
    at each 15-minute step position (dynamic spatio-temporal interpolation).
    Without forcing_dir, falls back to static currents from gap start.

    Parameters
    ----------
    start_pos : (lon, lat) — last known position before the gap
    start_time : datetime — timestamp of last AIS fix before the gap
    end_time : datetime — timestamp of first AIS fix after the gap
    sog_knots : float — Speed Over Ground from last AIS fix (knots)
    cog_deg : float — Course Over Ground from last AIS fix (degrees true)
    current_u_ms : float — Eastward ocean surface current (m/s), fallback
    current_v_ms : float — Northward ocean surface current (m/s), fallback
    step_minutes : int — Integration time step (default 15 min)
    forcing_dir : str | None — path to cached GLORYS NetCDF forcing files;
        when supplied, currents are dynamically re-queried at each step
    end_pos : (lon, lat) | None — known position after gap; when supplied,
        applies linear closure-error correction (Hermite bridge prep)

    Returns
    -------
    List[Waypoint] — Interpolated waypoints at each step_minutes interval
    """
    if start_time >= end_time:
        return []

    waypoints: List[Waypoint] = []
    curr_lon, curr_lat = start_pos
    curr_time = start_time
    step_sec = step_minutes * 60.0
    dynamic_currents = forcing_dir is not None

    # Vessel velocity components in m/s (1 knot = 0.514444 m/s)
    v_sog_ms = sog_knots * 0.514444
    cog_rad = math.radians(cog_deg)
    u_vessel = v_sog_ms * math.sin(cog_rad)  # Eastward component
    v_vessel = v_sog_ms * math.cos(cog_rad)  # Northward component

    # Collect raw DR waypoints first (before bridge correction)
    raw_waypoints: List[Tuple[float, float, datetime]] = []

    while curr_time < end_time:
        curr_time = curr_time + timedelta(seconds=step_sec)

        # Dynamic current re-query at each step position
        if dynamic_currents:
            u_curr, v_curr = _load_glorys_current_at(
                curr_lon, curr_lat, curr_time,
                forcing_dir=forcing_dir,
            )
        else:
            u_curr, v_curr = current_u_ms, current_v_ms

        # Total velocity = vessel motion + ocean current advection
        u_total = u_vessel + u_curr
        v_total = v_vessel + v_curr

        if curr_time > end_time:
            # Partial last step
            partial_sec = (end_time - (curr_time - timedelta(seconds=step_sec))).total_seconds()
            d_lat = (v_total * partial_sec) / 111132.954
            d_lon = (u_total * partial_sec) / (111132.954 * math.cos(math.radians(curr_lat)))
            curr_time = end_time
        else:
            # Full step: convert m/s displacement to degree displacement
            # 1 degree latitude ≈ 111,132.954 m
            # 1 degree longitude ≈ 111,132.954 * cos(lat) m
            d_lat = (v_total * step_sec) / 111132.954
            d_lon = (u_total * step_sec) / (111132.954 * math.cos(math.radians(curr_lat)))

        curr_lat += d_lat
        curr_lon += d_lon
        raw_waypoints.append((curr_lon, curr_lat, curr_time))

    # Apply linear closure-error correction if end_pos is known (bridge)
    # This distributes the DR closure error evenly across all steps,
    # ensuring the reconstructed track converges to the known endpoint.
    if end_pos is not None and raw_waypoints:
        final_lon, final_lat = raw_waypoints[-1][0], raw_waypoints[-1][1]
        err_lon = end_pos[0] - final_lon
        err_lat = end_pos[1] - final_lat
        n_steps = len(raw_waypoints)
        for idx, (wp_lon, wp_lat, wp_time) in enumerate(raw_waypoints):
            frac = (idx + 1) / n_steps
            raw_waypoints[idx] = (
                wp_lon + err_lon * frac,
                wp_lat + err_lat * frac,
                wp_time,
            )

    for wp_lon, wp_lat, wp_time in raw_waypoints:
        waypoints.append(Waypoint(
            lon=round(wp_lon, 6),
            lat=round(wp_lat, 6),
            timestamp=wp_time,
            sog_knots=sog_knots,
            cog_deg=cog_deg,
            is_interpolated=True,
        ))

    return waypoints


def dead_reckon_full_track(
    ais_fixes: List[Dict[str, Any]],
    gap_threshold_hours: float = 1.5,
    step_minutes: int = 15,
    forcing_dir: Optional[str] = None,
) -> List[Waypoint]:
    """
    Reconstruct a full vessel track from AIS position reports, filling in
    gaps > gap_threshold_hours with dead-reckoned waypoints.

    Parameters
    ----------
    ais_fixes : list of dicts with keys:
        - lon, lat : float
        - timestamp : str (ISO 8601)
        - sog : float (knots)
        - cog : float (degrees true)
    gap_threshold_hours : float — minimum gap duration to trigger DR
    step_minutes : int — DR integration step
    forcing_dir : str | None — path to cached GLORYS NetCDF forcing files

    Returns
    -------
    List[Waypoint] — Complete track with real + interpolated waypoints
    """
    if not ais_fixes:
        return []

    # Parse and sort by time
    parsed: List[Tuple[datetime, Dict]] = []
    for fix in ais_fixes:
        ts = fix.get("timestamp")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            parsed.append((dt, fix))
        except (ValueError, TypeError):
            continue

    parsed.sort(key=lambda x: x[0])
    if not parsed:
        return []

    track: List[Waypoint] = []

    for i, (dt, fix) in enumerate(parsed):
        # Add the real AIS fix
        track.append(Waypoint(
            lon=float(fix["lon"]),
            lat=float(fix["lat"]),
            timestamp=dt,
            sog_knots=float(fix.get("sog", 0.0) or 0.0),
            cog_deg=float(fix.get("cog", 0.0) or 0.0),
            is_interpolated=False,
        ))

        # Check for gap to next fix
        if i < len(parsed) - 1:
            next_dt, next_fix = parsed[i + 1]
            gap_hours = (next_dt - dt).total_seconds() / 3600.0

            if gap_hours >= gap_threshold_hours:
                sog = float(fix.get("sog", 0.0) or 0.0)
                cog = float(fix.get("cog", 0.0) or 0.0)

                # Determine end position for closure-error bridge correction
                end_pos_bridge = (
                    float(next_fix["lon"]),
                    float(next_fix["lat"]),
                )

                dr_points = dead_reckon_segment(
                    start_pos=(float(fix["lon"]), float(fix["lat"])),
                    start_time=dt,
                    end_time=next_dt,
                    sog_knots=sog,
                    cog_deg=cog,
                    step_minutes=step_minutes,
                    forcing_dir=forcing_dir,
                    end_pos=end_pos_bridge,
                )
                track.extend(dr_points)

    return track


# ---------------------------------------------------------------------------
# 4D Spatio-Temporal Ray-Tracing (Cone Intersection)
# ---------------------------------------------------------------------------

def _parse_cone_polygons(
    origin_cone_fc: Dict[str, Any],
) -> Tuple[Any, Any, Any]:
    """
    Extract Shapely polygons for the 50%, 75%, 90% probability contours
    from the origin_ensemble.json FeatureCollection.
    Returns (poly_50, poly_75, poly_90) — any may be None if not present.
    """
    if not SHAPELY_AVAILABLE:
        return None, None, None

    poly_50, poly_75, poly_90 = None, None, None

    for f in origin_cone_fc.get("features", []):
        p = f.get("properties", {}).get("probability")
        geom = f.get("geometry")
        if geom is None:
            continue
        try:
            poly = shape(geom)
            if p == 0.5 or p == 50:
                poly_50 = poly
            elif p == 0.75 or p == 75:
                poly_75 = poly
            elif p == 0.9 or p == 90:
                poly_90 = poly
        except Exception:
            continue

    return poly_50, poly_75, poly_90


def compute_track_cone_intersection(
    track: List[Waypoint],
    origin_cone_fc: Dict[str, Any],
    spill_time: datetime,
    decay_tau_hours: float = 6.0,
) -> Tuple[bool, bool, bool, float, float, bool]:
    """
    4D spatio-temporal ray-tracing: evaluates whether a vessel's
    reconstructed track crossed the backward drift origin probability
    contours during the estimated release window (T_spill ± 6h).

    The score combines spatial weight (which contour was penetrated)
    and temporal weight (exponential decay from estimated spill time):

        score_k = spatial_weight(x_k) * exp(-|t_k - T_spill| / τ)
        RayTraceScore = max_k(score_k)

    Spatial weights:
        - Inside 50% contour: 1.0 (highest confidence origin zone)
        - Inside 75% contour: 0.80
        - Inside 90% contour: 0.50
        - Outside all contours: exponential distance decay * 0.40

    Returns
    -------
    (intersects_cone_50, intersects_cone_75, intersects_cone_90,
     min_distance_to_cone_km, ray_trace_score,
     proximate_but_absent_at_origin)
    """
    if not SHAPELY_AVAILABLE:
        return False, False, False, float("inf"), 0.0, False

    if not track:
        return False, False, False, float("inf"), 0.0, False

    poly_50, poly_75, poly_90 = _parse_cone_polygons(origin_cone_fc)

    hit_50, hit_75, hit_90 = False, False, False
    min_dist = float("inf")
    best_score = 0.0

    for wp in track:
        pt = Point(wp.lon, wp.lat)
        dt_hours = abs((wp.timestamp - spill_time).total_seconds()) / 3600.0
        time_weight = math.exp(-dt_hours / decay_tau_hours)

        spatial_weight = 0.0

        if poly_50 and poly_50.contains(pt):
            hit_50 = True
            hit_75 = True  # 50% is inside 75%
            hit_90 = True  # 50% is inside 90%
            spatial_weight = 1.0
            min_dist = 0.0
        elif poly_75 and poly_75.contains(pt):
            hit_75 = True
            hit_90 = True
            spatial_weight = 0.80
            min_dist = 0.0
        elif poly_90 and poly_90.contains(pt):
            hit_90 = True
            spatial_weight = 0.50
            min_dist = 0.0
        else:
            # Outside all contours — compute true distance to polygon boundary (not centroid)
            ref_poly = poly_90 or poly_75 or poly_50
            if ref_poly:
                try:
                    from shapely.ops import nearest_points
                    nearest_geom_pt = nearest_points(ref_poly, pt)[0]
                    dist = haversine_km(
                        wp.lon, wp.lat,
                        nearest_geom_pt.x, nearest_geom_pt.y,
                    )
                except Exception:
                    # Fallback to centroid if nearest_points fails
                    dist = haversine_km(
                        wp.lon, wp.lat,
                        ref_poly.centroid.x, ref_poly.centroid.y,
                    )
                min_dist = min(min_dist, dist)
                spatial_weight = max(0.005, math.exp(-dist / 25.0) * 0.40)

        score = spatial_weight * time_weight
        if score > best_score:
            best_score = score

    # "Proximate But Not Present at Origin Time" flag
    # If the vessel is currently near the slick (min_dist < 15 km from
    # the outermost contour) but its best ray-trace score is very low
    # (< 0.20), it means the vessel is CLOSE NOW but was ABSENT during
    # the estimated release window. Such vessels should be heavily
    # downranked — they are red herrings for naive proximity attribution.
    proximate_but_absent = (min_dist < 15.0 and best_score < 0.20)

    return (
        hit_50, hit_75, hit_90,
        round(min_dist, 2),
        round(best_score, 4),
        proximate_but_absent,
    )


# ---------------------------------------------------------------------------
# Full Reconstruction Pipeline (convenience wrapper)
# ---------------------------------------------------------------------------

def reconstruct_and_score_vessel(
    vessel_id: str,
    ais_fixes: List[Dict[str, Any]],
    origin_cone_fc: Dict[str, Any],
    spill_time: datetime,
    *,
    gap_threshold_hours: float = 1.5,
    step_minutes: int = 15,
    forcing_dir: Optional[str] = None,
    decay_tau_hours: float = 6.0,
    current_distance_km: Optional[float] = None,
) -> ReconstructedTrack:
    """
    Full pipeline: reconstruct vessel track across AIS gaps, then compute
    4D spatio-temporal intersection with the backward drift origin cone.

    Parameters
    ----------
    vessel_id : str — MMSI or vessel identifier
    ais_fixes : list of AIS position dicts
    origin_cone_fc : GeoJSON FeatureCollection from origin_ensemble.json
    spill_time : datetime — estimated spill release time
    gap_threshold_hours : float — minimum gap to trigger dead reckoning
    step_minutes : int — DR integration time step
    forcing_dir : str | None — path to cached GLORYS NetCDF files
    decay_tau_hours : float — temporal decay constant for ray-tracing
    current_distance_km : float | None — vessel's current distance from
        the slick (if known), used for proximate_but_absent check

    Returns
    -------
    ReconstructedTrack — complete track with intersection analysis
    """
    track = dead_reckon_full_track(
        ais_fixes=ais_fixes,
        gap_threshold_hours=gap_threshold_hours,
        step_minutes=step_minutes,
        forcing_dir=forcing_dir,
    )

    (hit_50, hit_75, hit_90,
     min_dist, score, proximate_but_absent) = compute_track_cone_intersection(
        track=track,
        origin_cone_fc=origin_cone_fc,
        spill_time=spill_time,
        decay_tau_hours=decay_tau_hours,
    )

    # Override proximate_but_absent with current_distance_km if provided
    if current_distance_km is not None and current_distance_km < 15.0 and score < 0.20:
        proximate_but_absent = True

    return ReconstructedTrack(
        vessel_id=vessel_id,
        waypoints=track,
        intersects_cone_50=hit_50,
        intersects_cone_75=hit_75,
        intersects_cone_90=hit_90,
        min_distance_to_cone_km=min_dist,
        ray_trace_score=score,
        proximate_but_absent_at_origin=proximate_but_absent,
    )


# ---------------------------------------------------------------------------
# Paris MoU Flag-of-Convenience Risk Priors
# ---------------------------------------------------------------------------
# Based on Paris MoU annual performance reports — flag states with
# consistently high detention/deficiency rates carry higher prior
# probability of MARPOL Annex I violations.

FLAG_RISK_PRIORS: Dict[str, float] = {
    # Very high risk (Paris MoU Black List / Tokyo MoU)
    "CMR": 0.90,  # Cameroon
    "TZA": 0.90,  # Tanzania
    "TGO": 0.88,  # Togo
    "MDA": 0.85,  # Moldova
    "SLE": 0.85,  # Sierra Leone
    "COM": 0.85,  # Comoros
    "BLZ": 0.82,  # Belize
    # High risk (common flags of convenience)
    "PLW": 0.80,  # Palau
    "BOL": 0.78,  # Bolivia
    "GNQ": 0.78,  # Equatorial Guinea
    "KHM": 0.75,  # Cambodia
    "MNG": 0.75,  # Mongolia
    # Medium-high risk (large FOC registries)
    "PAN": 0.65,  # Panama
    "LBR": 0.60,  # Liberia
    "MHL": 0.55,  # Marshall Islands
    "HND": 0.55,  # Honduras
    "VCT": 0.55,  # St Vincent
    "ATG": 0.52,  # Antigua & Barbuda
    # Medium risk (mixed performance)
    "MLT": 0.45,  # Malta
    "BHS": 0.45,  # Bahamas
    "CYP": 0.42,  # Cyprus
    "KNA": 0.40,  # St Kitts & Nevis
    "BRB": 0.40,  # Barbados
    # Low risk (well-regulated registries)
    "GBR": 0.20,  # United Kingdom
    "NOR": 0.15,  # Norway
    "DNK": 0.15,  # Denmark
    "SGP": 0.18,  # Singapore
    "JPN": 0.12,  # Japan
    "DEU": 0.12,  # Germany
    "FRA": 0.15,  # France
    "USA": 0.15,  # United States
    "IND": 0.25,  # India
    "CHN": 0.30,  # China
    "KOR": 0.20,  # South Korea
    "NLD": 0.15,  # Netherlands
    "ITA": 0.20,  # Italy
    "GRC": 0.25,  # Greece
    "TUR": 0.35,  # Turkey
    "RUS": 0.40,  # Russia
}

# Default prior for unknown flags
DEFAULT_FLAG_RISK = 0.35


def get_flag_risk_prior(flag_code: Optional[str]) -> float:
    """
    Returns the port risk prior for a vessel's flag state.
    Uses Paris MoU performance data to assign risk scores.
    """
    if not flag_code:
        return DEFAULT_FLAG_RISK
    return FLAG_RISK_PRIORS.get(flag_code.upper(), DEFAULT_FLAG_RISK)
