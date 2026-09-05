/**
 * DarkVesselBanner.tsx
 *
 * Tactical alert strip shown when no broadcasting AIS vessel adequately
 * explains the observed slick. Deliberately static: no pulsing, no flashing
 * background, no siren iconography. It reads like a naval intelligence
 * notice, not a consumer alert toast.
 *
 * Trigger condition (per spec): `attributionData.dark_vessel_alert === true`
 * OR the highest candidate suspicion score is below the attribution
 * threshold (0.40). Both conditions are evaluated here rather than trusting
 * the backend flag alone, so the banner stays correct even if the backend
 * forgets to set `dark_vessel_alert` for a borderline scenario.
 *
 * The "MAX P" figure in the copy is computed live from `candidates[]`
 * rather than hardcoded, so the banner never states a stale or
 * demo-only number — consistent with the app's "never perform false
 * certainty" mandate.
 */
import { useMemo } from "react";
import { ShieldAlert } from "lucide-react";
import type { AttributionResult } from "../../types/schemas";

const ATTRIBUTION_THRESHOLD = 0.4;

export interface DarkVesselBannerProps {
  attributionData: AttributionResult | null | undefined;
  className?: string;
}

function formatProbability(score: number): string {
  return score.toFixed(3);
}

export default function DarkVesselBanner({
  attributionData,
  className,
}: DarkVesselBannerProps) {
  const { isTriggered, maxScore } = useMemo(() => {
    if (!attributionData) {
      return { isTriggered: false, maxScore: null as number | null };
    }

    const scored = attributionData.candidates
      .map((c) => c.suspicion_score)
      .filter((s): s is number => typeof s === "number");

    const max = scored.length > 0 ? Math.max(...scored) : null;
    const belowThreshold = max !== null && max < ATTRIBUTION_THRESHOLD;

    return {
      isTriggered: attributionData.dark_vessel_alert || belowThreshold,
      maxScore: max,
    };
  }, [attributionData]);

  if (!isTriggered) return null;

  const maxLabel = maxScore !== null ? formatProbability(maxScore) : "N/A";

  const fullText = `DARK VESSEL NOTICE // NO BROADCASTING AIS VESSEL EXPLAINS THIS SLICK (MAX P = ${maxLabel}). AIS TRANSMITTER WAS POWERED OFF OR DELIBERATELY SPOOFED. CANDIDATES BELOW SCORED UNDER ATTRIBUTION THRESHOLD AND ARE RETAINED FOR FORENSIC LOGGING.`;

  return (
    <div
      role="status"
      aria-live="polite"
      title={fullText}
      className={`flex h-9 min-h-[36px] w-full items-center gap-2.5 border border-[#DC2626] bg-[#150D0E] px-4 ${
        className ?? ""
      }`}
    >
      <ShieldAlert
        className="h-3.5 w-3.5 flex-shrink-0 text-[#DC2626]"
        strokeWidth={2}
        aria-hidden
      />
      <p className="truncate whitespace-nowrap text-[11px] font-medium uppercase tracking-[0.02em] text-[#E6EDF3] font-['IBM_Plex_Sans',_sans-serif]">
        <span className="font-semibold text-[#DC2626]">DARK VESSEL NOTICE // </span>
        NO BROADCASTING AIS VESSEL EXPLAINS THIS SLICK (MAX P ={" "}
        <span className="tabular-nums text-[#E6EDF3] font-['IBM_Plex_Mono',_monospace]">
          {maxLabel}
        </span>
        ). AIS TRANSMITTER WAS POWERED OFF OR DELIBERATELY SPOOFED. CANDIDATES
        BELOW SCORED UNDER ATTRIBUTION THRESHOLD AND ARE RETAINED FOR FORENSIC
        LOGGING.
      </p>
    </div>
  );
}
