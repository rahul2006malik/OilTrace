import type { Candidate } from "../../types/schemas";
import { ProvenanceBadge } from "./ProvenanceBadge";
import type { CandidateWithRegistry } from "./VesselIdentityModal";

interface CandidateRowProps {
  candidate: CandidateWithRegistry;
  rank: number;
  isSelected: boolean;
  onSelect: (vesselId: string) => void;
  onOpenDetails: (vesselId: string) => void;
  /**
   * Recomputed sandbox score, when the Sensitivity Sandbox weights are off
   * their 0.25/0.25/0.25/0.25 defaults. `null`/`undefined` means "sandbox
   * inactive or evidence trace insufficient" — fall back to the backend
   * `suspicion_score`.
   */
  sandboxScore?: number | null;
}

function formatPercent(value: number | null): string {
  if (value === null) return "N/A";
  return `${(value * 100).toFixed(1)}%`;
}

function formatCi(ci: Candidate["confidence_interval"]): string {
  if (!ci) return "CI UNAVAILABLE";
  return `[${formatPercent(ci[0])} \u2014 ${formatPercent(ci[1])}]`;
}

function scoreColorClass(score: number | null): string {
  if (score === null) return "text-ink-tertiary";
  if (score > 0.6) return "text-prov-gfw";
  if (score >= 0.4) return "text-signal-attention";
  return "text-ink-tertiary";
}

/** `MMSI 941234567 · IMO 9412345 · Flag PAN` — omits any field it can't resolve. */
function buildIdentitySubtitle(candidate: CandidateWithRegistry): string {
  const parts = [`MMSI ${candidate.vessel_id}`];
  if (candidate.imo) parts.push(`IMO ${candidate.imo}`);
  if (candidate.flag_state) parts.push(`Flag ${candidate.flag_state}`);
  return parts.join(" \u00B7 ");
}

export function CandidateRow({
  candidate,
  rank,
  isSelected,
  onSelect,
  onOpenDetails,
  sandboxScore,
}: CandidateRowProps) {
  const backendScore = candidate.suspicion_score;
  const hasSandboxDelta =
    sandboxScore !== null &&
    sandboxScore !== undefined &&
    backendScore !== null &&
    Math.abs(sandboxScore - backendScore) > 0.001;
  const displayScore = hasSandboxDelta ? sandboxScore! : backendScore;
  const displayName = candidate.vessel_name ?? `MMSI: ${candidate.vessel_id}`;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(candidate.vessel_id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") onSelect(candidate.vessel_id);
      }}
      className={[
        "grid h-12 cursor-pointer grid-cols-[32px_1fr_auto] items-center gap-2 border-b border-chart-contour px-2",
        "border-l-2",
        isSelected ? "border-l-prov-gfw bg-chart-hover" : "border-l-transparent hover:bg-chart-raised",
      ].join(" ")}
    >
      {/* Col 1: Rank */}
      <span className="font-mono text-[11px] tabular-nums text-ink-tertiary">
        {`#${String(rank).padStart(2, "0")}`}
      </span>

      {/* Col 2: Vessel identity */}
      <div className="flex min-w-0 flex-col justify-center">
        <span className="truncate font-sans text-[13px] font-semibold leading-tight text-ink-primary">
          {displayName}
        </span>
        <span className="truncate font-mono text-[10px] tabular-nums leading-tight text-ink-secondary">
          {buildIdentitySubtitle(candidate)}
        </span>
      </div>

      {/* Col 3 + 4: Provenance / Suspicion metric, right-aligned block */}
      <div className="flex flex-col items-end gap-1">
        <div className="flex items-center gap-1.5">
          <ProvenanceBadge provenance={candidate.data_provenance} compact />
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenDetails(candidate.vessel_id);
            }}
            className="rounded-sm border border-chart-contour px-1 py-[1px] font-mono text-[9px] tracking-wider text-ink-secondary hover:border-ink-secondary hover:text-ink-primary"
          >
            [DETAILS]
          </button>
        </div>
        <div className="flex flex-col items-end leading-tight">
          <span className={`font-mono text-[13px] font-medium tabular-nums ${scoreColorClass(displayScore)}`}>
            {hasSandboxDelta
              ? `${formatPercent(backendScore)} \u2192 ${formatPercent(sandboxScore!)}`
              : formatPercent(backendScore)}
          </span>
          <span className="font-mono text-[10px] tabular-nums text-ink-tertiary">
            {formatCi(candidate.confidence_interval)}
          </span>
        </div>
      </div>
    </div>
  );
}

export default CandidateRow;
