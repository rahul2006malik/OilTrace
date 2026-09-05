import { useState } from "react";
import { Info, RotateCcw } from "lucide-react";
import type { EvidenceTrace, SandboxWeights } from "../../types/schemas";
import { computeSandboxScore, SANDBOX_TEMPERATURE, weightsSumTo1 } from "./sandboxMath";
import { DEFAULT_SANDBOX_WEIGHTS } from "../../context/ScenarioContext";

interface SliderDef {
  key: keyof SandboxWeights;
  symbol: string;
  label: string;
}

const SLIDERS: SliderDef[] = [
  { key: "proximity", symbol: "w1", label: "Proximity Weight" },
  { key: "confession_match", symbol: "w2", label: "Confession Match Weight" },
  { key: "anomaly", symbol: "w3", label: "Anomaly Weight" },
  { key: "vessel_type_prior", symbol: "w4", label: "Vessel Prior Weight" },
];

export default function WeightSandbox({
  evidence,
  backendScore,
  weights,
  onWeightsChange,
}: {
  evidence: EvidenceTrace;
  /** `candidate.suspicion_score` from the backend attribution record, 0–1. */
  backendScore: number | null;
  weights: SandboxWeights;
  onWeightsChange: (weights: SandboxWeights) => void;
}) {
  const [showInfo, setShowInfo] = useState(false);

  const sandboxScore = computeSandboxScore(evidence, weights);
  const isDefault =
    JSON.stringify(weights) === JSON.stringify(DEFAULT_SANDBOX_WEIGHTS);
  const sumOk = weightsSumTo1(weights);

  function updateWeight(key: keyof SandboxWeights, value: number) {
    onWeightsChange({ ...weights, [key]: value });
  }

  function reset() {
    onWeightsChange(DEFAULT_SANDBOX_WEIGHTS);
  }

  return (
    <div className="border-t border-chart-contour pt-3 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <h3 className="text-2xs uppercase tracking-wider text-ink-secondary">
            Sensitivity Re-Weighting Sandbox
          </h3>
          <button
            type="button"
            onClick={() => setShowInfo((s) => !s)}
            aria-label="About the sensitivity sandbox"
            className="w-3.5 h-3.5 flex items-center justify-center border border-chart-contour text-ink-tertiary hover:text-ink-primary hover:border-ink-tertiary"
          >
            <Info size={9} strokeWidth={2.5} />
          </button>
        </div>
        <button
          type="button"
          onClick={reset}
          disabled={isDefault}
          className="flex items-center gap-1 text-2xs font-mono text-ink-secondary hover:text-ink-primary disabled:opacity-30 disabled:hover:text-ink-secondary px-1.5 py-0.5 border border-chart-contour"
        >
          <RotateCcw size={10} />
          RESET TO DEFAULTS
        </button>
      </div>

      <div className="text-2xs text-signal-attention/90 font-mono border border-signal-attention/30 bg-signal-attention/[0.06] px-2 py-1.5 leading-snug">
        EXPLORATORY SIMULATION // CLIENT-SIDE RECALCULATION (DOES NOT ALTER BACKEND FINDING)
      </div>

      {showInfo && (
        <div className="text-2xs text-ink-secondary leading-relaxed border border-chart-contour bg-chart-raised px-2.5 py-2">
          Drag the four weights to test how sensitive this candidate's suspicion score
          is to the relative importance placed on each evidence factor. Nothing here is
          written back to the case record — the backend score to the left of the arrow
          is the finding of record.
        </div>
      )}

      <div className="flex flex-col gap-2.5">
        {SLIDERS.map((slider) => {
          const value = weights[slider.key];
          return (
            <div key={slider.key}>
              <div className="flex items-center justify-between mb-1">
                <label htmlFor={`weight-${slider.key}`} className="text-[13px] text-ink-primary">
                  <span className="font-mono text-ink-tertiary mr-1.5">{slider.symbol}</span>
                  {slider.label}
                </label>
                <span className="font-mono text-[13px] text-ink-primary tabular-figures">
                  {value.toFixed(2)}
                </span>
              </div>
              <input
                id={`weight-${slider.key}`}
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={value}
                onChange={(e) => updateWeight(slider.key, parseFloat(e.target.value))}
                className="w-full h-[3px] appearance-none bg-chart-contour accent-prov-gfw cursor-pointer"
              />
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between text-2xs font-mono">
        <span className={sumOk ? "text-ink-tertiary" : "text-signal-attention"}>
          &Sigma;w = {(weights.proximity + weights.confession_match + weights.anomaly + weights.vessel_type_prior).toFixed(2)}
          {!sumOk && "  (unnormalized)"}
        </span>
      </div>

      <div className="border border-chart-contour bg-chart-raised px-2.5 py-2 flex flex-col gap-1.5">
        <p className="text-2xs text-ink-tertiary leading-relaxed">
          Suspicion = &sigma;( (w1&middot;s_prox + w2&middot;s_conf + w3&middot;s_anom + w4&middot;s_prior
          &minus; 0.5) / T ),&nbsp; T = {SANDBOX_TEMPERATURE.toFixed(2)}
        </p>
        <div className="flex items-baseline gap-2 font-mono">
          <span className="text-[15px] text-ink-secondary tabular-figures">
            {backendScore === null ? "n/a" : `${(backendScore * 100).toFixed(1)}%`}
          </span>
          <span className="text-ink-tertiary text-[13px]">&rarr;</span>
          <span className="text-[15px] text-signal-attention tabular-figures">
            {(sandboxScore * 100).toFixed(1)}%
          </span>
          <span className="text-2xs text-ink-tertiary uppercase tracking-wide">(Sandbox)</span>
        </div>
      </div>
    </div>
  );
}
