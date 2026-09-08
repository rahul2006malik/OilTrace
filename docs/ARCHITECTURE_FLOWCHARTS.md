# OilTrace (SIH26143 — NTRO) Complete Architecture & Flowchart Suite

This document contains the complete technical flowchart suite for **OilTrace: Satellite SAR Oil Spill Detection, Lagrangian Metocean Drift Hindcasting, and AIS/Dark-Vessel Attribution**.

---

## 1. Master End-to-End Forensics Pipeline

```mermaid
flowchart TD
    classDef input fill:#1e293b,stroke:#0284c7,stroke-width:2px,color:#f8fafc;
    classDef sub1 fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef sub2 fill:#0f172a,stroke:#818cf8,stroke-width:2px,color:#f8fafc;
    classDef sub3 fill:#0f172a,stroke:#f59e0b,stroke-width:2px,color:#f8fafc;
    classDef fusion fill:#0f172a,stroke:#ef4444,stroke-width:2px,color:#f8fafc;
    classDef output fill:#1e293b,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    S1["Sentinel-1 SAR Scene<br/>(C-Band Level-1 GRD GeoTIFF)"]:::input --> DETECT["Subsystem 1: SAR Cascade<br/>Stage 1 Classifier Gate + Stage 2 Whole-Scene U-Net"]:::sub1
    
    DETECT --> GEOJSON["Canonical slick_detection.geojson<br/>• Spill Centroid (lon, lat)<br/>• Area (km²), Elongation Ratio<br/>• Thickness Class (dB damping)"]:::sub1

    GEOJSON --> DRIFT["Subsystem 2: OpenDrift 1.14.10<br/>Hot Metocean Buffer (GLORYS + ERA5)<br/>25-Member RK4 Lagrangian Ensemble"]:::sub2

    DRIFT --> CONE["Canonical origin_ensemble.json<br/>• 50%, 75%, 90% KDE Probability Envelopes<br/>• Estimated Release Window (T_spill ± 6h)"]:::sub2

    CONE --> RECON["Subsystem 3: AIS Spatiotemporal Ingestion<br/>• Global Fishing Watch (GFW) API v2<br/>• Live AISstream WebSocket (live_ais.db)"]:::sub3

    RECON --> DR["4D Ocean-Current Dead Reckoning<br/>Euler Advection across AIS Blackout Gaps"]:::sub3

    DR --> CONF["Subsystem 4: Forward Confession Sim<br/>Reverse Hydrodynamic Testing on Top Suspects"]:::sub2

    CONF --> SCORER["Subsystem 5: 5-Factor Attribution Scorer<br/>• Proximity (0.35) • Confession (0.30)<br/>• Isolation Forest (0.15) • Prior (0.10) • Path Match (0.10)<br/>• SHAP Glass-Box XAI + Causal Veto Gate"]:::fusion

    SCORER --> ATTR_JSON["Canonical attribution_result.json<br/>• Ranked Candidate Suspects<br/>• Confidence Intervals [CI_lo, CI_hi]<br/>• Provenance (real_gfw | real_live | synthetic)"]:::fusion

    ATTR_JSON --> ORCH["FastAPI Backend Orchestrator<br/>Dual-Channel: REST /run & SSE /stream"]:::output

    ORCH --> UI["Frontend Tactical Cockpit (MapLibre GL)<br/>• 3-Column Persistent Forensic Console<br/>• -48h to 0h Temporal Scrubber<br/>• Point-Probe Physics Inspector"]:::output
    ORCH --> PDF["Admiralty Legal Dossier (ReportLab PDF)<br/>• UNCLOS Art. 211(5) Directive<br/>• SHA-256 Chain-of-Custody Digital Seal"]:::output
```

---

## 2. Subsystem 1: Two-Stage SAR Detection & Physical Feature Extraction

