import React, { useState } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import { Radio, Satellite, Layers, AlertCircle, CheckCircle2, Play, Flame, Activity } from 'lucide-react';

export const SarTelemetryPanel: React.FC<{ onDiagnosticOpen?: () => void }> = ({ onDiagnosticOpen }) => {
  const detection = useOilTraceStore((s) => s.detection);
  const isLoadingPipeline = useOilTraceStore((s) => s.isLoadingPipeline);
  const executeInvestigation = useOilTraceStore((s) => s.executeInvestigation);
  const selectedCandidate = useOilTraceStore((s) => s.getSelectedCandidate());
  const [xaiExpanded, setXaiExpanded] = useState(true);

  return (
    <div className="h-full bg-[#070C14] border-r border-[#1E2C3F] flex flex-col select-none overflow-y-auto font-mono">
      {/* Panel Header */}
      <div className="p-3 border-b border-[#1E2C3F] flex items-center justify-between bg-[#0A121C]">
        <div className="flex items-center space-x-2">
          <Satellite className="w-4 h-4 text-[#2DD4BF]" />
          <span className="text-xs font-bold text-slate-100 tracking-wider">SAR RADAR TELEMETRY</span>
        </div>
        <span className="text-[9px] px-1.5 py-0.5 bg-[#0D1522] border border-[#1E2C3F] text-[#2DD4BF] font-semibold rounded-sm">
          SENTINEL-1C IW
        </span>
      </div>

      <div className="p-3 space-y-3 flex-1">
        {/* SAR Scene Preview Card */}
        <div className="border border-[#1E2C3F] bg-[#0D1522] p-2 relative group rounded-sm">
          <div className="aspect-[16/9] w-full bg-[#070C14] relative overflow-hidden flex items-center justify-center border border-[#1E2C3F]/70 rounded-sm">
            <img
              src="/sar_enhanced.png"
              alt="Sentinel-1 SAR VV Channel"
              className="w-full h-full object-cover opacity-85 group-hover:opacity-100 transition-opacity"
            />
            {/* Tactical Crosshairs */}
            <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
              <div className="w-12 h-12 border border-[#2DD4BF]/40 rounded-full" />
              <div className="absolute w-full h-px bg-[#2DD4BF]/20" />
              <div className="absolute h-full w-px bg-[#2DD4BF]/20" />
            </div>
            <div className="absolute top-1.5 left-1.5 bg-[#070C14]/90 px-1.5 py-0.5 border border-[#1E2C3F] text-[9px] text-[#2DD4BF] font-bold">
              VV DAMPING SLICK
            </div>
            <div className="absolute bottom-1.5 right-1.5 bg-[#070C14]/90 px-1.5 py-0.5 border border-[#1E2C3F] text-[9px] text-slate-300">
              10m PIXEL RES
            </div>
          </div>
          <div className="mt-2 text-[10px] text-slate-400 truncate">
            SCENE: <span className="text-slate-200 font-semibold">{detection.source_scene_id}</span>
          </div>
        </div>

        {/* Primary Classification & Confidence Metrics */}
        <div className="grid grid-cols-2 gap-2">
          <div className="border border-[#1E2C3F] bg-[#0D1522] p-2.5 rounded-sm">
            <div className="text-[9px] text-slate-400 uppercase tracking-wider font-semibold">OIL CONFIDENCE</div>
            <div className="text-xl font-bold text-[#2DD4BF] tabular-nums mt-0.5">
              {(detection.oil_confidence * 100).toFixed(1)}%
            </div>
            <div className="w-full bg-[#070C14] h-1.5 mt-1.5 border border-[#1E2C3F] overflow-hidden rounded-full">
              <div
                className="bg-[#2DD4BF] h-full transition-all duration-500"
                style={{ width: `${Math.min(100, Math.max(0, detection.oil_confidence * 100))}%` }}
              />
            </div>
          </div>

          <div className="border border-[#1E2C3F] bg-[#0D1522] p-2.5 rounded-sm">
            <div className="text-[9px] text-slate-400 uppercase tracking-wider font-semibold">SLICK AREA</div>
            <div className="text-xl font-bold text-amber-300 tabular-nums mt-0.5">
              {detection.area_km2.toFixed(2)} <span className="text-xs font-normal text-slate-400">km²</span>
            </div>
            <div className="text-[9px] text-slate-400 mt-1">WGS84 GEODESIC</div>
          </div>
        </div>

        {/* Morphological Telemetry */}
        <div className="border border-[#1E2C3F] bg-[#0D1522] p-2.5 space-y-2 rounded-sm">
          <div className="text-[9px] text-slate-400 uppercase tracking-wider font-semibold border-b border-[#1E2C3F] pb-1">
            MORPHOLOGICAL SIGNATURE
          </div>

          <div className="flex justify-between items-center text-xs">
            <span className="text-slate-400 text-[11px]">Centroid:</span>
            <span className="text-slate-200 tabular-nums font-semibold text-[11px]">
              {detection.centroid[0].toFixed(4)}°E, {detection.centroid[1].toFixed(4)}°N
            </span>
          </div>

          <div className="flex justify-between items-center text-xs">
            <span className="text-slate-400 text-[11px]">Elongation:</span>
            <span className="text-slate-200 tabular-nums text-[11px]">
              {detection.elongation_ratio.toFixed(2)}x (Linear Bilge)
            </span>
          </div>

          <div className="flex justify-between items-center text-xs">
            <span className="text-slate-400 text-[11px]">Thickness Class:</span>
            <span className="px-1.5 py-0.5 bg-amber-500/10 border border-amber-500/40 text-amber-300 text-[9px] font-bold uppercase rounded-sm">
              {detection.thickness_class}
            </span>
          </div>

          <div className="flex justify-between items-center text-xs">
            <span className="text-slate-400 text-[11px]">Lookalike Filter:</span>
            <span className="flex items-center space-x-1 text-emerald-400 text-[11px] font-semibold">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>SUPPRESSED</span>
            </span>
          </div>
        </div>

        {/* VV/VH Polarimetric Damping Profile & SVG Waveform */}
        <div className="border border-[#1E2C3F] bg-[#0D1522] p-2.5 space-y-2 rounded-sm">
          <div className="flex justify-between items-center text-[9px] text-slate-400 uppercase tracking-wider font-semibold">
            <span>POLARIMETRIC TRANSECT (VV/VH)</span>
            <span className="text-[#2DD4BF] font-bold">
              {detection.thickness_class === 'thick' ? '-8.4 dB' : detection.thickness_class === 'thin' ? '-5.9 dB' : '-3.8 dB'}
            </span>
          </div>

          {/* Damping Profile SVG Waveform from Tactical Design */}
          <div className="h-16 w-full bg-[#070C14] border border-[#1E2C3F] relative overflow-hidden flex items-end">
            <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox="0 0 100 100">
              <line x1="0" y1="75" x2="100" y2="75" stroke="#334155" strokeWidth="1" strokeDasharray="2 2" />
              <polyline
                fill="none"
                points="0,75 20,74 35,70 45,28 50,18 55,28 65,71 80,74 100,75"
                stroke="#2DD4BF"
                strokeWidth="1.5"
              />
              <polyline
                fill="none"
                points="0,85 20,84 35,80 45,55 50,42 55,55 65,81 80,84 100,85"
                stroke="#64748B"
                strokeWidth="1"
                strokeDasharray="2 2"
              />
            </svg>
            <div className="absolute left-[40%] w-[20%] h-full bg-rose-500/10 border-l border-r border-rose-500/30 flex items-center justify-center">
              <span className="text-[7px] text-rose-400 font-bold tracking-widest uppercase">SLICK</span>
            </div>
          </div>
          <div className="flex justify-between font-mono text-[8px] text-slate-500 px-0.5">
            <span className="text-[#2DD4BF]">VV (CO-POL)</span>
            <span>-8.4 dB NOTCH</span>
            <span className="text-slate-400">VH (CROSS-POL)</span>
          </div>

          {/* Scott & Alpers Wind Validity Gate */}
          <div className="flex items-center justify-between p-1.5 bg-[#070C14] border border-[#1E2C3F] text-[10px]">
            <span className="text-slate-400">BRAGG WIND GATE:</span>
            <div className="flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-[#2DD4BF] animate-pulse" />
              <span className="text-[#2DD4BF] font-bold text-[9px]">4.8 m/s (OPTIMAL 2–12 m/s)</span>
            </div>
          </div>

          <div className="text-[9px] text-slate-500 pt-1 border-t border-[#1E2C3F]">
            ResNet-34 Filter → U-Net (~3.5s latency)
          </div>
          {onDiagnosticOpen && (
            <button
              onClick={onDiagnosticOpen}
              className="w-full mt-1.5 py-1.5 px-2 bg-[#0A121C] hover:bg-[#2DD4BF] hover:text-[#060B11] text-[#2DD4BF] text-[10px] font-bold tracking-wider uppercase border border-[#2DD4BF]/30 rounded-sm flex items-center justify-center space-x-1.5 transition-colors cursor-pointer"
            >
              <Activity className="w-3.5 h-3.5" />
              <span>Inspect Radar Profile</span>
            </button>
          )}
        </div>

        {/* XAI Evidence Decomposition Panel */}
        <div className="border border-[#1E2C3F] bg-[#0D1522] rounded-sm">
          <button
            onClick={() => setXaiExpanded((x) => !x)}
            className="w-full p-2.5 flex items-center justify-between text-[9px] text-slate-400 uppercase tracking-wider font-semibold hover:text-slate-200 transition-colors"
          >
            <span className="flex items-center gap-1.5">
              <Activity className="w-3 h-3 text-[#2DD4BF]" />
              XAI EVIDENCE DECOMPOSITION
            </span>
            <span className="text-[#2DD4BF] font-mono">{xaiExpanded ? '▲' : '▼'}</span>
          </button>

          {xaiExpanded && selectedCandidate && (() => {
            const et = selectedCandidate.evidence_trace;
            const factors = [
              { label: 'PROXIMITY', value: et?.proximity_score ?? 0, color: 'bg-[#2DD4BF]' },
              { label: 'CONFESSION', value: et?.confession_match_score ?? 0, color: 'bg-blue-400' },
              { label: 'ANOMALY', value: et?.anomaly_score ?? 0, color: 'bg-amber-400' },
              { label: 'PRIOR', value: typeof et?.vessel_type_prior === 'number' ? et.vessel_type_prior : 0.5, color: 'bg-purple-400' },
              { label: 'PATH MATCH', value: et?.path_match_score ?? 0, color: 'bg-emerald-400' },
            ];
            return (
              <div className="px-2.5 pb-2.5 space-y-1.5 border-t border-[#1E2C3F]/60 pt-2">
                <div className="text-[8px] text-slate-400 uppercase tracking-wider font-bold mb-1">
                  SUSPECT: <span className="text-slate-200">{selectedCandidate.vessel_name || `MMSI: ${selectedCandidate.vessel_id}`}</span>
                </div>
                {factors.map((f) => (
                  <div key={f.label} className="flex items-center gap-2 text-[10px]">
                    <span className="text-slate-400 w-20 shrink-0 font-mono text-[9px]">{f.label}</span>
                    <div className="flex-1 bg-[#060B11] border border-[#1D2E42] h-2 rounded-full overflow-hidden">
                      <div
                        className={`${f.color} h-full rounded-full transition-all duration-700`}
                        style={{ width: `${Math.round(Math.min(1, Math.max(0, f.value)) * 100)}%` }}
                      />
                    </div>
                    <span className="text-slate-200 tabular-nums w-8 text-right font-mono text-[9px]">{f.value.toFixed(2)}</span>
                  </div>
                ))}

                {et?.dominant_factor && et.dominant_factor !== 'none' && (
                  <div className="mt-2 p-1.5 bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[9px] font-mono rounded-xs">
                    ⚑ PRIMARY FACTOR: <span className="font-bold">{et.dominant_factor.replace(/_/g, ' ').toUpperCase()}</span>
                  </div>
                )}

                {et?.counterfactuals && et.counterfactuals.length > 0 && (
                  <div className="mt-1.5 space-y-1">
                    {et.counterfactuals.slice(0, 2).map((cf, i) => (
                      <div key={i} className="text-[9px] text-slate-400 border-l-2 border-[#2DD4BF]/50 pl-2 italic leading-relaxed font-sans">
                        {cf}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })()}

          {xaiExpanded && !selectedCandidate && (
            <div className="px-2.5 pb-2.5 text-[10px] text-slate-500 italic">
              No suspect selected. Run investigation to inspect XAI decomposition.
            </div>
          )}
        </div>
      </div>

      {/* Action Footer */}
      <div className="p-3 border-t border-[#1E2C3F] bg-[#0A121C]">
        <button
          onClick={() => executeInvestigation()}
          disabled={isLoadingPipeline}
          className="w-full py-2.5 px-3 bg-[#2DD4BF] hover:bg-[#26bba7] text-[#070C14] font-bold text-xs flex items-center justify-center space-x-2 transition-all shadow-md disabled:opacity-50 rounded-sm"
        >
          <Play className="w-3.5 h-3.5 fill-current" />
          <span>{isLoadingPipeline ? 'PROCESSING PIPELINE...' : 'RUN LIVE INVESTIGATION'}</span>
        </button>
      </div>
    </div>
  );
};
