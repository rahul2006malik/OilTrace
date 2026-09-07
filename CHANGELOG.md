# OilTrace — Changelog & Milestone Ledger

## [2026-09-06] Canonical v2 Overhaul & Hardening (SIH26143 / NTRO Problem Statement)

### 1. Canonical Data Contract Lockstep (v2.0)
- Defined `contracts/schema.ts` as the single canonical source of truth for all data entities (`SlickDetection`, `DriftEnsembleMember`, `DriftRun`, `EvidenceTrace`, `Candidate`, `AttributionResult`, `EvidenceDossier`, `PhysicsAtPoint`).
- Updated `schemas.md` to v2.0 matching the canonical schema.
- Synchronized FastAPI Pydantic models in `backend/app/models.py` and TypeScript definitions in `frontend/src/types/index.ts`.
- Established `scripts/check_contract_sync.py` to audit and fail CI on any schema drift.

### 2. Backend Honesty & Non-Negotiable Fixes
- **Zero Fake Milestones:** Eradicated hardcoded milestone templates (e.g. Fujairah/Vadinar) and fake SOG speed curves in `backend/app/main.py`. Implemented dynamic milestone derivation (`_derive_milestones_and_sog`) strictly based on real transponder gap intervals, reconstruction transitions, and 4D ray-trace cone intersections.
- **Genuine SHA-256 Checksums:** Replaced `hash()` placeholder with genuine SHA-256 computation over serialized canonical pipeline payloads (`hashlib.sha256`), providing true chain-of-custody verification.
- **Real Vessel Fraction:** Added dynamic computation of `real_vessel_fraction = count(real_*) / len(candidates)` rendered across UI headers and reports.
- **Proximity Fallback:** Enforced conservative 0.02 proximity fallback for candidates lacking coordinate fixes, preventing false spill-centroid clustering.

### 3. Drift Physics Inspectability ("No Black Box")
- Implemented `/drift/physics_at` and `/api/drift/physics_at` endpoint reading real GLORYS surface currents (`uo`, `vo`) and ERA5 winds (`u10`, `v10`) from cached NetCDF files using `xarray`.
- Returns live current speed ($m/s$, knots), current bearing ($^\circ$), wind speed ($m/s$), wind direction ($^\circ$), and windage-adjusted net particle velocity ($\alpha = 0.032$).

### 4. Clean Frontend Rebuild & ECDIS Command Center
- Rebuilt clean `frontend/` directory with Vite, React 18, TypeScript, Tailwind CSS, Zustand, and MapLibre GL.
- Implemented single source of truth in `useOilTraceStore.ts` — zero hardcoded numbers in JSX text nodes.
- Designed 3-column + bottom dock Command Center layout:
  - **Left (22%):** SAR radar telemetry, VV/VH polarimetric damping, geodesic area, oil confidence, elongation, and cascade execution trigger.
  - **Center (52%):** WebGL MapLibre tactical canvas rendering real slick geometry, 50/75/90% origin KDE cones, 25-member ensemble streamlines, candidate positions, and click-to-inspect physics.
  - **Right (26%):** Attributed suspects leaderboard with provenance badges (`REAL GFW` vs `SYNTHETIC`), suspicion score gauges, confidence intervals, and evidence decomposition bars.
  - **Bottom Dock:** Synchronized temporal scrubber (-48.0h to 0.0h) with playback speed controls driving both particle hindcast and vessel trajectory fixes.
- **Physics Inspector HUD:** Interactive HUD drawer displaying live GLORYS/ERA5 vectors, "Show the Math" RK4 formulation, 25-member ensemble build-up, and CMEMS/ECMWF forcing provenance banner.
- **Courtroom Evidence Dossier:** PDF exporter in `pdfGenerator.ts` utilizing Web Crypto API SHA-256 sealing for UNCLOS/MARPOL statutory admissibility.
