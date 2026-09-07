# OilTrace C2 Cockpit Elevation & Comprehensive Audit Plan (Round 1)

## Executive Summary
This document establishes the master execution plan for Round 1 Council operations across the **OilTrace** repository. The mandate spans full-stack elevation and rigorous verification:
1. **Frontend Maritime Intelligence C2 Cockpit**: Elevate UI/UX into an authoritative, mission-critical command-and-control interface with 60fps MapLibre GL rendering, high-density tactical telemetry panels, seamless 4D temporal playback scrubbing, speed-coded AIS tracks, SAR radar diagnostics, and automated Admiralty court legal dossier generation.
2. **Backend Concurrency & Pipeline Resilience**: Audit SQLite WAL concurrency, busy timeout enforcement, connection pooling, WebSocket streaming resilience, and strict adherence to `schemas.md` v1.1.
3. **100% Data Provenance Honesty**: Enforce explicit, untampered provenance labeling across all telemetry and detection layers (`real_gfw`, `real_aisstream_live`, `synthetic_fallback`).
4. **Zero-Regression Verification**: Validate end-to-end functionality via automated test suites (`pytest backend/tests attribution/test_offline_fixtures.py`) and production frontend build (`npm run build`).

---

## Council Roles & Claim Status

| Role | Domain & Key Responsibilities | Claim Status | Assigned Agent |
|---|---|---|---|
| **Chief-Systems-Orchestrator** | Overall architecture alignment, council synchronization, test execution, release gating | **Claimed** | Chief-Systems-Orchestrator |
| **Cartography-Engine-Lead** | MapLibre GL 60fps optimization, WebGL layer management, speed-coded vessel tracks, viewport bounds & coordinate standard (`[lon, lat]`) | **Claimed** | Cartography-Engine-Lead |
| **Temporal-Playback-Specialist** | 4D playback scrubbing, temporal interpolation, time-slider synchronization across detections, drift ensembles, and AIS pings | **Claimed** | Temporal-Playback-Specialist |
| **SAR-Radar-Forensics-Lead** | SAR diagnostics panel, VV/VH polarization inspection, wind-slick contrast, lookalike suppression validation | **Claimed** | SAR-Radar-Forensics-Lead |
| **Maritime-Attribution-Auditor** | Data provenance honesty enforcement (`real_gfw`, `real_aisstream_live`, `synthetic_fallback`), AIS spoofing indicators, vessel ranking accuracy | **Claimed** | Maritime-Attribution-Auditor |
| **FullStack-Contract-Guardian** | Strict `schemas.md` v1.1 contract verification, Pydantic/TypeScript sync (`scripts/check_contract_sync.py`), schema validation | **Claimed** | FullStack-Contract-Guardian |
| **Backend-Pipeline-Optimizer** | SQLite WAL concurrency (`PRAGMA journal_mode=WAL`, `busy_timeout=10000`), connection pool isolation, WebSocket streaming resilience | **Claimed** | Backend-Pipeline-Optimizer |
| **Admiralty-Legal-Reporter** | Court dossier generation (PDF/structured export), evidentiary chain of custody, cryptographic hashes, forensic audit trails | **Claimed** | Admiralty-Legal-Reporter |
| **Adversarial-Chaos-Tester** | Edge-case boundary testing, offline fixtures verification, automated test suites execution, build stability checks | **Claimed** | Adversarial-Chaos-Tester |

---

## Phase Breakdown

### Phase 1: Baseline Verification & Contract Inspection
- [ ] **T1.1**: Execute baseline automated test suite: `pytest backend/tests attribution/test_offline_fixtures.py -v`. *(Adversarial-Chaos-Tester)*
- [ ] **T1.2**: Execute baseline frontend production build: `npm --prefix frontend run build` to detect existing type and asset compilation issues. *(Adversarial-Chaos-Tester)*
- [ ] **T1.3**: Audit all data structures against `schemas.md` v1.1 using contract sync tooling (`python scripts/check_contract_sync.py`). *(FullStack-Contract-Guardian)*
- [ ] **T1.4**: Inventory all data ingestion pathways and establish exact boundaries for provenance labels: `real_gfw`, `real_aisstream_live`, and `synthetic_fallback`. *(Maritime-Attribution-Auditor)*

### Phase 2: Backend Concurrency, Schemas v1.1 & WebSocket Fortification
- [ ] **T2.1**: **SQLite Concurrency & WAL Audit**:
  - Enforce `PRAGMA journal_mode=WAL;` across all database connections (`backend/` databases and `data/live_ais.db`).
  - Set `PRAGMA busy_timeout=10000;` to prevent immediate `OperationalError: database is locked`.
  - Configure `PRAGMA synchronous=NORMAL;` and `PRAGMA foreign_keys=ON;`.
  - Enforce engine `connect_args={"timeout": 15}` and check session pool lifecycle across FastAPI endpoints and background threads. *(Backend-Pipeline-Optimizer)*
- [ ] **T2.2**: **WebSocket Streaming Resilience**:
  - Audit connection manager lifecycle, heartbeat/ping-pong mechanisms, reconnection logic, and backpressure handling for real-time AIS/SAR feeds. *(Backend-Pipeline-Optimizer)*
- [ ] **T2.3**: **Strict Schemas v1.1 Adherence**:
  - Verify Pydantic schemas in `backend/app/models.py` and routers against canonical specifications:
    - GeoJSON standard `[lon, lat]` ordering in geometry coordinates.
    - Required fields in `slick_detection.geojson` (`spill_id`, `detected_at`, `centroid`, `area_km2`, `oil_confidence`, `thickness_class`, `data_provenance`).
    - Required fields in `origin_ensemble.json` and `vessel_attribution.json`.
  - Eliminate any missing or misnamed attributes. *(FullStack-Contract-Guardian)*