```mermaid
flowchart TD
    classDef proc fill:#0f172a,stroke:#38bdf8,stroke-width:1.5px,color:#f8fafc;
    classDef dec fill:#1e293b,stroke:#f59e0b,stroke-width:2px,color:#f8fafc;
    classDef term fill:#1e293b,stroke:#ef4444,stroke-width:1.5px,color:#f8fafc;
    classDef pass fill:#1e293b,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    IN["Raw Sentinel-1 Scene<br/>(GeoTIFF, C-Band SAR)"] --> S1["Stage 1: Whole-Scene Screening Classifier<br/>CNN / ResNet Backbone"]:::proc
    
    S1 --> D1{"P(oil) ≥ 0.50<br/>(classify_threshold)?"}:::dec
    
    D1 -- "No (Look-alike / Clean Ocean)" --> EXIT1["Early Exit<br/>has_oil: False<br/>prob_map: None<br/>Execution: ~0.15s"]:::term
    
    D1 -- "Yes (Probable Spill)" --> S2["Stage 2: Whole-Scene U-Net Segmenter<br/>• 'mixed_v2' Checkpoint<br/>• Wide Decoder Architecture<br/>• 4-Way Test-Time Augmentation (TTA)"]:::proc

    S2 --> PMAP["Continuous Probability Map<br/>(H × W float32 array in [0.0, 1.0])"]:::proc

    PMAP --> THRESH["Binarization & Morphology<br/>Binary Mask = (prob_map ≥ 0.5)"]:::proc

    THRESH --> CONTOUR["cv2.findContours(RETR_EXTERNAL)<br/>Filter Blobs: Area < 50 px Dropped"]:::proc

    D2{"Surviving Contours > 0?"}:::dec
    CONTOUR --> D2
    D2 -- "No" --> EXIT2["Exit: No Significant Slick"]:::term

    D2 -- "Yes" --> UNIFY["Shapely Polygonization<br/>• unary_union(pixel_polygons)<br/>• Douglas-Peucker Simplification (ε = 1.5 px)"]:::proc

    UNIFY --> MORPH["Morphological Analysis (Dominant Blob)<br/>• cv2.minAreaRect(largest_contour)<br/>• Elongation = max(w, h) / min(w, h)"]:::proc

    RAW["Raw Non-Normalized Scene<br/>(VV + VH Sigma-0 dB bands)"] --> DAMP["Thickness Proxy Estimation<br/>Δ_VV = Mean(water_dB) - Mean(oil_dB)<br/>Δ_VH = Mean(water_dB) - Mean(oil_dB)"]:::proc

    DAMP --> THICK{"Threshold Check<br/>Δ_VV ≥ 6.0 dB & Δ_VH ≥ 4.0 dB?<br/>Δ_VV ≥ 3.0 dB & Δ_VH ≥ 1.0 dB?"}:::dec
    THICK -- "High Damping" --> C_THICK["thickness_class: 'thick'"]:::proc
    THICK -- "Moderate Damping" --> C_THIN["thickness_class: 'thin'"]:::proc
    THICK -- "Low Damping" --> C_SHEEN["thickness_class: 'sheen'"]:::proc

    UNIFY --> GEO["Georeferencing Engine<br/>Priority 1: GeoTIFF ModelPixelScale / Tiepoint Tags<br/>Priority 2: Geodesic Direct Problem (pyproj.Geod.fwd WGS84)"]:::proc

    GEO --> CENTROID["Centroid & Geodesic Area Calculation<br/>• Centroid: [lon, lat]<br/>• Area: _geodesic_area_km2()"]:::proc

    CENTROID & MORPH & C_THICK & C_THIN & C_SHEEN --> CONF["Confidence Calculation<br/>oil_confidence = Mean(seg_prob) × classify_prob"]:::proc

    CONF --> OUT["Output: slick_detection.geojson<br/>schemas.md §1 Ground Truth Contract"]:::pass
```

---

## 3. Subsystem 2: Metocean Forcing Ingestion, Hot Buffer & Lagrangian Backward Ensemble

