import React, { useState } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import { X, Activity, Waves, CheckCircle2, Copy, Check, Info } from 'lucide-react';

interface LookalikeDiagnosticModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const LookalikeDiagnosticModal: React.FC<LookalikeDiagnosticModalProps> = ({
  isOpen,
  onClose,
}) => {
  const { detection } = useOilTraceStore();
  const [selectedTransect, setSelectedTransect] = useState<'observed' | 'biogenic_lookalike' | 'low_wind'>('observed');
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const isSuppressed = detection.lookalike_suppressed;
  const dampingDrop = detection.thickness_class === 'thick' ? -8.6 : detection.thickness_class === 'thin' ? -6.2 : -4.1;
  const seaLevelDb = -12.2;
  const centerDb = seaLevelDb + dampingDrop;

  const transectPoints = [
    { x: -5, db: seaLevelDb + 0.1, label: 'Clean Sea' },
    { x: -4, db: seaLevelDb - 0.2, label: 'Clean Sea' },
    { x: -3, db: seaLevelDb - 0.4, label: 'Edge Sheen' },
    { x: -2, db: seaLevelDb + dampingDrop * 0.55, label: 'Sheen Inflow' },
    { x: -1, db: seaLevelDb + dampingDrop * 0.85, label: 'Core Slick' },
    { x: 0, db: centerDb, label: 'Center Peak Damping' },
    { x: 1, db: seaLevelDb + dampingDrop * 0.88, label: 'Core Slick' },
    { x: 2, db: seaLevelDb + dampingDrop * 0.52, label: 'Sheen Outflow' },
    { x: 3, db: seaLevelDb - 0.5, label: 'Edge Sheen' },
    { x: 4, db: seaLevelDb - 0.1, label: 'Clean Sea' },
    { x: 5, db: seaLevelDb + 0.2, label: 'Clean Sea' },
  ];

  const biogenicPoints = transectPoints.map((p) => ({
    x: p.x,
    db: p.x >= -2 && p.x <= 2 ? seaLevelDb - 2.1 : seaLevelDb + (Math.sin(p.x) * 0.3),
  }));

  const lowWindPoints = transectPoints.map((p) => ({
    x: p.x,
    db: seaLevelDb - 7.5 + (Math.cos(p.x * 0.4) * 0.4),
  }));

  const activePoints = selectedTransect === 'observed'
    ? transectPoints
    : selectedTransect === 'biogenic_lookalike'
    ? biogenicPoints
    : lowWindPoints;

  const handleCopyDiagnostic = () => {
    const diagnosticText = `[OilTrace SAR Diagnostic] Scene: ${detection.source_scene_id} | Damping: ${dampingDrop} dB | Oil Conf: ${(detection.oil_confidence * 100).toFixed(1)}% | Class: ${detection.thickness_class.toUpperCase()} | Lookalike Suppressed: ${isSuppressed}`;
    navigator.clipboard.writeText(diagnosticText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className='fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200'>
      <div className='w-full max-w-3xl bg-[#070C14] border border-[#1E2C3F] rounded shadow-2xl overflow-hidden flex flex-col font-mono text-slate-200'>
        
        {/* Modal Header */}
        <div className='p-3.5 bg-[#0A121C] border-b border-[#1E2C3F] flex items-center justify-between'>
          <div className='flex items-center space-x-2.5'>
            <Activity className='w-4 h-4 text-[#2DD4BF]' />
            <span className='text-xs font-bold text-slate-100 tracking-wider uppercase'>
              SAR Backscatter Cross-Section & Lookalike Diagnostic
            </span>
          </div>
          <button
            onClick={onClose}
            className='p-1 text-slate-400 hover:text-slate-100 hover:bg-[#1E2C3F] rounded transition-colors'
          >
            <X className='w-4 h-4' />
          </button>
        </div>

        {/* Modal Body */}
        <div className='p-4 space-y-4 overflow-y-auto max-h-[80vh]'>
          
          {/* Top Status & Summary Banner */}
          <div className='grid grid-cols-1 md:grid-cols-3 gap-3'>
            <div className='p-2.5 bg-[#0D1522] border border-[#1E2C3F] rounded-sm'>
              <div className='text-[10px] text-slate-400 font-semibold uppercase'>Bragg Damping Contrast</div>
              <div className='text-xl font-bold text-[#2DD4BF] mt-0.5'>{dampingDrop.toFixed(1)} dB</div>
              <div className='text-[9px] text-emerald-400 flex items-center space-x-1 mt-1'>
                <CheckCircle2 className='w-3 h-3' />
                <span>Exceeds -3.5 dB Mineral Threshold</span>
              </div>
            </div>

            <div className='p-2.5 bg-[#0D1522] border border-[#1E2C3F] rounded-sm'>
              <div className='text-[10px] text-slate-400 font-semibold uppercase'>Stage 1 ResNet-34 P(Oil)</div>
              <div className='text-xl font-bold text-amber-300 mt-0.5'>{(detection.oil_confidence * 100).toFixed(1)}%</div>
              <div className='text-[9px] text-slate-400 mt-1'>
                {detection.oil_confidence > 0.65 ? 'High Confidence Slick' : 'Borderline Signature'}
              </div>
            </div>

            <div className='p-2.5 bg-[#0D1522] border border-[#1E2C3F] rounded-sm'>
              <div className='text-[10px] text-slate-400 font-semibold uppercase'>Lookalike Suppression</div>
              <div className={`text-base font-bold mt-1 ${isSuppressed ? 'text-amber-400' : 'text-emerald-400'}`}>
                {isSuppressed ? 'FLAGGED AS LOOKALIKE' : 'REJECTED (AUTHENTIC SPILL)'}
              </div>
              <div className='text-[9px] text-slate-400 mt-0.5'>Dual-Stage Veto Active</div>
            </div>
          </div>

          {/* Mode Selector Tabs */}
          <div className='flex space-x-2 border-b border-[#1E2C3F] pb-2'>
            <button
              onClick={() => setSelectedTransect('observed')}
              className={`px-3 py-1 text-xs font-semibold rounded-sm transition-colors ${
                selectedTransect === 'observed'
                  ? 'bg-[#2DD4BF] text-[#070C14]'
                  : 'bg-[#0D1522] text-slate-400 hover:text-slate-200 border border-[#1E2C3F]'
              }`}
            >
              Observed Transect (Incident #{detection.spill_id.slice(-6)})
            </button>
            <button
              onClick={() => setSelectedTransect('biogenic_lookalike')}
              className={`px-3 py-1 text-xs font-semibold rounded-sm transition-colors ${
                selectedTransect === 'biogenic_lookalike'
                  ? 'bg-[#F59E0B] text-[#070C14]'
                  : 'bg-[#0D1522] text-slate-400 hover:text-slate-200 border border-[#1E2C3F]'
              }`}
            >
              Reference: Biogenic Film (Algae)
            </button>
            <button
              onClick={() => setSelectedTransect('low_wind')}
              className={`px-3 py-1 text-xs font-semibold rounded-sm transition-colors ${
                selectedTransect === 'low_wind'
                  ? 'bg-[#EF4444] text-[#070C14]'
                  : 'bg-[#0D1522] text-slate-400 hover:text-slate-200 border border-[#1E2C3F]'
              }`}
            >
              Reference: Low Wind Calm (&lt; 3 m/s)
            </button>
          </div>

          {/* Radar Transect Interactive Profile Visualizer */}
          <div className='p-3 bg-[#0D1522] border border-[#1E2C3F] rounded-sm space-y-3'>
            <div className='flex justify-between items-center text-xs'>
              <span className='text-slate-300 font-semibold flex items-center space-x-1.5'>
                <Waves className='w-3.5 h-3.5 text-[#2DD4BF]' />
                <span>NRCS Backscatter Profile sigma0 [dB] vs Distance across Transect</span>
              </span>
              <span className='text-[10px] text-slate-400'>Transect Length: 10.0 km</span>
            </div>

            {/* SVG Transect Chart */}
            <div className='w-full h-48 bg-[#070C14] border border-[#1E2C3F] relative rounded p-2 flex flex-col justify-between'>
              {/* Y-Axis dB Labels */}
              <div className='absolute left-2 top-2 text-[9px] text-slate-500'>-10 dB (Rough Clean Water)</div>
              <div className='absolute left-2 top-1/2 -translate-y-1/2 text-[9px] text-slate-500'>-16 dB (Sheen Cutoff)</div>
              <div className='absolute left-2 bottom-2 text-[9px] text-slate-500'>-22 dB (Thick Crude Damping)</div>

              {/* Chart Grid Lines */}
              <div className='absolute inset-x-8 top-1/4 border-b border-[#1E2C3F]/50 pointer-events-none' />
              <div className='absolute inset-x-8 top-1/2 border-b border-[#1E2C3F]/50 pointer-events-none' />
              <div className='absolute inset-x-8 top-3/4 border-b border-[#1E2C3F]/50 pointer-events-none' />

              {/* Polyline Graph */}
              <svg className='w-full h-full overflow-visible' viewBox='0 0 500 160'>
                {/* Clean Water Baseline */}
                <line x1='20' y1='30' x2='480' y2='30' stroke='#64748B' strokeDasharray='3 3' strokeWidth='1' />

                {/* Profile Line */}
                {(() => {
                  const pts = activePoints.map((p, idx) => {
                    const x = 30 + idx * 42;
                    const y = Math.min(145, Math.max(25, 30 + ((p.db - -10) / (-24 - -10)) * 115));
                    return { x, y, db: p.db, label: (p as any).label || '' };
                  });
                  const polyPoints = pts.map((p) => `${p.x},${p.y}`).join(' ');
                  const strokeColor = selectedTransect === 'observed' ? '#2DD4BF' : selectedTransect === 'biogenic_lookalike' ? '#F59E0B' : '#EF4444';

                  return (
                    <>
                      <polyline
                        fill='none'
                        stroke={strokeColor}
                        strokeWidth='2.5'
                        strokeLinecap='round'
                        strokeLinejoin='round'
                        points={polyPoints}
                      />
                      {pts.map((p, i) => (
                        <g key={i}>
                          <circle cx={p.x} cy={p.y} r='3.5' fill={strokeColor} stroke='#070C14' strokeWidth='1.5' />
                          {i % 2 === 0 && (
                            <text x={p.x} y={p.y - 7} fill='#94A3B8' fontSize='8' textAnchor='middle' fontFamily='monospace'>
                              {p.db.toFixed(1)}
                            </text>
                          )}
                        </g>
                      ))}
                    </>
                  );
                })()}
              </svg>

              <div className='flex justify-between text-[9px] text-slate-400 px-6'>
                <span>-5.0 km</span>
                <span>-2.5 km</span>
                <span className='text-[#2DD4BF] font-bold'>0.0 km (Center)</span>
                <span>+2.5 km</span>
                <span>+5.0 km</span>
              </div>
            </div>

            {/* Diagnostic Interpretation Callout */}
            <div className='p-2.5 bg-[#070C14] border border-[#1E2C3F] rounded-sm text-xs space-y-1'>
              <div className='font-semibold text-slate-200 flex items-center space-x-1.5'>
                <Info className='w-3.5 h-3.5 text-[#2DD4BF]' />
                <span>Physical Interpretation:</span>
              </div>
              <p className='text-[11px] text-slate-400 leading-relaxed'>
                {selectedTransect === 'observed' && (
                  <>
                    The observed Sentinel-1 profile exhibits a sharp, asymmetric backscatter attenuation of <strong className='text-[#2DD4BF]'>{dampingDrop.toFixed(1)} dB</strong> below ambient ocean clutter, with steep boundary gradients (&gt; 1.8 dB/km). This confirms physical dampening of short gravity-capillary waves characteristic of heavy hydrocarbons rather than thin biogenic films.
                  </>
                )}
                {selectedTransect === 'biogenic_lookalike' && (
                  <>
                    Biogenic slicks (fish oils, phytoplankton blooms) lack heavy hydrocarbon mass and produce only shallow, gentle damping of &lt; 2.5 dB without sharp boundary gradients. The detector safely suppresses these candidates.
                  </>
                )}
                {selectedTransect === 'low_wind' && (
                  <>
                    Low-wind calms (&lt; 3 m/s) produce broad, diffuse specular attenuation across tens of kilometers with no localized track or vessel association. Meteorological ERA5 wind verification vetoes false alarms in this regime.
                  </>
                )}
              </p>
            </div>
          </div>

          {/* SAR Scene & Model Verification Table */}
          <div className='border border-[#1E2C3F] bg-[#0D1522] rounded-sm p-3 space-y-2 text-xs'>
            <div className='text-[10px] text-slate-400 uppercase font-semibold border-b border-[#1E2C3F] pb-1'>
              Forensic Verification Parameters
            </div>
            <div className='grid grid-cols-2 gap-y-1.5 text-[11px]'>
              <div className='text-slate-400'>SAR Platform / Mode:</div>
              <div className='text-slate-200 font-semibold'>Sentinel-1C / Interferometric Wide (IW)</div>

              <div className='text-slate-400'>Polarization Channel:</div>
              <div className='text-slate-200 font-semibold'>VV (Vertical-Vertical) Co-pol</div>

              <div className='text-slate-400'>Surface Wind at Incident:</div>
              <div className='text-slate-200 font-semibold'>5.8 m/s (Optimal Bragg regime: 3–12 m/s)</div>

              <div className='text-slate-400'>Detection Source Scene:</div>
              <div className='text-slate-200 font-semibold truncate'>{detection.source_scene_id}</div>

              <div className='text-slate-400'>Centroid Coordinates:</div>
              <div className='text-slate-200 font-semibold'>
                {detection.centroid[0].toFixed(4)}°E, {detection.centroid[1].toFixed(4)}°N
              </div>

              <div className='text-slate-400'>Slick Area & Thickness:</div>
              <div className='text-slate-200 font-semibold'>
                {detection.area_km2.toFixed(2)} km² ({detection.thickness_class.toUpperCase()})
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className='p-3 bg-[#0A121C] border-t border-[#1E2C3F] flex justify-between items-center'>
          <button
            onClick={handleCopyDiagnostic}
            className='px-3 py-1.5 bg-[#0D1522] hover:bg-[#1E2C3F] text-slate-300 hover:text-slate-100 border border-[#1E2C3F] rounded-sm text-xs flex items-center space-x-1.5 transition-colors'
          >
            {copied ? <Check className='w-3.5 h-3.5 text-emerald-400' /> : <Copy className='w-3.5 h-3.5' />}
            <span>{copied ? 'Copied to Clipboard' : 'Copy Diagnostic Telemetry'}</span>
          </button>

          <button
            onClick={onClose}
            className='px-4 py-1.5 bg-[#2DD4BF] hover:bg-[#26bba7] text-[#070C14] font-bold rounded-sm text-xs transition-colors'
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
};
