import type { DataProvenance } from "../../types/schemas";

/**
 * ProvenanceBadge — the non-negotiable "aggressive ambient provenance"
 * indicator (Design Spec §0.2 / §1.1). Every candidate row and the vessel
 * identity modal must carry one of these; there is no "unmarked" state.
 *
 * Colors are pulled directly from the ECDIS token set (`--prov-gfw`,
 * `--prov-aisstream`, `--prov-synthetic`) — never re-derive a color here.
 */

interface ProvenanceBadgeProps {
  provenance: DataProvenance;
  /** Compact mode drops to a single-letter chip for tight table cells. */
  compact?: boolean;
  className?: string;
}

interface ProvenanceConfig {
  label: string;
  compactLabel: string;
  textClass: string;
  borderClass: string;
  bgClass: string;
}

const PROVENANCE_CONFIG: Record<DataProvenance, ProvenanceConfig> = {
  real_gfw: {
    label: "REAL GFW",
    compactLabel: "GFW",
    textClass: "text-prov-gfw",
    borderClass: "border-prov-gfw/40",
    bgClass: "bg-prov-gfw/10",
  },
  real_aisstream_live: {
    label: "AISSTREAM LIVE",
    compactLabel: "AIS-L",
    textClass: "text-prov-aisstream",
    borderClass: "border-prov-aisstream/40",
    bgClass: "bg-prov-aisstream/10",
  },
  synthetic_fallback: {
    label: "SYNTHETIC",
    compactLabel: "SYN",
    textClass: "text-prov-synthetic",
    borderClass: "border-prov-synthetic/40",
    bgClass: "bg-prov-synthetic/10",
  },
};

export function ProvenanceBadge({ provenance, compact = false, className = "" }: ProvenanceBadgeProps) {
  const cfg = PROVENANCE_CONFIG[provenance];

  return (
    <span
      className={[
        "inline-flex items-center whitespace-nowrap rounded-sm border px-1.5 py-[3px]",
        "font-mono text-[10px] font-medium leading-none tracking-wider",
        cfg.borderClass,
        cfg.bgClass,
        cfg.textClass,
        className,
      ].join(" ")}
      title={cfg.label}
    >
      {compact ? cfg.compactLabel : cfg.label}
    </span>
  );
}

export default ProvenanceBadge;
