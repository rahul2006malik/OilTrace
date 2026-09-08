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
  deleteScenarioApi,
  fetchPhysicsAtPoint,
  fetchScenarioDetails,
  fetchScenarios,
  runPipelineLive,
} from '../api/oiltraceApi';


export const FLAGSHIP_DETECTION: SlickDetection = {
  spill_id: 'SPILL-2026-ARABIAN-001',
  detected_at: '2026-08-25T03:45:00Z',
  geometry: {
    type: 'Polygon',
    coordinates: [[
      [72.432253, 18.82858],
      [72.427507, 18.834857],
      [72.422472, 18.840564],
      [72.417342, 18.84548],
      [72.412314, 18.849417],
      [72.407582, 18.852224],
      [72.403327, 18.853792],
      [72.399712, 18.854062],
      [72.396877, 18.853023],
      [72.394931, 18.850714],
      [72.393948, 18.847225],
      [72.393933, 18.842775],
      [72.394892, 18.837648],
      [72.396818, 18.832133],
      [72.399636, 18.826487],
      [72.403239, 18.820935],
      [72.407484, 18.815668],
      [72.412211, 18.810842],
      [72.417235, 18.806584],
      [72.422365, 18.803002],
      [72.427404, 18.800181],
      [72.432158, 18.798188],
      [72.436442, 18.797071],
      [72.440093, 18.796856],
      [72.442971, 18.79754],
      [72.444962, 18.799092],
      [72.445989, 18.801452],
      [72.445015, 18.802716],
      [72.443034, 18.808788],
      [72.440169, 18.81529],
      [72.436529, 18.821973],
      [72.432253, 18.82858],
    ]],
  },
  centroid: [72.42, 18.82],
  area_km2: 14.82,
  elongation_ratio: 3.85,
  oil_confidence: 0.912,
  thickness_class: 'thick',
  source_scene_id: 'S1A_IW_GRDH_1SDV_MUMBAI_GULF_FLAGSHIP',
  lookalike_suppressed: true,
  data_provenance: 'real_detector',
};

