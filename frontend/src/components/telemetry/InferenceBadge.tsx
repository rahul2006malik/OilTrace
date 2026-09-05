import { clsx } from "clsx";

export interface InferenceBadgeProps {
  /** Wall-clock inference time in seconds, from `execution_time_seconds`. */
  executionTimeSeconds: number;
  /** e.g. "CPU" or "GPU" — surfaced so the number can't be misread as GPU-fast. */
  device?: "CPU" | "GPU";
  /** The cascade architecture label. Override only if the backend changes stages. */
  cascadeLabel?: string;
  className?: string;
}

/**
 * A single-line, read-only telemetry strip:
 *   INFERENCE: 3.27s (CPU) · 2-STAGE CASCADE: RESNET-34 + WIDE U-NET
 *
 * No spinner, no glow — this renders once the result has already landed,
 * as a fact, not a status animation.
 */
export function InferenceBadge({
  executionTimeSeconds,
  device = "CPU",
  cascadeLabel = "2-STAGE CASCADE: RESNET-34 + WIDE U-NET",
  className,
}: InferenceBadgeProps) {
  return (
    <div
      className={clsx(
        "border border-chart-contour bg-chart-raised px-3 py-2",
        "flex items-center gap-2",
        className,
      )}
    >
      <span className="h-1.5 w-1.5 shrink-0 bg-signal-positive" aria-hidden="true" />
      <p className="font-mono text-[11px] tracking-wide text-ink-secondary tabular-nums">
        <span className="text-ink-primary">
          INFERENCE: {executionTimeSeconds.toFixed(2)}s ({device})
        </span>
        <span className="mx-1.5 text-ink-tertiary">·</span>
        {cascadeLabel}
      </p>
    </div>
  );
}
