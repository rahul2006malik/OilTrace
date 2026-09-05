import { useMemo, useState } from "react";
import type { Candidate, SandboxWeights } from "../../types/schemas";
import { useScenario } from "../../context/ScenarioContext";
import { CandidateRow } from "./CandidateRow";
import { VesselIdentityModal, type CandidateWithRegistry } from "./VesselIdentityModal";

/**
 * SuspectLeaderboard — right-column top panel.
 *
 * Reads `attributionData`, `selectedCandidateId`, `setSelectedCandidateId`,
 * and `sandboxWeights` off `ScenarioContext`. The sandbox-recalculation formula:
 *
 *   Suspicion = sigmoid( (w1*s_prox + w2*s_conf + w3*s_anom + w4*s_prior) / T )
 *
 * `T` is a fixed client-side temperature, not part of the backend contract —
 * this recalculation is explicitly an exploratory browser-side simulation
 * and never overwrites the backend-computed `suspicion_score`.
 */

const DEFAULT_WEIGHTS: SandboxWeights = {
  proximity: 0.25,
  confession_match: 0.25,
  anomaly: 0.25,
  vessel_type_prior: 0.25,
};

const SANDBOX_TEMPERATURE = 1;

function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x));
}

function weightsAreDefault(weights: SandboxWeights | null | undefined): boolean {
  if (!weights) return true;
  return (Object.keys(DEFAULT_WEIGHTS) as (keyof SandboxWeights)[]).every(
    (key) => Math.abs(weights[key] - DEFAULT_WEIGHTS[key]) < 1e-6
  );
}

function computeSandboxScore(candidate: Candidate, weights: SandboxWeights): number | null {
  const trace = candidate.evidence_trace;
  if (!trace) return null;
  const priorScore = trace.vessel_type_prior ?? 0;
  const weightedSum =
    weights.proximity * trace.proximity_score +
    weights.confession_match * trace.confession_match_score +
    weights.anomaly * trace.anomaly_score +
    weights.vessel_type_prior * priorScore;
  return sigmoid(weightedSum / SANDBOX_TEMPERATURE);
}

export function SuspectLeaderboard() {
  const { attributionData, selectedCandidateId, setSelectedCandidateId, sandboxWeights } = useScenario();
  const [detailsVesselId, setDetailsVesselId] = useState<string | null>(null);

  const candidates = (attributionData?.candidates ?? []) as CandidateWithRegistry[];
  const sandboxActive = !weightsAreDefault(sandboxWeights);

  const rankedCandidates = useMemo(() => {
    const withScores = candidates.map((candidate) => ({
      candidate,
      sandboxScore: sandboxActive && sandboxWeights ? computeSandboxScore(candidate, sandboxWeights) : null,
    }));

    withScores.sort((a, b) => {
      const scoreA = (sandboxActive ? a.sandboxScore : a.candidate.suspicion_score) ?? -Infinity;
      const scoreB = (sandboxActive ? b.sandboxScore : b.candidate.suspicion_score) ?? -Infinity;
      return scoreB - scoreA;
    });

    return withScores;
  }, [candidates, sandboxActive, sandboxWeights]);

  const detailsCandidate = candidates.find((c) => c.vessel_id === detailsVesselId) ?? null;

  return (
    <section className="flex h-full flex-col border-b border-chart-contour bg-chart-surface">
      {/* Header */}
      <div className="flex flex-col gap-0.5 border-b border-chart-contour px-3 py-2.5">
        <div className="flex items-baseline justify-between">
          <h2 className="font-sans text-[13px] font-semibold uppercase tracking-wide text-ink-primary">
            Vessel Attribution Ranking
          </h2>
          <span className="font-mono text-[11px] tabular-nums text-ink-secondary">
            {`(${candidates.length} TARGET${candidates.length === 1 ? "" : "S"})`}
          </span>
        </div>
        <p className="font-sans text-[11px] text-ink-tertiary">Ranked by Multi-Factor Evidentiary Fusion</p>
        {sandboxActive && (
          <p className="font-mono text-[9px] uppercase tracking-wider text-signal-attention">
            Exploratory re-weighting active // browser simulation
          </p>
        )}
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-y-auto">
        {rankedCandidates.length === 0 ? (
          <div className="px-3 py-4 font-mono text-[11px] text-ink-tertiary">
            NO CANDIDATE VESSELS RESOLVED FOR THIS SPILL.
          </div>
        ) : (
          rankedCandidates.map(({ candidate, sandboxScore }, index) => (
            <CandidateRow
              key={candidate.vessel_id}
              candidate={candidate}
              rank={index + 1}
              isSelected={selectedCandidateId === candidate.vessel_id}
              onSelect={setSelectedCandidateId}
              onOpenDetails={setDetailsVesselId}
              sandboxScore={sandboxScore}
            />
          ))
        )}
      </div>

      <VesselIdentityModal candidate={detailsCandidate} onClose={() => setDetailsVesselId(null)} />
    </section>
  );
}

export default SuspectLeaderboard;