```mermaid
flowchart TD
    classDef input fill:#1e293b,stroke:#0284c7,stroke-width:2px,color:#f8fafc;
    classDef proc fill:#0f172a,stroke:#818cf8,stroke-width:1.5px,color:#f8fafc;
    classDef dec fill:#1e293b,stroke:#f59e0b,stroke-width:2px,color:#f8fafc;
    classDef loop fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef pass fill:#1e293b,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    REQ["Pipeline Request:<br/>Centroid (lon, lat), detected_at, backward_hours=48"]:::input --> BBOX["Bounding Box & Temporal Window Calculation<br/>• Bbox: [lon ± 3.0°, lat ± 3.0°]<br/>• Time: (detected_at - 54h) to (detected_at + 6h)"]:::proc

    BBOX --> BUF{"Hot Metocean Buffer<br/>Available on Disk?"}:::dec
    
    BUF -- "No / Out-of-Bounds" --> REMOTE["Remote Acquisition Pipeline<br/>• CMEMS API: GLORYS12V1 Daily Surface Currents (uo, vo)<br/>• CDS API: ECMWF ERA5 10m Hourly Winds (u10, v10)<br/>• INCOIS Indian Ocean Regional Client (Fallback)"]:::proc
    
    BUF -- "Yes" --> CACHE["Load NetCDF CF Generic Files<br/>data/cache/forcing/*.nc"]:::proc
    REMOTE --> CACHE

    CACHE --> ENS_INIT["Initialize Monte Carlo Ensemble Engine<br/>N = 25 Independent Members, Δt = -900s (-15 min)"]:::proc

    ENS_INIT --> LOOP["For Each Ensemble Member (i = 1 to 25)"]:::loop

    LOOP --> PERTURB["Apply Physical Perturbations:<br/>1. Seed Radius: r ~ U(0.6, 1.4) × 500m<br/>2. Wind Drift Leeway: α ~ N(0.030, 0.004) (3% ± 0.4%)<br/>3. Turbulent Diffusivity: Kh = 10.0 m²/s (Random Walk)<br/>4. Current Uncertainty: GLORYS vector ± 15%"]:::proc

    PERTURB --> RK4["Runge-Kutta 4th-Order (RK4) Backward Integration<br/>dX/dt = - [U_current(X, t) + α · W_wind(X, t) + R_diff(Kh)]<br/>Total Steps: 193 steps (-48 hours)"]:::proc

    RK4 --> CHECK{"Member Reached Full Duration?<br/>(No Truncation / Boundary Exit)"}:::dec
    
    CHECK -- "No (Truncated / Left Domain)" --> DROP["Drop Member (Loud Diagnostic Warning)<br/>Prevent Origin Corruption"]:::proc
    CHECK -- "Yes (Full 48h)" --> KEEP["Keep Endpoint (lon, lat, -48h)<br/>Subsample Trajectory for Replay (8 particles)"]:::proc

    DROP & KEEP --> ALL_DONE{"All 25 Members Processed?"}:::dec
    ALL_DONE -- "No" --> LOOP

    ALL_DONE -- "Yes" --> VAL{"n_complete > 0?"}:::dec
    VAL -- "No (Zero Valid Endpoints)" --> FAIL["Raise RuntimeError: Window Too Narrow"]:::proc

    VAL -- "Yes" --> KDE["2D Gaussian Kernel Density Estimation (KDE)<br/>scipy.stats.gaussian_kde(lons, lats)<br/>Grid Resolution: 100 × 100 on Matplotlib Contour Engine"]:::proc

    KDE --> CONTOUR["Extract Iso-Probability Contours<br/>• Level 50%: Core Origin Envelope (P=0.50)<br/>• Level 75%: Confidence Envelope (P=0.75)<br/>• Level 90%: Maximum Dispersion Boundary (P=0.90)"]:::proc

    CONTOUR --> CLEAN_GEO["Shapely make_valid() & Polygon Simplification<br/>Ensure Clean Closed Polygons"]:::proc

    CLEAN_GEO --> AGE["Empirical Spill Age Heuristic<br/>Fay Spreading Law Inversion: t_age = (Area_km² / 1.5)^0.6<br/>Adjusted by Elongation Ratio"]:::proc

    AGE --> OUT["Output: origin_ensemble.json<br/>schemas.md §2 Ground Truth Contract"]:::pass
```

---

## 4. Subsystem 3: 4D Dead-Reckoning Route Reconstruction & Dark Vessel Identification

