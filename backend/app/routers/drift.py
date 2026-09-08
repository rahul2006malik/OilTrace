"""
backend/app/routers/drift.py — SIH26143

Drift & Metocean Router:
Provides point physics lookups, dynamic metocean vector grids, and spline-interpolated
particle trajectory paths.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

_NETCDF_LOCK = threading.Lock()

try:
    from drift.metocean_grid import generate_metocean_grid
except ImportError:
    generate_metocean_grid = None

try:
    from drift.trajectory_interpolator import interpolate_particle_trajectories
except ImportError:
    interpolate_particle_trajectories = None

logger = logging.getLogger("drift_router")
router = APIRouter(tags=["drift"])

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_METOCEAN_GRID_CACHE: Dict[tuple, dict] = {}
_METOCEAN_GRID_CACHE_MAX = 128


def _get_project_cache_dir() -> Path:
    curr = Path(__file__).resolve().parent.parent.parent
    for parent in [curr, curr.parent]:
        candidate = parent / "data" / "cache"
        if candidate.exists():
            return candidate
    return Path("data/cache")


@router.get("/drift/physics_at")
@router.get("/api/drift/physics_at")
async def get_drift_physics_at(
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude in degrees East"),
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude in degrees North"),
    time: Optional[str] = Query(None, description="ISO8601 UTC timestamp"),
) -> dict:
    """
    Looks up real GLORYS ocean surface current and ERA5 10m wind vectors
    at the exact requested coordinate and timestamp from cached NetCDFs.
    Computes genuine windage-adjusted particle velocity vector.
    """
    cache_dir = _get_project_cache_dir()
    forcing_dir = cache_dir / "forcing"

    glorys_files = sorted(forcing_dir.glob("glorys_currents_*.nc"))
    era5_files = sorted(forcing_dir.glob("era5_wind_*.nc"))

    if not glorys_files or not era5_files:
        raise HTTPException(
            status_code=404,
            detail=f"Forcing NetCDF files not found in {forcing_dir}"
        )

    time_str = time or "2026-08-25T00:00:00"

    try:
        import pandas as pd
        import xarray as xr

        t_target = pd.to_datetime(str(time_str).replace("Z", "+00:00"))
        if hasattr(t_target, "tz") and t_target.tz is not None:
            t_target = t_target.tz_localize(None)

        curr_file = None
        wind_file = None
        try:
            from drift.buffer_manager import resolve_best_forcing
            target_pydt = t_target.to_pydatetime() if hasattr(t_target, "to_pydatetime") else t_target
            curr_file, wind_file = resolve_best_forcing(lon, lat, target_pydt, pad_deg=0.1, forcing_dir=str(forcing_dir))
        except Exception as e:
            logger.debug("[drift/physics_at] resolve_best_forcing error: %s", e)

        glorys_path = Path(curr_file) if curr_file and Path(curr_file).exists() else None
        era5_path = Path(wind_file) if wind_file and Path(wind_file).exists() else None

        if not glorys_path:
            # Filter for current year files first to avoid picking historical test files
            c_year = str(t_target.year)
            year_glorys = [f for f in glorys_files if c_year in f.name]
            glorys_path = year_glorys[0] if year_glorys else glorys_files[-1]

        if not era5_path:
            c_year = str(t_target.year)
            year_era5 = [f for f in era5_files if c_year in f.name]
            era5_path = year_era5[0] if year_era5 else era5_files[-1]

        with _NETCDF_LOCK:
            with xr.open_dataset(glorys_path, engine="netcdf4") as ds_g:
                c_lon = "longitude" if "longitude" in ds_g else "lon"
                c_lat = "latitude" if "latitude" in ds_g else "lat"
                pt_g = ds_g.sel({c_lat: lat, c_lon: lon}, method="nearest")
                if "time" in ds_g.coords:
                    pt_g = pt_g.sel(time=t_target, method="nearest")
                # A5 FIX: GLORYS land mask fill values produce NaN floats.
                # NaN is not valid JSON and crashes JSONResponse serialization.
                # Replace NaN/inf with 0.0 to return a safe physics response.
                raw_u = float(pt_g["uo"].values.flat[0])
                raw_v = float(pt_g["vo"].values.flat[0])
                u_curr = 0.0 if (math.isnan(raw_u) or math.isinf(raw_u)) else raw_u
                v_curr = 0.0 if (math.isnan(raw_v) or math.isinf(raw_v)) else raw_v

            curr_spd = math.hypot(u_curr, v_curr)
            curr_bearing = (math.degrees(math.atan2(u_curr, v_curr)) + 360) % 360
            curr_knots = curr_spd * 1.94384

            with xr.open_dataset(era5_path, engine="netcdf4") as ds_w:
                w_lon = "longitude" if "longitude" in ds_w else "lon"
                w_lat = "latitude" if "latitude" in ds_w else "lat"
                time_coord = "valid_time" if "valid_time" in ds_w.coords else "time"
                pt_w = ds_w.sel({w_lat: lat, w_lon: lon}, method="nearest").sel({time_coord: t_target}, method="nearest")
                # A5 FIX: ERA5 fill values also produce NaN
                raw_u10 = float(pt_w["u10"].values.flat[0])
                raw_v10 = float(pt_w["v10"].values.flat[0])
                u_wind = 0.0 if (math.isnan(raw_u10) or math.isinf(raw_u10)) else raw_u10
                v_wind = 0.0 if (math.isnan(raw_v10) or math.isinf(raw_v10)) else raw_v10

        wind_spd = math.hypot(u_wind, v_wind)
        wind_from_deg = (math.degrees(math.atan2(-u_wind, -v_wind)) + 360) % 360

        alpha = 0.032
        u_net = u_curr + alpha * u_wind
        v_net = v_curr + alpha * v_wind
        part_spd = math.hypot(u_net, v_net)
        part_bearing = (math.degrees(math.atan2(u_net, v_net)) + 360) % 360

        return {
            "query": {
                "lon": round(lon, 4),
                "lat": round(lat, 4),
                "time": time_str,
            },
            "current": {
                "u": round(u_curr, 4),
                "v": round(v_curr, 4),
                "speed_ms": round(curr_spd, 4),
                "speed_knots": round(curr_knots, 2),
                "direction_deg": round(curr_bearing, 1),
                "source_dataset": glorys_path.name,
            },
            "wind": {
                "u10": round(u_wind, 4),
                "v10": round(v_wind, 4),
                "speed_ms": round(wind_spd, 4),
                "direction_deg": round(wind_from_deg, 1),
                "source_dataset": era5_path.name,
            },
            "particle_velocity": {
                "u_net": round(u_net, 4),
                "v_net": round(v_net, 4),
                "speed_ms": round(part_spd, 4),
                "bearing_deg": round(part_bearing, 1),
                "windage_coefficient_used": alpha,
            },
        }
    except Exception as e:
        logger.exception("[drift/physics_at] Point extraction failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to query physics vectors: {str(e)}")


@router.get("/api/metocean/grid")
async def get_metocean_grid_endpoint(
    min_lon: float = Query(70.0, description="Bounding box minimum longitude"),
    min_lat: float = Query(17.0, description="Bounding box minimum latitude"),
    max_lon: float = Query(74.0, description="Bounding box maximum longitude"),
    max_lat: float = Query(21.0, description="Bounding box maximum latitude"),
    grid_res: int = Query(12, ge=4, le=30, description="Grid points per axis"),
    time: Optional[str] = Query(None, description="ISO8601 UTC timestamp"),
    scenario_id: Optional[str] = Query(None, description="Active Scenario ID for drift trajectory alignment"),
) -> dict:
    """
    Slices the active GLORYS current and ERA5 wind NetCDFs to generate
    dynamic vector grids ((U, V) components, speed in knots, and bearing)
    for the requested spatial bounds.
    """
    if not generate_metocean_grid:
        raise HTTPException(status_code=503, detail="Metocean grid generator not available")

    target_dt = None
    if time:
        try:
            target_dt = datetime.fromisoformat(time.replace("Z", "+00:00"))
        except Exception:
            pass

    cache_dir = _get_project_cache_dir()
    forcing_dir = str(cache_dir / "forcing")

    cache_key = (
        round(min_lon, 3),
        round(min_lat, 3),
        round(max_lon, 3),
        round(max_lat, 3),
        grid_res,
        time or "none",
        scenario_id or "none",
    )
    if cache_key in _METOCEAN_GRID_CACHE:
        return _METOCEAN_GRID_CACHE[cache_key]

    grid_result = await run_in_threadpool(
        generate_metocean_grid,
        bbox=[min_lon, min_lat, max_lon, max_lat],
        target_time=target_dt,
        grid_points_x=grid_res,
        grid_points_y=grid_res,
        forcing_dir=forcing_dir,
        scenario_id=scenario_id,
    )

    if len(_METOCEAN_GRID_CACHE) >= _METOCEAN_GRID_CACHE_MAX:
        first_key = next(iter(_METOCEAN_GRID_CACHE))
        _METOCEAN_GRID_CACHE.pop(first_key, None)
    _METOCEAN_GRID_CACHE[cache_key] = grid_result

    return grid_result


@router.get("/api/trajectories/interpolated")
async def get_interpolated_trajectories(
    interval_minutes: int = Query(15, ge=5, le=60, description="Interpolation step in minutes"),
    scenario_id: Optional[str] = Query(None, description="Scenario ID"),
) -> dict:
    """
    Returns high-frequency spline-interpolated particle trajectories for
    smooth frontend temporal scrubber playback.
    """
    cache_dir = _get_project_cache_dir()
    traj_file = None
    if scenario_id:
        scen_traj = cache_dir / "scenarios" / scenario_id / "trajectories.json"
        if scen_traj.exists():
            traj_file = scen_traj
        else:
            cand = cache_dir / f"{scenario_id}_trajectories.json"
            if cand.exists():
                traj_file = cand

    if traj_file is None or not traj_file.exists():
        traj_file = cache_dir / "origin_ensemble.trajectories.json"

    if not traj_file.exists():
        raise HTTPException(status_code=404, detail="Trajectory cache file not found")

    raw_data = json.loads(traj_file.read_text(encoding="utf-8"))
    trajectories = raw_data.get("trajectories", [])

    if not interpolate_particle_trajectories or not trajectories:
        return raw_data

    interpolated = await run_in_threadpool(
        interpolate_particle_trajectories,
        trajectories,
        interval_minutes=interval_minutes,
    )

    return {
        "spill_id": raw_data.get("spill_id", scenario_id or "SPILL-2026-ARABIAN-001"),
        "total_particles": len(interpolated),
        "interval_minutes": interval_minutes,
        "trajectories": interpolated,
    }
