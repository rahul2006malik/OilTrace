"""
drift/backward_ensemble.py — SIH26143 Drift subsystem

Runs an ensemble backward OpenOil simulation from a detected slick centroid,
using real cached GLORYS current + ERA5 wind NetCDFs (from fetch_forcing.py),
and writes origin_ensemble.json matching schemas.md Section 2.

Verified against the ACTUAL installed opendrift API (1.14.11, Aug 2026) in a
sandbox before writing this — not from memory. Things that changed vs. older
OpenDrift docs/tutorials floating around online:
  1. Trajectory output lives in `o.result` (an xarray.Dataset, dims
     `trajectory` x `time`), NOT the old `o.history` masked-array /
     `get_lonlats()` API.
  2. For a backward run (negative duration/time_step), `o.result.time` is
     DESCENDING — index 0 is the seed/detection time, index -1 is the most
     backward-in-time step.
  3. **OpenDrift does NOT reliably raise a Python exception when it runs out
     of forcing data or all particles leave the cached spatial domain before
     the requested duration completes.** Verified directly: it logs
     "The simulation stopped before requested end time was reached" as a
     WARNING (opendrift's own logger, not a raised exception) and returns a
     SHORTER `o.result` with otherwise-valid (non-NaN) final positions. Those
     positions are NOT the true N-hour backward origin — they're wherever
     particles happened to be when data/domain ran out. A bare
     `try/except Exception` around `o.run()` will not catch this case, and
     naively using `ds['lon'].values[:, -1]` afterward will silently include
     truncated-duration endpoints in the cone with zero indication anything
     was wrong. This file explicitly checks achieved step count against
     requested step count and drops (with a loud print) any member that
     didn't reach full duration, rather than trusting non-NaN-ness alone.

Ensemble strategy (per Project Doc Section 6.3): perturb seed position
(radius) across members, run N backward simulations, take each FULL-DURATION
member's final position as one ensemble endpoint, then KDE those endpoints
into probability-level contours (never a single point/line).
"""
import argparse
import json
from datetime import datetime, timedelta

import numpy as np
from scipy.stats import gaussian_kde
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, mapping
from shapely.validation import make_valid

from opendrift.models.openoil import OpenOil
from opendrift.readers.reader_netCDF_CF_generic import Reader as NetCDFReader


