/**
 * Sensitivity sandbox scoring — the single source of truth for the
 * client-side re-weighting formula:
 *
 *   Suspicion = σ( (w1·s_prox + w2·s_conf + w3·s_anom + w4·s_prior) / T )
 *
 * Exported (not just used internally) so `<SuspectLeaderboard />`
 * can import the exact same function to recompute every candidate's
 * exploratory score and re-sort in lockstep with the sliders in
 * `<WeightSandbox />`. Keeping one implementation here avoids two
 * components drifting out of sync on the math.
 */
import type { EvidenceTrace, SandboxWeights } from "../../types/schemas";

/**
 * Calibration temperature. The raw weighted sum lands in [0, 1] with
 * defaults (0.25 each); a plain σ(x) with x in that range only ever
 * covers the flat middle of the sigmoid (0.5–0.73) and never reads as
 * "confident" or "cleared" the way the backend's own logistic scorer
 * does. To span the full 0–1 dial the same way the backend does, the
 * weighted sum is first centered on the panel's calibration midpoint
 * (0.5) and then scaled by T before the sigmoid — this constant is
 * displayed in the UI next to the formula so nothing here is hidden
 * from an analyst reading the sandbox output.
 */
export const SANDBOX_TEMPERATURE = 0.15;
export const SANDBOX_MIDPOINT = 0.5;

export function sigmoid(z: number): number {
  return 1 / (1 + Math.exp(-z));
}

/** Weighted linear combination of the four unweighted forensic factors. */
export function weightedSum(evidence: EvidenceTrace, weights: SandboxWeights): number {
  const prior = evidence.vessel_type_prior ?? 0;
  return (
    weights.proximity * evidence.proximity_score +
    weights.confession_match * evidence.confession_match_score +
    weights.anomaly * evidence.anomaly_score +
    weights.vessel_type_prior * prior
  );
}

/**
 * Full client-side exploratory suspicion score, in [0, 1]. This never
 * touches or overwrites `candidate.suspicion_score` — it is purely a
 * browser-side "what if these weights were different" projection.
 */
export function computeSandboxScore(
  evidence: EvidenceTrace,
  weights: SandboxWeights,
  temperature: number = SANDBOX_TEMPERATURE
): number {
  const sum = weightedSum(evidence, weights);
  const z = (sum - SANDBOX_MIDPOINT) / temperature;
  return sigmoid(z);
}

export function weightsSumTo1(weights: SandboxWeights, epsilon = 0.005): boolean {
  const total =
    weights.proximity + weights.confession_match + weights.anomaly + weights.vessel_type_prior;
  return Math.abs(total - 1) <= epsilon;
}
