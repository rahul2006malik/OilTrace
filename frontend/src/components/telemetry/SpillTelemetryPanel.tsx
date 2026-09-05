import { useState } from "react";
import { clsx } from "clsx";
import { useScenario } from "../../context/ScenarioContext";
import { runPipeline } from "../../api/client";
import { SarSceneSelector } from "./SarSceneSelector";
import { SpillGeometryCard } from "./SpillGeometryCard";
import { MetoceanTelemetryCard } from "./MetoceanTelemetryCard";

type PipelineRunState = "idle" | "running" | "done" | "error";

/**
 * Left Intelligence Panel (Spill Telemetry & Geometry).
 *
 * Reads `slickData` / `originEnsemble` off `ScenarioContext` and writes
 * newly-detected slicks back into it via `setSlickData`.
 */
export function SpillTelemetryPanel() {
  const {
    slickData,
    setSlickData,
    originEnsemble,
    setOriginConeData,
    setTrajectoriesData,
    setAttributionData,
  } = useScenario();
  const [pipelineState, setPipelineState] = useState<PipelineRunState>("idle");

  async function handleInitiateInvestigation() {
    if (!slickData) return;
    setPipelineState("running");
    try {
      const result = await runPipeline({
        spill_id: slickData.spill_id,
        location: { lon: slickData.centroid[0], lat: slickData.centroid[1] },
        detected_at: slickData.detected_at,
        slick_geojson_ref: slickData,
      });
      setAttributionData(result);
      if (result.origin_ensemble) {
        setOriginConeData(result.origin_ensemble);
      }
      if (result.trajectories) {
        setTrajectoriesData(result.trajectories);
      }
      setPipelineState("done");
    } catch {
      setPipelineState("error");
    }
  }

  return (
    <aside className="flex h-full w-full flex-col overflow-y-auto bg-chart-surface">
      <SarSceneSelector onDetection={setSlickData} />

      {slickData ? (
        <SpillGeometryCard slick={slickData} />
      ) : (
        <div className="border-b border-chart-contour p-3">
          <p className="font-mono text-[11px] text-ink-tertiary">
            NO INCIDENT LOADED // RUN LIVE DETECTION OR SELECT A SCENARIO
          </p>
        </div>
      )}

      {originEnsemble && originEnsemble.age_estimate_hours && (
        <MetoceanTelemetryCard
          ageEstimateHours={originEnsemble.age_estimate_hours}
          ensembleMemberCount={Array.isArray(originEnsemble.ensemble_members) ? originEnsemble.ensemble_members.length : 25}
        />
      )}

      <div className="p-3">
        <button
          type="button"
          onClick={handleInitiateInvestigation}
          disabled={!slickData || pipelineState === "running"}
          className={clsx(
            "w-full border px-3 py-2 text-xs font-medium uppercase tracking-wider",
            "disabled:cursor-not-allowed disabled:border-chart-contour disabled:text-ink-tertiary disabled:opacity-60",
            slickData && pipelineState !== "running"
              ? "border-prov-gfw text-prov-gfw hover:bg-chart-hover"
              : "border-chart-contour text-ink-tertiary",
          )}
        >
          {pipelineState === "running"
            ? "Running Forensic Pipeline…"
            : "Initiate Forensic Investigation"}
        </button>

        {pipelineState === "error" && (
          <p className="mt-2 font-mono text-[11px] text-signal-alert">
            PIPELINE REQUEST FAILED // CHECK BACKEND CONNECTIVITY
          </p>
        )}
      </div>
    </aside>
  );
}