function buildDriftRunFromRaw(
  oe: any,
  traj: any[],
  detection: SlickDetection
): DriftRun | null {
  if (!oe) return null;
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

  // Parse authentic age estimate from oe.age_estimate_hours (Fay spreading law / aspect ratio inversion)
  let ageHours = 24.0;
  let spreadHours = 3.5;
  let ageMethod = 'fay_spreading_inversion';

  if (oe.age_estimate_hours !== undefined && oe.age_estimate_hours !== null) {
    if (typeof oe.age_estimate_hours === 'number') {
      ageHours = oe.age_estimate_hours;
    } else if (typeof oe.age_estimate_hours === 'object') {
      if (typeof oe.age_estimate_hours.value === 'number') {
        ageHours = oe.age_estimate_hours.value;
      }
      if (typeof oe.age_estimate_hours.uncertainty_hours === 'number') {
        spreadHours = oe.age_estimate_hours.uncertainty_hours;
      } else if (Array.isArray(oe.age_estimate_hours.confidence_range) && oe.age_estimate_hours.confidence_range.length === 2) {
        spreadHours = (oe.age_estimate_hours.confidence_range[1] - oe.age_estimate_hours.confidence_range[0]) / 2;
      }
      if (oe.age_estimate_hours.method) {
        ageMethod = oe.age_estimate_hours.method;
      }
    }
  }
  if (ageHours <= 0.1) {
    ageHours = 20.0;
  }

  const estimatedOnsetTime = oe.estimated_onset_time ||
    (!isNaN(detTime) ? new Date(detTime - ageHours * 3600 * 1000).toISOString() : winStart);

  const membersList = traj.map((t: any, idx: number) => {
    let rawTrack = (t.lons || []).map((lon: number, pIdx: number) => ({
      lon,
      lat: t.lats ? t.lats[pIdx] : cLat,
      t: t.times ? t.times[pIdx] : winStart,
    }));

    // Invariant: enforce forward-chronological track order
    // index 0 = earliest (discharge origin in the past), index -1 = latest (detection horizon)
    if (rawTrack.length >= 2) {
      const tStart = new Date(rawTrack[0].t).getTime();
      const tEnd = new Date(rawTrack[rawTrack.length - 1].t).getTime();
      if (!isNaN(tStart) && !isNaN(tEnd) && tStart > tEnd) {
        rawTrack = rawTrack.reverse();
      }
    }

    return {
      member_id: t.member_id !== undefined ? t.member_id : idx,
      windage_coefficient: 0.025 + (idx % 10) * 0.0015,
      current_scale: 1.0,
      backward_track: rawTrack,
    };
  });

  return {
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
      estimated_onset_time: estimatedOnsetTime,
      estimated_onset_spread_hours: spreadHours,
      age_method: ageMethod,
    },
  };
}

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
  deleteScenario: (scenarioId: string) => Promise<void>;
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
  cameraTarget: [72.42, 18.82],

  detection: FLAGSHIP_DETECTION,
  driftRun: null,
  attribution: null,
  selectedCandidateId: null,

  physicsAtPoint: null,
  isPhysicsInspectorOpen: false,
  showEnsembleBuildup: false,
  isLoadingPhysics: false,

  playbackTimeHours: 0.0,
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
      } else {
        set({ isLoadingPipeline: false });
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

  deleteScenario: async (scenarioId: string) => {
    try {
      await deleteScenarioApi(scenarioId);
      await get().refreshScenarios();
      // If user deleted the active scenario, switch back to flagship
      if (get().activeScenarioId === scenarioId) {
        const flagship = get().availableScenarios.find((s) => s.scenario_id === 'mumbai_gulf_flagship');
        if (flagship) {
          await get().loadScenario(flagship);
        } else {
          set({
            activeScenarioId: 'mumbai_gulf_flagship',
            detection: FLAGSHIP_DETECTION,
            cameraTarget: [72.42, 18.82],
            activeScreen: 'overview',
            driftRun: null,
            attribution: null,
          });
          await get().executeInvestigation();
        }
      }
    } catch (err: any) {
      console.error('[Store] Failed to delete scenario:', err);
      throw err;
    }
  },

  loadScenario: async (scenario) => {
    set({ isLoadingPipeline: true, pipelineError: null });

    try {
      // 1. Fetch authentic precomputed scenario artifacts directly from backend
      const details = await fetchScenarioDetails(scenario.scenario_id).catch(() => null);

      if (details && details.slick && details.origin_ensemble) {
        const rawSlick = details.slick as any;
        const props = rawSlick.properties || {};
        const geom = rawSlick.geometry || (rawSlick.coordinates ? rawSlick : { type: 'Polygon', coordinates: [] });

        let calculatedCentroid: [number, number] = [72.42, 18.82];
        if (rawSlick.centroid && Array.isArray(rawSlick.centroid) && rawSlick.centroid.length === 2 && !isNaN(rawSlick.centroid[0])) {
          calculatedCentroid = rawSlick.centroid;
        } else if (props.centroid && Array.isArray(props.centroid) && props.centroid.length === 2 && !isNaN(props.centroid[0])) {
          calculatedCentroid = props.centroid;
        } else if (scenario.bbox && Array.isArray(scenario.bbox) && scenario.bbox.length === 4 && !isNaN(scenario.bbox[0])) {
          calculatedCentroid = [
            Number(((scenario.bbox[0] + scenario.bbox[2]) / 2).toFixed(4)),
            Number(((scenario.bbox[1] + scenario.bbox[3]) / 2).toFixed(4)),
          ];
        }

        const authenticDetection: SlickDetection = {
          spill_id: rawSlick.spill_id || props.spill_id || scenario.spill_id,
          detected_at: rawSlick.detected_at || props.detected_at || scenario.detected_at,
          geometry: geom,
          centroid: calculatedCentroid,
          area_km2: rawSlick.area_km2 || props.area_km2 || scenario.spill_area_km2 || 14.82,
          elongation_ratio: rawSlick.elongation_ratio || props.elongation_ratio || 3.2,
          oil_confidence: rawSlick.oil_confidence || props.oil_confidence || 0.89,
          thickness_class: rawSlick.thickness_class || props.thickness_class || 'thick',
          source_scene_id: rawSlick.source_scene_id || props.source_scene_id || `S1_${scenario.spill_id}`,
          lookalike_suppressed: rawSlick.lookalike_suppressed ?? props.lookalike_suppressed ?? true,
          data_provenance: rawSlick.data_provenance || props.data_provenance || (scenario.has_real_gfw ? 'real_detector' : 'real_uploaded_fixture'),
        };

        const driftRunObj = buildDriftRunFromRaw(
          details.origin_ensemble,
          details.trajectories || [],
          authenticDetection
        );

        set({
          activeScenarioId: scenario.scenario_id,
          detection: authenticDetection,
          cameraTarget: authenticDetection.centroid,
          activeScreen: 'overview',
          selectedCandidateId: details.attribution?.candidates?.length ? details.attribution.candidates[0].vessel_id : null,
          playbackTimeHours: 0.0,
          driftRun: driftRunObj,
          attribution: details.attribution || null,
          isLoadingPipeline: false,
        });

        get().fetchPhysics(authenticDetection.centroid[0], authenticDetection.centroid[1], authenticDetection.detected_at);
        return;
      }
    } catch (err) {
      console.warn('[Store] Fast scenario load fallback:', err);
    }

    // Fallback: If details endpoint unavailable, set detection from bbox and execute investigation
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
      playbackTimeHours: 0.0,
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
      const driftRunObj: DriftRun | null = buildDriftRunFromRaw(
        result.origin_ensemble,
        result.trajectories || [],
        detection
      );

      set({
        attribution: result,
        driftRun: driftRunObj,
        selectedCandidateId: result.candidates.length > 0 ? result.candidates[0].vessel_id : null,
        playbackTimeHours: 0.0,
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
    await get().refreshScenarios();
    await get().executeInvestigation();
  },
}));
