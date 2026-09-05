"""
drift/forward_simulation.py — SIH26143 Drift subsystem
Forward "Confession Simulation" runner — REWRITE.

## Why this file was rewritten, not just patched

The previous version of this file did NOT run any drift physics. It:
  - computed a Gaussian distance-decay between the candidate vessel's own
    reported (lon, lat) and the observed slick centroid,
  - drew a fixed-radius circle around the vessel's OWN position and called
    it `simulated_footprint`,
  - accepted `currents_path`/`winds_path` parameters but never used them.

That is functionally Cerulean's "Proximity" metric (Project Doc §3.1) with a
different decay curve — i.e. exactly the BASELINE this project is supposed to
replicate-then-beat (§7.2), not the physics-based differentiator (§6.4,
§13.2 point 1: "the confession-simulation match, shown live" is ranked the
single highest-leverage thing in the whole demo). Presenting the old
function's output as a "simulated footprint" to a judge would be inaccurate,
and a technical judge asking "which current field did that propagate
through?" would have no real answer — there wasn't one.

## What this version actually does

For each candidate vessel, seeds a REAL OpenOil forward simulation at the
vessel's real (lon, lat) at a real release time, runs it FORWARD through the
same real GLORYS+ERA5 readers already built and tested in
backward_ensemble.py, and takes the resulting particle cloud's convex hull as
the simulated footprint — genuine physics output, not a fixed circle.

`shape_overlap_score` is computed per schemas.md's explicitly-allowed "fast
fallback" method (centroid-distance + area-ratio; orientation left as a
documented TODO — see bottom of file), but now the centroid and area come
from an ACTUAL forward-simulated particle cloud, not the vessel's static
position. If/when Detection ships a real observed polygon, `observed_polygon`
can be passed for a real IoU instead — see `_iou_if_available`.

Every hypothesis's output carries a `method` field stating exactly which
computation ran, per the project's evidence-provenance philosophy (schemas.md:
"never omit it and never default it silently") — a judge (or Attribution)
should never have to guess whether a number is "real physics" or "fallback."
"""
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
from shapely.geometry import MultiPoint, Point, mapping, shape
from shapely.ops import unary_union

from opendrift.models.openoil import OpenOil
from opendrift.readers.reader_netCDF_CF_generic import Reader as NetCDFReader


EARTH_RADIUS_KM = 6371.0