```mermaid
flowchart TD
    classDef input fill:#1e293b,stroke:#0284c7,stroke-width:2px,color:#f8fafc;
    classDef proc fill:#0f172a,stroke:#f59e0b,stroke-width:1.5px,color:#f8fafc;
    classDef dec fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef alert fill:#1e293b,stroke:#ef4444,stroke-width:2px,color:#f8fafc;
    classDef pass fill:#1e293b,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    INPUT["Input: Candidate Vessel AIS Fixes<br/>+ Origin Probability Cone (origin_ensemble.json)<br/>+ Estimated Spill Window (T_spill ± 6h)"]:::input --> SORT["Sort Waypoints Chronologically (timestamp ASC)"]:::proc

    SORT --> SCAN["Iterate Consecutive Waypoints (P_k, P_{k+1})<br/>Compute Δt = t_{k+1} - t_k"]:::proc

    SCAN --> GAP{"Δt > 1.5 hours?<br/>(AIS Transponder Blackout)"}:::dec

    GAP -- "No (Continuous AIS)" --> KEEP_WP["Retain Verified AIS Fixes<br/>is_interpolated = False"]:::proc

    GAP -- "Yes (Dark Vessel Gap)" --> DR_INIT["Initialize Current-Assisted Dead Reckoning<br/>Step Size: Δt_step = 15 minutes"]:::proc

    DR_INIT --> DR_LOOP["Euler Advection across Gap:<br/>x_{t+Δt} = x_t + [V_vessel(SOG, COG) + U_GLORYS(x_t, t)] · Δt<br/>Generate Dead-Reckoned Waypoints<br/>is_interpolated = True"]:::proc

    KEEP_WP & DR_LOOP --> FULL_TRACK["Assembled Full 4D Reconstructed Track<br/>Polyline W = { (lon_i, lat_i, t_i, sog_i, cog_i) }"]:::proc

    FULL_TRACK --> RAYTRACE["4D Spatiotemporal Ray-Tracing against Origin Cone<br/>For each waypoint w_i in W:<br/>1. Evaluate Spatial Containment in Cone Polygons<br/>   ConeWeight = 1.0 (50%), 0.75 (75%), 0.50 (90%)<br/>2. Apply Exponential Temporal Decay:<br/>   T_decay = exp(- |t_i - T_origin| / τ) where τ = 6.0h"]:::proc

    RAYTRACE --> SCORE["Ray-Trace Score Calculation:<br/>RayTraceScore = max_i [ ConeWeight(w_i) · exp(-|t_i - T_origin| / 6.0) ]"]:::proc

    SCORE --> CPA["Compute Closest Point of Approach (CPA)<br/>• cpa_distance_km = min Haversine(w_i, Cone Centroid)<br/>• cpa_time_diff_hours = |t_CPA - T_origin|"]:::proc

    CPA --> RED_HERRING{"Current Distance < 15 km<br/>AND<br/>path_match_score < 0.20?"}:::dec

    RED_HERRING -- "Yes" --> FLAG_RH["Flag: [!] PROXIMATE NOW // ABSENT AT ORIGIN<br/>proximate_but_absent_at_origin = True<br/>Apply 0.25× Suspicion Penalty Factor"]:::alert

    RED_HERRING -- "No" --> CHECK_VETO{"cpa_time_diff > 12h<br/>OR<br/>(prox < 0.05 & conf < 0.05 & path < 0.05)?"}:::dec

    CHECK_VETO -- "Yes" --> APPLY_VETO["Trigger Causal Veto Gate<br/>causal_veto = True<br/>Force Suspicion Score ≤ 0.12 (Disconnected Vessel)"]:::alert

    CHECK_VETO -- "No" --> PASS["Valid Spatiotemporal Intercept<br/>path_match_score = round(RayTraceScore, 4)"]:::pass

    FLAG_RH & APPLY_VETO & PASS --> ATTR_INPUT["Transmit to 5-Factor Scorer & Tactical Cockpit"]:::proc
```

---

## 5. Subsystem 4: Hydrodynamic Forward Confession Simulation

