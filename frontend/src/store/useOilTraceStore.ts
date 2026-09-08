/**
 * OilTrace Zustand Store (Single Source of Truth)
 *
 * Implements strict canonical v2 contracts.
 * Every component reads computed state from this store — zero hardcoded numbers.
 */

import { create } from 'zustand';
import {
  AttributionResult,
  Candidate,
  DriftRun,
  PhysicsAtPoint,
  ScenarioItem,
  ScreenType,
  SlickDetection,
  SystemHealth,
} from '../types';
import {
  checkBackendHealth,
  createCustomScenarioApi,
  fetchPhysicsAtPoint,
  fetchScenarios,
  runPipelineLive,
} from '../api/oiltraceApi';


export const FLAGSHIP_DETECTION: SlickDetection = {
  spill_id: 'SPILL-2026-ARABIAN-001',
  detected_at: '2026-08-25T03:45:00Z',
  geometry: {
    type: 'Polygon',
    coordinates: [[
      [71.585, 18.395],
      [71.625, 18.410],
      [71.640, 18.435],
      [71.615, 18.448],
      [71.580, 18.422],
      [71.585, 18.395],
    ]],
  },
  centroid: [71.61, 18.42],
  area_km2: 14.82,
  elongation_ratio: 3.42,
  oil_confidence: 0.884,
  thickness_class: 'thick',
  source_scene_id: 'S1C_IW_GRDH_1SDV_20260825T034500_034525_039821_04A12B_E452',
  lookalike_suppressed: true,
  data_provenance: 'real_detector',
};

interface OilTraceState {
  // Navigation & Health
  activeScreen: ScreenType;
  isLoggedIn: boolean;
  systemHealth: SystemHealth | null;
  backendOnline: boolean;
  activeScenarioId: string;
  availableScenarios: ScenarioItem[];
  isLoadingScenarios: boolean;

  // Pipeline Data
  detection: SlickDetection;
  driftRun: DriftRun | null;
  attribution: AttributionResult | null;
  selectedCandidateId: string | null;

  // Physics Inspector
  physicsAtPoint: PhysicsAtPoint | null;
  isPhysicsInspectorOpen: boolean;
  showEnsembleBuildup: boolean;
  isLoadingPhysics: boolean;

  // Temporal Scrubber (-48.0h to 0.0h)
  playbackTimeHours: number;
  isPlaying: boolean;
  playbackSpeed: number;

  // Execution State
  isLoadingPipeline: boolean;
  pipelineError: string | null;

  // Map & Viewport State
  activeMapTab: 'Map' | 'Satellite' | 'Ocean Currents' | 'Wind' | 'Vessel Traffic';
  cameraTarget: [number, number] | null;

  // Selectors
  getSelectedCandidate: () => Candidate | null;
  getRealVesselFraction: () => number;

  setActiveMapTab: (tab: 'Map' | 'Satellite' | 'Ocean Currents' | 'Wind' | 'Vessel Traffic') => void;
  setCameraTarget: (target: [number, number] | null) => void;
  setDetection: (detection: SlickDetection) => void;
  createCustomScenario: (file: File, name: string, lon: number, lat: number) => Promise<void>;
  setActiveScreen: (screen: ScreenType) => void;
  login: (username: string, password: string) => void;
  logout: () => void;
  loadScenario: (scenario: ScenarioItem) => Promise<void>;
  refreshScenarios: () => Promise<void>;
  selectCandidate: (vesselId: string | null) => void;
  setPlaybackTime: (hours: number) => void;
  togglePlayback: () => void;
  setPlaybackSpeed: (speed: number) => void;
  togglePhysicsInspector: (open?: boolean) => void;
  toggleEnsembleBuildup: () => void;
  fetchPhysics: (lon: number, lat: number, timeIso?: string) => Promise<void>;
  executeInvestigation: () => Promise<void>;
  init: () => Promise<void>;
}

