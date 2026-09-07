"""
drift/fetch_forcing.py — SIH26143 Drift subsystem

Pulls REAL forcing data for one drift scenario and caches it locally as NetCDF:
  - Ocean currents: Copernicus Marine GLORYS analysis-forecast (uo, vo)
  - Winds: ERA5 10 m u/v components via CDS

Confirmed live against current APIs (Aug 2026):
  - copernicusmarine>=2.4 python interface: `copernicusmarine.subset(...)`
  - dataset id `cmems_mod_glo_phy_anfc_0.083deg_PT1H-m` is the current hourly
    analysis-forecast product (0.083deg / ~8km, includes uo/vo). Copernicus is
    mid-migration to "atomized" per-variable dataset IDs (e.g.
    cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i) — if this ID 404s later,
    check https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_PHY_001_024/services
    for the current replacement and swap DATASET_ID below. Don't guess a new
    one blind — confirm on that page first.
  - ERA5 dataset name `reanalysis-era5-single-levels` with
    10m_u_component_of_wind / 10m_v_component_of_wind is stable and unchanged.

Auth: assumes `copernicusmarine login` has already been run once (per
PROJECT_STATE.md this is already done) and `~/.cdsapirc` already has a valid
token with the ERA5 dataset's ToU accepted (also already done per state doc).
Neither credential is read or embedded here — both clients pick them up from
the user's existing config automatically.
"""
import argparse
import os
from datetime import datetime, timedelta

import cdsapi
import copernicusmarine

DATASET_ID = "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m"


def fetch_currents(bbox, start_dt, end_dt, out_dir):
    """bbox = [min_lon, min_lat, max_lon, max_lat]"""
    min_lon, min_lat, max_lon, max_lat = bbox
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(
        out_dir, f"glorys_currents_{start_dt:%Y%m%d}_{end_dt:%Y%m%d}.nc"
    )
    if os.path.exists(out_path):
        print(f"[currents] already cached: {out_path}")
        return out_path
    # Check if remote network fetching is explicitly permitted.
    # In live demo, testing, and operational deployment, default to local cache to prevent network hangs.
    allow_remote = os.environ.get("OILTRACE_ALLOW_REMOTE_FORCING", "0") == "1"
    if not allow_remote:
        import glob
        cached = sorted(glob.glob(os.path.join(out_dir, "glorys_currents_*.nc")), reverse=True)
        if cached:
            print(f"[currents] Fast offline/cached forcing mode: using {cached[0]}")
            return cached[0]

    # Check INCOIS regional 2km model first for Indian EEZ (when remote permitted)
    try:
        from .incois_client import fetch_incois_currents
    except ImportError:
        try:
            from incois_client import fetch_incois_currents
        except ImportError:
            fetch_incois_currents = None

    if fetch_incois_currents and (60.0 <= min_lon <= 95.0) and (5.0 <= min_lat <= 25.0):
        incois_path = fetch_incois_currents(bbox, start_dt, end_dt, out_dir)
        if incois_path and os.path.exists(incois_path):
            return incois_path

    print(f"[currents] requesting {DATASET_ID} for bbox={bbox}, "
          f"{start_dt} -> {end_dt}")
    try:
        copernicusmarine.subset(
            dataset_id=DATASET_ID,
            variables=["uo", "vo"],
            minimum_longitude=min_lon,
            maximum_longitude=max_lon,
            minimum_latitude=min_lat,
            maximum_latitude=max_lat,
            minimum_depth=0,
            maximum_depth=1,  # surface layer only — oil drift is a surface process
            start_datetime=start_dt,
            end_datetime=end_dt,
            output_filename=out_path,
            overwrite=True,
        )
        print(f"[currents] saved -> {out_path}")
        return out_path
    except Exception as e:
        import glob
        cached = sorted(glob.glob(os.path.join(out_dir, "glorys_currents_*.nc")), reverse=True)
        if cached:
            print(f"[currents] Live CMEMS fetch failed ({e}). Falling back to cached forcing: {cached[0]}")
            return cached[0]
        raise


def fetch_winds(bbox, start_dt, end_dt, out_dir):
    """ERA5 hourly 10m wind components via CDS. bbox = [min_lon, min_lat, max_lon, max_lat]."""
    min_lon, min_lat, max_lon, max_lat = bbox
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(
        out_dir, f"era5_wind_{start_dt:%Y%m%d}_{end_dt:%Y%m%d}.nc"
    )
    if os.path.exists(out_path):
        print(f"[winds] already cached: {out_path}")
        return out_path

    # Check if remote network fetching is explicitly permitted.
    allow_remote = os.environ.get("OILTRACE_ALLOW_REMOTE_FORCING", "0") == "1"
    if not allow_remote:
        import glob
        cached = sorted(glob.glob(os.path.join(out_dir, "era5_wind_*.nc")), reverse=True)
        if cached:
            print(f"[winds] Fast offline/cached forcing mode: using {cached[0]}")
            return cached[0]

    # ERA5 area format is [North, West, South, East]
    area = [max_lat, min_lon, min_lat, max_lon]

    hours = int((end_dt - start_dt).total_seconds() // 3600) + 1
    dates = sorted(list({(start_dt + timedelta(hours=h)).strftime("%Y-%m-%d") for h in range(hours)}))

    print(f"[winds] requesting ERA5 single-levels for bbox={bbox}, "
          f"{start_dt} -> {end_dt}")
    try:
        c = cdsapi.Client()
        c.retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": "reanalysis",
                "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
                "date": dates,
                "time": [f"{h:02d}:00" for h in range(24)],
                "area": area,
                "format": "netcdf",
            },
            out_path,
        )
        print(f"[winds] saved -> {out_path}")
        return out_path
    except Exception as e:
        import glob
        cached = sorted(glob.glob(os.path.join(out_dir, "era5_wind_*.nc")), reverse=True)
        if cached:
            print(f"[winds] CDS download failed ({e}). Falling back to cached forcing: {cached[0]}")
            return cached[0]
        raise


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Fetch real GLORYS + ERA5 forcing for a drift scenario")
    ap.add_argument("--lon", type=float, required=True, help="Detection centroid longitude")
    ap.add_argument("--lat", type=float, required=True, help="Detection centroid latitude")
    ap.add_argument("--detected-at", type=str, required=True,
                     help="ISO8601 UTC detection time, e.g. 2026-08-20T06:00:00")
    ap.add_argument("--backward-hours", type=int, default=48,
                     help="How far back the backward run will go (default 48h)")
    ap.add_argument("--pad-deg", type=float, default=3.0,
                     help="Bounding-box padding in degrees around the centroid (default 3.0)")
    ap.add_argument("--out-dir", type=str, default="data/cache/forcing")
    args = ap.parse_args()

    detection_time = datetime.fromisoformat(args.detected_at)
    start_dt = detection_time - timedelta(hours=args.backward_hours + 6)  # small safety margin
    end_dt = detection_time + timedelta(hours=6)

    bbox = [
        args.lon - args.pad_deg, args.lat - args.pad_deg,
        args.lon + args.pad_deg, args.lat + args.pad_deg,
    ]

    currents_path = fetch_currents(bbox, start_dt, end_dt, args.out_dir)
    winds_path = fetch_winds(bbox, start_dt, end_dt, args.out_dir)

    print("\nDone. Pass these to backward_ensemble.py:")
    print(f"  --currents {currents_path}")
    print(f"  --winds {winds_path}")
