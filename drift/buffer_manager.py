"""
drift/buffer_manager.py — SIH26143 Drift Subsystem

Hot Metocean Buffer Manager:
Maintains, inspects, and intelligently matches real ocean hydrodynamic and atmospheric
forcing NetCDFs (Copernicus GLORYS + ECMWF ERA5) for live OpenDrift simulations.

Prevents OpenDrift boundary drops by validating spatial and temporal containment
before launching RK4 ensemble runs.
"""

from __future__ import annotations

import glob
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("drift_buffer_manager")

try:
    import xarray as xr
    XARRAY_AVAILABLE = True
except ImportError:
    XARRAY_AVAILABLE = False


def _inspect_netcdf(filepath: str) -> Optional[dict]:
    """Inspects spatial and temporal bounds of a forcing NetCDF."""
    if not XARRAY_AVAILABLE or not os.path.exists(filepath):
        return None
    try:
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
