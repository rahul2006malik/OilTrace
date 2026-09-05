/**
 * MapLegend — Austere nautical chart legend (bottom-left).
 *
 * Static HTML overlay showing colour swatches for all forensic layers:
 * observed slick, origin probability contours (50/75/90%), hindcast
 * streamlines, and vessel provenance markers.
 *
 * No blur, no glow, no decorative effects — matches IHO S-52 ECDIS
 * chart legend conventions.
 */

export default function MapLegend() {
  return (
    <div className="absolute bottom-7 left-3 z-10 min-w-[180px] border border-chart-contour bg-chart-surface/95 px-3 py-2.5">
      {/* Header */}
      <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-ink-secondary">
        CHART LEGEND
      </div>

      {/* SAR Observed Slick */}
      <LegendItem>
        <SwatchRect color="#2DD4BF" opacity={0.15} borderColor="#2DD4BF" />
        <LegendLabel>SAR OBSERVED SLICK</LegendLabel>
      </LegendItem>

      {/* Origin Cone Tiers */}
      <LegendItem>
        <SwatchRect color="rgba(45,212,191,0.45)" borderColor="#2DD4BF" />
        <LegendLabel>ORIGIN 50%</LegendLabel>
      </LegendItem>
      <LegendItem>
        <SwatchRect color="rgba(45,212,191,0.22)" borderColor="#2DD4BF" />
        <LegendLabel>ORIGIN 75%</LegendLabel>
      </LegendItem>
      <LegendItem>
        <SwatchRect
          color="rgba(45,212,191,0.08)"
          borderColor="rgba(45,212,191,0.5)"
          dashed
        />
        <LegendLabel>ORIGIN 90%</LegendLabel>
      </LegendItem>

      {/* Hindcast Streamlines */}
      <LegendItem>
        <SwatchLine color="rgba(56,189,248,0.5)" />
        <LegendLabel>HINDCAST STREAMLINES</LegendLabel>
      </LegendItem>

      {/* Divider */}
      <div className="my-1.5 border-t border-chart-contour" />

      {/* Vessel Provenance Markers */}
      <LegendItem>
        <SwatchCircle color="#2DD4BF" />
        <LegendLabel>VESSEL (REAL GFW)</LegendLabel>
      </LegendItem>
      <LegendItem>
        <SwatchCircle color="#38BDF8" />
        <LegendLabel>VESSEL (AISSTREAM LIVE)</LegendLabel>
      </LegendItem>
      <LegendItem>
        <SwatchCircle color="#927B56" />
        <LegendLabel>VESSEL (SYNTHETIC)</LegendLabel>
      </LegendItem>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LegendItem({ children }: { children: React.ReactNode }) {
  return <div className="flex items-center gap-2 py-[2px]">{children}</div>;
}

function LegendLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10px] text-ink-secondary">{children}</span>
  );
}

function SwatchRect({
  color,
  borderColor,
  opacity,
  dashed,
}: {
  color: string;
  borderColor: string;
  opacity?: number;
  dashed?: boolean;
}) {
  return (
    <span
      className="inline-block h-[10px] w-[16px] shrink-0"
      style={{
        backgroundColor: color,
        opacity: opacity ?? 1,
        border: `1px ${dashed ? "dashed" : "solid"} ${borderColor}`,
      }}
    />
  );
}

function SwatchLine({ color }: { color: string }) {
  return (
    <span className="inline-flex h-[10px] w-[16px] shrink-0 items-center">
      <span
        className="h-[1.5px] w-full"
        style={{ backgroundColor: color }}
      />
    </span>
  );
}

function SwatchCircle({ color }: { color: string }) {
  return (
    <span
      className="inline-block h-[8px] w-[8px] shrink-0 rounded-full"
      style={{
        backgroundColor: `${color}33`,
        border: `2px solid ${color}`,
      }}
    />
  );
}
