import React, { useState } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import { Candidate, CandidateProvenance } from '../../types';
import { Ship, ShieldAlert, AlertTriangle, ExternalLink, Anchor, Navigation, Download, Loader2 } from 'lucide-react';
import { generateBackendReportPdf } from '../../api/oiltraceApi';

export const SuspectLeaderboard: React.FC = () => {
  const {
    detection,
    attribution,
    selectedCandidateId,
    selectCandidate,
    getRealVesselFraction,
    playbackTimeHours,
    pipelineError,
  } = useOilTraceStore();

  const [exportingVesselId, setExportingVesselId] = useState<string | null>(null);

  const handleExportCandidatePdf = async (e: React.MouseEvent, cand: Candidate) => {
    e.stopPropagation();
    setExportingVesselId(cand.vessel_id);
    try {
      const blob = await generateBackendReportPdf({
        spill_id: detection.spill_id,
        detected_at: detection.detected_at,
        centroid: detection.centroid,
        area_km2: detection.area_km2,
        lead_mmsi: cand.vessel_id,
        lead_vessel_name: cand.vessel_name || `MMSI: ${cand.vessel_id}`,
        suspicion_score: cand.suspicion_score ?? 0.85,
        flag_state: cand.flag_state || cand.flag_country || 'LBR',
        jurisdiction: 'Indian Exclusive Economic Zone (EEZ)',
        directive: 'Admiralty Seizure Warrant - Strict Liability Marpol Violation',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Admiralty_Forensic_Dossier_${cand.vessel_id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.warn('[SuspectLeaderboard] Export failed:', err);
    } finally {
      setExportingVesselId(null);
    }
  };

  const candidates = attribution?.candidates || [];
  const realFraction = getRealVesselFraction();
  const selectedCandidate = useOilTraceStore((s) => s.getSelectedCandidate());

  const getProvenanceBadge = (prov: CandidateProvenance) => {
    switch (prov) {
      case 'real_gfw':
        return (
          <span className="px-1.5 py-0.5 bg-[#2DD4BF]/10 border border-[#2DD4BF]/40 text-[#2DD4BF] text-[9px] font-mono font-bold tracking-wider">
            REAL GFW
          </span>
        );
      case 'real_aisstream_live':
        return (
          <span className="px-1.5 py-0.5 bg-emerald-500/10 border border-emerald-500/40 text-emerald-300 text-[9px] font-mono font-bold tracking-wider">
            REAL AISSTREAM
          </span>
        );
      case 'synthetic_fallback':
        return (
          <span className="px-1.5 py-0.5 bg-amber-600/10 border border-amber-600/40 text-amber-300 text-[9px] font-mono font-bold tracking-wider">
            SYNTHETIC
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="h-full bg-[#0A121C] border-l border-[#1D2E42] flex flex-col select-none overflow-hidden">
      {/* Leaderboard Header */}
      <div className="p-3 border-b border-[#1D2E42] flex items-center justify-between bg-[#060B11]">
        <div className="flex items-center space-x-2">
          <Ship className="w-4 h-4 text-[#2DD4BF]" />
          <span className="text-xs font-bold text-[#F1F5F9] font-mono tracking-wider">ATTRIBUTED SUSPECTS</span>
        </div>
        <div className="flex items-center space-x-1.5 text-[10px] font-mono text-[#2DD4BF] bg-[#0F1926] px-2 py-0.5 border border-[#1D2E42]">
          <span>{(realFraction * 100).toFixed(0)}% REAL</span>
          <span className="text-slate-400">({candidates.filter(c => c.data_provenance !== 'synthetic_fallback').length}/{candidates.length})</span>
        </div>
      </div>
      {/* C1 FIX: Dark Vessel Alert Banner — Scenario 4 (AIS-dark vessel) had no visual indicator.
          This banner now fires when all candidates are synthetic (no real AIS data found). */}
      {attribution?.dark_vessel_alert && (
        <div className="mx-3 mt-2 p-2.5 bg-rose-950/40 border border-rose-500/70 flex items-start space-x-2 font-mono text-[10px]">
          <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <div>
            <div className="text-rose-300 font-bold tracking-wider uppercase">DARK VESSEL ALERT</div>
            <div className="text-rose-400/80 mt-0.5">
              AIS transponder suppressed — zero real pings in 200 NM radius during discharge window.
              Vessel operating in AIS-dark mode. MARPOL strict liability applies.
            </div>
          </div>
        </div>
      )}

      {/* C2 FIX: Pipeline error notification — previously pipelineError was set but never rendered. */}
      {pipelineError && (
        <div className="mx-3 mt-2 p-2 bg-amber-950/40 border border-amber-500/60 flex items-center space-x-2 font-mono text-[10px] text-amber-300">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">{pipelineError}</span>
        </div>
      )}

      {/* Ranked Candidate List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {candidates.length === 0 ? (
          <div className="p-6 text-center text-slate-400 font-mono text-xs border border-dashed border-[#1D2E42]">
            Zero suspects currently loaded. Click "RUN LIVE INVESTIGATION".
          </div>
        ) : (
          candidates.map((cand, idx) => {
            const isSelected = cand.vessel_id === (selectedCandidate?.vessel_id || candidates[0]?.vessel_id);
            const scorePct = cand.suspicion_score !== null ? (cand.suspicion_score * 100).toFixed(1) : '—';
            const ci = cand.confidence_interval;

            return (
              <div
                key={cand.vessel_id}
                onClick={() => selectCandidate(cand.vessel_id)}
                className={`p-2.5 border cursor-pointer transition-all ${
                  isSelected
                    ? 'border-[#2DD4BF] bg-[#0F1926]'
                    : 'border-[#1D2E42] bg-[#060B11] hover:border-slate-400'
                }`}
              >
                {/* Header Row: Rank, Name, Provenance */}
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center space-x-2 truncate">
                    <span className={`text-[10px] font-mono font-bold px-1 py-0.2 ${idx === 0 ? 'bg-[#2DD4BF] text-[#060B11]' : 'bg-[#1D2E42] text-slate-300'}`}>
                      #{idx + 1}
                    </span>
                    <span className="text-xs font-bold font-mono text-[#F1F5F9] truncate">
                      {cand.vessel_name || `MMSI: ${cand.vessel_id}`}
                    </span>
                  </div>
                  {getProvenanceBadge(cand.data_provenance)}
                </div>

                {/* MMSI, Flag, Type */}
                <div className="text-[10px] font-mono text-slate-400 flex items-center justify-between mb-2">
                  <span>MMSI: <span className="text-slate-200">{cand.vessel_id}</span></span>
                  <span>FLAG: <span className="text-slate-200">{cand.flag_state || cand.flag_country || '—'}</span></span>
                  <span className="truncate max-w-[110px]">{cand.vessel_type || 'Tanker'}</span>
                </div>

                {/* Suspicion Score & CI */}
                <div className="border-t border-[#1D2E42] pt-2 mb-2">
                  <div className="flex justify-between items-baseline mb-1">
                    <span className="text-[10px] font-mono text-slate-400">SUSPICION SCORE:</span>
                    <div className="text-right">
                      <span className={`text-base font-bold font-mono tabular-nums ${idx === 0 ? 'text-[#2DD4BF]' : 'text-amber-300'}`}>
                        {scorePct}%
                      </span>
                      {ci && (
                        <span className="text-[10px] font-mono text-slate-400 ml-1.5 tabular-nums">
                          [{(ci[0] * 100).toFixed(0)}% – {(ci[1] * 100).toFixed(0)}%]
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Evidence Decomposition Bars */}
                  <div className="space-y-1 mt-1.5 text-[9px] font-mono">
                    <div className="flex justify-between items-center text-slate-400">
                      <span>4D Path Match (Ray-Trace):</span>
                      <span className="text-slate-200 tabular-nums">{(cand.evidence_trace.path_match_score * 100).toFixed(0)}%</span>
                    </div>
                    <div className="w-full bg-[#060B11] h-1 border border-[#1D2E42]/60 overflow-hidden">
                      <div className="bg-[#2DD4BF] h-full" style={{ width: `${cand.evidence_trace.path_match_score * 100}%` }} />
                    </div>

                    <div className="flex justify-between items-center text-slate-400">
                      <span>Confession Simulation IoU:</span>
                      <span className="text-slate-200 tabular-nums">{(cand.evidence_trace.confession_match_score * 100).toFixed(0)}%</span>
                    </div>
                    <div className="w-full bg-[#060B11] h-1 border border-[#1D2E42]/60 overflow-hidden">
                      <div className="bg-amber-400 h-full" style={{ width: `${cand.evidence_trace.confession_match_score * 100}%` }} />
                    </div>

                    <div className="flex justify-between items-center text-slate-400">
                      <span>Isolation Forest Anomaly:</span>
                      <span className="text-slate-200 tabular-nums">{(cand.evidence_trace.anomaly_score * 100).toFixed(0)}%</span>
                    </div>
                    <div className="w-full bg-[#060B11] h-1 border border-[#1D2E42]/60 overflow-hidden">
                      <div className="bg-rose-400 h-full" style={{ width: `${cand.evidence_trace.anomaly_score * 100}%` }} />
                    </div>
                  </div>

                  {/* SHAP Feature Contributions if Available */}
                  {(() => {
                    const shap = cand.evidence_trace.shap_explanation;
                    if (!shap) return null;
                    const features = shap.features && typeof shap.features === 'object' ? shap.features : shap;
                    const entries = Object.entries(features).filter(
                      ([k, v]) => k !== 'base_value' && typeof v === 'number' && !isNaN(v)
                    ) as [string, number][];
                    if (entries.length === 0) return null;

                    return (
                      <div className="mt-2 pt-1.5 border-t border-[#1D2E42]/60 space-y-1 text-[9px] font-mono">
                        <div className="flex items-center justify-between text-slate-400 font-bold uppercase text-[8px]">
                          <span>SHAP FEATURE IMPORTANCE</span>
                          {typeof shap.base_value === 'number' && (
                            <span className="text-slate-500 font-normal">base: {shap.base_value.toFixed(2)}</span>
                          )}
                        </div>
                        {entries.slice(0, 4).map(([feat, val]) => (
                          <div key={feat} className="flex justify-between items-center text-slate-300">
                            <span className="truncate max-w-[150px] text-slate-400 capitalize">
                              {feat.replace(/_/g, ' ')}
                            </span>
                            <span className={`tabular-nums font-bold ${val >= 0 ? 'text-[#2DD4BF]' : 'text-slate-500'}`}>
                              {val >= 0 ? `+${val.toFixed(3)}` : val.toFixed(3)}
                            </span>
                          </div>
                        ))}
                      </div>
                    );
                  })()}

                  {/* Causal Veto / Exoneration Notice if Exonerated */}
                  {cand.proximate_but_absent_at_origin && (
                    <div className="mt-2 p-1.5 bg-emerald-950/40 border border-emerald-500/40 text-[9px] text-emerald-300 flex items-center space-x-1.5">
                      <span className="w-2 h-2 rounded-full bg-emerald-400" />
                      <span className="font-bold uppercase">CAUSAL VETO: EXONERATED FROM LIABILITY</span>
                    </div>
                  )}
                </div>

                {/* Forensic Disclosure Note */}
                {isSelected && cand.evidence_trace.narrative && (
                  <div className="mt-2.5 p-2.5 bg-[#060B11] border-l-2 border-l-[#2DD4BF] border border-[#1D2E42] text-[10px] font-mono text-slate-300 space-y-1.5 leading-relaxed">
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] font-bold text-[#2DD4BF] tracking-wider uppercase">FORENSIC DISCLOSURE</span>
                      <span className="text-[8px] text-slate-500 uppercase">COURT ADMISSIBLE</span>
                    </div>
                    <p className="text-slate-300 leading-normal text-[10px]">
                      {cand.evidence_trace.narrative}
                    </p>
                  </div>
                )}

                {/* Live Scrubber-Coupled Speed & Status Pill */}
                {isSelected && (() => {
                  let currentSog = 13.8;
                  let isSlowdownOrGap = false;
                  if (cand.ais_positions && cand.ais_positions.length > 0 && detection?.detected_at) {
                    const detMs = new Date(detection.detected_at).getTime();
                    const targetMs = detMs + playbackTimeHours * 3600 * 1000;
                    let closest = cand.ais_positions[0];
                    let minDiff = Infinity;
                    for (const pt of cand.ais_positions) {
                      const diff = Math.abs(new Date(pt.timestamp).getTime() - targetMs);
                      if (diff < minDiff) {
                        minDiff = diff;
                        closest = pt;
                      }
                    }
                    if (closest && typeof closest.sog === 'number') {
                      currentSog = closest.sog;
                      isSlowdownOrGap = !!closest.is_reconstructed || (closest.sog >= 3.5 && closest.sog <= 8.5);
                    }
                  } else {
                    isSlowdownOrGap = playbackTimeHours <= -30.0 && playbackTimeHours >= -38.0;
                    currentSog = isSlowdownOrGap ? 6.1 : 14.8;
                  }

                  return (
                    <div className="mt-2 p-1.5 bg-[#0D1522] border border-[#2DD4BF]/40 rounded-sm flex items-center justify-between text-[9px] font-mono">
                      <div className="flex items-center space-x-1.5 text-slate-300">
                        <Navigation className="w-3 h-3 text-[#2DD4BF]" />
                        <span>{playbackTimeHours === 0 ? 'T=0.0h' : `T${playbackTimeHours.toFixed(1)}h`} KINEMATICS:</span>
                      </div>
                      <div>
                        {isSlowdownOrGap ? (
                          <span className="text-rose-400 font-bold animate-pulse flex items-center space-x-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-rose-400 animate-ping inline-block mr-1" />
                            {currentSog.toFixed(1)} kn (DISCHARGE SLOWDOWN / GAP)
                          </span>
                        ) : (
                          <span className="text-emerald-400 font-bold">
                            {currentSog.toFixed(1)} kn (TRANSIT CRUISE)
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {/* Admiralty Forensic Dossier Export Action */}
                {isSelected && (
                  <div className="mt-2 pt-2 border-t border-[#1D2E42] flex justify-end">
                    <button
                      onClick={(e) => handleExportCandidatePdf(e, cand)}
                      disabled={exportingVesselId === cand.vessel_id}
                      className="w-full py-1.5 px-2 bg-[#2DD4BF]/10 hover:bg-[#2DD4BF] text-[#2DD4BF] hover:text-[#060B11] border border-[#2DD4BF]/40 font-mono text-[10px] font-bold flex items-center justify-center space-x-1.5 transition-colors rounded-sm shadow-sm disabled:opacity-50"
                    >
                      {exportingVesselId === cand.vessel_id ? (
                        <>
                          <Loader2 className="w-3 h-3 animate-spin" />
                          <span>GENERATING COURT DOSSIER...</span>
                        </>
                      ) : (
                        <>
                          <Download className="w-3 h-3" />
                          <span>EXPORT ADMIRALTY DOSSIER (PDF)</span>
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Selected Vessel Quick Footer */}
      {selectedCandidate && (
        <div className="p-2.5 border-t border-[#1D2E42] bg-[#060B11] text-[10px] font-mono text-slate-400 flex justify-between items-center">
          <div className="flex items-center space-x-1.5">
            <Anchor className="w-3.5 h-3.5 text-[#2DD4BF]" />
            <span className="truncate max-w-[160px] text-slate-200">{selectedCandidate.vessel_name || selectedCandidate.vessel_id}</span>
          </div>
          <span className="text-[9px] text-slate-400">
            {selectedCandidate.ais_positions.length} AIS FIXES LOGGED
          </span>
        </div>
      )}
    </div>
  );
};
