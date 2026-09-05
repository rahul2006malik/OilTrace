import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import type { Candidate, LonLat } from "../../types/schemas";
import { ProvenanceBadge } from "./ProvenanceBadge";

/**
 * The canonical `Candidate` contract (schemas.md §3) intentionally does not
 * carry full vessel-registry fields — IMO, call sign, flag state, ship type,
 * AIS gap duration, loitering counts. Those live in the GFW vessel-registry
 * lookup and the behavior-event caches (`gap_events_*.json`,
 * `loitering_events_*.json`; Design Spec §2.2) that sit outside this
 * contract's scope for now.
 *
 * This modal treats those fields as an optional supplement: if a joined /
 * future API response attaches them onto the candidate object, they render.
 * If not, the field renders as `UNRESOLVED` / `NOT REPORTED` — never
 * fabricated. This keeps faith with the "mathematically honest, never false
 * certainty" mandate (Design Spec §0.1) even where the data contract is
 * still catching up to the mock.
 */
export interface VesselRegistryExtras {
  imo?: string | null;
  call_sign?: string | null;
  flag_state?: string | null;
  ship_type?: string | null;
  /** Hours of AIS silence overlapping the drift window. */
  ais_gap_hours?: number | null;
  loitering_event_count?: number | null;
}

export type CandidateWithRegistry = Candidate & Partial<VesselRegistryExtras>;

interface VesselIdentityModalProps {
  candidate: CandidateWithRegistry | null;
  onClose: () => void;
}

function formatCoordinate(position: LonLat | null): string {
  if (!position) return "POSITION UNRESOLVED";
  const [lon, lat] = position;
  const latDir = lat >= 0 ? "N" : "S";
  const lonDir = lon >= 0 ? "E" : "W";
  return `${Math.abs(lon).toFixed(3)}\u00B0${lonDir}, ${Math.abs(lat).toFixed(3)}\u00B0${latDir}`;
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "UNRESOLVED";
  return `${(value * 100).toFixed(1)}%`;
}

function RegistryField({ label, value }: { label: string; value: string | null | undefined }) {
  const resolved = value === null || value === undefined || value === "";
  return (
    <div className="flex flex-col gap-0.5 border-b border-chart-contour py-2">
      <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</span>
      <span
        className={
          resolved
            ? "font-mono text-[13px] text-ink-tertiary"
            : "font-mono text-[13px] tabular-nums text-ink-primary"
        }
      >
        {resolved ? "UNRESOLVED" : value}
      </span>
    </div>
  );
}

export function VesselIdentityModal({ candidate, onClose }: VesselIdentityModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!candidate) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [candidate, onClose]);

  if (!candidate) return null;

  const displayName = candidate.vessel_name ?? `MMSI: ${candidate.vessel_id}`;
  const gapReported = candidate.ais_gap_hours !== undefined && candidate.ais_gap_hours !== null;
  const loiterReported =
    candidate.loitering_event_count !== undefined && candidate.loitering_event_count !== null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-chart-abyss/80"
      role="dialog"
      aria-modal="true"
      aria-label="Vessel identity record"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        className="flex max-h-[80vh] w-[420px] flex-col overflow-hidden rounded-sm border border-chart-contour bg-chart-surface shadow-none"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-chart-contour bg-chart-raised px-4 py-3">
          <div className="flex flex-col gap-1">
            <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
              Vessel Registry Record
            </span>
            <span className="font-sans text-[15px] font-semibold leading-tight text-ink-primary">
              {displayName}
            </span>
            <ProvenanceBadge provenance={candidate.data_provenance} />
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close vessel record"
            className="rounded-sm border border-chart-contour p-1 text-ink-secondary hover:border-ink-secondary hover:text-ink-primary"
          >
            <X size={14} strokeWidth={2} />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-4 py-1">
          <div className="grid grid-cols-2 gap-x-4">
            <RegistryField label="MMSI" value={candidate.vessel_id} />
            <RegistryField label="IMO" value={candidate.imo ?? null} />
            <RegistryField label="Call Sign" value={candidate.call_sign ?? null} />
            <RegistryField label="Flag State" value={candidate.flag_state ?? null} />
          </div>
          <RegistryField label="Ship Type" value={candidate.ship_type ?? null} />
          <RegistryField label="Last Known Coordinate" value={formatCoordinate(candidate.last_known_position)} />

          <div className="mt-1 border-b border-chart-contour pb-2 pt-2">
            <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
              AIS Transmission Status
            </span>
            <div className="mt-1 flex items-center justify-between">
              <span className="font-mono text-[13px] tabular-nums text-ink-primary">
                {gapReported ? `${candidate.ais_gap_hours!.toFixed(1)} hrs blackout` : "NO GAP REPORTED"}
              </span>
              <span className="font-mono text-[12px] tabular-nums text-ink-secondary">
                {loiterReported
                  ? `${candidate.loitering_event_count} LOITERING EVENT${
                      candidate.loitering_event_count === 1 ? "" : "S"
                    }`
                  : "LOITERING: NOT REPORTED"}
              </span>
            </div>
          </div>

          <div className="mt-2 flex items-center justify-between border-b border-chart-contour pb-3 pt-1">
            <div className="flex flex-col">
              <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
                Suspicion Probability
              </span>
              <span className="font-mono text-[16px] tabular-nums text-ink-primary">
                {formatPercent(candidate.suspicion_score)}
              </span>
            </div>
            <div className="flex flex-col items-end">
              <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
                Bootstrap 95% CI
              </span>
              <span className="font-mono text-[12px] tabular-nums text-ink-secondary">
                {candidate.confidence_interval
                  ? `[${formatPercent(candidate.confidence_interval[0])} \u2014 ${formatPercent(
                      candidate.confidence_interval[1]
                    )}]`
                  : "CI UNAVAILABLE"}
              </span>
            </div>
          </div>

          <div className="py-3">
            <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
              Dominant Evidence Factor
            </span>
            <div className="mt-1 font-mono text-[12px] uppercase tracking-wide text-signal-attention">
              {candidate.evidence_trace.dominant_factor}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default VesselIdentityModal;
