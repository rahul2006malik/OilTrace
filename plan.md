# OilTrace Audit & Fortification Plan (Round 1)

## Executive Summary
Audit of the **OilTrace** repository for edge-case bugs, SQLite concurrency issues, and data contract compliance against `schemas.md` (v1.1 / canonical data contracts), followed by end-to-end verification via backend `pytest` suite and `frontend` build.

---

## Team Roles & Claim Status

| Role | Focus Area | Claim Status | Assigned Agent |
|---|---|---|---|
| **Lead Agent** | Contract compliance audit, model-schema synchronization, and coordination | **Claimed** | Lead Agent |
| **Systems-Architect** | SQLite concurrency audit, WAL mode configuration, connection pool & transaction management | **Claimed** | Systems-Architect |
| **Adversarial-QA** | Edge-case fuzzing, pytest execution, frontend build verification, and boundary condition audit | **Claimed** | Adversarial-QA |

---

## Phase Breakdown

### Phase 1: Baseline Verification & Environment Sanity
- [ ] Run backend `pytest` to establish the baseline failure/pass state. *(Adversarial-QA)*
- [ ] Run frontend type-check / build (`npm run build`) to identify compilation or lint errors. *(Adversarial-QA)*
- [ ] Verify test database fixtures and schema synchronization scripts (`scripts/check_contract_sync.py`). *(Lead Agent)*

### Phase 2: SQLite Concurrency & Transaction Integrity Audit
- [ ] Audit SQLite database engine initialization in `backend/`:
  - Enforce `PRAGMA journal_mode=WAL;`
  - Enforce `PRAGMA busy_timeout=5000;`
  - Enforce `PRAGMA synchronous=NORMAL;`
  - Enforce foreign keys `PRAGMA foreign_keys=ON;` *(Systems-Architect)*
- [ ] Audit FastAPI session lifecycle (`get_db` dependency / scoped sessions) to prevent thread contention or leaky transactions across async endpoints. *(Systems-Architect)*
- [ ] Check background task runners and simulation jobs for isolated DB connections to prevent `sqlite3.OperationalError: database is locked`. *(Systems-Architect)*

### Phase 3: Data Contract Compliance Audit (`schemas.md` v1.1 / Canonical)
- [ ] Verify `slick_detection.geojson` contract:
  - Mandatory fields (`spill_id`, `detected_at`, `centroid`, `area_km2`, `oil_confidence`, `thickness_class`, `lookalike_suppressed`, `data_provenance`).
  - Strict provenance validation (`real_detector` | `real_uploaded_fixture`). *(Lead Agent)*
- [ ] Verify `origin_ensemble.json` contract:
  - Forcing dataset metadata, ensemble member array structures, coordinate arrays. *(Lead Agent)*
- [ ] Verify `vessel_attribution.json` contract:
  - Suspect vessel ranking, distance/time anomaly scores, AIS spoofing indicators. *(Lead Agent)*
- [ ] Audit bidirectional synchronization between:
  - Backend Pydantic models (`backend/app/models.py`)
  - Frontend TypeScript types (`frontend/src/types/index.ts`, `contracts/schema.ts`)
  - Run `scripts/check_contract_sync.py` if present. *(Lead Agent)*

### Phase 4: Edge-Case Bug Hunting & Boundary Hardening
- [ ] **Detection Subsystem**:
  - Empty or invalid SAR scene input handling.
  - Zero-area slicks, non-closed polygon GeoJSON, invalid coordinate ranges.
  - Lookalike suppression veto logic edge cases. *(Adversarial-QA)*
- [ ] **Drift Subsystem**:
  - Division by zero in RK4 integration step sizes or trajectory velocities.
  - Out-of-bounds geographic coordinates during backward drift integration.
  - Missing or incomplete ocean current / wind forcing datasets fallback behavior. *(Systems-Architect)*
- [ ] **Attribution Subsystem**:
  - Missing AIS vessel pings or temporal gaps.
  - Empty candidate vessel set handling.
  - Confidence score clamping in range `[0.0, 1.0]`. *(Lead Agent)*

### Phase 5: Verification & Full Suite Execution
- [ ] Re-run full backend `pytest` suite ensuring all tests pass cleanly. *(Adversarial-QA)*
- [ ] Run full frontend production build (`npm run build`) in `frontend/`. *(Adversarial-QA)*
- [ ] Validate final audit report and document any fixes made. *(All Members)*

---

## Detailed Task Checklist

- [ ] **T1.1**: Run baseline `pytest` and log failing test signatures.
- [ ] **T1.2**: Run baseline `frontend` build check (`npm run build` / `npm run type-check`).
- [ ] **T2.1**: Audit SQLite connection strings and PRAGMA settings across backend database configuration.
- [ ] **T2.2**: Audit async session concurrency in FastAPI route handlers and background tasks.
- [ ] **T3.1**: Inspect `schemas.md` specifications against Pydantic schemas in `backend/app/models.py`.
- [ ] **T3.2**: Inspect TypeScript interfaces in `frontend/src/types/` and `contracts/` against `schemas.md`.
- [ ] **T3.3**: Ensure strict validation and enum enforcement (`data_provenance`, `thickness_class`, etc.).
- [ ] **T4.1**: Check edge cases in backward ensemble drift calculations (zero time steps, missing grids).
- [ ] **T4.2**: Check edge cases in polygon centroid and geodesic area calculation (polar/antimeridian/zero vertices).
- [ ] **T4.3**: Check vessel attribution scoring when zero candidate vessels match time-space window.
- [ ] **T5.1**: Execute comprehensive test suite (`pytest -v`).
- [ ] **T5.2**: Execute frontend build (`cd frontend && npm run build`).
- [ ] **T5.3**: Compile audit summary report.
