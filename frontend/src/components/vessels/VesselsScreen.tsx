import React from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import { Ship, MapPin, Clock, Radio, AlertTriangle, Navigation, Anchor, Activity, ExternalLink } from 'lucide-react';

export const VesselsScreen: React.FC = () => {
  const { attribution, selectedCandidateId, selectCandidate, detection } = useOilTraceStore();
  const candidates = attribution?.candidates || [];
  const selected = candidates.find((c) => c.vessel_id === selectedCandidateId) || candidates[0];

  return (
    <div className="flex h-full w-full bg-[#060B11] text-[#F1F5F9] font-mono overflow-hidden">
      {/* Left: Vessel Registry List */}
      <div className="w-80 shrink-0 border-r border-[#1D2E42] flex flex-col">
        <div className="p-4 border-b border-[#1D2E42] bg-[#0A121C]">
          <div className="flex items-center space-x-2 text-[#2DD4BF] text-xs font-bold tracking-wider mb-1">
            <Ship className="w-4 h-4" />
            <span>VESSEL REGISTRY</span>
          </div>
          <p className="text-[10px] text-slate-400">Candidate vessels in surveillance window</p>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {candidates.length === 0 ? (
            <div className="text-xs text-slate-500 text-center p-8">
              No vessels loaded. Run investigation from Overview.
            </div>
          ) : (
            candidates.map((c, idx) => {
              const isSelected = c.vessel_id === (selected?.vessel_id);
              return (
                <button
                  key={c.vessel_id}
                  onClick={() => selectCandidate(c.vessel_id)}
                  className={`w-full text-left p-3 border transition-all ${
                    isSelected
                      ? 'border-[#2DD4BF] bg-[#2DD4BF]/5'
                      : 'border-[#1D2E42] bg-[#0A121C] hover:border-slate-500'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-[10px] font-bold px-1 ${idx === 0 ? 'bg-[#2DD4BF] text-[#060B11]' : 'bg-[#1D2E42] text-slate-300'}`}>
                      #{idx + 1}
                    </span>
                    <span className={`text-[9px] px-1.5 py-0.5 border font-bold ${
                      c.suspicion_score && c.suspicion_score > 0.7
                        ? 'border-rose-500/40 text-rose-300 bg-rose-500/5'
                        : c.suspicion_score && c.suspicion_score > 0.5
                        ? 'border-amber-500/40 text-amber-300 bg-amber-500/5'
                        : 'border-emerald-500/40 text-emerald-300 bg-emerald-500/5'
                    }`}>
                      {c.suspicion_score
                        ? `${(c.suspicion_score * 100).toFixed(0)}% RISK`
                        : 'UNKNOWN'}
                    </span>
                  </div>
                  <div className="text-xs font-bold text-slate-100 truncate">
                    {c.vessel_name || `MMSI: ${c.vessel_id}`}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5">
                    {c.vessel_id} · {c.flag_state || c.flag_country || '—'} · {c.vessel_type || 'Unknown'}
                  </div>
                  <div className="text-[9px] text-slate-500 mt-0.5">
                    {c.ais_positions.length} AIS fixes · {c.data_provenance === 'real_gfw' ? 'Real GFW' : c.data_provenance === 'real_aisstream_live' ? 'Real AIS' : 'Synthetic'}
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Right: Vessel Dossier */}
      {selected ? (
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Header */}
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center space-x-2 text-[#2DD4BF] text-xs font-bold tracking-wider mb-1">
                <Ship className="w-4 h-4" />
                <span>VESSEL FORENSIC DOSSIER</span>
              </div>
              <h1 className="text-2xl font-bold text-slate-100">
                {selected.vessel_name || `MMSI: ${selected.vessel_id}`}
              </h1>
              <div className="text-sm text-slate-400 mt-1">
                {selected.vessel_type || 'Unknown Type'} · Flag: {selected.flag_state || selected.flag_country || 'Unknown'}
              </div>
            </div>
            <div className={`px-3 py-1.5 border font-bold text-sm ${
              selected.suspicion_score && selected.suspicion_score > 0.7
                ? 'border-rose-500/50 text-rose-300 bg-rose-500/10'
                : 'border-amber-500/50 text-amber-300 bg-amber-500/10'
            }`}>
              {selected.suspicion_score
                ? `${(selected.suspicion_score * 100).toFixed(1)}% — ${selected.suspicion_score > 0.7 ? 'HIGH RISK' : 'MEDIUM RISK'}`
                : 'UNKNOWN RISK'}
            </div>
          </div>

          {/* Identity card grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: 'MMSI', value: selected.vessel_id, icon: <Radio className="w-3.5 h-3.5" /> },
              { label: 'IMO', value: selected.imo || '—', icon: <Ship className="w-3.5 h-3.5" /> },
              { label: 'Flag State', value: selected.flag_state || selected.flag_country || '—', icon: <MapPin className="w-3.5 h-3.5" /> },
              { label: 'Vessel Type', value: selected.vessel_type || '—', icon: <Anchor className="w-3.5 h-3.5" /> },
              { label: 'Departure', value: selected.departure_port || '—', icon: <Navigation className="w-3.5 h-3.5" /> },
              { label: 'Destination', value: selected.destination_port || '—', icon: <Navigation className="w-3.5 h-3.5" /> },
              { label: 'Voyage Status', value: selected.voyage_status || '—', icon: <Activity className="w-3.5 h-3.5" /> },
              { label: 'AIS Fixes', value: `${selected.ais_positions.length} recorded`, icon: <Clock className="w-3.5 h-3.5" /> },
            ].map(({ label, value, icon }) => (
              <div key={label} className="bg-[#0A121C] border border-[#1D2E42] p-3">
                <div className="flex items-center space-x-1.5 text-slate-400 text-[10px] mb-1">
                  {icon}
                  <span className="uppercase tracking-wider">{label}</span>
                </div>
                <div className="text-sm font-bold text-slate-100 truncate">{value}</div>
              </div>
            ))}
          </div>

          {/* Evidence Breakdown */}
          <div className="bg-[#0A121C] border border-[#1D2E42] p-4">
            <div className="text-xs font-bold text-slate-200 mb-3 pb-2 border-b border-[#1D2E42] flex items-center space-x-2">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              <span>EVIDENCE DECOMPOSITION</span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {[
                { label: '4D Path Match (Ray-Trace)', value: selected.evidence_trace.path_match_score, color: '#2DD4BF' },
                { label: 'Confession Simulation IoU', value: selected.evidence_trace.confession_match_score, color: '#F59E0B' },
                { label: 'Isolation Forest Anomaly', value: selected.evidence_trace.anomaly_score, color: '#EF4444' },
                { label: 'Proximity to Origin Zone', value: selected.evidence_trace.proximity_score, color: '#818CF8' },
              ].map(({ label, value, color }) => (
                <div key={label}>
                  <div className="flex justify-between items-center text-[10px] text-slate-400 mb-1">
                    <span>{label}</span>
                    <span className="font-bold text-slate-200">{(value * 100).toFixed(0)}%</span>
                  </div>
                  <div className="w-full bg-[#060B11] h-2 border border-[#1D2E42] overflow-hidden">
                    <div
                      className="h-full transition-all duration-700"
                      style={{ width: `${value * 100}%`, backgroundColor: color }}
                    />
                  </div>
                </div>
              ))}
            </div>
            {selected.proximate_but_absent_at_origin && (
              <div className="mt-3 p-2 border border-emerald-500/40 bg-emerald-950/30 text-[10px] text-emerald-300 flex items-center space-x-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="font-bold">CAUSAL VETO: Vessel was NOT present at origin zone at spill onset time. Exonerated.</span>
              </div>
            )}
          </div>

          {/* Voyage Timeline */}
          {selected.voyage_milestones && selected.voyage_milestones.length > 0 && (
            <div className="bg-[#0A121C] border border-[#1D2E42] p-4">
              <div className="text-xs font-bold text-slate-200 mb-3 pb-2 border-b border-[#1D2E42]">VOYAGE TIMELINE</div>
              <div className="space-y-3">
                {selected.voyage_milestones.map((m, idx) => (
                  <div key={idx} className="flex items-start space-x-3">
                    <div className={`mt-1 w-2.5 h-2.5 rounded-full shrink-0 ${
                      m.type === 'blackout_start' ? 'bg-rose-400' :
                      m.type === 'spill_intersect' ? 'bg-amber-400' :
                      m.type === 'current_position' ? 'bg-[#2DD4BF]' :
                      'bg-slate-400'
                    }`} />
                    <div>
                      <div className="text-[11px] font-bold text-slate-200">{m.label}</div>
                      <div className="text-[10px] text-slate-500">{m.timestamp?.replace('T', ' ').replace('Z', ' UTC')}</div>
                      {m.note && <div className="text-[10px] text-slate-400 mt-0.5">{m.note}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SHAP explanations */}
          {(() => {
            const exp = selected.evidence_trace.shap_explanation;
            if (!exp) return null;
            const entries: [string, number][] = (exp as any).features
              ? Object.entries((exp as any).features)
              : (Object.entries(exp).filter(([_, v]) => typeof v === 'number') as [string, number][]);
            if (!entries || entries.length === 0) return null;

            return (
              <div className="bg-[#0A121C] border border-[#1D2E42] p-4">
                <div className="text-xs font-bold text-slate-200 mb-3 pb-2 border-b border-[#1D2E42]">SHAP FEATURE CONTRIBUTIONS</div>
                <div className="space-y-2">
                  {entries.slice(0, 8).map(([feat, val]) => (
                    <div key={feat} className="flex justify-between items-center text-[10px]">
                      <span className="text-slate-400">{feat.replace(/_/g, ' ')}</span>
                      <span className={val >= 0 ? 'text-[#2DD4BF] font-bold' : 'text-slate-500'}>
                        {val >= 0 ? `+${Number(val).toFixed(3)}` : Number(val).toFixed(3)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* Narrative */}
          {selected.evidence_trace.narrative && (
            <div className="bg-[#0A121C] border border-[#1D2E42] p-4">
              <div className="text-xs font-bold text-slate-200 mb-2">FORENSIC NARRATIVE</div>
              <p className="text-xs text-slate-300 leading-relaxed">{selected.evidence_trace.narrative}</p>
            </div>
          )}

          {/* Counterfactuals */}
          {selected.evidence_trace.counterfactuals && selected.evidence_trace.counterfactuals.length > 0 && (
            <div className="bg-[#0A121C] border border-[#1D2E42] p-4">
              <div className="text-xs font-bold text-slate-200 mb-2">COUNTERFACTUAL ANALYSIS</div>
              <div className="space-y-1.5">
                {selected.evidence_trace.counterfactuals.map((cf, idx) => (
                  <div key={idx} className="flex items-start space-x-2 text-[11px] text-slate-300">
                    <span className="text-[#2DD4BF] font-bold shrink-0">IF:</span>
                    <span>{cf}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-slate-500 text-sm font-mono">
          Select a vessel from the registry to view its forensic dossier.
        </div>
      )}
    </div>
  );
};
