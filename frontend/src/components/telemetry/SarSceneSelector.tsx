import { useState } from "react";
import { clsx } from "clsx";
import { predictDetection } from "../../api/client";
import type { SlickDetection } from "../../types/schemas";
import { InferenceBadge } from "./InferenceBadge";
import { normalizeDetectionResponse } from "./format";

const SCENE_ROOT = "data/processed/part1/_batches/batch0001/images/";

interface SarScene {
  file: string;
  label: string;
  spillId?: string;
  detectedAt?: string;
}

const SCENES: SarScene[] = [
  {
    file: "00000.tif",
    label: "00000.tif — FLAGSHIP: ARABIAN SEA OIL SLICK (MUMBAI OFFSHORE)",
    spillId: "SPILL-2026-ARABIAN-001",
    detectedAt: "2026-08-25T06:00:00Z",
  },
  {
    file: "00001.tif",
    label: "00001.tif — TEST SCENE: GULF OF OMAN",
    spillId: "SPILL-2026-OMAN-002",
    detectedAt: "2026-08-25T06:00:00Z",
  },
  {
    file: "00002.tif",
    label: "00002.tif — NEGATIVE CONTROL: CLEAN WATER",
    spillId: "SPILL-2026-CONTROL-003",
    detectedAt: "2026-08-25T06:00:00Z",
  },
];

/** Stage-1 classifier gate threshold quoted in the negative-result notice. */
const STAGE1_GATE_P = 0.02;

type RunState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "positive"; executionTimeSeconds: number }
  | { status: "negative"; executionTimeSeconds: number; confidence: number }
  | { status: "error"; message: string };

export interface SarSceneSelectorProps {
  /** Called with the newly-detected slick once a positive run resolves. */
  onDetection: (slick: SlickDetection) => void;
}

export function SarSceneSelector({ onDetection }: SarSceneSelectorProps) {
  const [selectedScene, setSelectedScene] = useState<SarScene>(SCENES[0]);
  const [run, setRun] = useState<RunState>({ status: "idle" });

  async function handleRunLiveDetection() {
    setRun({ status: "running" });
    try {
      const response = await predictDetection(SCENE_ROOT + selectedScene.file);
      const executionTimeSeconds = Number(response.execution_time_seconds ?? 0);

      if (!response.has_oil) {
        setRun({
          status: "negative",
          executionTimeSeconds,
          confidence: Number(response.oil_confidence ?? 0),
        });
        return;
      }

      const spillId = selectedScene.spillId || `spill_${selectedScene.file.replace(".tif", "")}_${Date.now().toString(36)}`;
      const detectedAt = selectedScene.detectedAt || "2026-08-25T06:00:00Z";
      const normalized = normalizeDetectionResponse(
        response as unknown as Record<string, unknown>,
        { spillId, sourceSceneId: selectedScene.file.replace(".tif", "") },
      ) as Record<string, unknown>;
      normalized.spill_id = spillId;
      normalized.detected_at = detectedAt;
      onDetection(normalized as unknown as SlickDetection);
      setRun({ status: "positive", executionTimeSeconds });
    } catch (err) {
      setRun({
        status: "error",
        message: err instanceof Error ? err.message : "DETECTION REQUEST FAILED",
      });
    }
  }

  const isRunning = run.status === "running";

  return (
    <section className="border-b border-chart-contour p-3">
      <h2 className="mb-2 text-[11px] font-medium uppercase tracking-wider text-ink-secondary">
        Live SAR Scene Trigger
      </h2>

      <label className="mb-1 block text-[10px] uppercase tracking-wider text-ink-tertiary">
        Sentinel-1 Scene
      </label>
      <select
        value={selectedScene.file}
        disabled={isRunning}
        onChange={(e) => {
          const next = SCENES.find((s) => s.file === e.target.value);
          if (next) setSelectedScene(next);
        }}
        className={clsx(
          "mb-2 w-full border border-chart-contour bg-chart-surface px-2 py-1.5",
          "font-mono text-xs text-ink-primary tabular-nums",
          "focus:border-prov-gfw focus:outline-none",
          "disabled:opacity-50",
        )}
      >
        {SCENES.map((scene) => (
          <option key={scene.file} value={scene.file}>
            {scene.label}
          </option>
        ))}
      </select>

      <button
        type="button"
        onClick={handleRunLiveDetection}
        disabled={isRunning}
        className={clsx(
          "w-full border border-chart-contour bg-chart-accent px-3 py-2",
          "text-xs font-medium uppercase tracking-wider text-ink-primary",
          "hover:border-prov-gfw hover:bg-chart-hover",
          "disabled:cursor-not-allowed disabled:opacity-60",
        )}
      >
        {isRunning ? "Running Inference…" : "Run Live Detection"}
      </button>

      {isRunning && (
        <p className="mt-2 font-mono text-[11px] text-ink-secondary">
          PROCESSING SATELLITE RADIOMETRY (VV/VH)…
        </p>
      )}

      {run.status === "positive" && (
        <div className="mt-2">
          <InferenceBadge executionTimeSeconds={run.executionTimeSeconds} />
        </div>
      )}

      {run.status === "negative" && (
        <div className="mt-2 space-y-2">
          <InferenceBadge executionTimeSeconds={run.executionTimeSeconds} />
          <p className="border border-chart-contour bg-chart-raised px-2 py-2 font-mono text-[11px] leading-relaxed text-signal-attention">
            NO SLICK DETECTED // STAGE 1 CLASSIFIER GATE HALTED (P &lt; {STAGE1_GATE_P.toFixed(2)})
          </p>
        </div>
      )}

      {run.status === "error" && (
        <p className="mt-2 border border-signal-alert bg-chart-raised px-2 py-2 font-mono text-[11px] text-signal-alert">
          {run.message}
        </p>
      )}
    </section>
  );
}
