import React, { useEffect, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import TopBar from "./components/layout/TopBar";
import ChartCanvas from "./components/map/ChartCanvas";
import { SpillTelemetryPanel } from "./components/telemetry/SpillTelemetryPanel";
import { SuspectLeaderboard } from "./components/leaderboard/SuspectLeaderboard";
import EvidenceTraceCard from "./components/forensics/EvidenceTraceCard";
import DarkVesselBanner from "./components/operations/DarkVesselBanner";
import ValidationAuditPanel from "./components/operations/ValidationAuditPanel";
import PrintDossierView from "./components/operations/PrintDossierView";
import { ScenarioProvider, useScenario } from "./context/ScenarioContext";
import { fetchHealth, fetchScenarios, fetchScenarioData } from "./api/client";
import type { ScenarioSummary } from "./types/schemas";



function ErrorToast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="absolute bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 border border-signal-alert bg-chart-surface px-3 py-2 shadow-lg">
      <AlertTriangle size={14} className="text-signal-alert" />
      <span className="font-mono text-[11px] text-ink-primary">{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        className="ml-2 font-mono text-[11px] text-ink-tertiary hover:text-ink-primary"
      >
        DISMISS
      </button>
    </div>
  );
}

function LoadingOverlay() {
  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center bg-chart-abyss/70">
      <div className="flex items-center gap-2 border border-chart-contour bg-chart-surface px-3 py-2">
        <Loader2 size={14} className="animate-spin text-ink-secondary" />
        <span className="font-mono text-[11px] text-ink-secondary">LOADING SCENARIO DATA</span>
      </div>
    </div>
  );
}

function AppShell() {
  const {
    currentScenario,
    slickData,
    originConeData,
    attributionData,
    isLoading,
    errorMessage,
    setErrorMessage,
    setCurrentScenario,
    setOriginConeData,
    setTrajectoriesData,
    setSlickData,
    setAttributionData,
  } = useScenario();
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [backendOperational, setBackendOperational] = useState(false);

  useEffect(() => {
    let cancelled = false;

    fetchHealth()
      .then(() => {
        if (!cancelled) setBackendOperational(true);
      })
      .catch(() => {
        if (!cancelled) setBackendOperational(false);
      });

    fetchScenarios()
      .then((list) => {
        if (cancelled) return;
        setScenarios(list);
        if (list.length > 0) setCurrentScenario(list[0]);
      })
      .catch(() => {
        if (!cancelled) setErrorMessage("Unable to load scenario list.");
      });

    return () => {
      cancelled = true;
    };
  }, [setCurrentScenario, setErrorMessage]);

  useEffect(() => {
    if (!currentScenario) return;
    let cancelled = false;

    fetchScenarioData(currentScenario.scenario_id)
      .then((data: any) => {
        if (cancelled) return;
        if (data.origin_ensemble) setOriginConeData(data.origin_ensemble);
        if (data.trajectories) setTrajectoriesData(data.trajectories);
        if (data.slick) setSlickData(data.slick);
        if (data.attribution) setAttributionData(data.attribution);
      })
      .catch((err) => {
        console.warn("Could not pre-load scenario data:", err);
      });

    return () => {
      cancelled = true;
    };
  }, [currentScenario, setOriginConeData, setTrajectoriesData, setSlickData, setAttributionData]);

  const handlePrintDossier = () => {
    window.print();
  };

  return (
    <div className="relative flex h-screen w-screen flex-col overflow-hidden bg-chart-abyss">
      <TopBar
        scenarios={scenarios}
        backendOperational={backendOperational}
        onPrintDossier={handlePrintDossier}
      />

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-[22%] min-w-[280px] max-w-[340px] shrink-0 border-r border-chart-contour bg-chart-surface">
          <SpillTelemetryPanel />
        </aside>

        <main className="relative flex-1 bg-chart-abyss">
          <ChartCanvas />
        </main>

        <aside className="flex w-[26%] min-w-[340px] max-w-[420px] shrink-0 flex-col border-l border-chart-contour bg-chart-surface">
          <div className="h-1/2 border-b border-chart-contour">
            <SuspectLeaderboard />
          </div>
          <div className="h-1/2 overflow-hidden">
            <EvidenceTraceCard />
          </div>
        </aside>
      </div>

      {/* Dark Vessel Alert Banner */}
      <DarkVesselBanner attributionData={attributionData} />

      {/* Validation Ground Truth Audit Drawer */}
      <ValidationAuditPanel topKRecovery={attributionData?.top_k_recovery} />

      {/* Courtroom Evidentiary Dossier Print-Only View */}
      {currentScenario && slickData && originConeData && attributionData && (
        <PrintDossierView
          scenario={currentScenario}
          slick={slickData}
          origin={originConeData}
          attribution={attributionData}
          caseId={`CASE-${currentScenario.spill_id || slickData.spill_id}`}
          checksum="a7f8c4e3b290184d856291a03f8e5c1d"
          generatedAt={new Date().toISOString()}
        />
      )}

      {isLoading && <LoadingOverlay />}
      {errorMessage && (
        <ErrorToast message={errorMessage} onDismiss={() => setErrorMessage(null)} />
      )}
    </div>
  );
}

export default function App() {
  return (
    <ScenarioProvider>
      <AppShell />
    </ScenarioProvider>
  );
}