```mermaid
flowchart TD
    classDef input fill:#1e293b,stroke:#0284c7,stroke-width:2px,color:#f8fafc;
    classDef proc fill:#0f172a,stroke:#818cf8,stroke-width:1.5px,color:#f8fafc;
    classDef dec fill:#1e293b,stroke:#f59e0b,stroke-width:2px,color:#f8fafc;
    classDef pass fill:#1e293b,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    IN["Top Candidate Vessels (Ranked 1 to 4)<br/>• Vessel Trajectory Waypoints<br/>• Estimated Release Time T_spill"]:::input --> LOC["Extract Candidate Coordinate at T_spill<br/>(rel_lon, rel_lat)"]:::proc

    LOC --> RELEASE["Seed Forward Oil Particles<br/>N = 100 Particles per Candidate<br/>Release Time: T_spill"]:::proc

    RELEASE --> FORWARD["Execute Forward Lagrangian Advection<br/>(Fast RK4 Engine or OpenOil Forward)<br/>Time Direction: POSITIVE (T_spill → T_SAR)"]:::proc

    FORWARD --> FORCING["Drive with Same Metocean Forcing Fields:<br/>• CMEMS GLORYS Current Vectors (uo, vo)<br/>• ECMWF ERA5 Wind Vectors (u10, v10)"]:::proc

    FORCING --> ARRIVE["Forward Simulation Arrives at T_SAR<br/>Particle Positions: { (lon_j, lat_j) }"]:::proc

    ARRIVE --> HULL["Construct Particle Cluster Geometry<br/>Alpha Shape / Convex Hull in Shapely"]:::proc

    HULL --> OVERLAP["Spatial Intersection Analysis with Observed SAR Polygon:<br/>1. Centroid Miss Distance: d_miss = Haversine(Hull_centroid, SAR_centroid)<br/>2. Distance Score: S_dist = exp(- d_miss / 15.0 km)<br/>3. Shape IoU Overlap: IoU = Area(Hull ∩ SAR) / Area(Hull ∪ SAR)"]:::proc

    OVERLAP --> FUSED_CONF["Confession Match Score Formulation:<br/>shape_overlap_score = 0.65 · S_dist + 0.35 · IoU"]:::proc

    FUSED_CONF --> HYP["Record Forward Hypothesis Entry:<br/>{<br/>  vessel_id: MMSI,<br/>  shape_overlap_score: float,<br/>  predicted_centroid: [lon, lat],<br/>  drift_error_km: d_miss<br/>}"]:::proc

    HYP --> FEED["Feed into 5-Factor Attribution Scorer<br/>Weight: 0.30 of Total Suspicion Score"]:::pass
```

---

## 6. Subsystem 5: 5-Factor Explainable AI (XAI) Attribution Scorer

```mermaid
flowchart TD
    classDef input fill:#1e293b,stroke:#0284c7,stroke-width:2px,color:#f8fafc;
    classDef proc fill:#0f172a,stroke:#38bdf8,stroke-width:1.5px,color:#f8fafc;
    classDef xai fill:#0f172a,stroke:#f59e0b,stroke-width:2px,color:#f8fafc;
    classDef dec fill:#1e293b,stroke:#ef4444,stroke-width:2px,color:#f8fafc;
    classDef pass fill:#1e293b,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    CAND["Candidate Vessel Population<br/>(GFW Surveillance + Live AISstream DB)"]:::input --> FEAT["14 Domain-Specific Feature Vectors:<br/>• presence_hours • gap_count • gap_duration_hours<br/>• loitering_count • loitering_duration_hours • encounter_count<br/>• speed_variance • heading_change_rate • mean_lane_deviation_km<br/>• discharge_speed_fraction (4-8 kn band) • nighttime_gap_ratio<br/>• temporal_proximity_hours • track_intersection_score • port_risk_prior"]:::proc

    FEAT --> IMPUTE["Median Imputation for Sparse AISstream Features<br/>Populate _debug_imputed_features (Zero Silent Smoothing)"]:::proc

    IMPUTE --> IFOREST["sklearn.ensemble.IsolationForest Scorer<br/>• Unsupervised Tree Partitioning<br/>• Standardized Z-Score Normalization to [0.0, 1.0]"]:::proc

    IFOREST --> SHAP_MOD["TreeSHAP Explainability Engine<br/>• Computes Base Value (Expected Value E[f(x)])<br/>• Per-Feature Marginal Contributions (φ_i)<br/>• Identifies dominant_factor (Highest Positive φ_i)"]:::xai

    SHAP_MOD --> NARRATIVE["Automated Glass-Box Natural Language Generator<br/>• Plain English Forensic Narrative<br/>• Counterfactual Explanations:<br/>  'If vessel had not disabled AIS for 14.5h, suspicion drops by 38%'"]:::xai

    PROX_IN["Drift Backward Proximity Score (0.35)<br/>Inverse Distance to 50/75/90% Cone"]:::input --> FUSION["5-Factor Weighted Score Fusion:"]:::proc
    CONF_IN["Forward Confession Match Score (0.30)<br/>Shape Overlap IoU + Centroid Miss"]:::input --> FUSION
    IFOREST --> FUSION
    PRIOR_IN["Vessel Type Maritime Risk Prior (0.10)<br/>Tanker: 0.85-0.90, Cargo: 0.55, Rig: 0.02"]:::input --> FUSION
    PATH_IN["4D Dead-Reckoning Path Match Score (0.10)<br/>RayTraceScore across AIS Gaps"]:::input --> FUSION

    FUSION --> RAW_SUSP["Compute Weighted Suspicion:<br/>S_raw = 0.35·S_prox + 0.30·S_conf + 0.15·S_anom + 0.10·S_prior + 0.10·S_path"]:::proc

    RAW_SUSP --> C1{"proximate_but_absent_at_origin<br/>Flagged True?"}:::dec
    C1 -- "Yes (Red Herring)" --> PEN1["Apply 0.25× Penalty Multiplier<br/>S_fused = S_raw · 0.25"]:::proc
    C1 -- "No" --> C2{"Causal Veto Triggered?<br/>(prox < 0.05 & conf < 0.05 & path < 0.05)"}:::dec

    C2 -- "Yes (Physically Disconnected)" --> PEN2["Apply 0.15× Veto Multiplier<br/>S_fused = S_raw · 0.15 (Max 0.12)"]:::proc
    C2 -- "No" --> OK_SUSP["S_fused = S_raw"]:::proc

    PEN1 & PEN2 & OK_SUSP --> BOOTSTRAP["Dynamic Confidence Interval Engine<br/>Dispersion scale from Ensemble Spread:<br/>CI_half_width = max(0.04, min(0.12, σ_ens · 0.85))<br/>CI = [ max(0, S - CI_w), min(1, S + CI_w) ]"]:::proc

    BOOTSTRAP --> RANK["Sort by Suspicion Score (DESC)"]:::proc

    RANK --> OUT["Output: attribution_result.json<br/>• Top Suspects Leaderboard<br/>• Evidence Trace & Provenance<br/>• dark_vessel_alert & top_k_recovery"]:::pass
```