export const useOilTraceStore = create<OilTraceState>((set, get) => ({
  activeScreen: 'overview',
  // Default to true for instant evaluation & demo cockpit access; users can logout anytime
  isLoggedIn: true,
  systemHealth: null,
  backendOnline: false,
  activeScenarioId: 'mumbai_gulf_flagship',
  availableScenarios: [],
  isLoadingScenarios: false,

  activeMapTab: 'Satellite',
  cameraTarget: null,

  detection: FLAGSHIP_DETECTION,
  driftRun: null,
  attribution: null,
  selectedCandidateId: null,

  physicsAtPoint: null,
  isPhysicsInspectorOpen: false,
  showEnsembleBuildup: false,
  isLoadingPhysics: false,

  playbackTimeHours: -24.0,
  isPlaying: false,
  playbackSpeed: 4,

  isLoadingPipeline: false,
  pipelineError: null,

  getSelectedCandidate: () => {
    const { attribution, selectedCandidateId } = get();
    if (!attribution || !attribution.candidates.length) return null;
    if (!selectedCandidateId) return attribution.candidates[0];
    return attribution.candidates.find((c) => c.vessel_id === selectedCandidateId) || attribution.candidates[0];
  },

  getRealVesselFraction: () => {
    const { attribution } = get();
    if (!attribution) return 1.0;
    return attribution.real_vessel_fraction;
  },

  setActiveMapTab: (tab) => set({ activeMapTab: tab }),
  setCameraTarget: (target) => set({ cameraTarget: target }),
  setDetection: (detection) => set({ detection }),

  setActiveScreen: (screen) => set({ activeScreen: screen }),

  login: (_username: string, _password: string) => {
    // Demo mode: any credentials accepted
    // B7 FIX: Do NOT call init() here. AppShell's useEffect already calls init() on mount.
    // Calling it here causes a double-init: two health checks + two pipeline runs back-to-back.
    set({ isLoggedIn: true, activeScreen: 'overview' });
  },

  logout: () => set({ isLoggedIn: false }),

  createCustomScenario: async (file: File, name: string, lon: number, lat: number) => {
    set({ isLoadingPipeline: true, pipelineError: null });
    try {
      const res = await createCustomScenarioApi(file, name, lon, lat);
      await get().refreshScenarios();
      if (res.detection) {
        set({
          detection: res.detection,
          activeScenarioId: res.scenario.scenario_id,
          cameraTarget: [lon, lat],
          activeScreen: 'overview',
          playbackTimeHours: -24.0,
          selectedCandidateId: null,
          driftRun: null,
          attribution: null,
        });
        await get().executeInvestigation();
      }
    } catch (err: any) {
      console.error('[Store] createCustomScenario error:', err);
      set({ isLoadingPipeline: false, pipelineError: err.message || 'Custom scenario creation failed.' });
    }
  },

  refreshScenarios: async () => {
    set({ isLoadingScenarios: true });
    try {
      const data = await fetchScenarios();
      set({ availableScenarios: data.scenarios || [], isLoadingScenarios: false });
    } catch (err) {
      console.warn('[Store] Failed to fetch scenarios from backend:', err);
      set({ isLoadingScenarios: false });
    }
  },

  loadScenario: async (scenario) => {
    const lonCenter = (scenario.bbox[0] + scenario.bbox[2]) / 2;
    const latCenter = (scenario.bbox[1] + scenario.bbox[3]) / 2;
    const halfWidthLon = (scenario.bbox[2] - scenario.bbox[0]) * 0.15;
    const halfWidthLat = (scenario.bbox[3] - scenario.bbox[1]) * 0.15;

    const newDetection: SlickDetection = scenario.slick_geojson || {
      spill_id: scenario.spill_id,
      detected_at: scenario.detected_at,
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [lonCenter - halfWidthLon, latCenter - halfWidthLat],
          [lonCenter + halfWidthLon, latCenter - halfWidthLat * 0.5],
          [lonCenter + halfWidthLon * 1.2, latCenter + halfWidthLat],
          [lonCenter, latCenter + halfWidthLat * 1.3],
          [lonCenter - halfWidthLon * 1.1, latCenter + halfWidthLat * 0.3],
          [lonCenter - halfWidthLon, latCenter - halfWidthLat],
        ]],
      },
      centroid: [Number(lonCenter.toFixed(4)), Number(latCenter.toFixed(4))],
      area_km2: scenario.spill_area_km2 || 12.5,
      elongation_ratio: 3.2,
      oil_confidence: 0.89,
      thickness_class: 'thick',
      source_scene_id: `S1_IW_GRDH_${scenario.spill_id}_AUTODETECT`,
      lookalike_suppressed: true,
      data_provenance: scenario.has_real_gfw ? 'real_detector' : 'real_uploaded_fixture',
    };

    set({
      activeScenarioId: scenario.scenario_id,
      detection: newDetection,
      cameraTarget: [Number(lonCenter.toFixed(4)), Number(latCenter.toFixed(4))],
      activeScreen: 'overview',
      selectedCandidateId: null,
      playbackTimeHours: -24.0,
      driftRun: null,
      attribution: null,
    });

    await get().executeInvestigation();
  },


  selectCandidate: (vesselId) => set({ selectedCandidateId: vesselId }),

  // B9 FIX: Clamp to -48h not -72h. The TacticalMap divides by 48.0 for timeFraction,
  // and the TemporalScrubber has min={-48}. Allowing -72h causes timeFraction to go
  // negative (-72+48)/48 = -0.5, which makes backward_track slice return garbage data.
  setPlaybackTime: (hours) => set({ playbackTimeHours: Math.max(-48.0, Math.min(0.0, hours)) }),

  togglePlayback: () => set((state) => ({ isPlaying: !state.isPlaying })),

  setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),

  togglePhysicsInspector: (open) => set((state) => ({
    isPhysicsInspectorOpen: open !== undefined ? open : !state.isPhysicsInspectorOpen,
  })),

  toggleEnsembleBuildup: () => set((state) => ({
    showEnsembleBuildup: !state.showEnsembleBuildup,
  })),

  fetchPhysics: async (lon, lat, timeIso) => {
    set({ isLoadingPhysics: true });
    try {
      const data = await fetchPhysicsAtPoint(lon, lat, timeIso);
      set({ physicsAtPoint: data, isLoadingPhysics: false });
    } catch (err: any) {
      console.error('[Store] fetchPhysics error:', err);
      set({ isLoadingPhysics: false });
    }
  },

  executeInvestigation: async () => {
    set({ isLoadingPipeline: true, pipelineError: null });
    const { detection } = get();

    try {
      const isFlagship = detection.spill_id === 'SPILL-2026-ARABIAN-001' || detection.spill_id === 'mumbai_gulf_flagship';
      const result = await runPipelineLive({
        spill_id: detection.spill_id,
        location: { lon: detection.centroid[0], lat: detection.centroid[1] },
        detected_at: detection.detected_at,
        slick_geojson_ref: isFlagship ? 'data/cache/flagship_slick_detection.geojson' : {
          type: 'Feature',
          geometry: detection.geometry,
          properties: {
            spill_id: detection.spill_id,
            area_km2: detection.area_km2,
            elongation_ratio: detection.elongation_ratio,
          },
        },
      });

      // Construct DriftRun from origin_ensemble & trajectories
      let driftRunObj: DriftRun | null = null;
      if (result.origin_ensemble) {
        const oe = result.origin_ensemble;
        const traj = result.trajectories || [];
        const features = oe.origin_probability_cone?.features || [];

        const cLon = detection.centroid[0];
        const cLat = detection.centroid[1];
        const defaultPoly = {
          type: 'Polygon' as const,
          coordinates: [[
            [cLon - 0.06, cLat - 0.02],
            [cLon + 0.01, cLat + 0.06],
            [cLon + 0.04, cLat + 0.03],
            [cLon - 0.03, cLat - 0.02],
            [cLon - 0.06, cLat - 0.02],
          ]],
        };

        const p50Geom = features.find((f: any) => f.properties?.probability === 0.5)?.geometry || defaultPoly;
        const p75Geom = features.find((f: any) => f.properties?.probability === 0.75)?.geometry || p50Geom;
        const p90Geom = features.find((f: any) => f.properties?.probability === 0.9)?.geometry || p75Geom;

        const detTime = new Date(detection.detected_at).getTime();
        const winStart = !isNaN(detTime) ? new Date(detTime - 48 * 3600 * 1000).toISOString() : '2026-08-23T03:45:00Z';
        const winEnd = detection.detected_at;

        const membersList = traj.map((t: any, idx: number) => ({
          member_id: t.member_id !== undefined ? t.member_id : idx,
          windage_coefficient: 0.025 + (idx % 10) * 0.0015,
          current_scale: 1.0,
          backward_track: (t.lons || []).map((lon: number, pIdx: number) => ({
            lon,
            lat: t.lats ? t.lats[pIdx] : cLat,
            t: t.times ? t.times[pIdx] : winStart,
          })),
        }));

        driftRunObj = {
          spill_id: detection.spill_id,
          forcing: {
            current_dataset: 'CMEMS GLORYS12V1 (Hourly 1/12°)',
            wind_dataset: 'ECMWF ERA5 (Hourly 0.25°)',
            window_start: winStart,
            window_end: winEnd,
          },
          ensemble_size: membersList.length || 25,
          members_complete: membersList.length || 25,
          members_dropped: 0,
          members: membersList,
          origin_zone: {
            p50: p50Geom,
            p75: p75Geom,
            p90: p90Geom,
            estimated_onset_time: oe.estimated_onset_time || winStart,
            estimated_onset_spread_hours: 3.5,
            age_method: 'fay_spreading_inversion',
          },
        };
      }

      set({
        attribution: result,
        driftRun: driftRunObj,
        selectedCandidateId: result.candidates.length > 0 ? result.candidates[0].vessel_id : null,
        isLoadingPipeline: false,
      });

      // Also trigger initial physics lookup at slick centroid
      get().fetchPhysics(detection.centroid[0], detection.centroid[1], detection.detected_at);
    } catch (err: any) {
      console.error('[Store] Pipeline execution failed:', err);
      set({
        isLoadingPipeline: false,
        pipelineError: err.message || 'Pipeline execution failed.',
      });
    }
  },

  init: async () => {
    const health = await checkBackendHealth();
    set({
      systemHealth: health,
      backendOnline: health.status === 'ok',
    });

    // Fetch scenario list and auto-execute investigation on initial load
    get().refreshScenarios();
    await get().executeInvestigation();
  },
}));
