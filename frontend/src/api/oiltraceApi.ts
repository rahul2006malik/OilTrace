/**
 * OilTrace API Client (Canonical v2.0)
 *
 * Interacts directly with the FastAPI backend. All response shapes match
 * the canonical v2 contracts defined in contracts/schema.ts.
 */

import {
  AttributionResult,
  Candidate,
  DriftRun,
  PhysicsAtPoint,
  SlickDetection,
  SystemHealth,
} from '../types';

const API_BASE = ''; // Leverages Vite development proxy or relative route

/**
 * Health check endpoint verifying backend and all subsystem statuses.
 */
export async function checkBackendHealth(): Promise<SystemHealth> {
  try {
    const res = await fetch(`${API_BASE}/health`, { method: 'GET' });
    if (!res.ok) {
      throw new Error(`Health check returned status ${res.status}`);
    }
    const data = await res.json();
    return {
      status: data.status === 'ok' ? 'ok' : 'degraded',
      subsystems: data.subsystems || {
        detection_available: false,
        drift_available: false,
        attribution_available: false,
      },
      cache_dir: data.cache_dir || '',
    };
  } catch (err) {
    console.warn('[oiltraceApi] Backend offline or unreachable:', err);
    return {
      status: 'error',
      subsystems: {
        detection_available: false,
        drift_available: false,
        attribution_available: false,
      },
      cache_dir: '',
    };
  }
}

/**
 * Executes or loads the end-to-end investigation pipeline.
 */
export async function runPipelineLive(payload: {
  spill_id: string;
  location: { lon: number; lat: number };
  detected_at: string;
  slick_geojson_ref?: string | object;
  image_path?: string;
}): Promise<AttributionResult> {
  const res = await fetch(`${API_BASE}/pipeline/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Pipeline failed (${res.status}): ${errorText}`);
  }

  return await res.json();
}

/**
 * Queries real GLORYS current and ERA5 wind vectors at coordinate & time.
 */
export async function fetchPhysicsAtPoint(
  lon: number,
  lat: number,
  timeIso?: string
): Promise<PhysicsAtPoint> {
  const params = new URLSearchParams({
    lon: lon.toFixed(4),
    lat: lat.toFixed(4),
  });
  if (timeIso) {
    params.set('time', timeIso);
  }

  const res = await fetch(`${API_BASE}/drift/physics_at?${params.toString()}`);
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Physics query failed (${res.status}): ${errorText}`);
  }

  return await res.json();
}

/**
 * Executes live two-stage SAR detection on a local scene file.
 */
export async function runDetectionPredict(imagePath: string): Promise<any> {
  const res = await fetch(`${API_BASE}/detection/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_path: imagePath }),
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Detection predict failed (${res.status}): ${errorText}`);
  }

  return await res.json();
}

/**
 * Submits forensic analyst feedback to the immutable audit ledger.
 */
export async function submitAnalystFeedback(payload: {
  spill_id: string;
  vessel_id: string;
  action: 'verify' | 'dismiss' | 'override';
  analyst_id?: string;
  notes?: string;
}): Promise<any> {
  const res = await fetch(`${API_BASE}/analyst/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`Analyst feedback failed: ${res.statusText}`);
  }

  return await res.json();
}

/**
 * Fetches list of all demo scenarios from the backend.
 */
export async function fetchScenarios(): Promise<{ scenarios: any[] }> {
  // B5 FIX: Use /api/scenarios prefix consistently with all other endpoints.
  // The bare /scenarios path bypasses the Vite proxy in dev mode which only
  // handles /api/* routes, causing the SPA's own index.html to be returned instead
  // of JSON — silently breaking scenario loading every time.
  const res = await fetch(`${API_BASE}/api/scenarios`);
  if (!res.ok) {
    throw new Error(`Failed to fetch scenarios (${res.status})`);
  }
  return await res.json();
}

export async function deleteScenarioApi(scenarioId: string): Promise<{ status: string; scenario_id: string; files_purged: number; message: string }> {
  const res = await fetch(`${API_BASE}/api/scenarios/${encodeURIComponent(scenarioId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to delete scenario (${res.status}): ${errorText}`);
  }
  return await res.json();
}

