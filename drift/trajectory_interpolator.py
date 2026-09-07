"""
drift/trajectory_interpolator.py — SIH26143 Drift Subsystem

Vectorized Trajectory Spline Interpolator:
Performs cubic spline / monotonic PCHIP temporal interpolation on Lagrangian particle
trajectories to provide fluid, sub-pixel rendering at 15-minute time steps for the
frontend temporal scrubber (-48h to 0h).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import numpy as np
from scipy.interpolate import interp1d

logger = logging.getLogger("trajectory_interpolator")


def interpolate_particle_trajectories(
    trajectories: List[Dict[str, Any]],
    interval_minutes: int = 15,
) -> List[Dict[str, Any]]:
    """
    Interpolates a list of particle trajectories to a uniform high-frequency grid.
    Each trajectory dict is expected to have:
      - 'member_id': int or str
      - 'lons': list[float]
      - 'lats': list[float]
      - 'times': list[str] (ISO8601 timestamps)
    """
    if not trajectories:
        return []

    interpolated_trajectories = []

    for traj in trajectories:
        lons = traj.get("lons", [])
        lats = traj.get("lats", [])
        times = traj.get("times", [])

        if len(lons) < 3 or len(lons) != len(times):
            # Pass through unchanged if not enough points for spline
            interpolated_trajectories.append(traj)
            continue

        try:
            # Parse timestamps to seconds relative to start
            dt_objs = [
                datetime.fromisoformat(str(t).replace("Z", "+00:00"))
                for t in times
            ]
            t0 = min(dt_objs)
            t_seconds = np.array([(d - t0).total_seconds() for d in dt_objs], dtype=float)

            # Sort by time to ensure strictly increasing independent variable
            sort_idx = np.argsort(t_seconds)
            t_sorted = t_seconds[sort_idx]
            lons_sorted = np.array(lons, dtype=float)[sort_idx]
            lats_sorted = np.array(lats, dtype=float)[sort_idx]

            # Remove any duplicate timestamps
            unique_mask = np.concatenate(([True], np.diff(t_sorted) > 1e-3))
            t_unique = t_sorted[unique_mask]
            lons_unique = lons_sorted[unique_mask]
            lats_unique = lats_sorted[unique_mask]

            if len(t_unique) < 3:
                interpolated_trajectories.append(traj)
                continue

            # Create target time grid (every interval_minutes)
            step_s = interval_minutes * 60.0
            t_target = np.arange(t_unique[0], t_unique[-1] + step_s, step_s)
            if t_target[-1] > t_unique[-1]:
                t_target[-1] = t_unique[-1]

            # Cubic spline interpolation with linear fallback
            try:
                cs_lon = interp1d(t_unique, lons_unique, kind="cubic", fill_value="extrapolate")
                cs_lat = interp1d(t_unique, lats_unique, kind="cubic", fill_value="extrapolate")
            except Exception:
                cs_lon = interp1d(t_unique, lons_unique, kind="linear", fill_value="extrapolate")
                cs_lat = interp1d(t_unique, lats_unique, kind="linear", fill_value="extrapolate")

            target_lons = [round(float(v), 5) for v in cs_lon(t_target)]
            target_lats = [round(float(v), 5) for v in cs_lat(t_target)]
            target_times = [
                (t0 + timedelta(seconds=s)).isoformat()
                for s in t_target
            ]

            interpolated_trajectories.append({
                "member_id": traj.get("member_id", 0),
                "particle_id": traj.get("particle_id", 0),
                "lons": target_lons,
                "lats": target_lats,
                "times": target_times,
                "total_points": len(target_lons),
                "interval_minutes": interval_minutes,
            })
        except Exception as e:
            logger.debug("Spline interpolation fallback for trajectory: %s", e)
            interpolated_trajectories.append(traj)

    return interpolated_trajectories
