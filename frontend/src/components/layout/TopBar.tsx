import React, { useEffect, useMemo, useState } from "react";
import { ChevronDown, Printer } from "lucide-react";
import { useScenario } from "../../context/ScenarioContext";
import type { ScenarioSummary } from "../../types/schemas";
import LiveAisMonitor from "../operations/LiveAisMonitor";

function useUtcClock(): string {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const hh = String(now.getUTCHours()).padStart(2, "0");
  const mm = String(now.getUTCMinutes()).padStart(2, "0");
  const ss = String(now.getUTCSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss} UTC`;
}

interface ProvenanceTallyProps {
  real: number;
  total: number;
}

function ProvenanceTally({ real, total }: ProvenanceTallyProps) {
  const allReal = total > 0 && real === total;
  const dotColor = total === 0 ? "bg-ink-tertiary" : allReal ? "bg-prov-gfw" : "bg-signal-attention";
  const textColor = total === 0 ? "text-ink-tertiary" : allReal ? "text-prov-gfw" : "text-signal-attention";

  return (
    <div
      className="flex items-center gap-2 border border-chart-contour px-2 py-1"
      title="Share of candidates backed by real GFW / AISstream data, not synthetic fallback"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
      <span className={`font-mono text-[11px] tabular-nums ${textColor}`}>
        {total === 0 ? "NO CANDIDATES" : `${real}/${total} REAL`}
      </span>
    </div>
  );
}

interface BackendStatusProps {
  operational: boolean;
}

function BackendStatus({ operational }: BackendStatusProps) {
  return (
    <div className="flex items-center gap-2 border border-chart-contour px-2 py-1">
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          operational ? "bg-signal-positive" : "bg-signal-alert"
        }`}
      />
      <span className="font-mono text-[11px] text-ink-secondary">
        {operational ? "SYS OPERATIONAL // S1+DRIFT+ATTR" : "SYS DEGRADED // CHECK BACKEND"}
      </span>
    </div>
  );
}

interface ScenarioSelectorProps {
  scenarios: ScenarioSummary[];
  current: ScenarioSummary | null;
  onSelect: (scenario: ScenarioSummary) => void;
}

function ScenarioSelector({ scenarios, current, onSelect }: ScenarioSelectorProps) {
  return (
    <div className="relative flex items-center">
      <select
        className="appearance-none border border-chart-contour bg-chart-surface px-2 py-1 pr-6 font-mono text-[11px] text-ink-primary outline-none hover:bg-chart-hover focus-visible:outline-none"
        value={current?.scenario_id ?? ""}
        onChange={(event) => {
          const next = scenarios.find((s) => s.scenario_id === event.target.value);
          if (next) onSelect(next);
        }}
      >
        {scenarios.length === 0 && <option value="">NO SCENARIOS LOADED</option>}
        {scenarios.map((scenario) => (
          <option key={scenario.scenario_id} value={scenario.scenario_id}>
            {scenario.name.toUpperCase()}
          </option>
        ))}
      </select>
      <ChevronDown size={12} className="pointer-events-none absolute right-2 text-ink-tertiary" />
    </div>
  );
}

interface TopBarProps {
  scenarios?: ScenarioSummary[];
  backendOperational?: boolean;
  onScenarioSelect?: (scenario: ScenarioSummary) => void;
  onPrintDossier?: () => void;
}

export default function TopBar({
  scenarios = [],
  backendOperational = false,
  onScenarioSelect,
  onPrintDossier,
}: TopBarProps) {
  const { currentScenario, setCurrentScenario, attributionData } = useScenario();
  const clock = useUtcClock();

  const provenanceCounts = useMemo(() => {
    const candidates = attributionData?.candidates ?? [];
    const real = candidates.filter((c) => c.data_provenance !== "synthetic_fallback").length;
    return { real, total: candidates.length };
  }, [attributionData]);

  const handleSelect = (scenario: ScenarioSummary) => {
    setCurrentScenario(scenario);
    onScenarioSelect?.(scenario);
  };

  return (
    <header className="flex h-12 min-h-[48px] items-center justify-between border-b border-chart-contour bg-chart-surface px-3">
      <div className="flex items-center gap-4">
        <span className="font-serif text-[15px] font-medium tracking-tight text-ink-primary">
          OILTRACE <span className="text-ink-tertiary">// NTRO MDA</span>
        </span>
        <ScenarioSelector
          scenarios={scenarios}
          current={currentScenario}
          onSelect={handleSelect}
        />
      </div>

      <div className="flex items-center gap-3">
        <LiveAisMonitor />
        <ProvenanceTally real={provenanceCounts.real} total={provenanceCounts.total} />
        <BackendStatus operational={backendOperational} />
        <span className="font-mono text-[11px] tabular-nums text-ink-secondary">{clock}</span>
        <button
          type="button"
          onClick={onPrintDossier}
          className="flex items-center gap-1.5 border border-chart-contour px-2 py-1 font-mono text-[11px] text-ink-secondary hover:bg-chart-hover hover:text-ink-primary"
          title="Print dossier PDF"
        >
          <Printer size={12} />
          DOSSIER
        </button>
      </div>
    </header>
  );
}
