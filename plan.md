# OilTrace Council Plan: Comprehensive Audit & C2 Elevation (Round 1)

## Executive Summary
This document establishes the authoritative execution plan for elevating the OilTrace maritime intelligence platform into a mission-critical Command & Control (C2) cockpit and auditing backend systems for absolute schema fidelity, SQLite WAL concurrency, WebSocket resilience, and uncompromised data provenance.

---

## Council Roles & Claim Status

| Role | Council Member | Status | Focus Area |
| :--- | :--- | :--- | :--- |
| **Naval UI Architect** | `@Naval-UI-Architect` | `CLAIMED` | C2 Cockpit layout, high-density telemetry panels, MIL-SPEC tactical aesthetics |
| **Cartography Engine Lead** | `@Cartography-Engine-Lead` | `CLAIMED` | MapLibre GL 60fps rendering, speed-coded vector tracks, GPU layer pipelines |
| **Temporal Playback Specialist**| `@Temporal-Playback-Specialist`| `CLAIMED` | 4D temporal playback scrubber, discrete interpolation, historical timeline |
| **SAR Radar Forensics Lead** | `@SAR-Radar-Forensics-Lead` | `CLAIMED` | SAR radar diagnostics, Sentinel-1 polarimetry, slick contour verification |
| **FullStack Contract Guardian** | `@FullStack-Contract-Guardian` | `CLAIMED` | Strict `schemas.md` v1.1 compliance across Python Pydantic & TS interfaces |
| **Backend Pipeline Optimizer** | `@Backend-Pipeline-Optimizer` | `CLAIMED` | SQLite WAL concurrency, thread safety, connection pooling, query efficiency |
| **Admiralty Legal Reporter** | `@Admiralty-Legal-Reporter` | `CLAIMED` | Court-admissible dossier generation, evidence chain of custody, PDF audit |
| **Adversarial Chaos Tester** | `@Adversarial-Chaos-Tester` | `CLAIMED` | WebSocket resilience, network reconnect backoff, telemetry fuzzing |
| **Chief Systems Orchestrator** | `@Chief-Systems-Orchestrator` | `CLAIMED` | 100% provenance honesty, automated test verification, release sign-off |

---

## Phase Breakdown & Work Packages

### Phase 1: Data Contract Audit & Provenance Verification
- [ ] **Audit Pydantic Models & TypeScript Types**:
  - Reconcile `backend/app/models.py` with `schemas.md` v1.1.
  - Verify all fields for AIS points, dark vessel events, slick detections, and attribution scores.
  - Validate TypeScript interfaces in `frontend/src/types/index.ts` against API contract schemas.
- [ ] **Enforce 100% Data Provenance Honesty**:
  - Verify explicit provenance tagging on every vessel track and telemetry packet (`real_gfw`, `real_aisstream_live`, `synthetic_fallback`).
  - Guarantee zero synthetic data masking as real-world live AIS or GFW feeds.
  - Inspect fallback cascades to ensure provenance flags are immutable across transformations.

### Phase 2: Backend Architecture, Concurrency & Stream Resilience
- [ ] **SQLite WAL Concurrency & Locking Mitigation**:
  - Audit `backend/app/db.py` and SQLite connection initialization.
  - Ensure `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `PRAGMA busy_timeout=5000`.
  - Validate write queues and thread locks for high-frequency live AIS ingestion.
- [ ] **WebSocket Streaming Resilience**:
  - Implement heartbeat keep-alives and automatic exponential backoff reconnection.
  - Ensure state recovery on socket reconnect without duplication or race conditions.
  - Test client buffer management under high telemetry ingress.

### Phase 3: Frontend C2 Cockpit & Visual Intelligence Elevation
- [ ] **Maritime Intelligence C2 Cockpit Architecture**:
  - Refactor layout into an integrated tactical C2 interface with high-density data readouts.
  - Telemetry panels for vessel specifications, MMSI, flag state, IMO, draught, SOG, COG, and radar cross-section.
- [ ] **MapLibre GL 60fps Cartography & Speed-Coded Tracks**:
  - Optimize GeoJSON source updates using diffs rather than full re-renders.
  - Render vessel tracks with color-ramped velocity coding (knots) and heading direction vectors.
  - Ensure 60fps smooth pan/zoom during active multi-track rendering.
- [ ] **4D Temporal Playback Scrubbing Engine**:
  - Time scrubber allowing scrubbing across incident timelines (T0 detection, AIS blackout, drift cone, rendezvous).
  - Synchronized track interpolation and spatial slick dispersion modeling.
- [ ] **SAR Radar Diagnostics & Forensics**:
  - SAR polarimetry visualization, backscatter threshold histograms, and wind speed correction matrices.
- [ ] **Admiralty Legal Court Dossier Generation**:
  - Generate comprehensive, court-admissible PDF forensic reports.
  - Embed cryptographic hashes (SHA-256), chain of custody timestamps, source imagery metadata, and satellite ephemeris.

### Phase 4: Automated Verification, Builds & Regression Zero-Tolerance
- [ ] **Backend Test Suite**:
  - Run `pytest backend/tests` to ensure 100% passing tests.
  - Run `pytest attribution/test_offline_fixtures.py` for attribution calculation validation.
- [ ] **Frontend Production Build**:
  - Run `npm run build` in `frontend/` to ensure zero type errors and clean asset compilation.
- [ ] **End-to-End Integrity Audit**:
  - Validate end-to-end data flow from SQLite WAL -> FastAPI WebSocket/REST -> MapLibre C2 Cockpit.

---

## Verification Plan

### Test Commands
```bash
# 1. Backend test suite
python -m pytest backend/tests -v

# 2. Offline attribution fixtures test
python -m pytest attribution/test_offline_fixtures.py -v

# 3. Frontend production build
cd frontend && npm run build
```

### Acceptance Criteria
1. All pytest test suites execute with zero failures and zero warnings.
2. Frontend build completes with zero TypeScript errors.
3. Provenance indicators prominently displayed in UI for every entity.
4. Concurrency stress test against SQLite shows zero `database is locked` errors.
5. C2 Cockpit renders MapLibre layers smoothly with 4D scrubbing capabilities.