def _haversine_km(lon1, lat1, lon2, lat2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(max(0.0, a)), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_KM * c


def _iou_if_available(sim_polygon, observed_polygon):
    """Real IoU between the simulated footprint and an observed polygon,
    if the caller has one (e.g. once Detection ships slick_detection.geojson
    geometry). Returns None if no observed polygon was provided — caller
    must fall back explicitly, never silently.
    """
    if observed_polygon is None:
        return None
    obs = shape(observed_polygon) if isinstance(observed_polygon, dict) else observed_polygon
    if not sim_polygon.is_valid or not obs.is_valid:
        return None
    inter = sim_polygon.intersection(obs).area
    union = sim_polygon.union(obs).area
    if union == 0:
        return None
    return float(np.clip(inter / union, 0.0, 1.0))


def run_forward_hypothesis(vessel_id, release_lon, release_lat, release_time,
                            detected_at, currents_path, winds_path,
                            observed_lon, observed_lat,
                            observed_polygon=None, observed_area_km2=None,
                            n_particles=100, time_step_s=900, loglevel=30):
    """Run ONE real forward OpenOil simulation for one candidate vessel and
    score it against the observed slick.

    release_time: when this vessel is hypothesized to have discharged oil
      (a real datetime, ideally from the vessel's real AIS track / a real
      AIS-disabling event, per schemas.md's dark-vessel/anomaly fields --
      NOT invented here).
    detected_at: the real Detection timestamp (slick_detection.geojson
      `detected_at`).
    currents_path / winds_path: real cached GLORYS/ERA5 NetCDFs. Must cover
      the [release_time, detected_at] window -- if release_time falls
      outside the cached forcing window, this will raise (loudly), not
      silently degrade.

    Returns one dict matching schemas.md's forward_hypotheses[] shape, plus
    a `method` field for transparency.
    """
    if isinstance(detected_at, str):
        detected_at = datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
    if isinstance(release_time, str):
        release_time = datetime.fromisoformat(release_time.replace("Z", "+00:00"))
    if detected_at.tzinfo is not None:
        detected_at = detected_at.replace(tzinfo=None)
    if release_time.tzinfo is not None:
        release_time = release_time.replace(tzinfo=None)

    forward_hours = (detected_at - release_time).total_seconds() / 3600.0
    if forward_hours <= 0:
        raise ValueError(
            f"release_time ({release_time}) is not before detected_at "
            f"({detected_at}) -- cannot run a forward hypothesis with "
            f"non-positive duration for vessel {vessel_id}"
        )

    o = OpenOil(loglevel=loglevel)
    currents = NetCDFReader(currents_path)
    winds = NetCDFReader(winds_path)
    o.add_reader([currents, winds])

    o.seed_elements(
        lon=release_lon, lat=release_lat, time=release_time,
        number=n_particles, radius=200,
    )
    try:
        o.run(duration=timedelta(hours=forward_hours), time_step=time_step_s)
    except Exception as e:
        return {
            "vessel_id": str(vessel_id),
            "simulated_footprint": None,
            "shape_overlap_score": 0.0,
            "method": f"forward_openoil_aborted_{type(e).__name__}",
            "particles_survived": 0,
            "forward_hours_simulated": round(forward_hours, 2),
        }

    ds = o.result
    if ds is None or "lon" not in ds:
        return {
            "vessel_id": str(vessel_id),
            "simulated_footprint": None,
            "shape_overlap_score": 0.0,
            "method": "forward_openoil_no_result",
            "particles_survived": 0,
            "forward_hours_simulated": round(forward_hours, 2),
        }
    final_lon = ds["lon"].values[:, -1]
    final_lat = ds["lat"].values[:, -1]
    valid = ~(np.isnan(final_lon) | np.isnan(final_lat))
    n_valid = int(valid.sum())

    if n_valid < 3:
        # Not enough surviving particles to form a polygon (e.g. all beached
        # or left the cached forcing domain) -- report this honestly rather
        # than fabricating a footprint from too few points.
        return {
            "vessel_id": str(vessel_id),
            "simulated_footprint": None,
            "shape_overlap_score": 0.0,
            "method": "forward_openoil_insufficient_particles",
            "particles_survived": n_valid,
            "forward_hours_simulated": round(forward_hours, 2),
        }

    sim_lon = final_lon[valid]
    sim_lat = final_lat[valid]
    sim_points = MultiPoint(list(zip(sim_lon, sim_lat)))
    sim_hull = sim_points.convex_hull
    sim_centroid = sim_hull.centroid
    # rough deg^2 -> km^2 conversion at this latitude, consistent with the
    # small-area/local-projection assumption already used elsewhere in this
    # codebase (create_circular_footprint's deg-per-km conversion)
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * max(0.1, math.cos(math.radians(sim_centroid.y)))
    sim_area_km2 = sim_hull.area * km_per_deg_lat * km_per_deg_lon

    iou = _iou_if_available(sim_hull, observed_polygon)
    if iou is not None:
        method = "iou_vs_observed_polygon"
        overlap = iou
    else:
        # fast fallback per schemas.md §2 field notes: centroid-distance + area-ratio
        dist_km = _haversine_km(sim_centroid.x, sim_centroid.y, observed_lon, observed_lat)
        sigma_km = 15.0  # dispersion scale; TODO calibrate against MV Rak/Ennore
        spatial_match = math.exp(-0.5 * (dist_km / sigma_km) ** 2)
        if observed_area_km2 and observed_area_km2 > 0:
            area_ratio = min(sim_area_km2, observed_area_km2) / max(sim_area_km2, observed_area_km2)
        else:
            area_ratio = None  # honestly unavailable, not silently 1.0
        overlap = spatial_match * (area_ratio if area_ratio is not None else 1.0)
        method = ("centroid_distance_area_ratio_fallback" if area_ratio is not None
                  else "centroid_distance_fallback_no_area_data")

    return {
        "vessel_id": str(vessel_id),
        "simulated_footprint": mapping(sim_hull),
        "shape_overlap_score": round(float(np.clip(overlap, 0.0, 1.0)), 4),
        "method": method,
        "particles_survived": n_valid,
        "forward_hours_simulated": round(forward_hours, 2),
        "simulated_area_km2": round(sim_area_km2, 3),
    }


def run_forward_confession_simulation(candidates, observed_lon, observed_lat,
                                       detected_at, currents_path, winds_path,
                                       observed_polygon=None, observed_area_km2=None,
                                       default_release_hours_before_detection=24.0):
    """Run a real forward confession simulation for each candidate vessel.

    candidates: list of dicts, each needs at minimum 'vessel_id', 'lon', 'lat'.
      Optionally 'release_time' (datetime or ISO string) -- the real AIS
      position/time this vessel is hypothesized to have discharged from. If a
      candidate has no 'release_time', this function falls back to
      `detected_at - default_release_hours_before_detection`, and TAGS that
      hypothesis's method with '_default_release_time' so it's never mistaken
      for a real Attribution-supplied release time. This should become
      unnecessary once Attribution/age_estimate_hours supplies a real value
      per schemas.md.
    """
    if isinstance(detected_at, str):
        detected_at = datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
    if detected_at.tzinfo is not None:
        detected_at = detected_at.replace(tzinfo=None)

    hypotheses = []
    for cand in candidates:
        vessel_id = cand.get("vessel_id", "UNKNOWN")
        cand_lon = cand.get("lon")
        cand_lat = cand.get("lat")
        if cand_lon is None or cand_lat is None:
            raise ValueError(f"candidate {vessel_id} missing lon/lat -- cannot run forward hypothesis")

        used_default_release = "release_time" not in cand or cand["release_time"] is None
        if used_default_release:
            release_time = detected_at - timedelta(hours=default_release_hours_before_detection)
        else:
            rt = cand["release_time"]
            if isinstance(rt, str):
                try:
                    release_time = datetime.fromisoformat(rt.replace("Z", "+00:00"))
                except ValueError:
                    release_time = detected_at - timedelta(hours=default_release_hours_before_detection)
                    used_default_release = True
            else:
                release_time = rt

            if release_time.tzinfo is not None:
                release_time = release_time.replace(tzinfo=None)

            if release_time >= detected_at:
                release_time = detected_at - timedelta(hours=default_release_hours_before_detection)
                used_default_release = True

        result = run_forward_hypothesis(
            vessel_id, cand_lon, cand_lat, release_time, detected_at,
            currents_path, winds_path, observed_lon, observed_lat,
            observed_polygon=observed_polygon, observed_area_km2=observed_area_km2,
        )
        if used_default_release:
            result["method"] += "_default_release_time"
            result["release_time_source"] = "DEFAULT (no real release_time from Attribution -- placeholder)"
        else:
            result["release_time_source"] = "real"
        hypotheses.append(result)

    hypotheses.sort(key=lambda h: h["shape_overlap_score"], reverse=True)
    return hypotheses


# TODO (not yet implemented, documented honestly rather than faked):
# - Orientation match component (schemas.md §2 fast-fallback mentions
#   "centroid-distance + area-ratio + orientation" -- orientation is not yet
#   scored here; would compare the simulated hull's major-axis bearing
#   against the observed slick's elongation_ratio/orientation once Detection
#   ships that field).
# - Real observed_polygon wiring from slick_detection.geojson once Detection
#   finishes its inference + geometry post-processing step (PROJECT_STATE.md
#   Detection section flags this as still outstanding on their end too).
