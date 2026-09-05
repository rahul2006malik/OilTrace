# Drift subsystem — toy backward run, step 1-3 done

## What's verified (actually run in a sandbox, not assumed from memory)

1. **`pip install opendrift` works cleanly** on Python 3.9+ as of opendrift 1.14.11
   (Jun 2026 release) — pulls in Cartopy, geopandas, copernicusmarine, adios_db,
   etc. automatically. The official docs still lead with conda/mamba, but pip
   installed with no compile errors in a clean Linux venv. **Windows caveat:**
   Cartopy/GDAL-family wheels are the traditional pip-on-Windows pain point.
   If `pip install opendrift` fails on your Windows venv with a Cartopy or GDAL
   build error, fall back to:
   ```
   conda create -n opendrift -c conda-forge python=3.11 opendrift
   conda activate opendrift
   pip install copernicusmarine cdsapi
   ```
   Try plain pip first — it may just work — but don't burn more than ~20 min on
   a Cartopy build error before switching to conda.

2. **The OpenDrift trajectory-output API has changed** since a lot of tutorials
   were written. On 1.14.11:
   - Results live in `o.result`, an **xarray.Dataset** with dims `trajectory` x `time`.
   - There is **no** `o.history` masked array and **no** `get_lonlats()` method
     in this version — code copied from older blog posts/tutorials using those
     will fail with `AttributeError`. Use `o.result['lon'].values`, etc.
   - For a **backward** run, `o.result.time` is **descending**: index `0` is
     the seed/detection time, index `-1` is the most-backward step. The
     "origin" endpoints are `[:, -1]`, not `[:, 0]`.

3. **Full pipeline logic tested end-to-end** (ensemble loop → KDE → GeoJSON
   cone → schema-conformant JSON) using synthetic constant-current/wind readers
   as a stand-in for real GLORYS/ERA5 files (I don't have your Copernicus/CDS
   credentials in this sandbox). 15 members x 100 particles = 1500 endpoints
   produced 3 clean, non-degenerate polygon contours at 50/75/90% probability
   containment — see `origin_ensemble_TOY_EXAMPLE.json`. This confirms the KDE
   contour extraction and schema serialization work; it does **not** confirm
   your real GLORYS/ERA5 downloads will succeed, since that needs your actual
   credentials running on your machine.

4. **Dataset IDs confirmed live (25-31 Aug 2026):**
   - GLORYS currents: `cmems_mod_glo_phy_anfc_0.083deg_PT1H-m` (has `uo`,`vo`),
     confirmed still serving data through 24-25 Aug 2026 on Copernicus's own
     product page. Copernicus is mid-migration to per-variable "atomized"
     dataset IDs (e.g. `cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i`) — if the
     ID in `fetch_forcing.py` ever 404s, check
     https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_PHY_001_024/services
     for the current name rather than guessing.
   - ERA5: `reanalysis-era5-single-levels` with `10m_u_component_of_wind` /
     `10m_v_component_of_wind` — unchanged, stable.

## Files

- `fetch_forcing.py` — pulls real GLORYS currents + real ERA5 winds for a bbox
  around your detection centroid, caches as NetCDF under `data/cache/forcing/`.
- `backward_ensemble.py` — runs N independent backward OpenOil simulations
  (perturbed seed radius per member), collects each member's most-backward
  endpoint, KDE's the endpoint cloud into a 50/75/90%-containment probability
  cone, and writes `origin_ensemble.json` matching `schemas.md` exactly.
- `origin_ensemble_TOY_EXAMPLE.json` — real output from the synthetic-reader
  test run above, so you can see the actual shape before running against real
  forcing data.

## How to run for real, on your machine

```bash
# from C:\WORK\OilTrace\, venv activated, copernicusmarine + cdsapi already configured
python drift/fetch_forcing.py \
  --lon 65.0 --lat 18.5 \
  --detected-at 2026-08-30T06:00:00 \
  --backward-hours 48 \
  --out-dir data/cache/forcing

# use the --currents / --winds paths it prints:
python drift/backward_ensemble.py \
  --spill-id TEST-001 \
  --lon 65.0 --lat 18.5 \
  --detected-at 2026-08-30T06:00:00 \
  --currents data/cache/forcing/glorys_currents_....nc \
  --winds data/cache/forcing/era5_wind_....nc \
  --n-members 25 --backward-hours 48 \
  --out origin_ensemble.json
```

25 members x 200 particles = ~5000 endpoints, each member running for 48h of
15-min backward steps — expect low tens of seconds total on a laptop CPU, not
minutes. If it's much slower than that, paste the real timing/output here
before assuming something's wrong.

## What's honestly NOT done yet (don't claim otherwise)

- `age_estimate_hours` is a placeholder (`null`) — per schemas.md, backward
  drift gives position, not age; the real heuristic needs Detection's
  area/perimeter growth data, which doesn't exist yet.
- `forward_hypotheses` is intentionally `[]` — the "confession simulation"
  forward run needs candidate vessels from Attribution, which hasn't started.
  Don't fabricate placeholder vessels here; wire this once Attribution ships
  its first candidate list.
- Real GLORYS/ERA5 download has **not** been executed end-to-end from this
  sandbox (no access to your credentials) — only the ensemble/KDE/schema logic
  downstream of that has been verified. Run `fetch_forcing.py` yourself and
  paste any real error output back into this thread per the debugging template
  in the Orchestration Playbook — don't guess at fixes for errors you haven't
  seen yet.