- [ ] **T2.4**: **Data Provenance Honesty Verification**:
  - Ensure every record emitted by backend pipelines carries verified `data_provenance` (`real_gfw`, `real_aisstream_live`, or `synthetic_fallback`).
  - Prohibit synthetic mocks from masquerading as live AIS or GFW inputs. *(Maritime-Attribution-Auditor)*

### Phase 3: Frontend Maritime Intelligence C2 Cockpit Elevation
- [ ] **T3.1**: **High-Performance MapLibre GL Rendering (60fps Target)**:
  - Optimize GeoJSON source updates via `setData` debouncing / diffing.
  - Implement speed-coded vessel trajectories (color-ramped lines based on SOG/speed over ground knots).
  - Ensure slick polygons, drift cones, and vessel tracks render smoothly without frame drops. *(Cartography-Engine-Lead)*
- [ ] **T3.2**: **4D Temporal Playback & Scrubbing Engine**:
  - Synchronize timeline scrubber with detection timestamp, backward/forward drift simulation steps, and vessel AIS track positions.
  - Provide variable playback speed (1x, 5x, 10x, 60x) and frame-accurate stepping. *(Temporal-Playback-Specialist)*
- [ ] **T3.3**: **SAR Radar Diagnostics & Forensics Panel**:
  - Display co-polarized (VV) and cross-polarized (VH) metrics, incidence angle, and wind-slick contrast ratios.
  - Surface lookalike suppression veto factors (biogenic slicks, low-wind zones, internal waves) with visual indicators. *(SAR-Radar-Forensics-Lead)*
- [ ] **T3.4**: **High-Density Telemetry & Tactical UI**:
  - Equip C2 cockpit with real-time status bars: AIS stream status, active satellite passes, suspect vessel attribution ranking, and confidence scores.
  - Maintain crisp military/intelligence HUD aesthetic with dark mode contrast and responsive layout. *(Chief-Systems-Orchestrator & Cartography-Engine-Lead)*
- [ ] **T3.5**: **Admiralty Court Dossier Generation**:
  - Implement authoritative legal export (comprehensive PDF / audit dossier) containing incident overview, satellite capture metadata, drift trajectory probability envelopes, AIS suspect match rankings, and SHA-256 evidence chain of custody. *(Admiralty-Legal-Reporter)*

### Phase 4: Edge-Case Hardening & Integration
- [ ] **T4.1**: Audit RK4 numerical drift model for division-by-zero, missing environmental grid boundaries, and antimeridian/polar limits. *(Backend-Pipeline-Optimizer & Adversarial-Chaos-Tester)*
- [ ] **T4.2**: Test empty/zero-candidate vessel attribution queries and missing AIS ping windows. *(Maritime-Attribution-Auditor & Adversarial-Chaos-Tester)*
- [ ] **T4.3**: Validate frontend graceful fallbacks on network dropouts or backend WebSocket disconnects. *(Temporal-Playback-Specialist & Adversarial-Chaos-Tester)*

### Phase 5: Verification, Regression & Release Gating
- [ ] **T5.1**: Execute full test suite:
  ```bash
  pytest backend/tests attribution/test_offline_fixtures.py -v
  ```
  Ensure all tests pass with zero errors. *(Adversarial-Chaos-Tester & Chief-Systems-Orchestrator)*
- [ ] **T5.2**: Execute production frontend build:
  ```bash
  cd frontend && npm run build
  ```
  Ensure zero TypeScript errors, zero lint warnings, and clean bundle generation. *(FullStack-Contract-Guardian & Adversarial-Chaos-Tester)*
- [ ] **T5.3**: Perform comprehensive audit review and compile release dossier. *(Chief-Systems-Orchestrator)*

---

## Detailed Task Checklist

- [ ] **CHK-01**: Run baseline `pytest backend/tests attribution/test_offline_fixtures.py` and capture status.
- [ ] **CHK-02**: Run baseline `npm --prefix frontend run build` and capture build output.
- [ ] **CHK-03**: Verify SQLite engine configurations: `journal_mode=WAL`, `busy_timeout=10000`, `synchronous=NORMAL`.
- [ ] **CHK-04**: Audit FastAPI WebSocket routes (`/ws/*`) for connection lifecycles, disconnect resilience, and thread safety.
- [ ] **CHK-05**: Reconcile backend models with `schemas.md` v1.1, ensuring correct GeoJSON coordinate order `[lon, lat]`.
- [ ] **CHK-06**: Audit data ingestion scripts for 100% provenance honesty (`real_gfw`, `real_aisstream_live`, `synthetic_fallback`).
- [ ] **CHK-07**: Verify MapLibre GL 60fps rendering, speed-coded vessel track shaders/styles, and layer toggle responsiveness.
- [ ] **CHK-08**: Test 4D temporal playback scrubber for smooth interpolation across drift steps and AIS vessel pings.
- [ ] **CHK-09**: Inspect SAR radar diagnostics panel: polarization ratio, incidence angle, and lookalike suppression factors.
- [ ] **CHK-10**: Verify Admiralty court dossier generator output, formatting, and evidence chain completeness.
- [ ] **CHK-11**: Re-run complete backend test suite and verify 0 failures.
- [ ] **CHK-12**: Re-run frontend production build and verify 0 errors.
