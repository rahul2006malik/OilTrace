import type { AgeEstimateHours } from "../../types/schemas";

interface VectorReading {
  speedMs: number;
  bearingDeg: number;
  source: string;
}

export interface MetoceanTelemetryCardProps {
  ageEstimateHours: AgeEstimateHours;
  ensembleMemberCount?: number;
  /**
   * `schemas.ts` OriginEnsemble carries no current/wind vector fields today —
   * these forcing readouts aren't yet part of the Section 2 contract. Callers
   * should pass real GLORYS/ERA5 values once the backend exposes them; the
   * defaults below are the flagship-scenario figures from the design spec so
   * the card renders correctly for the demo scenario out of the box.
   */
  current?: VectorReading;
  wind?: VectorReading;
  physicsLabel?: string;
}

const DEFAULT_CURRENT: VectorReading = {
  speedMs: 0.42,
  bearingDeg: 78,
  source: "Copernicus GLORYS Daily NetCDF",
};

const DEFAULT_WIND: VectorReading = {
  speedMs: 8.5,
  bearingDeg: 245,
  source: "ECMWF ERA5 10m Vectors",
};

export function MetoceanTelemetryCard({
  ageEstimateHours,
  ensembleMemberCount = 25,
  current = DEFAULT_CURRENT,
  wind = DEFAULT_WIND,
  physicsLabel = "OpenDrift 1.14.11 // Runge-Kutta 4th Order",
}: MetoceanTelemetryCardProps) {
  const [ciLow, ciHigh] = ageEstimateHours.confidence_range;

  return (
    <section className="border-b border-chart-contour p-3">
      <h2 className="mb-3 text-[11px] font-medium uppercase tracking-wider text-ink-secondary">
        Metocean Forcing &amp; Age Estimate
      </h2>

      <VectorRow label="Ocean Surface Currents" reading={current} />
      <VectorRow label="10m Atmospheric Wind" reading={wind} />

      <div className="flex items-center justify-between border-b border-chart-contour py-1.5">
        <span className="text-[10px] uppercase tracking-wider text-ink-tertiary">
          Hindcast Age Window
        </span>
        <span className="font-mono text-xs text-ink-primary tabular-nums">
          ~{ageEstimateHours.value.toFixed(0)}h ({ciLow.toFixed(0)}h — {ciHigh.toFixed(0)}h 90% CI)
        </span>
      </div>

      <div className="flex items-center justify-between py-1.5">
        <span className="text-[10px] uppercase tracking-wider text-ink-tertiary">
          Hindcast Physics
        </span>
        <span className="text-right font-mono text-[11px] text-ink-secondary tabular-nums">
          {physicsLabel} // {ensembleMemberCount} Members
        </span>
      </div>
    </section>
  );
}

function VectorRow({ label, reading }: { label: string; reading: VectorReading }) {
  return (
    <div className="border-b border-chart-contour py-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</span>
        <span className="font-mono text-xs text-ink-primary tabular-nums">
          {reading.speedMs.toFixed(2)} m/s @ {String(Math.round(reading.bearingDeg)).padStart(3, "0")}°
        </span>
      </div>
      <p className="mt-0.5 text-right text-[10px] text-ink-tertiary">{reading.source}</p>
    </div>
  );
}