---

## 7. Backend Architecture & Dual-Mode Orchestration (REST + SSE)

```mermaid
flowchart TD
    classDef client fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef router fill:#0f172a,stroke:#818cf8,stroke-width:1.5px,color:#f8fafc;
    classDef worker fill:#0f172a,stroke:#f59e0b,stroke-width:1.5px,color:#f8fafc;
    classDef storage fill:#1e293b,stroke:#10b981,stroke-width:2px,color:#f8fafc;

    CLIENT["Frontend Tactical Cockpit"]:::client --> REQ_REST["POST /api/pipeline/run<br/>(Standard JSON Contract)"]:::router
    CLIENT --> REQ_SSE["POST /api/pipeline/stream<br/>(Server-Sent Events Stream)"]:::router
    CLIENT --> REQ_REPORT["GET /api/reports/{spill_id}/pdf<br/>(Admiralty Dossier Request)"]:::router

    subgraph FastAPI_Async_Service ["FastAPI High-Performance Async Backend"]
        REQ_SSE --> SSE_GEN["SSE Event Generator<br/>Streams Real-Time Progress"]:::worker
        
        SSE_GEN --> P15["15%: Detection Phase<br/>U-Net Ingestion"]:::worker
        P15 --> P30["30%: Metocean Buffer<br/>GLORYS / ERA5 Resolution"]:::worker
        P30 --> P55["55%: RK4 Ensemble<br/>25 Lagrangian Backward Tracks"]:::worker
        P55 --> P75["75%: Origin KDE Envelopes<br/>Iso-density Contours"]:::worker
        P75 --> P88["88%: Attribution Reconstruction<br/>4D Ray-Tracing & AIS Gap DR"]:::worker
        P88 --> P98["98%: Forward Confession<br/>Hydrodynamic Verification"]:::worker
        P98 --> P100["100%: Pipeline Complete<br/>Emit AttributionResult JSON"]:::worker

        REQ_REST --> EXEC["Orchestrator: run_pipeline()"]:::worker
        EXEC --> SCEN_CHECK{"Benchmark Scenario Match?<br/>(Mumbai, Vadinar, Goa, Dark)"}:::worker
        
        SCEN_CHECK -- "Match Found" --> SCEN_CACHE["Load Validated Scenario Profile<br/>Instant High-Fidelity Response"]:::storage
        SCEN_CHECK -- "Custom / Live Spill" --> FULL_PIPE["Execute Full Computational Subsystems<br/>Drift → Attribution → RouteRecon"]:::worker

        REQ_REPORT --> PDF_GEN["ReportLab Admiralty PDF Generator<br/>generate_admiralty_pdf_report()"]:::worker
    end

    subgraph Data_Layer ["Persistent & Caching Infrastructure"]
        SQLITE[("SQLite live_ais.db<br/>Real-Time AIS Pings")]:::storage
        NETCDF[("data/cache/forcing/*.nc<br/>Hot Metocean Buffer")]:::storage
        REPORTS[("data/cache/reports/RPT-*.pdf<br/>Generated Legal Dossiers")]:::storage
    end

    FULL_PIPE <--> SQLITE
    FULL_PIPE <--> NETCDF
    PDF_GEN --> REPORTS
    REPORTS --> CLIENT
    P100 --> CLIENT
    SCEN_CACHE --> CLIENT
```