def run_ensemble(lon, lat, detection_time, currents_path, winds_path,
                  n_members=25, backward_hours=48, seed_radius_m=500,
                  seed_number_per_member=200, loglevel=30,
                  trajectory_particles_per_member=8, trajectory_time_stride=4,
                  time_step_s=900):
    """Run N independent backward simulations, one per ensemble member.

    Each member gets its own OpenOil instance (cheap: seconds each at this
    particle count) so members are fully independent perturbations, per the
    project doc's "vary seed position within a radius" ensemble design.

    Members that don't complete the full requested `backward_hours` (ran out
    of cached forcing data, or all particles left the cached spatial domain)
    are DROPPED entirely, not partially credited — see module docstring point
    3 for why silently keeping them would corrupt the cone.

    Also captures a SUBSAMPLED full trajectory (not just the final/origin
    endpoint) for a handful of particles per FULL-DURATION member, for later
    frontend replay (e.g. a deck.gl TripsLayer). Real simulated data already
    sitting in `o.result` at zero extra simulation cost — only the export is
    new.

    Returns (lons, lats, times, trajectories, diagnostics) — diagnostics is a
    dict with n_complete/n_dropped so callers (and Integration) can see if
    too many members are being silently lost, rather than a clean-looking
    cone hiding a mostly-broken run.
    """
    endpoints_lon = []
    endpoints_lat = []
    endpoints_time = []
    trajectories = []  # list of {member, lons: [...], lats: [...], times: [...]}
    rng = np.random.default_rng(42)

    expected_steps = int(round(backward_hours * 3600 / time_step_s)) + 1
    n_complete = 0
    n_dropped = 0

    for i in range(n_members):
        o = OpenOil(loglevel=loglevel)
        currents = NetCDFReader(currents_path)
        winds = NetCDFReader(winds_path)
        o.add_reader([currents, winds])

        # small extra jitter on the seed radius per member, on top of
        # OpenOil's own within-radius random scatter, so members don't all
        # sample the exact same effective radius
        member_radius = seed_radius_m * float(rng.uniform(0.6, 1.4))

        o.seed_elements(
            lon=lon, lat=lat, time=detection_time,
            number=seed_number_per_member, radius=member_radius,
        )

        try:
            o.run(duration=timedelta(hours=-backward_hours), time_step=-time_step_s)
        except Exception as e:
            print(f"[ensemble] member {i+1}/{n_members}: run() raised "
                  f"{type(e).__name__}: {e} -- DROPPING (no exception-path "
                  f"endpoints kept, even if o.result is partially populated)")
            n_dropped += 1
            continue

        ds = o.result
        if ds is None or "lon" not in ds:
            print(f"[ensemble] member {i+1}/{n_members}: no result -- dropping")
            n_dropped += 1
            continue

        achieved_steps = len(ds.time)
        if achieved_steps < expected_steps - 1:  # allow off-by-one at the boundary
            print(f"[ensemble] member {i+1}/{n_members}: TRUNCATED "
                  f"({achieved_steps}/{expected_steps} steps -- ran out of "
                  f"forcing data or all particles left the cached domain "
                  f"before {backward_hours}h backward). DROPPING -- these "
                  f"endpoints are NOT valid {backward_hours}h origins.")
            n_dropped += 1
            continue

        final_lon = ds["lon"].values[:, -1]
        final_lat = ds["lat"].values[:, -1]
        final_time = ds.time.values[-1]
        valid = ~(np.isnan(final_lon) | np.isnan(final_lat))

        endpoints_lon.extend(final_lon[valid].tolist())
        endpoints_lat.extend(final_lat[valid].tolist())
        endpoints_time.extend([str(final_time)] * int(valid.sum()))
        n_complete += 1

        # capture full (subsampled) paths for a few particles from this member
        all_lon = ds["lon"].values  # (n_particles, n_time)
        all_lat = ds["lat"].values
        times = [str(t) for t in ds.time.values[::trajectory_time_stride]]
        valid_particle_ids = np.where(valid)[0]
        n_take = min(trajectory_particles_per_member, len(valid_particle_ids))
        chosen = rng.choice(valid_particle_ids, size=n_take, replace=False) if n_take > 0 else []
        for pid in chosen:
            path_lon = all_lon[pid, ::trajectory_time_stride]
            path_lat = all_lat[pid, ::trajectory_time_stride]
            keep = ~(np.isnan(path_lon) | np.isnan(path_lat))
            if keep.sum() < 2:
                continue
            trajectories.append({
                "member": i,
                "lons": path_lon[keep].tolist(),
                "lats": path_lat[keep].tolist(),
                "times": [t for t, k in zip(times, keep) if k],
            })

        print(f"[ensemble] member {i+1}/{n_members}: OK, "
              f"{int(valid.sum())} valid endpoints, radius={member_radius:.0f}m, "
              f"{n_take} trajectories captured")

    diagnostics = {"n_members_requested": n_members, "n_complete": n_complete, "n_dropped": n_dropped}
    if n_dropped > 0:
        print(f"[ensemble] WARNING: {n_dropped}/{n_members} members dropped "
              f"(truncated or errored) -- cone is based on {n_complete} "
              f"complete members. If this is a large fraction, your cached "
              f"forcing window is probably too narrow for the requested "
              f"backward_hours/bbox -- widen --pad-deg or the fetch window "
              f"in fetch_forcing.py, don't just trust the output looks fine.")

    return np.array(endpoints_lon), np.array(endpoints_lat), endpoints_time, trajectories, diagnostics


