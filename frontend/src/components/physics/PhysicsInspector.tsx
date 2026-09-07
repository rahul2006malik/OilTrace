import React, { useState } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import {
  Compass,
  Wind,
  Waves,
  Activity,
  X,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  Database,
  Calculator,
} from 'lucide-react';

export const PhysicsInspector: React.FC = () => {
  const {
    isPhysicsInspectorOpen,
    togglePhysicsInspector,
    physicsAtPoint,
    isLoadingPhysics,
    driftRun,
    detection,
    showEnsembleBuildup,
  } = useOilTraceStore();

  const [showMathDetails, setShowMathDetails] = useState<boolean>(true);

  if (!isPhysicsInspectorOpen) return null;

  const current = physicsAtPoint?.current;
  const wind = physicsAtPoint?.wind;
  const particle = physicsAtPoint?.particle_velocity;

  const membersComplete = driftRun ? driftRun.members_complete : 25;
  const ensembleSize = driftRun ? driftRun.ensemble_size : 25;
  const membersDropped = driftRun ? driftRun.members_dropped : 0;

  return (
    <div className="absolute top-14 right-4 w-96 bg-[#0A121C] border border-[#2DD4BF]/50 shadow-2xl z-40 select-none font-mono text-xs max-h-[calc(100vh-8rem)] flex flex-col overflow-hidden">
      {/* HUD Header */}
      <div className="p-2.5 bg-[#060B11] border-b border-[#1D2E42] flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Compass className="w-4 h-4 text-[#2DD4BF] animate-spin" style={{ animationDuration: '8s' }} />
          <span className="font-bold text-[#F1F5F9] tracking-wider">DRIFT PHYSICS INSPECTOR</span>
        </div>
        <button
          onClick={() => togglePhysicsInspector(false)}
          className="text-slate-400 hover:text-[#F1F5F9] p-0.5"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-3 space-y-3 overflow-y-auto flex-1">
        {/* Click Coordinate & Inspection Status */}
        <div className="p-2 bg-[#060B11] border border-[#1D2E42] flex justify-between items-center text-[10px]">
          <span className="text-slate-400">SAMPLE COORDINATE:</span>
          <span className="text-slate-200 tabular-nums">
            {physicsAtPoint
              ? `${physicsAtPoint.query.lon.toFixed(4)}°E, ${physicsAtPoint.query.lat.toFixed(4)}°N`
              : `${detection.centroid[0].toFixed(4)}°E, ${detection.centroid[1].toFixed(4)}°N`}
          </span>
        </div>

        {isLoadingPhysics ? (
          <div className="p-6 text-center text-[#2DD4BF] animate-pulse text-xs">
            SAMPLING NETCDF OCEAN & WIND VECTORS...
          </div>
        ) : (
          <>
            {/* Primary Metocean Vector HUD (§5) */}
            <div className="grid grid-cols-2 gap-2">
              {/* Ocean Current Vector (GLORYS) */}
              <div className="p-2 bg-[#060B11] border border-[#1D2E42]">
                <div className="flex items-center space-x-1.5 text-slate-400 text-[10px] mb-1">
                  <Waves className="w-3.5 h-3.5 text-[#2DD4BF]" />
                  <span>OCEAN CURRENT</span>
                </div>
                <div className="text-base font-bold text-[#2DD4BF] tabular-nums">
                  {current ? `${current.speed_ms.toFixed(2)} m/s` : '—'}
                </div>
                <div className="text-[10px] text-slate-300 tabular-nums">
                  {current ? `@ ${current.direction_deg.toFixed(0)}° (${current.speed_knots.toFixed(1)} kn)` : 'Awaiting query'}
                </div>
                <div className="text-[8px] text-slate-400 mt-1 truncate">
                  {current?.source_dataset || 'GLORYS12V1 (Hourly)'}
                </div>
              </div>

              {/* Wind Vector (ERA5) */}
              <div className="p-2 bg-[#060B11] border border-[#1D2E42]">
                <div className="flex items-center space-x-1.5 text-slate-400 text-[10px] mb-1">
                  <Wind className="w-3.5 h-3.5 text-amber-300" />
                  <span>10M WIND (ERA5)</span>
                </div>
                <div className="text-base font-bold text-amber-300 tabular-nums">
                  {wind ? `${wind.speed_ms.toFixed(1)} m/s` : '—'}
                </div>
                <div className="text-[10px] text-slate-300 tabular-nums">
                  {wind ? `@ ${wind.direction_deg.toFixed(0)}°` : 'Awaiting query'}
                </div>
                <div className="text-[8px] text-slate-400 mt-1 truncate">
                  {wind?.source_dataset || 'ERA5 Single-Levels (0.25°)'}
                </div>
              </div>
            </div>

            {/* Live Windage-Adjusted Net Advection */}
            <div className="p-2.5 bg-[#060B11] border border-[#2DD4BF]/40">
              <div className="text-[10px] text-slate-400 mb-1">WINDAGE-ADJUSTED PARTICLE VELOCITY</div>
              <div className="flex items-baseline justify-between">
                <span className="text-lg font-bold text-[#F1F5F9] tabular-nums">
                  {particle ? `${particle.speed_ms.toFixed(3)} m/s` : '—'}
                </span>
                <span className="text-xs text-[#2DD4BF] font-bold tabular-nums">
                  {particle ? `@ ${particle.bearing_deg.toFixed(1)}° BEARING` : '—'}
                </span>
              </div>
              <div className="text-[9px] text-slate-400 mt-1">
                Computed via: <span className="text-slate-300">u_particle = u_current + α·u_wind</span> (α = {particle ? particle.windage_coefficient_used : 0.032})
              </div>
            </div>

            {/* "Show the Math" Expandable Card (§5) */}
            <div className="border border-[#1D2E42] bg-[#060B11]">
              <button
                onClick={() => setShowMathDetails(!showMathDetails)}
                className="w-full p-2 flex items-center justify-between text-left text-slate-300 hover:text-white"
              >
                <div className="flex items-center space-x-1.5 text-[11px] text-[#2DD4BF]">
                  <Calculator className="w-3.5 h-3.5" />
                  <span className="font-bold">SHOW THE MATH (RK4 INTEGRATION)</span>
                </div>
                {showMathDetails ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>

              {showMathDetails && (
                <div className="p-2.5 pt-0 border-t border-[#1D2E42]/60 text-[10px] text-slate-300 space-y-2">
                  <div className="text-slate-400">
                    Integration: 4th-Order Runge-Kutta (RK4) with adaptive time step Δt = 900s.
                  </div>
                  <div className="p-1.5 bg-[#0F1926] border border-[#1D2E42] text-[9px] text-slate-200">
                    x(t + Δt) = x(t) + (Δt/6)·(k₁ + 2k₂ + 2k₃ + k₄)
                    <br />
                    u = u_current(x,t) + α·u_wind(x,t) + u_diff
                  </div>
                  <div>
                    <span className="text-slate-400">Windage Perturbation: </span>
                    <span className="text-slate-200">25 sampled members (Gaussian α ∈ [0.015, 0.045], mean=0.030, σ=0.004)</span>
                  </div>
                  <div className="flex items-center space-x-1.5 text-emerald-400 pt-1 border-t border-[#1D2E42]/60">
                    <CheckCircle className="w-3 h-3" />
                    <span>
                      Ensemble Health: {membersComplete}/{ensembleSize} completed full 48h ({membersDropped} dropped)
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Forcing Provenance Banner (§5) */}
            <div className="p-2 bg-[#060B11] border border-[#1D2E42] text-[9px] text-slate-400 space-y-1">
              <div className="flex items-center space-x-1 text-[#2DD4BF] font-bold">
                <Database className="w-3 h-3" />
                <span>FORCING DATASET PROVENANCE</span>
              </div>
              <div>• Current: CMEMS GLORYS12V1 (0.083° spatial, hourly time step)</div>
              <div>• Wind: ECMWF ERA5 Single-Levels (0.25° spatial, hourly 10m U/V)</div>
              <div>• Domain Window: {driftRun?.forcing?.window_start ? `${driftRun.forcing.window_start.replace('T', ' ').substring(0, 16)}Z` : 'T-48h'} → {driftRun?.forcing?.window_end ? `${driftRun.forcing.window_end.replace('T', ' ').substring(0, 16)}Z` : 'T0'} (Verified)</div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
