/**
 * Central API client for the Integration+Frontend backend.
 *
 * Every method is typed against `src/types/schemas.ts`, which mirrors
 * `schemas.md` v1.2 and `backend/app/models.py`. This file owns HTTP
 * concerns only — no subsystem logic, no reshaping beyond what the wire
 * contract already specifies.
 */

import type {
  AttributionResult,
  DetectionPredictRequest,
  DetectionPredictResponse,
  PipelineRunRequest,
  ScenarioData,
  ScenarioSummary,
  SlickDetection,
} from "../types/schemas";

const API_BASE = "http://localhost:8000";

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (err) {
    throw new ApiError(
      `Unable to reach backend at ${API_BASE}${path} — is the server running?`
    );
  }

  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = body?.detail ? ` — ${JSON.stringify(body.detail)}` : "";
    } catch {
      // response body wasn't JSON; ignore
    }
    throw new ApiError(`${path} failed (${response.status})${detail}`, response.status);
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Local fallback — the Arabian Sea flagship scenario, used only when
// GET /scenarios cannot be reached. Never used to silently mask a live
// pipeline failure; only the scenario picker's initial list falls back.
// ---------------------------------------------------------------------------

const LOCAL_SCENARIO_FALLBACK: ScenarioSummary[] = [
  {
    scenario_id: "arabian-sea-flagship",
    name: "Arabian Sea — Flagship Scenario",
    spill_id: "spill_arabian_sea_001",
    bbox: [65.0, 15.0, 70.0, 20.0],
    detected_at: "2026-08-27T00:00:00Z",
  },
];

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  [key: string]: unknown;
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------

export async function fetchScenarios(): Promise<ScenarioSummary[]> {
  try {
    const res = await request<ScenarioSummary[] | { scenarios: ScenarioSummary[] }>("/scenarios");
    if (Array.isArray(res)) return res;
    if (res && Array.isArray((res as { scenarios: ScenarioSummary[] }).scenarios)) {
      return (res as { scenarios: ScenarioSummary[] }).scenarios;
    }
    return LOCAL_SCENARIO_FALLBACK;
  } catch (err) {
    return LOCAL_SCENARIO_FALLBACK;
  }
}

export function fetchScenarioData(scenarioId: string): Promise<ScenarioData> {
  return request<ScenarioData>(`/scenarios/${scenarioId}`);
}

// ---------------------------------------------------------------------------
// Detection
// ---------------------------------------------------------------------------

export function predictDetection(imagePath: string): Promise<DetectionPredictResponse> {
  const payload: DetectionPredictRequest = { image_path: imagePath };
  return request<DetectionPredictResponse>("/detection/predict", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

export function runPipeline(payload: PipelineRunRequest): Promise<AttributionResult> {
  return request<AttributionResult>("/pipeline/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
