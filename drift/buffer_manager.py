"""
drift/buffer_manager.py — SIH26143 Drift Subsystem

Hot Metocean Buffer Manager:
Maintains, inspects, and intelligently matches real ocean hydrodynamic and atmospheric
forcing NetCDFs (Copernicus GLORYS + ECMWF ERA5) for live OpenDrift simulations.

Prevents OpenDrift boundary drops by validating spatial and temporal containment
before launching RK4 ensemble runs.
"""

from __future__ import annotations

import functools
import glob
import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("drift_buffer_manager")
_INSPECT_LOCK = threading.Lock()

try:
    import xarray as xr
    XARRAY_AVAILABLE = True
except ImportError:
    XARRAY_AVAILABLE = False


@functools.lru_cache(maxsize=128)
def _inspect_netcdf(filepath: str) -> Optional[dict]:
    """Inspects spatial and temporal bounds of a forcing NetCDF."""
    if not XARRAY_AVAILABLE or not os.path.exists(filepath):
        return None
    try:
        with _INSPECT_LOCK:
            with xr.open_dataset(filepath) as ds:
                lon_name = "longitude" if "longitude" in ds else ("lon" if "lon" in ds else None)
                lat_name = "latitude" if "latitude" in ds else ("lat" if "lat" in ds else None)
                time_name = "time" if "time" in ds else ("valid_time" if "valid_time" in ds else None)

                if not lon_name or not lat_name or not time_name:
                    return None

                lon_min = float(ds[lon_name].min())
                lon_max = float(ds[lon_name].max())
                lat_min = float(ds[lat_name].min())
                lat_max = float(ds[lat_name].max())

                t_vals = ds[time_name].values
                t_min = str(t_vals[0])[:19]
                t_max = str(t_vals[-1])[:19]

                return {
                    "filepath": filepath,
                    "lon_min": lon_min,
                    "lon_max": lon_max,
                    "lat_min": lat_min,
                    "lat_max": lat_max,
                    "t_min": t_min,
                    "t_max": t_max,
                }
    except Exception as e:
        logger.debug("Failed inspecting %s: %s", filepath, e)
        return None


def resolve_best_forcing(
    lon: float,
    lat: float,
    target_time: datetime,
    backward_hours: int = 24,
    pad_deg: float = 1.5,
    forcing_dir: str = "data/cache/forcing",
) -> Tuple[Optional[str], Optional[str]]:
    """
    Intelligently selects the best matching GLORYS currents and ERA5 wind NetCDFs
    that contain the requested point (lon, lat) with safety padding.

    Returns (currents_path, winds_path).
    """
    if not os.path.isabs(forcing_dir):
        base_dir = Path(__file__).resolve().parent.parent
        resolved_dir = str(base_dir / forcing_dir)
        if os.path.exists(resolved_dir):
            forcing_dir = resolved_dir

    current_files = sorted(glob.glob(os.path.join(forcing_dir, "glorys_currents_*.nc")), reverse=True)
    wind_files = sorted(glob.glob(os.path.join(forcing_dir, "era5_wind_*.nc")), reverse=True)

    if not current_files or not wind_files:
        logger.warning("No forcing files found in %s", forcing_dir)
        return None, None

    req_lon_min = lon - pad_deg
    req_lon_max = lon + pad_deg
    req_lat_min = lat - pad_deg
    req_lat_max = lat + pad_deg

    # Score files based on spatial containment + temporal proximity to target_time
    target_dt = target_time
    if target_dt.tzinfo is not None:
        target_dt = target_dt.replace(tzinfo=None)

    def _score_file(filepath: str) -> float:
        meta = _inspect_netcdf(filepath)
        if not meta:
            return -1e9
        score = 0.0
        # Spatial scoring
        if meta["lon_min"] <= lon <= meta["lon_max"] and meta["lat_min"] <= lat <= meta["lat_max"]:
            score += 1000.0
            if meta["lon_min"] <= req_lon_min and meta["lon_max"] >= req_lon_max and meta["lat_min"] <= req_lat_min and meta["lat_max"] >= req_lat_max:
                score += 500.0
        else:
            # Distance penalty if outside
            d_lon = max(0.0, meta["lon_min"] - lon, lon - meta["lon_max"])
            d_lat = max(0.0, meta["lat_min"] - lat, lat - meta["lat_max"])
            score -= (d_lon + d_lat) * 100.0

        # Temporal scoring
        try:
            t0 = datetime.fromisoformat(meta["t_min"])
            t1 = datetime.fromisoformat(meta["t_max"])
            if t0.tzinfo is not None:
                t0 = t0.replace(tzinfo=None)
            if t1.tzinfo is not None:
                t1 = t1.replace(tzinfo=None)

            if t0 <= target_dt <= t1:
                score += 2000.0
            else:
                diff_sec = min(abs((target_dt - t0).total_seconds()), abs((target_dt - t1).total_seconds()))
                diff_hours = diff_sec / 3600.0
                score -= diff_hours * 2.0
        except Exception:
            pass

        return score

    best_current = max(current_files, key=_score_file) if current_files else None
    best_wind = max(wind_files, key=_score_file) if wind_files else None

    return best_current, best_wind


