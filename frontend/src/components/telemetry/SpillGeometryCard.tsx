import { useState } from "react";
import { clsx } from "clsx";
import { Copy, Check } from "lucide-react";
import type { SlickDetection } from "../../types/schemas";
import {
  formatArea,
  formatCentroid,
  formatDetectedAt,
  formatElongation,
  formatPercent,
  formatSourceSceneId,
} from "./format";

export interface SpillGeometryCardProps {
  slick: SlickDetection;
}

const THICKNESS_STYLES: Record<SlickDetection["thickness_class"], string> = {
  sheen: "border-prov-gfw text-prov-gfw",
  thin: "border-signal-attention text-signal-attention",
  thick: "border-signal-alert text-signal-alert",
};

const ELONGATION_LINEAR_THRESHOLD = 3.0;

export function SpillGeometryCard({ slick }: SpillGeometryCardProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopySpillId() {
    try {
      await navigator.clipboard.writeText(slick.spill_id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard permission denied or unavailable — fail silently, no modal.
    }
  }

  const isLinear = slick.elongation_ratio > ELONGATION_LINEAR_THRESHOLD;

  return (
    <section className="border-b border-chart-contour p-3">
      <h2 className="mb-3 text-[11px] font-medium uppercase tracking-wider text-ink-secondary">
        Incident Telemetry // SAR S-1
      </h2>

      {/* Spill ID */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="truncate font-mono text-xs text-ink-primary tabular-nums">
          {slick.spill_id}
        </span>
        <button
          type="button"
          onClick={handleCopySpillId}
          className="relative shrink-0 border border-chart-contour p-1 text-ink-tertiary hover:border-prov-gfw hover:text-prov-gfw"
          aria-label="Copy spill ID"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied && (
            <span className="absolute -top-6 right-0 whitespace-nowrap border border-chart-contour bg-chart-raised px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-prov-gfw">
              Copied
            </span>
          )}
        </button>
      </div>

      {/* Hero: oil confidence */}
      <div className="mb-3">
        <p className="mb-1 text-[10px] uppercase tracking-wider text-ink-tertiary">
          Oil Confidence
        </p>
        <p className="font-serif text-4xl leading-none text-ink-primary tabular-nums">
          {formatPercent(slick.oil_confidence)}
        </p>
        <div className="mt-2 h-[3px] w-full bg-chart-contour">
          <div
            className="h-[3px] bg-prov-gfw"
            style={{ width: `${Math.min(100, Math.max(0, slick.oil_confidence * 100))}%` }}
          />
        </div>
      </div>

      {/* Detected at */}
      <Row label="Detected">
        <span className="font-mono text-xs text-ink-primary tabular-nums">
          {formatDetectedAt(slick.detected_at)}
        </span>
      </Row>

      {/* Centroid */}
      <Row label="Centroid">
        <span className="font-mono text-xs text-ink-primary tabular-nums">
          {formatCentroid(slick.centroid)}
        </span>
      </Row>

      {/* Area */}
      <Row label="Area">
        <span className="font-mono text-xs text-ink-primary tabular-nums">
          {formatArea(slick.area_km2)}
        </span>
      </Row>

      {/* Elongation ratio + routing badge */}
      <Row label="Elongation">
        <span className="font-mono text-xs text-ink-primary tabular-nums">
          {formatElongation(slick.elongation_ratio)}
        </span>
      </Row>
      <div
        className={clsx(
          "mb-3 border px-2 py-1 text-center font-mono text-[10px] uppercase tracking-wider",
          isLinear
            ? "border-prov-gfw text-prov-gfw"
            : "border-signal-attention text-signal-attention",
        )}
      >
        {isLinear
          ? "Linear Slick // Routed for Vessel Attribution"
          : "Blob-Shaped // Seep Deprioritized"}
      </div>

      {/* Thickness class */}
      <Row label="Thickness">
        <span
          className={clsx(
            "border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider",
            THICKNESS_STYLES[slick.thickness_class],
          )}
        >
          {slick.thickness_class}
        </span>
      </Row>

      {/* Lookalike suppressed */}
      <Row label="Lookalike Suppressed">
        <span
          className={clsx(
            "font-mono text-xs tabular-nums",
            slick.lookalike_suppressed ? "text-signal-positive" : "text-ink-tertiary",
          )}
        >
          {slick.lookalike_suppressed ? "TRUE" : "FALSE"}
        </span>
      </Row>

      {/* Source scene id */}
      <Row label="Source Scene" last>
        <span className="font-mono text-xs text-ink-primary tabular-nums">
          {formatSourceSceneId(slick.source_scene_id)}
        </span>
      </Row>
    </section>
  );
}

function Row({
  label,
  children,
  last = false,
}: {
  label: string;
  children: React.ReactNode;
  last?: boolean;
}) {
  return (
    <div
      className={clsx(
        "flex items-center justify-between py-1.5",
        !last && "border-b border-chart-contour",
      )}
    >
      <span className="text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</span>
      {children}
    </div>
  );
}
