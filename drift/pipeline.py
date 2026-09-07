"""
drift/pipeline.py — SIH26143 Drift subsystem

Combines fetch_forcing.py + backward_ensemble.py into ONE importable function,
so Integration's /pipeline/run doesn't have to shell out to two CLI scripts
later. This is pure wiring — no new physics/logic beyond what's already in
those two (already-tested-against-real-data) modules.

Usage from Integration (once wired):

    from drift.pipeline import run_drift_backward

    result = run_drift_backward(
        spill_id="TEST-001",
        lon=65.0, lat=18.5,
        detected_at="2026-08-25T06:00:00",
    )
    # result is the exact dict written to origin_ensemble.json — Integration
    # can validate it against schemas.md and pass it straight to Attribution,
    # no file round-trip required (though `out_dir` still caches the
    # NetCDFs + JSON to disk, same as the CLI scripts did).

Still CLI-runnable directly for testing:

    python drift/pipeline.py --spill-id TEST-001 --lon 65.0 --lat 18.5 \
        --detected-at 2026-08-25T06:00:00
"""
import argparse
import json
import os
from datetime import datetime

try:
    from .fetch_forcing import fetch_currents, fetch_winds
    from .backward_ensemble import run_ensemble, kde_probability_cone, age_estimate_heuristic
except ImportError:
    from fetch_forcing import fetch_currents, fetch_winds
    from backward_ensemble import run_ensemble, kde_probability_cone, age_estimate_heuristic
import numpy as np
from datetime import timedelta


def run_drift_backward(spill_id, lon, lat, detected_at,
                        backward_hours=48, pad_deg=3.0,
                        n_members=25, out_dir="data/cache/forcing",
                        write_files=True, out_path="origin_ensemble.json",
                        trajectory_out_path=None,
                        area_km2=None, elongation_ratio=None):
    """One-call real backward-drift run: fetch real forcing -> run ensemble
    -> KDE cone -> schema-conformant dict. Reuses cached NetCDFs on repeat
    calls with the same date range (fetch_currents/fetch_winds already
    skip re-download if the target file exists).

    Returns the origin_ensemble.json-shaped dict (also written to disk if
    write_files=True). Raises on any real fetch/simulation error rather than
    swallowing it — Integration's /pipeline/run should surface that as a
    named-field or upstream error per schemas.md's error-handling rule, not
    silently fall back to synthetic data.
    """
    if isinstance(detected_at, str):
        detection_time = datetime.fromisoformat(detected_at)
    else:
        detection_time = detected_at

    start_dt = detection_time - timedelta(hours=backward_hours + 6)
    end_dt = detection_time + timedelta(hours=6)
    bbox = [lon - pad_deg, lat - pad_deg, lon + pad_deg, lat + pad_deg]

    try:
        from .buffer_manager import resolve_best_forcing
    except ImportError:
        try:
            from buffer_manager import resolve_best_forcing
        except ImportError:
            resolve_best_forcing = None

    try:
        currents_path = fetch_currents(bbox, start_dt, end_dt, out_dir)
        winds_path = fetch_winds(bbox, start_dt, end_dt, out_dir)
    except Exception as e:
        if resolve_best_forcing:
            currents_path, winds_path = resolve_best_forcing(lon, lat, detection_time, backward_hours=backward_hours, pad_deg=pad_deg, forcing_dir=out_dir)
        else:
            raise

    if (not currents_path or not winds_path) and resolve_best_forcing:
        c_alt, w_alt = resolve_best_forcing(lon, lat, detection_time, backward_hours=backward_hours, pad_deg=pad_deg, forcing_dir=out_dir)
        currents_path = currents_path or c_alt
        winds_path = winds_path or w_alt

    try:
        from .backward_ensemble import fast_rk4_backward_ensemble
    except ImportError:
        try:
            from backward_ensemble import fast_rk4_backward_ensemble
        except ImportError:
            fast_rk4_backward_ensemble = None

    use_fast = os.environ.get("OILTRACE_DRIFT_ENGINE", "fast_rk4") != "openoil"
    if use_fast and fast_rk4_backward_ensemble:
        lons, lats, times, trajectories, diagnostics = fast_rk4_backward_ensemble(
            lon, lat, detection_time, currents_path, winds_path,
            n_members=n_members, backward_hours=backward_hours,
        )
    else:
        lons, lats, times, trajectories, diagnostics = run_ensemble(
            lon, lat, detection_time, currents_path, winds_path,
            n_members=n_members, backward_hours=backward_hours,
        )
    if diagnostics["n_complete"] == 0:
        raise RuntimeError(
            f"All {diagnostics['n_members_requested']} ensemble members were "
            f"dropped (truncated/errored) for spill_id={spill_id} -- cached "
            f"forcing window is likely too narrow for backward_hours={backward_hours}h "
            f"around ({lon},{lat}). Refusing to write a cone from zero valid "
            f"endpoints. Widen pad_deg or the forcing fetch window and retry."
        )

    cone = kde_probability_cone(lons, lats)

    n_report = min(200, len(lons))
    idx = np.random.default_rng(0).choice(len(lons), size=n_report, replace=False)
    ensemble_members = [
        {"lon": float(lons[i]), "lat": float(lats[i]), "time": times[i]}
        for i in idx
    ]

    output = {
        "spill_id": spill_id,
        "origin_probability_cone": {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"probability": f["probability"]},
                 "geometry": f["geometry"]}
                for f in cone
            ],
        },
        "age_estimate_hours": age_estimate_heuristic(area_km2, elongation_ratio),
        "ensemble_members": ensemble_members,
        "forward_hypotheses": [],
    }
    output["_diagnostics"] = diagnostics  # NOT part of schemas.md -- internal health info, strip before external validation if needed

    if write_files:
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2)
        if trajectories:
            traj_path = trajectory_out_path or (out_path.rsplit(".", 1)[0] + ".trajectories.json")
            with open(traj_path, "w") as f:
                json.dump({"spill_id": spill_id,
                           "note": "Supplementary, not part of schemas.md contract.",
                           "trajectories": trajectories}, f, indent=2)

    return output


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run the full real drift backward pipeline in one call")
    ap.add_argument("--spill-id", required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--detected-at", required=True)
    ap.add_argument("--n-members", type=int, default=25)
    ap.add_argument("--backward-hours", type=int, default=48)
    ap.add_argument("--out", default="origin_ensemble.json")
    args = ap.parse_args()

    result = run_drift_backward(
        args.spill_id, args.lon, args.lat, args.detected_at,
        backward_hours=args.backward_hours, n_members=args.n_members,
        out_path=args.out,
    )
    print(f"\nDone. spill_id={result['spill_id']}, "
          f"cone levels={[f['properties']['probability'] for f in result['origin_probability_cone']['features']]}, "
          f"ensemble_members={len(result['ensemble_members'])}")