def analytical_monsoon_forcing(
    lons: Any,
    lats: Any,
    target_dt: datetime,
) -> Tuple[Any, Any, Any, Any]:
    """
    Physical analytical hydrodynamic & atmospheric forcing model for the Northern Indian Ocean
    (Arabian Sea, Bay of Bengal, Lakshadweep Sea, and Andaman Sea).
    
    Computes (u_current, v_current, u_wind, v_wind) in m/s based on:
      1. Seasonal Monsoon Wind Regimes:
         - SW Monsoon (May-Oct): ENE winds 8-14 m/s
         - NE Monsoon (Nov-Apr): WSW winds 4-7 m/s
      2. Ekman Surface Layer Deflection (45 degrees right of wind in Northern Hemisphere)
      3. Boundary Coastal Currents (WICC & EICC)
    """
    import numpy as np

    q_lons = np.asarray(lons, dtype=float)
    q_lats = np.asarray(lats, dtype=float)

    clean_dt = target_dt
    if clean_dt.tzinfo is not None:
        clean_dt = clean_dt.replace(tzinfo=None)
    doy = clean_dt.timetuple().tm_yday

    # 1. Seasonal wind field
    is_sw_monsoon = 135 <= doy <= 290  # Mid-May to mid-October
    if is_sw_monsoon:
        phase = (doy - 135.0) / (290.0 - 135.0) * np.pi
        w_speed = 7.5 + 4.5 * np.sin(phase)
        # Wind blowing toward ~060 deg (u > 0, v > 0)
        u_w = w_speed * np.sin(np.radians(60.0))
        v_w = w_speed * np.cos(np.radians(60.0))
    else:
        # NE Monsoon (Nov-Apr)
        w_speed = 4.0 + 2.5 * np.cos(((doy + 45) % 365) / 365.0 * 2 * np.pi)
        # Wind blowing toward ~240 deg (u < 0, v < 0)
        u_w = -w_speed * np.sin(np.radians(60.0))
        v_w = -w_speed * np.cos(np.radians(60.0))

    # 2. Wind-driven surface Ekman drift (2.8% of wind speed, deflected 45 deg right)
    # Rotation by -45 degrees (clockwise in cartesian coords)
    cos45 = np.cos(np.radians(-45.0))
    sin45 = np.sin(np.radians(-45.0))
    u_ekman = 0.028 * (u_w * cos45 - v_w * sin45)
    v_ekman = 0.028 * (u_w * sin45 + v_w * cos45)

    # 3. Geostrophic boundary currents (WICC & EICC)
    # Arabian Sea (lon < 77.0): West India Coastal Current
    # Bay of Bengal (lon >= 77.0): East India Coastal Current
    u_boundary = np.zeros_like(q_lons)
    v_boundary = np.zeros_like(q_lats)

    is_arabian = q_lons < 77.0
    if is_sw_monsoon:
        # WICC flows southward along west coast in Summer
        v_boundary = np.where(is_arabian & (q_lats < 22.0), -0.22, 0.05)
        # EICC flows northward along east coast in Summer
        v_boundary = np.where(~is_arabian & (q_lats < 20.0), 0.28, v_boundary)
        u_boundary = np.where(is_arabian, -0.08, 0.12)
    else:
        # WICC flows northward along west coast in Winter
        v_boundary = np.where(is_arabian & (q_lats < 22.0), 0.18, -0.05)
        # EICC flows southward in Winter
        v_boundary = np.where(~is_arabian & (q_lats < 20.0), -0.20, v_boundary)
        u_boundary = np.where(is_arabian, 0.05, -0.10)

    u_curr = u_boundary + u_ekman
    v_curr = v_boundary + v_ekman

    u_w_arr = np.full_like(q_lons, u_w)
    v_w_arr = np.full_like(q_lats, v_w)

    return u_curr, v_curr, u_w_arr, v_w_arr