---

## 8. Frontend Tactical Cockpit & Operational User Workflow

```mermaid
flowchart TD
    classDef auth fill:#1e293b,stroke:#ef4444,stroke-width:2px,color:#f8fafc;
    classDef ui fill:#0f172a,stroke:#38bdf8,stroke-width:1.5px,color:#f8fafc;
    classDef map fill:#0f172a,stroke:#818cf8,stroke-width:2px,color:#f8fafc;
    classDef modal fill:#0f172a,stroke:#f59e0b,stroke-width:1.5px,color:#f8fafc;

    LOGIN["Tactical Login Screen<br/>Role: Maritime Enforcement Officer"]:::auth --> APP["AppShell: 3-Column Persistent Tactical Cockpit"]:::ui

    subgraph Command_Cockpit ["Persistent Command Cockpit"]
        TOP["TopBar: Scenario Switcher, Backend Health, Dark Mode, Legal Dossier Export"]:::ui
        
        COL1["Left Column (22%)<br/>SAR Telemetry Panel<br/>• VV/VH Radar Decibel Contrast<br/>• Damping Ratio Graph<br/>• Look-alike Diagnostic Button<br/>• Sentinel-1 Metadata"]:::ui
        
        COL2["Center Column (Flex-1)<br/>Tactical MapLibre Canvas<br/>• SAR Slick Polygon (Purple Neon)<br/>• 50/75/90% Origin Cone (Gradient)<br/>• 25 Lagrangian Backward Particles<br/>• Reconstructed Vessel Tracks<br/>• EEZ / Maritime UNCLOS Borders<br/>• Metocean Streamlines (Current/Wind)"]:::map
        
        COL3["Right Column (26%)<br/>Suspect Leaderboard<br/>• Ranked Candidate Cards<br/>• Suspicion Gauge & Confidence CI<br/>• 5-Factor Radar Breakdown<br/>• SHAP Feature Waterfall<br/>• Counterfactual Narratives<br/>• [!] Red Herring Penalty Badge"]:::ui
        
        DOCK["Bottom Dock<br/>Temporal Scrubber (-48.0h to 0.0h)<br/>• Space: Play/Pause<br/>• Left/Right: ±1h Step<br/>• Home/End: Jump to Slick/Origin"]:::ui
    end

    APP --> TOP & COL1 & COL2 & COL3 & DOCK

    COL2 --> PROBE["Physics Inspector Point-Probe<br/>Click Anywhere on Ocean → Instant Lat/Lon,<br/>Current Vector, Wind Vector, Depth"]:::modal

    COL1 --> DIAG["Lookalike Diagnostic Modal<br/>GLCM Texture & Aspect Ratio Proof"]:::modal

    TOP --> DOSSIER["Admiralty Legal Dossier Modal<br/>Live PDF Preview & UNCLOS Warrant Download"]:::modal

    COL3 --> SELECT["Select Candidate Vessel<br/>Camera Smoothly Pans to Track<br/>Highlights 4D Intercept Point on Map"]:::ui
```
