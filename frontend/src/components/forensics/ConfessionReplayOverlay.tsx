import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import type { ForwardHypothesis } from "../../types/schemas";

function matchLabel(iou: number): { text: string; tone: string } {
  if (iou >= 0.6) return { text: "STRONG MATCH", tone: "text-signal-positive" };
  if (iou >= 0.35) return { text: "PARTIAL MATCH", tone: "text-signal-attention" };
  return { text: "WEAK MATCH", tone: "text-ink-tertiary" };
}

export default function ConfessionReplayOverlay({
  hypothesis,
  confessionMatchScore,
  onToggleReplay,
}: {
  /** The candidate's forward-drift simulation, if the drift engine produced one. */
  hypothesis: ForwardHypothesis | null;
  /** `evidence_trace.confession_match_score` — shown alongside for cross-check. */
  confessionMatchScore: number;
  /** Notifies the map (`ConfessionFootprintLayer`) to show/hide the overlay. */
  onToggleReplay?: (visible: boolean) => void;
}) {
  const [visible, setVisible] = useState(false);

  function toggle() {
    const next = !visible;
    setVisible(next);
    onToggleReplay?.(next);
  }

  if (!hypothesis) {
    return (
      <div className="border-t border-chart-contour pt-3">
        <h3 className="text-2xs uppercase tracking-wider text-ink-secondary mb-1.5">
          Forward Confession Replay
        </h3>
        <p className="text-2xs text-ink-tertiary leading-snug">
          No forward-drift simulation is available for this candidate. The dispersion
          model was not run from this vessel's last known position, or it fell outside
          the 48h hindcast window.
        </p>
      </div>
    );
  }

  const iou = hypothesis.shape_overlap_score;
  const match = matchLabel(iou);
  const scoresDiverge = Math.abs(iou - confessionMatchScore) > 0.03;

  return (
    <div className="border-t border-chart-contour pt-3 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-2xs uppercase tracking-wider text-ink-secondary">
          Forward Confession Replay
        </h3>
        <button
          type="button"
          onClick={toggle}
          className="flex items-center gap-1 text-2xs font-mono text-ink-secondary hover:text-ink-primary px-1.5 py-0.5 border border-chart-contour"
        >
          {visible ? <EyeOff size={10} /> : <Eye size={10} />}
          {visible ? "HIDE ON CHART" : "SHOW ON CHART"}
        </button>
      </div>

      <p className="text-2xs text-ink-tertiary leading-snug">
        Simulated dispersion from vessel <span className="font-mono text-ink-secondary">{hypothesis.vessel_id}</span>{" "}
        run forward through the hindcast, compared against the observed SAR slick footprint.
      </p>

      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-[13px] text-ink-primary">Simulated / Observed Overlap (IoU)</span>
          <span className="font-mono text-[13px] text-ink-primary tabular-figures">{iou.toFixed(3)}</span>
        </div>
        <div className="h-[6px] w-full bg-chart-raised border border-chart-contour">
          <div
            className="h-full bg-prov-aisstream"
            style={{ width: `${Math.max(0, Math.min(1, iou)) * 100}%` }}
          />
        </div>
      </div>

      <div className="flex items-center justify-between">
        <span className={`text-2xs font-mono uppercase tracking-wide ${match.tone}`}>
          {match.text}
        </span>
        <span className="text-2xs font-mono text-ink-tertiary">
          IoU MATCH: {(iou * 100).toFixed(0)}%
        </span>
      </div>

      {scoresDiverge && (
        <p className="text-2xs text-ink-tertiary leading-snug border-l-2 border-chart-contour pl-2">
          Note: the attribution engine's stored confession-match score (
          {confessionMatchScore.toFixed(3)}) differs from this replay's IoU (
          {iou.toFixed(3)}). The stored score may use a centroid-distance + area-ratio
          fallback rather than a full raster IoU — see schema note on{" "}
          <code className="font-mono">shape_overlap_score</code>.
        </p>
      )}
    </div>
  );
}
