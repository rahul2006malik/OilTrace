import { useScenario } from "../../context/ScenarioContext";
import ComponentScoreBars from "./ComponentScoreBars";
import WeightSandbox from "./WeightSandbox";
import ConfessionReplayOverlay from "./ConfessionReplayOverlay";

export default function EvidenceTraceCard() {
  const { attributionData, selectedCandidateId, originConeData, sandboxWeights, setSandboxWeights } =
    useScenario();

  const candidate = attributionData?.candidates.find((c) => c.vessel_id === selectedCandidateId) ?? null;

  const hypothesis =
    candidate && originConeData
      ? originConeData.forward_hypotheses?.find((h) => h.vessel_id === candidate.vessel_id) ?? null
      : null;

  return (
    <section className="flex flex-col h-full min-h-0 bg-chart-surface">
      <header className="flex items-center justify-between px-3 py-2 border-b border-chart-contour flex-shrink-0">
        <h2 className="text-2xs uppercase tracking-wider text-ink-secondary">
          Forensic Evidence Trace
        </h2>
        {candidate && (
          <span className="text-2xs font-mono text-ink-tertiary">
            {candidate.vessel_name ?? `MMSI ${candidate.vessel_id}`}
          </span>
        )}
      </header>

      <div className="flex-1 min-h-0 overflow-y-auto px-3 py-3">
        {!candidate ? (
          <div className="h-full flex items-center justify-center text-center px-4">
            <p className="text-2xs text-ink-tertiary leading-relaxed">
              Select a vessel in the attribution ranking above to inspect its evidentiary
              decomposition and run sensitivity re-weighting.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <ComponentScoreBars evidence={candidate.evidence_trace} />

            <ConfessionReplayOverlay
              hypothesis={hypothesis}
              confessionMatchScore={candidate.evidence_trace.confession_match_score}
            />

            <WeightSandbox
              evidence={candidate.evidence_trace}
              backendScore={candidate.suspicion_score}
              weights={sandboxWeights}
              onWeightsChange={setSandboxWeights}
            />
          </div>
        )}
      </div>
    </section>
  );
}
