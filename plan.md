# OilTrace Round 1 Master Execution Plan: Comprehensive Maritime C2 Audit & Elevation

## Executive Summary
This document establishes the strategic, architectural, and verification roadmap for elevating the **OilTrace** repository into an authoritative, world-class maritime intelligence Command & Control (C2) cockpit. The unified council will audit and harden both Frontend and Backend systems: ensuring MapLibre GL 60fps GPU rendering, high-density tactical telemetry, 4D temporal playback scrubbing, speed-coded AIS tracks, SAR radar diagnostics, and Admiralty court dossier generation, while guaranteeing SQLite WAL concurrency, WebSocket streaming resilience, strict `schemas.md` v1.1 adherence, and 100% data provenance honesty (`real_gfw`, `real_aisstream_live`, `synthetic_fallback`).

---

## Council Member Task Allocation & Claim Status

| Role | Council Member | Status | Core Focus Area & Deliverables |
| :--- | :--- | :--- | :--- |
| **Naval UI Architect** | `@Naval-UI-Architect` | `[CLAIMED]` | C2 Cockpit ergonomics, high-density tactical HUD, telemetry gauges, dark-navy nautical visual hierarchy, responsive layout in `AppShell.tsx` |
| **Cartography Engine Lead** | `@Cartography-Engine-Lead` | `[CLAIMED]` | MapLibre GL 60fps WebGL rendering, speed-coded AIS vessel tracks, slick oil polygon shaders, drift uncertainty cones, viewport clustering |
| **Temporal Playback Specialist** | `@Temporal-Playback-Specialist` | `[CLAIMED]` | 4D temporal scrubber, forward/backward drift animation synchronization, play/pause/step controls, unified UTC epoch tracking |
| **SAR Radar Forensics Lead** | `@SAR-Radar-Forensics-Lead` | `[CLAIMED]` | Sentinel-1 SAR VV/VH polarization diagnostics, oil spill contour extraction, backscatter histogram analysis, cross-ratio forensics panel |
| **Maritime Attribution Auditor** | `@Maritime-Attribution-Auditor` | `[CLAIMED]` | Bayesian attribution scoring, dark vessel detection, AIS gap identification, route reconstruction audit, 100% provenance verification (`real_gfw`, `real_aisstream_live`, `synthetic_fallback`) |
| **FullStack Contract Guardian** | `@FullStack-Contract-Guardian` | `[CLAIMED]` | `schemas.md` v1.1 validation, backend Pydantic models vs TypeScript interface consistency, API contract parity, strict field checks |
| **Backend Pipeline Optimizer** | `@Backend-Pipeline-Optimizer` | `[CLAIMED]` | SQLite WAL concurrency (`journal_mode=WAL`, `busy_timeout=15000`), WebSocket streaming resilience, heartbeat/reconnect lifecycle, query optimization |
| **Adversarial Chaos Tester** | `@Adversarial-Chaos-Tester` | `[CLAIMED]` | Chaos fault injection, WebSocket drop/reconnect resilience, edge-case corrupt telemetry handling |
| **Admiralty Legal Reporter** | `@Admiralty-Legal-Reporter` | `[CLAIMED]` | UNCLOS & MARPOL Annex I compliance dossier generation, cryptographic chain-of-custody audit trail (SHA-256), exportable legal evidence packet |
| **Chief Systems Orchestrator** | `@Chief-Systems-Orchestrator` | `[CLAIMED]` | Test suite gating (`pytest backend/tests attribution/test_offline_fixtures.py`), frontend production build (`npm run build`), regression audit |

---

## Phase Breakdown & Detailed Task Checklist

### Phase 1: Contract Enforcement & Backend Concurrency Hardening
- [ ] **Contract Integrity & Schema v1.1 Validation** (`@FullStack-Contract-Guardian`)
  - Audit all Pydantic models in `backend/app/models.py` against `schemas.md` v1.1 specifications.
  - Verify mandatory fields: `source_type` (`real_gfw` | `real_aisstream_live` | `synthetic_fallback`), `provenance`, `confidence_score`, `mmsi`, `imo`, `spill_id`, `timestamp`.
  - Harmonize TypeScript interfaces in `frontend/src/types/index.ts` to ensure 1:1 type safety with backend responses.
