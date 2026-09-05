import type { EvidenceTrace } from "../../types/schemas";

interface FactorDef {
  key: keyof Pick<
    EvidenceTrace,
    "proximity_score" | "confession_match_score" | "anomaly_score" | "vessel_type_prior"
  >;
  dominantKey: string;
  label: string;
  formulaSymbol: string;
  note: (value: number) => string;
}

const FACTORS: FactorDef[] = [
  {
    key: "proximity_score",
    dominantKey: "proximity",
    label: "Distance from Origin Zone",
    formulaSymbol: "s_prox",
    note: (v) =>
      v >= 0.85
        ? "Candidate coordinates intersect the 50% KDE origin probability cone."
        : v >= 0.55
        ? "Candidate coordinates fall within the 75% KDE origin probability band."
        : "Candidate coordinates lie outside the primary drift-origin cone.",
  },
  {
    key: "confession_match_score",
    dominantKey: "confession_match",
    label: "Forward-Simulation Match (IoU)",
    formulaSymbol: "s_conf",
    note: (v) =>
      `Simulated oil dispersion overlaps the observed SAR slick shape at IoU = ${v.toFixed(2)}.`,
  },
  {
    key: "anomaly_score",
    dominantKey: "anomaly",
    label: "AIS Behavior Anomaly (Isolation Forest)",
    formulaSymbol: "s_anom",
    note: (v) =>
      v >= 0.7
        ? "AIS blackout gap detected inside the drift window; flagged as a high-severity isolation-forest outlier."
        : v >= 0.4
        ? "Irregular AIS transmission cadence detected inside the drift window."
        : "AIS transmission pattern is consistent with normal transit behavior.",
  },
  {
    key: "vessel_type_prior",
    dominantKey: "vessel_type_prior",
    label: "Vessel-Type Likelihood Prior",
    formulaSymbol: "s_prior",
    note: (v) =>
      v === null
        ? "No vessel-type classification available for this candidate."
        : v >= 0.75
        ? "Registry classifies this hull as a Crude Oil Tanker — high risk profile."
        : v >= 0.45
        ? "Registry classifies this hull as a moderate spill-risk vessel type."
        : "Registry classifies this hull as a low spill-risk vessel type.",
  },
];

function barColor(value: number, isDominant: boolean): string {
  if (isDominant) return "bg-signal-attention";
  if (value >= 0.7) return "bg-prov-gfw";
  if (value >= 0.4) return "bg-ink-secondary";
  return "bg-chart-accent";
}

export default function ComponentScoreBars({ evidence }: { evidence: EvidenceTrace }) {
  const dominant = FACTORS.find((f) => f.dominantKey === evidence.dominant_factor);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h3 className="text-2xs uppercase tracking-wider text-ink-secondary">
          Evidence Breakdown &amp; XAI
        </h3>
        <span className="text-2xs text-ink-tertiary font-mono">unweighted, 0.00&ndash;1.00</span>
      </div>

      <div className="flex flex-col gap-2.5">
        {FACTORS.map((factor) => {
          const raw = evidence[factor.key];
          const value = raw === null || raw === undefined ? 0 : raw;
          const isDominant = factor.dominantKey === evidence.dominant_factor;
          const isUnavailable = raw === null || raw === undefined;

          return (
            <div key={factor.key} className="relative">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  {isDominant && (
                    <span
                      aria-hidden
                      className="inline-block w-0 h-0 border-l-[5px] border-l-transparent border-r-[5px] border-r-transparent border-t-[6px] border-t-signal-attention"
                    />
                  )}
                  <span className="text-[13px] text-ink-primary leading-none">{factor.label}</span>
                </div>
                <span
                  className={`font-mono text-[13px] tabular-figures ${
                    isUnavailable ? "text-ink-tertiary" : "text-ink-primary"
                  }`}
                >
                  {isUnavailable ? "n/a" : value.toFixed(3)}
                </span>
              </div>

              <div className="h-[6px] w-full bg-chart-raised border border-chart-contour">
                <div
                  className={`h-full ${barColor(value, isDominant)}`}
                  style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
                />
              </div>

              <p className="mt-1 text-2xs text-ink-tertiary leading-snug">{factor.note(value)}</p>
            </div>
          );
        })}
      </div>

      {dominant && (
        <div className="mt-1 flex items-start gap-2 border border-signal-attention/40 bg-signal-attention/10 px-2.5 py-2">
          <span className="mt-[3px] inline-block w-1.5 h-1.5 bg-signal-attention flex-shrink-0" />
          <p className="text-2xs text-signal-attention uppercase tracking-wide leading-snug font-mono">
            Dominant evidence: {dominant.label.toUpperCase()} (
            {dominant.key === "vessel_type_prior"
              ? "prior"
              : dominant.formulaSymbol.split("_")[1] === "conf"
              ? "IoU"
              : dominant.formulaSymbol}
            {" = "}
            {(evidence[dominant.key] ?? 0).toFixed(2)})
          </p>
        </div>
      )}
    </div>
  );
}
