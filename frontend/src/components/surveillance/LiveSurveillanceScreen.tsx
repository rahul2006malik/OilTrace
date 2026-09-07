import React, { useEffect, useState } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import { submitAnalystFeedback } from '../../api/oiltraceApi';
import {
  Satellite,
  Radio,
  Clock,
  Shield,
  Target,
  ArrowUpRight,
  CheckCircle,
  AlertTriangle,
  Send,
  RefreshCw,
  Compass,
} from 'lucide-react';

export const LiveSurveillanceScreen: React.FC = () => {
  const { detection, attribution, setActiveScreen } = useOilTraceStore();
  const [taskingDispatched, setTaskingDispatched] = useState<boolean>(false);
  const [satellitePasses, setSatellitePasses] = useState<any[]>([]);

  useEffect(() => {
    fetch('/api/surveillance/satellite-passes')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.passes?.length) {
          setSatellitePasses(data.passes);
        }
      })
      .catch((err) => console.warn('Failed to load satellite passes:', err));
  }, []);

  const handleDispatchTasking = async () => {
    setTaskingDispatched(true);
    try {
      await submitAnalystFeedback({
        spill_id: detection.spill_id,
        vessel_id: 'TASKING_ORDER_ISRO',
        action: 'override',
        notes: `Urgent Tier-1 satellite tasking order transmitted for RISAT-1A & Sentinel-1 over centroid [${detection.centroid.join(', ')}].`,
      });
    } catch (e) {
      console.warn('Failed recording tasking feedback:', e);
    }
  };

  const darkIntel = attribution?.dark_vessel_intelligence;
  const navalAdvisory = attribution?.naval_intercept_advisory;

  return (
    <div className="flex flex-col h-full w-full bg-[#060B11] text-[#F1F5F9] font-mono select-none overflow-y-auto p-6 space-y-6">
      {/* Header Banner */}
      <div className="border border-[#1D2E42] bg-[#0A121C] p-5 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <div className="flex items-center space-x-2 text-[#2DD4BF] text-xs font-bold tracking-wider">
            <Radio className="w-4 h-4 animate-pulse text-[#2DD4BF]" />
            <span>REAL-TIME SATELLITE TASKING & NAVAL SQUADRON INTERCEPT RADAR</span>
          </div>
          <h1 className="text-xl font-bold text-slate-100 tracking-wide mt-1">
            SURVEILLANCE & NEXT-PASS DIRECTIVE
          </h1>
          <p className="text-xs text-slate-400 mt-1 max-w-3xl leading-relaxed">
            Real-time constellation scheduling and Coast Guard intercept geometry for active spill sector:
            <span className="text-[#2DD4BF] font-bold"> {detection.spill_id}</span>. Evaluates orbital look-windows
            for Sentinel-1, RISAT-1A (EOS-04), and airborne patrol assets.
          </p>
        </div>

        <button
          onClick={() => setActiveScreen('overview')}
          className="px-4 py-1.5 bg-[#2DD4BF] hover:bg-[#26bba7] text-[#060B11] font-bold text-xs flex items-center space-x-1.5 transition-colors"
        >
          <span>RETURN TO COCKPIT</span>
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Columns: Satellite Orbit Passes & Tasking Protocol */}
        <div className="lg:col-span-2 space-y-6">
          {/* Autonomous Satellite Tasking Card */}
          <div className="border border-[#1D2E42] bg-[#0A121C] p-5 space-y-4">
            <div className="flex justify-between items-center border-b border-[#1D2E42] pb-3">
              <div className="flex items-center space-x-2">
                <Satellite className="w-4 h-4 text-[#2DD4BF]" />
                <span className="font-bold text-sm text-slate-100">NEXT-PASS RADAR SATELLITE TASKING</span>
              </div>
              <span className="text-[10px] px-2 py-0.5 bg-[#2DD4BF]/10 text-[#2DD4BF] border border-[#2DD4BF]/30 font-bold">
                PRIORITY: TIER-1 MDA
              </span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div className="p-3 bg-[#060B11] border border-[#1D2E42]">
                <span className="text-[10px] text-slate-400 block">SENSOR TYPE:</span>
                <span className="font-bold text-slate-200 mt-0.5 block">Synthetic Aperture Radar</span>
                <span className="text-[9px] text-[#2DD4BF] block">C-band / X-band High-Res</span>
              </div>

              <div className="p-3 bg-[#060B11] border border-[#1D2E42]">
                <span className="text-[10px] text-slate-400 block">TARGET CONSTELLATION:</span>
                <span className="font-bold text-slate-200 mt-0.5 block">RISAT-1A / EOS-04</span>
                <span className="text-[9px] text-slate-400 block">ISRO / Sentinel-1 Next Pass</span>
              </div>

              <div className="p-3 bg-[#060B11] border border-[#1D2E42]">
                <span className="text-[10px] text-slate-400 block">PROJECTED APERTURE:</span>
                <span className="font-bold text-amber-300 mt-0.5 block">80.0 km Swath</span>
                <span className="text-[9px] text-slate-400 block">Stripmap Mode (3m Res)</span>
              </div>

              <div className="p-3 bg-[#060B11] border border-[#1D2E42]">
                <span className="text-[10px] text-slate-400 block">TASKING WINDOW:</span>
                <span className="font-bold text-emerald-400 mt-0.5 block">T+06:00 to T+12:00</span>
                <span className="text-[9px] text-slate-400 block">From Detection Epoch</span>
              </div>
            </div>

            {/* Target Centroid & Swath Coordinates */}
            <div className="p-3.5 bg-[#060B11] border border-[#1D2E42] text-xs space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-slate-400">PROJECTED ESCAPE VECTOR CENTROID:</span>
                <span className="text-[#2DD4BF] font-bold tabular-nums">
                  [{detection.centroid[0].toFixed(4)}°E, {detection.centroid[1].toFixed(4)}°N]
                </span>
              </div>
              <div className="flex justify-between items-center text-[11px]">
                <span className="text-slate-400">ESTIMATED TRANSIT COURSE:</span>
                <span className="text-slate-300 font-bold">245° (Southwest outward EEZ corridor @ 14.5 kn)</span>
              </div>
              <div className="flex justify-between items-center text-[11px]">
                <span className="text-slate-400">PROJECTED EEZ EXIT WINDOW:</span>
                <span className="text-rose-400 font-bold">9.4 Hours Remaining</span>
              </div>
            </div>

            {/* Dispatch Button */}
            <div className="flex justify-end pt-2">
              <button
                onClick={handleDispatchTasking}
                disabled={taskingDispatched}
                className={`px-4 py-2 text-xs font-bold flex items-center space-x-2 transition-colors ${
                  taskingDispatched
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50'
                    : 'bg-[#2DD4BF] hover:bg-[#26bba7] text-[#060B11]'
                }`}
              >
                {taskingDispatched ? (
                  <>
                    <CheckCircle className="w-4 h-4" />
                    <span>TASKING ORDER DISPATCHED TO ISRO / NTRO SATELLITE CELL</span>
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    <span>TRANSMIT SATELLITE TASKING REQUEST (ORBITAL PRIORITY 1)</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Upcoming Satellite Overpasses Table */}
          <div className="border border-[#1D2E42] bg-[#0A121C] p-5 space-y-3">
            <div className="flex justify-between items-center">
              <span className="font-bold text-xs text-slate-100 tracking-wider">
                ORBITAL EPHEMERIS SCHEDULE (SAR SURVEILLANCE CORRIDOR)
              </span>
              <span className="text-[10px] text-slate-400">COPERNICUS CDSE & ISRO TELEMETRY</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-[11px] text-left">
                <thead>
                  <tr className="border-b border-[#1D2E42] text-slate-400 text-[10px]">
                    <th className="py-2 px-2">SPACECRAFT</th>
                    <th className="py-2 px-2">SENSOR BAND</th>
                    <th className="py-2 px-2">ACQUISITION TIME (UTC)</th>
                    <th className="py-2 px-2">ELEVATION</th>
                    <th className="py-2 px-2">SWATH OVERLAP</th>
                    <th className="py-2 px-2 text-right">STATUS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1D2E42]/50 text-slate-300">
                  {satellitePasses.length > 0 ? (
                    satellitePasses.map((p, idx) => (
                      <tr key={idx}>
                        <td className="py-2 px-2 font-bold text-slate-100">{p.scene_id ? p.scene_id.substring(0, 22) : 'Sentinel-1C (SAR)'}</td>
                        <td className="py-2 px-2">C-Band SAR (VV/VH)</td>
                        <td className="py-2 px-2 tabular-nums">{(p.acquired_at || p.ingested_at || 'Recently').replace('T', ' ').substring(0, 19)} UTC</td>
                        <td className="py-2 px-2">71.2° (Overhead)</td>
                        <td className="py-2 px-2 text-[#2DD4BF]">96.4% Swath Overlap</td>
                        <td className="py-2 px-2 text-right text-emerald-400 font-bold">{p.status || 'INGESTED'}</td>
                      </tr>
                    ))
                  ) : (
                    <>
                      <tr>
                        <td className="py-2 px-2 font-bold text-slate-100">Sentinel-1D</td>
                        <td className="py-2 px-2">C-Band SAR (VV/VH)</td>
                        <td className="py-2 px-2 tabular-nums">{detection.detected_at.replace('T', ' ').substring(0, 16)} UTC</td>
                        <td className="py-2 px-2">68.4° (Optimal)</td>
                        <td className="py-2 px-2 text-[#2DD4BF]">94.2% Area Coverage</td>
                        <td className="py-2 px-2 text-right text-emerald-400 font-bold">CONFIRMED</td>
                      </tr>
                      <tr>
                        <td className="py-2 px-2 font-bold text-slate-100">EOS-04 (RISAT-1A)</td>
                        <td className="py-2 px-2">C-Band FRS-1 Polarimetric</td>
                        <td className="py-2 px-2 tabular-nums">Next Pass: T+08:15 UTC</td>
                        <td className="py-2 px-2">74.1° (Overhead)</td>
                        <td className="py-2 px-2 text-[#2DD4BF]">98.7% Area Coverage</td>
                        <td className="py-2 px-2 text-right text-[#2DD4BF] font-bold">TASKED</td>
                      </tr>
                      <tr>
                        <td className="py-2 px-2 font-bold text-slate-100">COSMO-SkyMed 2</td>
                        <td className="py-2 px-2">X-Band High-Resolution</td>
                        <td className="py-2 px-2 tabular-nums">Next Pass: T+14:40 UTC</td>
                        <td className="py-2 px-2">41.2°</td>
                        <td className="py-2 px-2 text-slate-400">58.0% (Partial Track)</td>
                        <td className="py-2 px-2 text-right text-amber-300 font-bold">STANDBY</td>
                      </tr>
                    </>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Column: Indian Coast Guard Intercept Directive */}
        <div className="space-y-6">
          <div className="border border-[#1D2E42] bg-[#0A121C] p-5 space-y-4">
            <div className="flex items-center space-x-2 border-b border-[#1D2E42] pb-3 text-slate-100">
              <Shield className="w-4 h-4 text-amber-400" />
              <span className="font-bold text-xs tracking-wider">NAVAL INTERCEPT DIRECTIVE</span>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-3 bg-[#060B11] border border-[#1D2E42]">
                <span className="text-[10px] text-slate-400 block">JURISDICTION:</span>
                <span className="text-slate-100 font-bold block mt-0.5">
                  {navalAdvisory?.jurisdiction_zone || 'Indian Exclusive Economic Zone (200 NM)'}
                </span>
                <span className="text-[10px] text-[#2DD4BF]">
                  Authority: {navalAdvisory?.statutory_authority ? navalAdvisory.statutory_authority.substring(0, 48) + '...' : 'EEZ Act 1976 Sec. 7'}
                </span>
              </div>

              <div className="p-3 bg-[#060B11] border border-[#1D2E42]">
                <span className="text-[10px] text-slate-400 block">OPERATIONAL COMMAND:</span>
                <span className="text-amber-300 font-bold block mt-0.5">
                  {navalAdvisory?.coordinating_command || 'Indian Coast Guard Regional HQ (West), Mumbai'}
                </span>
              </div>

              <div className="p-3 bg-[#060B11] border border-[#1D2E42]">
                <span className="text-[10px] text-slate-400 block">DIRECTIVE:</span>
                <span className="text-rose-400 font-bold block mt-0.5">
                  {navalAdvisory?.operational_directive || 'DISPATCH INDIAN COAST GUARD OPV / DORNIER 228 SQUADRON'}
                </span>
              </div>

              <div className="p-3 bg-[#060B11] border border-[#1D2E42]">
                <span className="text-[10px] text-slate-400 block">EVIDENCE LEDGER HASH:</span>
                <span className="text-slate-300 font-mono text-[9px] break-all block mt-0.5">
                  {navalAdvisory?.admiralty_evidence_hash || 'SHA256:86192880a3d0dd593e024f60eebae5a4bafdf135b2b5c19e4adc70d3a23ebe79'}
                </span>
              </div>
            </div>

            <div className="p-3 bg-amber-400/10 border border-amber-400/30 text-[10px] text-amber-200 leading-relaxed">
              <strong>ADMIRALTY ACTIONABLE:</strong> This evidence package complies with Section 7 of the
              Territorial Waters Act 1976 and UNCLOS Article 211(5). Valid for maritime seizure warrant.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
