# OilTrace Audit & Fortification Plan (Round 1)

## Executive Summary
Comprehensive audit and fortification of the **OilTrace** repository covering:
1. **SQLite Concurrency & Multi-Tenant Locking**: Eliminating `OperationalError: database is locked` via WAL mode, busy timeouts, connection pool architecture, and transaction boundary hardening.
2. **Contract Compliance**: Validating end-to-end alignment with `schemas.md` v1.1 (backend Pydantic models, frontend TypeScript types, GeoJSON standard `[lon, lat]` coordinate order, and strict provenance enums).
3. **Edge-Case Bugs & Boundary Hardening**: Null/empty inputs, zero-area polygon handling, polar/antimeridian edge cases, division-by-zero in RK4 integration, and unhandled AIS gaps.
4. **Verification**: Full validation through backend `pytest` suite and frontend production build (`npm run build`).

---

## Team Roles & Claim Status

| Role | Focus Area | Claim Status | Assigned Agent |
|---|---|---|---|
| **Forensic-Auditor** | Contract compliance audit (`schemas.md` v1.1), model-schema synchronization, and forensic data provenance verification | **Claimed** | Forensic-Auditor |
| **Systems-Architect** | SQLite concurrency audit, WAL mode configuration, connection pool & transaction management, RK4 drift numerical edge-cases | **Claimed** | Systems-Architect |
| **Adversarial-QA** | Edge-case fuzzing, baseline & regression pytest execution, frontend build verification, and boundary condition audit | **Claimed** | Adversarial-QA |

---

## Phase Breakdown

### Phase 1: Baseline Verification & Environment Sanity
- [ ] Run backend `pytest` to establish the baseline failure/pass state. *(Adversarial-QA)*
- [ ] Run frontend type-check / build (`npm run build`) to identify compilation or lint errors. *(Adversarial-QA)*
- [ ] Verify test database fixtures and schema synchronization scripts (`scripts/check_contract_sync.py`). *(Forensic-Auditor)*

### Phase 2: SQLite Concurrency & Transaction Integrity Audit
- [ ] Audit SQLite database engine initialization in `backend/`:
  - Enforce `PRAGMA journal_mode=WAL;` (Write-Ahead Logging for concurrent readers/single writer).
  - Enforce `PRAGMA busy_timeout=10000;` (10s busy wait instead of immediate failure).
  - Enforce `PRAGMA synchronous=NORMAL;` (Optimal balance of durability and speed in WAL mode).
  - Enforce foreign keys `PRAGMA foreign_keys=ON;`.
  - Verify SQLAlchemy / SQLite `connect_args={"timeout": 15}` and check pool class (`NullPool` vs `QueuePool` for multi-threaded Uvicorn). *(Systems-Architect)*
- [ ] Audit FastAPI session lifecycle (`get_db` dependency / scoped sessions) to prevent thread contention, unclosed sessions, or leaky transactions across async endpoints. *(Systems-Architect)*
- [ ] Check background task runners (simulation jobs, AIS ingestion) for isolated DB connections to avoid cross-thread session reuse and lockups. *(Systems-Architect)*
- [ ] Concurrency stress validation: verify database behavior under simultaneous read and write API operations. *(Systems-Architect & Adversarial-QA)*

### Phase 3: Data Contract Compliance Audit (`schemas.md` v1.1 / Canonical)
- [ ] Verify `slick_detection.geojson` contract:
  - Mandatory fields (`spill_id`, `detected_at`, `centroid` as `[lon, lat]`, `area_km2`, `oil_confidence`, `thickness_class`, `lookalike_suppressed`, `data_provenance`).
  - Strict provenance validation (`real_detector` | `real_uploaded_fixture`).
  - Strict enum validation for `thickness_class` (`negligible` | `sheen` | `rainbow` | `metallic` | `true_color` | `discontinuous_true_color`). *(Forensic-Auditor)*
- [ ] Verify `origin_ensemble.json` contract:
  - Forcing dataset metadata, ensemble member array structures, coordinate arrays. *(Forensic-Auditor)*
- [ ] Verify `vessel_attribution.json` contract:
  - Suspect vessel ranking, distance/time anomaly scores, AIS spoofing indicators. *(Forensic-Auditor)*
- [ ] Audit bidirectional synchronization between:
  - Backend Pydantic models (`backend/app/models.py`, `backend/app/schemas/`)
  - Frontend TypeScript types (`frontend/src/types/index.ts`, `contracts/schema.ts`)
  - Execute `scripts/check_contract_sync.py` to verify full type alignment. *(Forensic-Auditor)*

### Phase 4: Edge-Case Bug Hunting & Boundary Hardening
- [ ] **Detection Subsystem**:
  - Empty or invalid SAR scene input handling (corrupt TIFF, missing metadata).
  - Zero-area slicks, non-closed polygon GeoJSON, invalid coordinate ranges (`[-180, 180]`, `[-90, 90]`).
  - Lookalike suppression veto logic edge cases (handling NaN / borderline confidence values). *(Adversarial-QA)*
- [ ] **Drift Subsystem**:
  - Division by zero in RK4 integration step sizes or trajectory velocities.
  - Out-of-bounds geographic coordinates during backward drift integration (polar regions, antimeridian crossing).
  - Missing or incomplete ocean current / wind forcing datasets fallback behavior. *(Systems-Architect)*
- [ ] **Attribution Subsystem**:
  - Missing AIS vessel pings or temporal gaps.
  - Empty candidate vessel set handling (graceful empty array response rather than 500 error).
  - Confidence score clamping in range `[0.0, 1.0]`. *(Forensic-Auditor)*

### Phase 5: Verification & Full Suite Execution
- [ ] Re-run full backend `pytest` suite ensuring all tests pass cleanly. *(Adversarial-QA)*
- [ ] Run full frontend production build (`npm run build`) in `frontend/`. *(Adversarial-QA)*
- [ ] Validate final audit report and document any fixes made. *(All Members)*

---

## Detailed Task Checklist

- [ ] **T1.1**: Run baseline `pytest` and log failing test signatures.
- [ ] **T1.2**: Run baseline `frontend` build check (`npm run build` / `npm run type-check`).
- [ ] **T2.1**: Audit SQLite connection strings, PRAGMA settings (`WAL`, `busy_timeout`), and connection pooling across backend database configuration.
- [ ] **T2.2**: Audit async session concurrency and cleanup in FastAPI route handlers and background tasks.
- [ ] **T2.3**: Verify SQLite locking resilience under concurrent request patterns.
- [ ] **T3.1**: Inspect `schemas.md` v1.1 specifications against Pydantic schemas in `backend/app/models.py`.
- [ ] **T3.2**: Inspect TypeScript interfaces in `frontend/src/types/` and `contracts/` against `schemas.md` v1.1.
- [ ] **T3.3**: Ensure strict validation and enum enforcement (`data_provenance`, `thickness_class`, etc.).
- [ ] **T4.1**: Check edge cases in backward ensemble drift calculations (zero time steps, missing grids, polar/antimeridian limits).
- [ ] **T4.2**: Check edge cases in polygon centroid and geodesic area calculation (polar/antimeridian/zero vertices).
- [ ] **T4.3**: Check vessel attribution scoring when zero candidate vessels match time-space window.
- [ ] **T5.1**: Execute comprehensive test suite (`pytest -v`).
- [ ] **T5.2**: Execute frontend build (`cd frontend && npm run build`).
- [ ] **T5.3**: Compile audit summary report.
