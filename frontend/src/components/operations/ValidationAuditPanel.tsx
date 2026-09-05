/**
 * ValidationAuditPanel.tsx
 *
 * Collapsible drawer surfacing `attributionData.top_k_recovery` — the
 * benchmark ground-truth recovery check used to validate the attribution
 * pipeline against constructed evaluation scenarios.
 *
 * Per schemas.ts, `recovered`/`confidence` are `null` for live/unknown
 * scenarios where there is no ground truth to check against. That is a
 * legitimate, first-class state — not an error — so it's rendered as an
 * explicit "N/A, no ground truth" message rather than a misleading
 * YES/NO fallback.
 */
import { useState } from "react";
import { ChevronDown, ChevronUp, CheckCircle2, XCircle, HelpCircle } from "lucide-react";
import type { TopKRecovery } from "../../types/schemas";

export interface ValidationAuditPanelProps {
  topKRecovery: TopKRecovery | null | undefined;
  benchmarkReference?: string;
  defaultOpen?: boolean;
  className?: string;
}

export default function ValidationAuditPanel({
  topKRecovery,
  benchmarkReference = "SIH26143 Flagship Evaluation Baseline",
  defaultOpen = false,
  className,
}: ValidationAuditPanelProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  const hasGroundTruth = !!topKRecovery && topKRecovery.recovered !== null;
  const recovered = topKRecovery?.recovered ?? null;
  const confidencePct =
    topKRecovery?.confidence !== null && topKRecovery?.confidence !== undefined
      ? (topKRecovery.confidence * 100).toFixed(1)
      : null;
  const k = topKRecovery?.k ?? null;

  const StatusIcon =
    recovered === true ? CheckCircle2 : recovered === false ? XCircle : HelpCircle;
  const statusColor =
    recovered === true ? "#10B981" : recovered === false ? "#DC2626" : "#526573";

  return (
    <div className={`border-t border-[#1D2E42] bg-[#0A121C] ${className ?? ""}`}>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        aria-expanded={isOpen}
      >
        <span className="flex items-center gap-2">
          <StatusIcon
            className="h-3.5 w-3.5"
            style={{ color: statusColor }}
            strokeWidth={2}
            aria-hidden
          />
          <span className="text-[11px] font-medium uppercase tracking-[0.04em] text-[#8D9EA8] font-['IBM_Plex_Sans',_sans-serif]">
            VALIDATION AUDIT // TOP-K GROUND TRUTH RECOVERY
          </span>
        </span>
        {isOpen ? (
          <ChevronUp className="h-3.5 w-3.5 text-[#526573]" strokeWidth={2} aria-hidden />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-[#526573]" strokeWidth={2} aria-hidden />
        )}
      </button>

      {isOpen && (
        <div className="border-t border-[#1D2E42] px-3 py-2.5 text-[11px] text-[#E6EDF3] font-['IBM_Plex_Mono',_monospace]">
          {!topKRecovery ? (
            <p className="text-[#526573]">NO VALIDATION RECORD FOR THIS SCENARIO.</p>
          ) : !hasGroundTruth ? (
            <p className="text-[#526573]">
              N/A — LIVE / UNKNOWN SCENARIO, NO GROUND-TRUTH VESSEL AVAILABLE
              FOR TOP-{k ?? "K"} RECOVERY CHECK.
            </p>
          ) : (
            <>
              <p>
                <span className="text-[#8D9EA8]">RECOVERED IN TOP-{k}: </span>
                <span style={{ color: statusColor }} className="font-medium">
                  {recovered ? "YES" : "NO"}
                </span>
                {confidencePct !== null && (
                  <span className="tabular-nums text-[#8D9EA8]">
                    {" "}
                    (CONFIDENCE {confidencePct}%)
                  </span>
                )}
              </p>
              <p className="mt-1 text-[10px] text-[#526573]">
                Benchmark Reference: {benchmarkReference}
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