- [ ] **SQLite WAL Concurrency & Thread-Safety** (`@Backend-Pipeline-Optimizer`)
  - Configure PRAGMA `journal_mode=WAL`, PRAGMA `synchronous=NORMAL`, and PRAGMA `busy_timeout=15000` across all database connections (`live_ais.db`, analytics DB).
  - Verify concurrent read/write isolation to prevent `sqlite3.OperationalError: database is locked` during heavy live AIS ingestion and WebSocket reads.
- [ ] **WebSocket Streaming Resilience** (`@Backend-Pipeline-Optimizer`, `@FullStack-Contract-Guardian`)
  - Implement bidirectional heartbeat (ping/pong) and keepalive intervals in FastAPI WebSocket endpoints.
  - Ensure frontend reconnection logic with exponential backoff and message deduplication.

### Phase 2: Data Provenance Honesty & Maritime Forensics Audit
- [ ] **100% Provenance Transparency** (`@Maritime-Attribution-Auditor`)
  - Audit all data sources across live streams, historical replays, and test fixtures.
  - Mandate visual provenance badges in the UI for `REAL GFW`, `REAL AISSTREAM LIVE`, and `SYNTHETIC FALLBACK`.
  - Guarantee zero synthetic data masquerades as live real-world AIS telemetry.
- [ ] **Drift Simulation & Route Reconstruction Forensics** (`@SAR-Radar-Forensics-Lead`, `@Maritime-Attribution-Auditor`)
  - Audit Runge-Kutta 4 (RK4) numerical integration in `drift/backward_ensemble.py` for physical bounds and drift accuracy.
  - Validate candidate suspect vessel ranking formulas in `attribution/` ensuring robust handling of AIS gaps, dark periods, and speed anomalies.
- [ ] **SAR Radar Diagnostics Elevation** (`@SAR-Radar-Forensics-Lead`)
  - Verify Sentinel-1 SAR VV/VH polarization diagnostics and backscatter thresholding in `SarTelemetryPanel.tsx`.
  - Ensure clear visual representation of wind-dampened slick signatures versus look-alikes.

### Phase 3: Maritime C2 Cockpit & MapLibre 60fps Elevation
- [ ] **MapLibre GL 60fps Cartographic Performance** (`@Cartography-Engine-Lead`)
  - Optimize WebGL layer render cycles in `frontend/src/components/map/layers/useVesselTracksLayer.ts`.
  - Implement speed-coded track coloration (low/cruising/high speed gradients) and smooth interpolation.
  - Render slick polygons, drift ensemble paths, and vessel uncertainty ellipses without main-thread jank.
- [ ] **4D Temporal Playback Scrubbing** (`@Temporal-Playback-Specialist`)
  - Validate high-precision timeline scrubber with playback controls (play, pause, reverse, 1x/5x/10x speed).
  - Synchronize viewport vessel coordinates and slick boundary states to the active scrubber time cursor ($T_0 \pm \Delta t$).
- [ ] **Tactical C2 Cockpit UX & Admiralty Legal Dossier** (`@Naval-UI-Architect`, `@Admiralty-Legal-Reporter`)
  - Elevate `AppShell.tsx` into a mission-grade naval tactical cockpit: high-contrast telemetry panels, alert feeds, and coordinate tracking.
  - Audit Admiralty legal dossier generation: verify MARPOL Annex I / UNCLOS evidentiary compliance with cryptographic SHA-256 chain-of-custody verification.

### Phase 4: Automated Verification & Test Gating
- [ ] **Backend Test Suite Execution** (`@Chief-Systems-Orchestrator`)
  - Execute `pytest backend/tests attribution/test_offline_fixtures.py -v`.
  - Ensure 100% test passing, zero regressions, and zero unhandled warnings.
- [ ] **Frontend Production Build Verification** (`@Chief-Systems-Orchestrator`)
  - Execute `npm run build` in `frontend/`.
  - Verify zero TypeScript compiler errors, clean bundle compilation, and zero asset resolution errors.
- [ ] **Final Pre-Execution Signoff** (`Council Consensus`)
  - Verify all council members' requirements are satisfied and ready for execution transition.

---

## Consensus Gating Checklist
- [x] Current repository state inspected via `git log --oneline -5`
- [x] Workspace structure reviewed
- [x] Master execution plan synthesized and committed to `plan.md`
- [ ] Round 1 Consensus voting initiated