def kde_probability_cone(lons, lats, containment_levels=(0.5, 0.75, 0.9), grid_n=150):
    """Render ensemble endpoints as a KDE probability-cone polygon set.

    Returns a list of {"probability": p, "geometry": GeoJSON Polygon/MultiPolygon}
    dicts, one per containment level, matching schemas.md's
    "GeoJSON polygon set with probability levels" contract — never a single
    point or line.
    """
    if len(lons) < 5:
        raise ValueError("Need at least 5 ensemble endpoints for a KDE cone "
                          "(if this fires after an ensemble run, check the "
                          "[ensemble] dropped-member warnings above first)")

    xy = np.vstack([lons, lats])
    kde = gaussian_kde(xy)

    pad = 0.15
    xmin, xmax = lons.min() - pad, lons.max() + pad
    ymin, ymax = lats.min() - pad, lats.max() + pad
    xx, yy = np.mgrid[xmin:xmax:complex(grid_n), ymin:ymax:complex(grid_n)]
    positions = np.vstack([xx.ravel(), yy.ravel()])
    density = np.reshape(kde(positions), xx.shape)

    flat = density.ravel().copy()
    order = np.argsort(flat)[::-1]
    sorted_density = flat[order]
    cell_mass = sorted_density / sorted_density.sum()
    cumulative = np.cumsum(cell_mass)

    levels = []
    for p in sorted(containment_levels):
        idx = np.searchsorted(cumulative, p)
        idx = min(idx, len(sorted_density) - 1)
        levels.append(sorted_density[idx])

    cs = plt.contour(xx, yy, density, levels=sorted(levels))
    plt.close()

    cone_features = []
    for level_value, segs, p in zip(cs.levels, cs.allsegs, sorted(containment_levels)):
        polys = []
        for seg in segs:
            if len(seg) < 4:
                continue
            poly = Polygon(seg)
            if not poly.is_valid:
                poly = make_valid(poly)
            if poly.area > 0:
                polys.append(poly)
        if not polys:
            continue
        from shapely.ops import unary_union
        merged = unary_union(polys)
        cone_features.append({
            "probability": p,
            "geometry": mapping(merged),
        })

    return cone_features


def age_estimate_heuristic(area_km2=None, elongation_ratio=None):
    """Heuristic age proxy (Project Doc Section 5.5 / schemas.md field notes):
    backward drift gives POSITION, not age. Placeholder until wired to real
    Detection output.
    """
    return {"value": None, "confidence_range": [None, None],
            "note": "not yet computed — needs real Detection geometry input, see schemas.md field notes"}


def main():
    ap = argparse.ArgumentParser(description="Run ensemble backward drift and write origin_ensemble.json")
    ap.add_argument("--spill-id", required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--detected-at", required=True, help="ISO8601 UTC, e.g. 2026-08-20T06:00:00")
    ap.add_argument("--currents", required=True, help="Path to cached GLORYS NetCDF")
    ap.add_argument("--winds", required=True, help="Path to cached ERA5 NetCDF")
    ap.add_argument("--n-members", type=int, default=25)
    ap.add_argument("--backward-hours", type=int, default=48)
    ap.add_argument("--out", default="origin_ensemble.json")
    ap.add_argument("--trajectory-out", default=None)
    ap.add_argument("--no-trajectories", action="store_true")
    args = ap.parse_args()

    detection_time = datetime.fromisoformat(args.detected_at)

    lons, lats, times, trajectories, diagnostics = run_ensemble(
        args.lon, args.lat, detection_time,
        args.currents, args.winds,
        n_members=args.n_members, backward_hours=args.backward_hours,
        trajectory_particles_per_member=0 if args.no_trajectories else 8,
    )
    print(f"[ensemble] total endpoints collected: {len(lons)} "
          f"from {diagnostics['n_complete']}/{diagnostics['n_members_requested']} complete members")

    cone = kde_probability_cone(lons, lats)

    n_report = min(200, len(lons))
    idx = np.random.default_rng(0).choice(len(lons), size=n_report, replace=False)
    ensemble_members = [
        {"lon": float(lons[i]), "lat": float(lats[i]), "time": times[i]}
        for i in idx
    ]

    output = {
        "spill_id": args.spill_id,
        "origin_probability_cone": {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"probability": f["probability"]},
                 "geometry": f["geometry"]}
                for f in cone
            ],
        },
        "age_estimate_hours": age_estimate_heuristic(),
        "ensemble_members": ensemble_members,
        "forward_hypotheses": [],
    }

    with open(args.out, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {args.out}")
    print(f"  cone levels: {[f['probability'] for f in cone]}")
    print(f"  ensemble_members reported: {len(ensemble_members)}")
    print(f"  ensemble health: {diagnostics['n_complete']} complete, "
          f"{diagnostics['n_dropped']} dropped")
    print("  forward_hypotheses: [] (populate once Attribution supplies candidate vessels)")

    if trajectories:
        traj_out = args.trajectory_out or (args.out.rsplit(".", 1)[0] + ".trajectories.json")
        with open(traj_out, "w") as f:
            json.dump({
                "spill_id": args.spill_id,
                "note": "Supplementary file, NOT part of schemas.md contract.",
                "trajectories": trajectories,
            }, f, indent=2)
        print(f"Wrote {traj_out} ({len(trajectories)} particle paths)")


if __name__ == "__main__":
    main()