/**
 * Fetches full scenario data (slick detection GeoJSON, drift ensemble, trajectories, attribution).
 */
export async function fetchScenarioDetails(scenarioId: string): Promise<{
  scenario_id: string;
  origin_ensemble: any;
  trajectories: any[];
  slick: SlickDetection | null;
  attribution: AttributionResult | null;
}> {
  const res = await fetch(`${API_BASE}/api/scenarios/${encodeURIComponent(scenarioId)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch scenario details for ${scenarioId} (${res.status})`);
  }
  return await res.json();
}
/**
 * Uploads a custom SAR image with incident coordinates to create and register a new scenario.
 */
export async function createCustomScenarioApi(
  file: File,
  name: string,
  lon: number,
  lat: number
): Promise<{ status: string; scenario: any; detection: SlickDetection }> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('name', name);
  formData.append('lon', lon.toString());
  formData.append('lat', lat.toString());

  const res = await fetch(`${API_BASE}/api/scenarios/create-custom`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Upload and scenario creation failed: ${errorText}`);
  }

  return await res.json();
}

/**
 * Fetches dynamic ERA5 wind and GLORYS ocean current vector grid for bounding box.
 */
export async function fetchMetoceanGrid(
  bbox: [number, number, number, number],
  timeIso?: string,
  gridStep: number = 0.5,
  scenarioId?: string
): Promise<any> {
  const lonSpan = Math.max(0.1, bbox[2] - bbox[0]);
  const calculatedRes = Math.max(4, Math.min(24, Math.round(lonSpan / Math.max(0.05, gridStep))));
  const params = new URLSearchParams({
    min_lon: bbox[0].toFixed(4),
    min_lat: bbox[1].toFixed(4),
    max_lon: bbox[2].toFixed(4),
    max_lat: bbox[3].toFixed(4),
    grid_res: calculatedRes.toString(),
  });
  if (timeIso) {
    params.set('time', timeIso);
  }
  if (scenarioId) {
    params.set('scenario_id', scenarioId);
  }

  const res = await fetch(`${API_BASE}/api/metocean/grid?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Metocean grid query failed (${res.status}): ${await res.text()}`);
  }
  return await res.json();
}

/**
 * Queries upcoming Sentinel-1 and RISAT-1A orbital passes and swath coverage.
 */
export async function fetchSatellitePasses(
  lon: number,
  lat: number,
  spillId?: string
): Promise<any> {
  const params = new URLSearchParams({
    lon: lon.toFixed(4),
    lat: lat.toFixed(4),
  });
  if (spillId) {
    params.set('spill_id', spillId);
  }

  const res = await fetch(`${API_BASE}/api/surveillance/satellite-passes?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Satellite passes query failed (${res.status}): ${await res.text()}`);
  }
  return await res.json();
}

/**
 * Generates an Admiralty multi-page PDF dossier from the backend ReportLab engine.
 */
export async function generateBackendReportPdf(payload: {
  spill_id: string;
  detected_at?: string;
  centroid?: [number, number];
  area_km2?: number;
  lead_mmsi?: string;
  lead_vessel_name?: string;
  suspicion_score?: number;
  flag_state?: string;
  jurisdiction?: string;
  directive?: string;
}): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/reports/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`Report generation failed (${res.status}): ${await res.text()}`);
  }

  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const data = await res.json();
    const pdfUrl = data.pdfUrl?.startsWith('http') ? data.pdfUrl : `${API_BASE}${data.pdfUrl}`;
    const pdfRes = await fetch(pdfUrl);
    if (!pdfRes.ok) {
      throw new Error(`Failed to download report PDF (${pdfRes.status})`);
    }
    return await pdfRes.blob();
  }

  return await res.blob();
}

/**
 * Fetches entries from the human-in-the-loop analyst feedback ledger.
 */
export async function fetchAnalystLedger(): Promise<any[]> {
  try {
    const res = await fetch(`${API_BASE}/api/analyst/ledger`);
    if (!res.ok) return [];
    const data = await res.json();
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.entries)) return data.entries;
    return [];
  } catch (err) {
    console.warn('[oiltraceApi] Failed to fetch analyst ledger:', err);
    return [];
  }
}

