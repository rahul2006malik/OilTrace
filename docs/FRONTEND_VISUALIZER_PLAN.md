# OilTrace — World-Class Maritime Forensics Visualizer & Tactical Command Dashboard
## Master UI/UX Architecture, Interaction Flows, and Engineering Specification (SIH26143 — NTRO)

**Document Version:** 2.0.0 (Comprehensive Master Specification)  
**Classification:** Operational / NTRO Tactical Maritime Domain Awareness (MDA)  
**Target Delivery:** High-Impact Grand Finale Defense & Live Operations Center  

---

## Table of Contents
1. [Executive Vision, Design System & Aesthetic Foundation](#1-executive-vision-design-system--aesthetic-foundation)
2. [High-Fidelity 3-Column Tactical HUD Layout & Hierarchy](#2-high-fidelity-3-column-tactical-hud-layout--hierarchy)
3. [Exhaustive Component-by-Component Specifications](#3-exhaustive-component-by-component-specifications)
   - 3.1 [Top Telemetry & Alert Bar](#31-top-telemetry--alert-bar)
   - 3.2 [Left Intelligence Panel: Incident & Metocean Analytics](#32-left-intelligence-panel-incident--metocean-analytics)
   - 3.3 [Center Tactical Geospatial Canvas & WebGL Visualizer](#33-center-tactical-geospatial-canvas--webgl-visualizer)
   - 3.4 [Temporal Playback HUD ("Time-Machine" Scrubber)](#34-temporal-playback-hud-time-machine-scrubber)
   - 3.5 [Right Intelligence Panel: Suspect Attribution & XAI Forensics](#35-right-intelligence-panel-suspect-attribution--xai-forensics)
   - 3.6 [Bottom Status & Subsystem Diagnostic Telemetry](#36-bottom-status--subsystem-diagnostic-telemetry)
4. [Step-by-Step User Journeys & Interactive Workflow Maps](#4-step-by-step-user-journeys--interactive-workflow-maps)
   - 4.1 [Flow A: The 3-Minute Executive/Judge VIP Walkthrough](#41-flow-a-the-3-minute-executivejudge-vip-walkthrough)
   - 4.2 [Flow B: Investigative Deep-Dive & Time-Travel Intersection](#42-flow-b-investigative-deep-dive--time-travel-intersection)
   - 4.3 [Flow C: Live Custom GeoJSON Spill Upload & Execution](#43-flow-c-live-custom-geojson-spill-upload--execution)
   - 4.4 [Flow D: Dark-Vessel Forensic Alert & Uncooperative Target Analysis](#44-flow-d-dark-vessel-forensic-alert--uncooperative-target-analysis)
   - 4.5 [Flow E: Live Weight Sensitivity Tuning Sandbox](#45-flow-e-live-weight-sensitivity-tuning-sandbox)
5. [WebGL MapLibre GL Layer Stack & Visual Shaders](#5-webgl-maplibre-gl-layer-stack--visual-shaders)
6. [State Management Architecture & TypeScript Interfaces](#6-state-management-architecture--typescript-interfaces)
7. [Courtroom-Ready Evidentiary PDF Dossier Generator](#7-courtroom-ready-evidentiary-pdf-dossier-generator)
8. [Edge Cases, Error Handling & Offline Fallbacks](#8-edge-cases-error-handling--offline-fallbacks)
9. [Component Directory Structure & File Map](#9-component-directory-structure--file-map)
10. [Implementation Roadmap & Milestones](#10-implementation-roadmap--milestones)

---

## 1. Executive Vision, Design System & Aesthetic Foundation

The **OilTrace Visualizer** is designed as a mission-critical **Tactical Maritime Operations Command Center** (comparable to Palantir Foundry, Starboard Maritime Intelligence, and Windward MDA), customized for the **National Technical Research Organisation (NTRO)** and maritime law enforcement authorities.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    OILTRACE TACTICAL COMMAND HUD                                │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│ 🛰️ INCIDENT & METOCEAN (25%)   │ 🗺️ TACTICAL GEOSPATIAL (50%)    │ 🎯 VESSEL FORENSICS (25%)      │
│  - SAR Scene & VV/VH Damping   │  - WebGL Dark Canvas (MapLibre)│  - Ranked Suspect Leaderboard  │
│  - Spill Geometry & Thickness  │  - 50%/75%/90% Drift Origin KDE│  - Suspicion Score & CI        │
│  - GLORYS Current / ERA5 Wind  │  - Ensemble Hindcast Streamline│  - Explainable AI Spider/Bar   │
│  - Spill Age & Origin Window   │  - AIS Traffic & Forward Match │  - AIS Gap & Loiter Timelines  │
│  - Live Pipeline Trigger       │  - Temporal Playback Scrubber  │  - 1-Click Forensic Dossier PDF│
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

### Color Palette & Design Tokens (Cyber-Tactical Dark Theme)

| Token Name | Hex Code | Semantic Role & UI Application |
|---|---|---|
| `bg-space-dark` | `#070a13` | Deep background canvas & base layout |
| `bg-panel-slate` | `#0f172a` | Glassmorphism sidebars & floating HUD cards (`backdrop-blur-md`) |
| `bg-card-hover` | `#1e293b` | Interactive card hover state and active selections |
| `border-tactical`| `#334155` | 1px subtle borders and divider lines |
| `radar-cyan` | `#06b6d4` | Primary telemetry accent, live coordinates, 90% outer KDE contour |
| `origin-gold` | `#f59e0b` | Core 50% origin probability cone, primary warning highlights |
| `origin-orange` | `#f97316` | Intermediate 75% origin probability contour |
| `dark-crimson` | `#ef4444` | High suspicion ($> 0.60$), AIS blackout gaps, Dark Vessel alerts |
| `cyber-emerald` | `#10b981` | Real GFW data provenance badge, verified vessels, system healthy |
| `slick-violet` | `#a855f7` | Observed SAR oil slick polygon and iridescent boundary glow |
| `forward-sky` | `#38bdf8` | Forward confession simulated footprint & IoU match boundary |
| `text-primary` | `#f8fafc` | Crisp high-contrast headings and primary metrics |
| `text-muted` | `#94a3b8` | Subtitles, labels, and secondary metadata |

### Typography & Iconography
- **Primary Font:** `Inter`, `system-ui`, sans-serif (ultra-clean readability).
- **Telemetry & Numbers:** `JetBrains Mono` / `Fira Code` tabular figures (zero jitter during real-time value updates).
- **Icons:** `lucide-react` (standardized 16px/18px/20px monochrome icons with semantic color fills).

---

## 2. High-Fidelity 3-Column Tactical HUD Layout & Hierarchy

```
+----------------------------------------------------------------------------------------------------------------------+
| [LOGO] OILTRACE MDA | SPILL ID: SPILL-2026-ARABIAN-001 | DETECTED: 2026-08-25 06:00Z | [🚨 DARK VESSEL ALERT] | [EXPORT PDF] |
+----------------------------------------------------------------------------------------------------------------------+
| LEFT PANEL (25% Width, Scrollable)   | CENTER TACTICAL CANVAS (50% Width, Fullscreen WebGL) | RIGHT PANEL (25% Width, Scrollable)   |
|                                      |                                                      |                                      |
| ── 1. SAR SLICK CHARACTERIZATION ── | [ Map Overlay Controls: 2D/3D | Layers | Recenter ]   | ── 4. SUSPECT LEADERBOARD ────────── |
|  • Scene: S1A_IW_GRDH_20260825_...   |                                                      |  #01 MOPU SAGAR SAMRAT (Tanker)      |
|  • VV/VH Radar Damping Graph (dB)    |   ┌──────────────────────────────────────────────┐   |      Suspicion: 0.824 [0.75 - 0.89]  |
|  • Area: 14.82 km² | Damping: -7.8dB |   │ (90% Outer Prob. Bound - Cyan Contour)       │   |      Provenance: [REAL GFW] 🟢       |
|  • Elongation: 3.42 (Linear Sheen)   |   │   (75% Intermediate Bound - Orange Ring)     │   |      Flag: AIS Gap 18.4h | Loiter    |
|  • Thickness: Thick Crude (Class 3)  |   │     (50% Core Origin Zone - Gold Core) 🟡    │   |                                      |
|                                      |   │         * Suspect Ship Track Crossing        │   |  #02 MARAN GAS APOLLONIA (LNG)       |
| ── 2. METOCEAN PHYSICS HINDCAST ───  |   │                                              │   |      Suspicion: 0.412 [0.32 - 0.50]  |
|  • GLORYS Currents: 0.42 m/s @ 078°  |   │   Observed Oil Slick Polygon 🟣              │   |      Provenance: [REAL GFW] 🟢       |
|  • ERA5 10m Wind: 8.5 m/s @ 245°     |   └──────────────────────────────────────────────┘   |                                      |
|  • Hindcast Window: -48.0 Hours      |                                                      | ── 5. SUSPECT FORENSIC DEEP-DIVE ─── |
|  • Est. Spill Age: 26.5 ± 3.0 Hours  | ┌──────────────────────────────────────────────────┐ |  • Multi-Factor Radar Decomposition    |
|                                      | │ ⏱️ TEMPORAL PLAYBACK SCRUBBER (-48h -> 0h)       │ |  • Isolation Forest XAI Feature Bars |
| ── 3. SCENARIO & CUSTOM PIPELINE ──  | │ [ |<< ] [ ▶ PLAY ] [ >>| ] [ Speed: 5x ]         │ |  • AIS Blackout Timeline (Gantt)     |
|  • Active: Mumbai-Gulf Flagship      | │ Time: T - 26.5 hrs (2026-08-24 03:30 UTC)       │ |  • Forward Confession IoU Match: 0.78|
|  • [ + Run Custom GeoJSON Spill ]    | └──────────────────────────────────────────────────┘ |  • [ Sensitivity Weight Sandbox ]    |
+----------------------------------------------------------------------------------------------------------------------+
| TELEMETRY: 🟢 Subsystems Operational | Drift Engine: OpenDrift 1.14.11 | Attribution: GFW v2 + IF | Latency: 38ms | 60 FPS  |
+----------------------------------------------------------------------------------------------------------------------+
```

---

## 3. Exhaustive Component-by-Component Specifications

### 3.1 Top Telemetry & Alert Bar

- **Branding Badge:** Glowing radar sweep icon + `OILTRACE` + `NTRO MDA COMMAND`.
- **Spill Context Pill:** Displays `spill_id` (e.g. `SPILL-2026-ARABIAN-001`), Lat/Lon coordinates (`19.2000° N, 66.5000° E`), and SAR capture timestamp.
- **Scenario Selector Dropdown:**
  - `🇮🇳 Scenario 1: Mumbai-Gulf Commercial Corridor (Arabian Sea) [Flagship]`
  - `🚢 Scenario 2: Gulf of Kutch VLCC Tanker Approach`
  - `⚡ Scenario 3: Strait of Malacca Dark-Vessel Transit`
  - `⚙️ Custom User-Uploaded Scenario`
- **Dark Vessel Threat Alert Pill:**
  - If `dark_vessel_alert == true` (top candidate suspicion $< 0.40$), pulses in glowing crimson `#ef4444` with a siren icon:  
    `🚨 DARK VESSEL ALERT: Probable Uncooperative Discharger (AIS Disabled)`.
  - If `dark_vessel_alert == false`, shows a calm emerald badge:  
    `🎯 COOPERATIVE CORRELATION: Prime Suspect Identified`.
- **Action Buttons:**
  - `[🔄 Re-run Pipeline]`: Triggers live backend execution against current parameters.
  - `[📄 Export Evidentiary Dossier]`: Opens PDF generation modal.

---

### 3.2 Left Intelligence Panel: Incident & Metocean Analytics

#### Card A: Satellite SAR Slick Characterization
1. **SAR Optical/Radar Scene View:**
   - Thumbnail with layer toggle: **VV Backscatter** vs **VH Cross-Pol** vs **Segmented Binary Mask**.
   - **Cross-Sectional Radar Damping Profile Graph:** Mini SVG line chart plotting dB values across the slick transect (highlighting the $-7.8\text{ dB}$ damping dip confirming mineral oil versus biogenic lookalike).
2. **Geometric Metric Grid:**
   - **Total Slick Area:** `14.82 km²` (with equivalent volume estimate $\approx 44.5\text{ m}^3$).
   - **Elongation Ratio:** `3.42` (labeled `Linear Dispersion Trajectory`).
   - **Orientation Heading:** `112.5° ESE` (matching dominant surface current vector).
   - **Thickness Classification:** `Thick Emulsion (Class 3)` with color-coded sheen gradient.

#### Card B: Metocean Physics & Ocean Drift Hindcast
1. **GLORYS Surface Current Vector Rose:** Interactive circular compass displaying current speed ($0.42\text{ m/s}$) and direction ($078^\circ\text{ ENE}$).
2. **ERA5 10-meter Wind Gauge:** Dual-needle analog gauge displaying wind speed ($8.5\text{ m/s} \approx 16.5\text{ knots}$) and meteorological direction ($245^\circ\text{ WSW}$).
3. **Drift Ensemble Hindcast Summary:**
   - Ensemble Members: `15 Perturbed Runs` (200 particles each, 48 hours backward).
   - Estimated Discharge Window: `Aug 24, 2026, 03:30 UTC` ($T - 26.5\text{ hrs}$).
   - Spatial Dispersion Radius: `1.85 km` (at 50% core confidence).

#### Card C: Custom Scenario Pipeline Trigger
- **Drag-and-Drop Zone:** Accepts custom `slick_detection.geojson` or GeoTIFF.
- **Manual Coordinate Input:** Lon, Lat, Detection Date/Time, Hindcast Duration (24h/48h/72h).
- **Execution Progress Stepper:** Visually shows live status: `[1. Detection Parsing] -> [2. Forcing Fetch] -> [3. Backward Drift Ensemble] -> [4. GFW Feature Extraction] -> [5. Isolation Forest Scoring] -> [6. Forward Confession IoU] -> [7. Score Fusion]`.

---

### 3.3 Center Tactical Geospatial Canvas & WebGL Visualizer

The map canvas is powered by **MapLibre GL JS** running at a locked 60 FPS with hardware WebGL acceleration.

#### Layer Stack & Visual Styling
1. **Base Cartography:** CartoDB Dark Matter with dimmed bathymetric contour lines and major shipping traffic separation schemes (TSS lanes).
2. **Observed SAR Slick Polygon:** Semi-transparent violet polygon fill (`rgba(168, 85, 247, 0.35)`) with an iridescent neon border (`#c084fc`, width: 2.5px) and glowing centroid crosshair.
3. **Probabilistic Origin Cone (Drift Hindcast):**
   - **50% Core Probability Zone:** Vibrant Gold fill (`rgba(245, 158, 11, 0.40)`) with an animated dashed outline (`#fbbf24`).
   - **75% Intermediate Probability Zone:** Amber fill (`rgba(249, 115, 22, 0.22)`).
   - **90% Outer Boundary Zone:** Cyan contour fill (`rgba(6, 182, 212, 0.12)`).
4. **Backward Ensemble Particle Streamlines:** 15 distinct particle paths showing backward drift tracks across the Arabian Sea with alpha-decay tails.
5. **AIS Marine Traffic & Vessel Positions:**
   - Dynamic vessel glyphs oriented by Course Over Ground (`COG`).
   - Color coded:
     - 🟢 Normal ($< 0.30$): Emerald icon (`#10b981`).
     - 🟡 Medium Anomaly ($0.30 - 0.60$): Amber icon (`#f59e0b`).
     - 🔴 High Suspicion ($> 0.60$): Glowing crimson icon (`#ef4444`) with animated radar ping.
   - **AIS Gap Vectors:** Dotted red lines marking the trajectory during transponder blackout periods.
6. **Forward Confession Simulated Footprint:** Overlays the selected candidate's simulated forward dispersion polygon (`#38bdf8`) directly against the observed slick (`#a855f7`), highlighting the intersection area.

---

### 3.4 Temporal Playback HUD ("Time-Machine" Scrubber)

Located as a floating glassmorphism dock at the bottom of the map canvas.

- **Time Range Slider:** $T_{-48\text{h}} \rightarrow T_{\text{detection}} \rightarrow T_{+24\text{h}}$.
- **Playback Controls:**
  - `|<<`: Jump to Spill Estimated Origin ($T - 26.5\text{h}$).
  - `◀`: Step Backward 1 Hour.
  - `▶ / ❚❚`: Play / Pause historical animation.
  - `▶`: Step Forward 1 Hour.
  - `>>|`: Jump to Satellite Detection Time ($T = 0\text{h}$).
  - `Speed Selector`: `1x`, `5x`, `20x`, `50x`.
- **Synchronized Visual Animation:**
  - When playing, OpenDrift particles backtrack toward the origin cone while AIS vessels advance along their historical tracks.
  - At $T = -26.5\text{h}$, the suspect vessel visually crosses directly into the gold 50% origin cone, providing instant, undeniable visual proof of correlation!

---

### 3.5 Right Intelligence Panel: Suspect Attribution & XAI Forensics

#### Section A: Ranked Suspect Leaderboard
- Displays top suspect candidates sorted by `suspicion_score` descending.
- **Candidate Card Item:**
  - **Rank & Vessel Identity:** `#01` | `MOPU SAGAR SAMRAT` (Flag: 🇮🇳 India | MMSI: `419381000` | IMO: `8751234`).
  - **Vessel Class:** `Offshore Drilling / Crude Tanker`.
  - **Suspicion Score Gauge:** `0.824` with confidence bracket `[0.754 — 0.894]`.
  - **Data Provenance Badge:** `[REAL GFW]` (Emerald) or `[REAL AISSTREAM]` (Cyan).
  - **Forensic Flags:** `🚨 AIS Gap (18.4h)`, `⏳ Loitering (7.9h)`, `⚠️ Off-Lane (14.2 km)`.

#### Section B: Selected Suspect Explainability (XAI) Inspector
1. **Multi-Factor Score Radar Chart:**
   - Breaks down the four mathematical components of the fusion formula:
     $$\text{Suspicion} = 0.35 \cdot P_{\text{prox}} + 0.25 \cdot M_{\text{conf}} + 0.25 \cdot A_{\text{anom}} + 0.15 \cdot V_{\text{prior}}$$
   - Visual polygon showing exact weight contributions.
2. **Isolation Forest Feature Deviation Bars:**
   - Horizontal bars comparing this vessel's features against the regional background median:
     - `AIS Gap Duration`: `18.4h` ($+420\%$ vs median) $\rightarrow$ 🔴 **Severe Anomaly**.
     - `Loitering Duration`: `7.9h` ($+650\%$ vs median) $\rightarrow$ 🔴 **Severe Anomaly**.
     - `Lane Deviation`: `14.2 km` ($+110\%$ vs median) $\rightarrow$ 🟡 **Moderate Anomaly**.
     - `Speed Variance`: `0.8 kn²` (Normal transit) $\rightarrow$ 🟢 **Nominal**.
3. **AIS Blackout & Event Gantt Timeline:**
   - `00:00 - 04:00`: AIS Active (Speed 14.2 kn, Heading 082°).
   - `04:00 - 18:24`: **AIS DISABLED (14.4h Blackout)** $\leftarrow$ *Crosses 50% origin cone at 06:15 UTC*.
   - `18:24 - 24:00`: AIS Re-enabled (Speed 13.8 kn, 24nm downstream).
4. **Forward Confession Match Diagnostics:**
   - Simulated Footprint Area: `4.43 km²`.
   - Particles Survived: `100 / 100` (100% validity).
   - Shape IoU Overlap Score: `0.782` (High geometric correlation).

#### Section C: Dynamic Weight Sensitivity Sandbox
- Expandable drawer allowing judges to adjust $\alpha, \beta, \gamma, \delta$ sliders:
  - $\alpha$ (Spatial Proximity): `0.00 — 1.00` (Default: `0.35`)
  - $\beta$ (Forward Confession IoU): `0.00 — 1.00` (Default: `0.25`)
  - $\gamma$ (Isolation Forest Anomaly): `0.00 — 1.00` (Default: `0.25`)
  - $\delta$ (Vessel Type Prior): `0.00 — 1.00` (Default: `0.15`)
- Recalculates candidate rankings dynamically in real-time with smooth animated re-sorting.

---

### 3.6 Bottom Status & Subsystem Diagnostic Telemetry

- **Subsystem 1 (Detection):** `🟢 Active (ResNet34 U-Net SAR Engine)`
- **Subsystem 2 (Drift):** `🟢 Operational (OpenDrift 1.14.11 / GLORYS + ERA5)`
- **Subsystem 3 (Attribution):** `🟢 Operational (GFW API v2 + Isolation Forest)`
- **Backend Service:** `🟢 Connected (FastAPI @ http://localhost:8000)`
- **Data Mode:** `💾 Flagship Cache (Mumbai-Gulf Scenario / 1,681 Vessels)`
- **Render Latency:** `38ms | 60 FPS WebGL`

---

## 4. Step-by-Step User Journeys & Interactive Workflow Maps

### 4.1 Flow A: The 3-Minute Executive/Judge VIP Walkthrough

```mermaid
journey
    title 3-Minute Judge Demonstration Flow
    section 1. Launch & Overview
      Open Dashboard: 5: Executive
      Observe Dark HUD & Map Canvas: 5: Executive
      Inspect SAR Slick Polygon & Area (14.82 km²): 5: Executive
    section 2. Physical Hindcast
      Inspect 50%/75%/90% Drift Origin Cone: 5: Executive
      Review Metocean GLORYS currents & ERA5 winds: 4: Executive
    section 3. Temporal Playback
      Click Play on Temporal Scrubber: 5: Executive
      Watch ship track intersect 50% origin cone at T-26.5h: 5: Executive
    section 4. Forensic Attribution
      Select Rank #1 Suspect (MOPU SAGAR SAMRAT): 5: Executive
      Review Isolation Forest XAI feature deviations: 5: Executive
      Inspect AIS Blackout Gantt timeline: 5: Executive
    section 5. Export Verdict
      Click Export Evidentiary Dossier: 5: Executive
      Download formatted PDF Intelligence Briefing: 5: Executive
```

---

### 4.2 Flow B: Investigative Deep-Dive & Time-Travel Intersection

1. User opens scenario: `Mumbai-Gulf Commercial Corridor`.
2. Center map displays observed slick at `(66.50° E, 19.20° N)`.
3. User drags the **Temporal Scrubber** back to $T = -26.5\text{h}$.
4. Map shows particle cloud collapsing into the gold $50\%$ origin cone at `(66.82° E, 19.14° N)`.
5. Simultaneously, suspect tanker `419381000`'s historical position aligns directly inside the $50\%$ cone.
6. The user clicks on the vessel marker:
   - Center map draws the **Forward Confession dispersion footprint** originating from that vessel's coordinate.
   - Right panel updates with candidate's full identity (`MOPU SAGAR SAMRAT`), suspicion score ($0.824$), and AIS gap proof ($18.4\text{h}$).

---

### 4.3 Flow C: Live Custom GeoJSON Spill Upload & Execution

1. User clicks **`[+ Run Custom Spill]`** in the left panel.
2. Modal opens with drag-and-drop zone. User drops a custom `slick_detection.geojson`.
3. Modal displays extracted attributes: Centroid `(67.12° E, 18.95° N)`, Area `8.45 km²`, Time `2026-08-28 14:00 UTC`.
4. User clicks **`[🚀 Execute Forensics Pipeline]`**.
5. Live progress bar advances through 7 stages:
   - `[1/7]` Parsing SAR slick polygon...
   - `[2/7]` Resolving GLORYS ocean currents & ERA5 winds...
   - `[3/7]` Running 15-member OpenDrift backward ensemble...
   - `[4/7]` Querying GFW vessel presence & event registries...
   - `[5/7]` Fitting Isolation Forest anomaly model...
   - `[6/7]` Simulating forward confession footprints...
   - `[7/7]` Fusing evidence traces & determining dark vessel alert...
6. Dashboard transitions smoothly to render the new spill polygon, origin cone, and ranked suspects!

---

### 4.4 Flow D: Dark-Vessel Forensic Alert & Uncooperative Target Analysis

1. An oil slick is detected in an area where no vessel was transmitting AIS during the estimated release window.
2. The pipeline executes: highest candidate suspicion score is $0.28 < 0.40$.
3. Top header triggers a glowing **`🚨 DARK VESSEL ALERT: Uncooperative Discharger`**.
4. The map displays:
   - The 50%/75%/90% origin cone.
   - Dotted red lines indicating where vessels entered the region and turned off their AIS transponders.
   - Candidate leaderboard highlights suspect vessels with severe AIS gap events during the discharge window.
5. Evidentiary dossier marks case as **`Non-Cooperative / Dark Vessel Violation (MARPOL Annex I)`**.

---

### 4.5 Flow E: Live Weight Sensitivity Tuning Sandbox

1. Judge asks: *"How sensitive is this ranking to the Isolation Forest anomaly weight vs the ocean drift proximity?"*
2. Presenter clicks **`[⚙️ Forensic Weight Tuner]`**.
3. Presenter drags the $\alpha$ (Proximity) slider down from $0.35$ to $0.10$ and increases $\gamma$ (Anomaly) to $0.50$.
4. The candidate leaderboard smoothly animates: vessels with massive AIS blackout gaps rise in rank while passive drifting vessels fall.
5. Proves to judges that the system is fully explainable, configurable, and transparent!

---

## 5. WebGL MapLibre GL Layer Stack & Visual Shaders

```
Z-Index Layer Hierarchy (Top to Bottom):
┌────────────────────────────────────────────────────────┐
│ Layer 7: Interactive Hover/Selection Halo (#ffffff)     │
├────────────────────────────────────────────────────────┤
│ Layer 6: Forward Confession Simulated Footprint (#38bdf8)│
├────────────────────────────────────────────────────────┤
│ Layer 5: AIS Vessel Points & Heading Glyphs (🟢/🟡/🔴)  │
├────────────────────────────────────────────────────────┤
│ Layer 4: AIS Gap Blackout Trajectories (Dotted Red)    │
├────────────────────────────────────────────────────────┤
│ Layer 3: Observed SAR Oil Slick Polygon (#a855f7 Glow)  │
├────────────────────────────────────────────────────────┤
│ Layer 2: 50%/75%/90% KDE Origin Probability Contours   │
├────────────────────────────────────────────────────────┤
│ Layer 1: Backward Ensemble Drift Streamlines (15 runs) │
├────────────────────────────────────────────────────────┤
│ Layer 0: CartoDB Dark Matter WebGL Base Tiles          │
└────────────────────────────────────────────────────────┘
```

---

## 6. State Management Architecture & TypeScript Interfaces

### Zustand Store (`src/store/useOilTraceStore.ts`)

```typescript
export interface OilTraceState {
  // Scenario & Incident State
  activeScenarioId: string;
  spillId: string;
  spillLocation: { lon: number; lat: number };
  detectedAt: string;
  slickGeometry: GeoJSON.Polygon | null;
  slickProperties: {
    area_km2: number;
    elongation_ratio: number;
    thickness_class: 'sheen' | 'thin' | 'thick';
    oil_confidence: number;
  };

  // Drift Subsystem State
  originEnsemble: {
    origin_probability_cone: GeoJSON.FeatureCollection;
    age_estimate_hours: number;
    ensemble_members: number;
  } | null;
  trajectories: Array<{ id: number; coordinates: Array<[number, number, string]> }>;

  // Attribution Subsystem State
  candidates: Candidate[];
  selectedCandidateId: string | null;
  darkVesselAlert: boolean;
  topKRecovery: { k: number; recovered: boolean | null; confidence: number | null };

  // Temporal Playback State
  playbackTimeHours: number; // -48.0 to 0.0
  isPlaying: boolean;
  playbackSpeed: number; // 1, 5, 20, 50

  // UI & Sandbox State
  activeTab: 'analytics' | 'custom_run';
  weights: { alpha: number; beta: number; gamma: number; delta: number };
  isExportingPdf: boolean;
  pipelineRunning: boolean;
  pipelineProgressStep: number;

  // Actions
  loadScenario: (scenarioId: string) => Promise<void>;
  runLivePipeline: (payload: PipelineRunRequest) => Promise<void>;
  setSelectedCandidate: (candidateId: string | null) => void;
  setPlaybackTime: (timeHours: number) => void;
  togglePlayback: () => void;
  setWeights: (weights: Partial<OilTraceState['weights']>) => void;
}
```

---

## 7. Courtroom-Ready Evidentiary PDF Dossier Generator

The visualizer includes a built-in **`pdfReportGenerator.ts`** engine using `jsPDF` that formats a 2-page intelligence briefing:

### Document Layout & Structure:
- **Header:** `NATIONAL TECHNICAL RESEARCH ORGANISATION (NTRO) — MARITIME CRIME REPORT`.
- **Case Reference:** `NTRO-MDA-2026-ARABIAN-001` | Timestamp: `2026-08-25 06:00:00 UTC`.
- **Satellite Evidence Block:** High-resolution SAR crop, backscatter damping analysis, slick coordinates.
- **Physical Ocean Hindcast Proof:** Render of the 50%/75%/90% probability cone, GLORYS current vectors, ERA5 wind direction.
- **Vessel Attribution Table:** Ranked candidates, IMO/MMSI, Flag state, Suspicion score with confidence interval, and Data provenance tags.
- **Prime Suspect Evidentiary Breakdown:** AIS blackout duration, speed variance anomalies, and forward confession shape IoU match score.
- **Cryptographic Verification Block:** SHA-256 digital fingerprint ensuring non-repudiation in maritime court proceedings.

---

## 8. Edge Cases, Error Handling & Offline Fallbacks

| Failure Mode / Edge Case | System Behavior & Graceful Degradation |
|---|---|
| **Backend API Offline / Unreachable** | Displays a top alert banner `⚠️ Backend Offline — Operating in Local Cache Mode`. Automatically falls back to bundled pre-computed scenario fixtures. |
| **Zero AIS Vessels in Bounding Box** | Prevents crash. Triggers `🚨 DARK VESSEL ALERT: Zero Cooperative AIS Transponders Logged in Spill Corridor`. |
| **Missing Forcing NetCDF File** | `_get_scenario_forcing_paths()` logs a clear diagnostic warning and falls back to pre-cached GLORYS/ERA5 slices with transparent provenance tagging. |
| **Invalid/Corrupt GeoJSON Upload** | Client-side validation catches topology errors before submission and highlights invalid rings with an intuitive error toast. |
| **WebGL Not Supported on Display Device** | Automatically falls back to standard 2D canvas rendering with an optimization tip banner. |

---

## 9. Component Directory Structure & File Map

```
frontend/
├── index.html                           # Tactical dark theme shell
├── package.json                         # React 18, MapLibre GL, Recharts, Lucide, jsPDF
├── tsconfig.json                        # Strict TypeScript config
├── vite.config.ts                       # Vite bundler with FastAPI proxy
├── tailwind.config.js                   # Custom cyber-tactical tokens
└── src/
    ├── main.tsx                         # Root mount
    ├── App.tsx                          # Three-column layout shell
    ├── api/
    │   ├── oiltraceApi.ts               # FastAPI client (/health, /scenarios, /pipeline/run)
    │   └── types.ts                     # TypeScript schemas matching schemas.md v1.1
    ├── store/
    │   └── useOilTraceStore.ts          # Zustand state store
    ├── components/
    │   ├── header/
    │   │   ├── TopNavBar.tsx            # Header HUD, incident metadata, alert pills
    │   │   ├── ScenarioSwitcher.tsx     # Flagship vs secondary vs custom picker
    │   │   └── ExportReportModal.tsx    # PDF preview & download modal
    │   ├── left_panel/
    │   │   ├── SarAnalyticsCard.tsx     # VV/VH radar damping graph & slick geometry
    │   │   ├── MetoceanCard.tsx         # GLORYS current rose & ERA5 wind gauges
    │   │   └── CustomRunModal.tsx       # Drag-and-drop custom spill pipeline runner
    │   ├── map/
    │   │   ├── TacticalMapCanvas.tsx    # MapLibre GL WebGL canvas orchestrator
    │   │   ├── SlickPolygonLayer.ts     # Observed SAR slick glow layer
    │   │   ├── OriginConeLayer.ts       # 50/75/90% KDE probability contours
    │   │   ├── DriftStreamlineLayer.ts  # 15-member backward ensemble particle traces
    │   │   ├── VesselTrafficLayer.ts    # AIS vessel markers & heading arrows
    │   │   ├── ForwardFootprintLayer.ts # Candidate forward confession polygon
    │   │   └── MapControls.tsx          # 2D/3D tilt, layer checkboxes, reset bounds
    │   ├── timeline/
    │   │   └── TemporalScrubber.tsx     # -48h to +24h historical time scrubber
    │   └── right_panel/
    │       ├── SuspectLeaderboard.tsx   # Ranked suspect list with provenance pills
    │       ├── VesselCandidateCard.tsx  # Individual candidate item with CI bar
    │       ├── ExplainabilitySpider.tsx # Multi-factor score decomposition radar
    │       ├── IsolationForestBars.tsx  # Feature anomaly deviation bars
    │       ├── AisGapTimeline.tsx       # AIS blackout Gantt chart
    │       ├── WeightSandboxModal.tsx   # Live weight sensitivity sliders
    │       └── DarkVesselBanner.tsx     # Pulsing crimson threat banner
    └── utils/
        ├── geojsonUtils.ts              # Bounding box & geometry calculations
        ├── formatters.ts                # Lat/Lon DMS, timestamps, and unit formatters
        └── pdfReportGenerator.ts        # jsPDF forensic dossier engine
```

---

## 10. Implementation Roadmap & Milestones

1. **Phase 1 — Project Scaffolding & Theme Engine:** Setup Vite + React 18 + Tailwind CSS + MapLibre GL in `frontend/`.
2. **Phase 2 — State Management & API Client:** Implement `oiltraceApi.ts` and `useOilTraceStore.ts` hooked to FastAPI backend.
3. **Phase 3 — WebGL Geospatial Engine:** Build `TacticalMapCanvas.tsx` with SAR slick, 50%/75%/90% origin contours, particle streamlines, and AIS ship layers.
4. **Phase 4 — Intelligence Panels & Explainability:** Build SAR damping graphs, metocean gauges, suspect cards, XAI radar/bar charts, and AIS gap timelines.
5. **Phase 5 — Temporal Scrubber & PDF Dossier:** Implement historical time-travel playback slider and 1-click forensic intelligence briefing export.
6. **Phase 6 — Validation & Presentation Polish:** Verify 60 FPS performance, offline fallback resilience, and live custom pipeline execution.
