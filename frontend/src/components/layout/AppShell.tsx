import React, { useEffect, useState } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import { TopBar } from '../layout/TopBar';
import { LeftSidebar } from '../layout/LeftSidebar';

// Screens
import { SarTelemetryPanel } from '../telemetry/SarTelemetryPanel';
import { TacticalMap } from '../map/TacticalMap';
import { SuspectLeaderboard } from '../candidates/SuspectLeaderboard';
import { TemporalScrubber } from '../dock/TemporalScrubber';
import { PhysicsInspector } from '../physics/PhysicsInspector';
import { DossierModal } from '../export/DossierModal';
import { LookalikeDiagnosticModal } from '../analytics/LookalikeDiagnosticModal';
import { ScenarioPickerScreen } from '../scenarios/ScenarioPickerScreen';
import { LiveSurveillanceScreen } from '../surveillance/LiveSurveillanceScreen';
import { ReportsScreen } from '../reports/ReportsScreen';
import { ModelGovernanceScreen } from '../settings/ModelGovernanceScreen';
import { VesselsScreen } from '../vessels/VesselsScreen';

export const AppShell: React.FC = () => {
  const init = useOilTraceStore((s) => s.init);
  const activeScreen = useOilTraceStore((s) => s.activeScreen);
  const setActiveScreen = useOilTraceStore((s) => s.setActiveScreen);
  const togglePlayback = useOilTraceStore((s) => s.togglePlayback);
  const setPlaybackTime = useOilTraceStore((s) => s.setPlaybackTime);

  const [isDossierOpen, setIsDossierOpen] = useState(false);
  const [isDiagnosticOpen, setIsDiagnosticOpen] = useState(false);

  useEffect(() => {
    init();
  }, [init]);

  // Global Tactical Keyboard Navigation Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore keystrokes when typing into an input or textarea
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) {
        return;
      }

      const curTime = useOilTraceStore.getState().playbackTimeHours;
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlayback();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        setPlaybackTime(Math.max(-48.0, curTime - 1.0));
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        setPlaybackTime(Math.min(0.0, curTime + 1.0));
      } else if (e.code === 'Home') {
        e.preventDefault();
        setPlaybackTime(0.0);
      } else if (e.code === 'End') {
        e.preventDefault();
        setPlaybackTime(-48.0);
      } else if (e.code === 'Escape') {
        e.preventDefault();
        if (activeScreen !== 'overview') {
          setActiveScreen('overview');
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [togglePlayback, setPlaybackTime, activeScreen, setActiveScreen]);

  return (
    <div className="flex flex-col h-screen w-screen bg-[#060B11] text-[#F1F5F9] overflow-hidden select-none">
      {/* Top Bar — B3 FIX: Pass onDossierOpen so the Dossier button in TopBar can trigger the modal */}
      <TopBar onDossierOpen={() => setIsDossierOpen(true)} />

      {/* Body: Sidebar + Main Stage */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Left Sidebar */}
        <LeftSidebar />

        {/* ── PERSISTENT 3-COLUMN TACTICAL COMMAND COCKPIT ── */}
        <div className="flex-1 flex flex-col overflow-hidden min-w-0 relative">
          <div className="flex-1 flex overflow-hidden relative">
            {/* Left Column (22%): SAR Telemetry */}
            <div className="w-[22%] min-w-[260px] max-w-[340px] h-full shrink-0">
              <SarTelemetryPanel onDiagnosticOpen={() => setIsDiagnosticOpen(true)} />
            </div>

            {/* Center Column (flex-1): MapLibre Tactical Canvas */}
            <div className="flex-1 h-full relative min-w-0">
              <TacticalMap />
              <PhysicsInspector />
            </div>

            {/* Right Column (26%): Attributed Suspects Leaderboard */}
            <div className="w-[26%] min-w-[300px] max-w-[400px] h-full shrink-0">
              <SuspectLeaderboard />
            </div>
          </div>

          {/* Bottom Temporal Scrubber Dock */}
          <TemporalScrubber />
        </div>

        {/* ── SECONDARY SLIDE-OVER TACTICAL DRAWERS (Preserves Map Context) ── */}
        {activeScreen !== 'overview' && (
          <>
            {/* Backdrop click to dismiss */}
            <div
              onClick={() => setActiveScreen('overview')}
              className="absolute inset-0 z-30 bg-black/50 backdrop-blur-[2px] transition-opacity duration-200"
            />

            {/* Slide-over Drawer Pane */}
            <div className="absolute inset-y-0 right-0 w-full max-w-5xl z-40 bg-[#060B11]/98 border-l border-[#1E2C3F] backdrop-blur-2xl shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
              {/* Drawer Header with Breadcrumb and Tactical Close */}
              <div className="p-3 bg-[#0A121C] border-b border-[#1E2C3F] flex justify-between items-center px-6 shrink-0">
                <div className="flex items-center space-x-2.5">
                  <span className="w-2 h-2 rounded-full bg-[#2DD4BF] animate-pulse" />
                  <span className="font-mono text-xs font-bold text-[#2DD4BF] tracking-wider uppercase">
                    {activeScreen === 'scenarios' && 'Incident Scenario Archive'}
                    {activeScreen === 'reports' && 'Admiralty Court Evidence Archive & Audit Ledger'}
                    {activeScreen === 'governance' && 'Model Governance & Checkpoint Benchmarks'}
                    {activeScreen === 'surveillance' && 'Satellite Tasking & Intercept Radar'}
                    {activeScreen === 'vessels' && 'Vessel Registry & 4D Trajectories'}
                  </span>
                </div>
                <button
                  onClick={() => setActiveScreen('overview')}
                  className="px-3 py-1 bg-[#1E2C3F] hover:bg-[#2DD4BF] hover:text-[#060B11] text-slate-200 font-mono text-xs font-bold transition-colors rounded-sm flex items-center space-x-1.5"
                >
                  <span>✕ Return to Cockpit (ESC)</span>
                </button>
              </div>

              {/* Drawer Body Screen */}
              <div className="flex-1 overflow-hidden">
                {activeScreen === 'scenarios' && <ScenarioPickerScreen />}
                {activeScreen === 'reports' && <ReportsScreen />}
                {activeScreen === 'governance' && <ModelGovernanceScreen />}
                {activeScreen === 'surveillance' && <LiveSurveillanceScreen />}
                {activeScreen === 'vessels' && <VesselsScreen />}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Dossier Modal */}
      <DossierModal isOpen={isDossierOpen} onClose={() => setIsDossierOpen(false)} />

      {/* Lookalike Radar Diagnostic Modal */}
      <LookalikeDiagnosticModal isOpen={isDiagnosticOpen} onClose={() => setIsDiagnosticOpen(false)} />
    </div>
  );
};
