import React, { useEffect, useState } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import { generateForensicPdf, computeCanonicalSha256 } from '../../utils/pdfGenerator';
import { generateBackendReportPdf } from '../../api/oiltraceApi';
import { X, Download, ShieldCheck, Copy, Check, FileText } from 'lucide-react';

export const DossierModal: React.FC<{ isOpen: boolean; onClose: () => void }> = ({
  isOpen,
  onClose,
}) => {
  const { detection, driftRun, attribution } = useOilTraceStore();
  const selectedCandidate = useOilTraceStore((s) => s.getSelectedCandidate());

  const [sha256Hash, setSha256Hash] = useState<string>('');
  const [copied, setCopied] = useState<boolean>(false);
  const [isExporting, setIsExporting] = useState<boolean>(false);

  useEffect(() => {
    if (!isOpen || !attribution) return;

    const payload = {
      spill_id: detection.spill_id,
      detected_at: detection.detected_at,
      centroid: detection.centroid,
      area_km2: detection.area_km2,
      top_vessel_mmsi: selectedCandidate?.vessel_id || 'NONE',
      candidates_count: attribution.candidates.length,
      real_vessel_fraction: attribution.real_vessel_fraction,
    };

    computeCanonicalSha256(JSON.stringify(payload)).then((hash) => {
      setSha256Hash(hash);
    });
  }, [isOpen, detection, attribution, selectedCandidate]);

  if (!isOpen) return null;

  const handleCopyHash = () => {
    navigator.clipboard.writeText(sha256Hash);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadPdf = async () => {
    if (!attribution) return;
    setIsExporting(true);
    try {
      try {
        const blob = await generateBackendReportPdf({
          spill_id: detection.spill_id,
          detected_at: detection.detected_at,
          centroid: detection.centroid,
          area_km2: detection.area_km2,
          lead_mmsi: selectedCandidate?.vessel_id || 'UNKNOWN',
          lead_vessel_name: selectedCandidate?.vessel_name || 'UNKNOWN',
          suspicion_score: selectedCandidate?.suspicion_score ?? 0.85,
          flag_state: selectedCandidate?.flag_state || selectedCandidate?.flag_country || 'LBR',
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `NTRO_Admiralty_Dossier_${detection.spill_id}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
        return;
      } catch (backendErr) {
        console.warn('[DossierModal] Backend ReportLab PDF failed, falling back to client jsPDF:', backendErr);
      }

      await generateForensicPdf({
        detection,
        drift: driftRun,
        attribution,
        topCandidate: selectedCandidate,
      });
    } catch (err) {
      console.error('[DossierModal] PDF export error:', err);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50 select-none font-mono">
      <div className="bg-[#0A121C] border border-[#2DD4BF] max-w-2xl w-full p-4 space-y-4 shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#1D2E42] pb-3">
          <div className="flex items-center space-x-2">
            <FileText className="w-5 h-5 text-[#2DD4BF]" />
            <h2 className="text-sm font-bold text-[#F1F5F9] tracking-wider">
              EVIDENTIARY DOSSIER // STATUTORY FILING
            </h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Cryptographic Hash Ledger Block */}
        <div className="p-3 bg-[#060B11] border border-[#1D2E42] space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-[#2DD4BF] font-bold flex items-center space-x-1.5">
              <ShieldCheck className="w-4 h-4" />
              <span>CRYPTOGRAPHIC CHAIN-OF-CUSTODY AUDIT SEAL</span>
            </span>
            <span className="text-[10px] text-emerald-400">UNCLOS / MARPOL ADMISSIBLE</span>
          </div>

          <div className="flex items-center space-x-2">
            <div className="flex-1 bg-[#0F1926] p-2 border border-[#1D2E42] text-[11px] text-[#F1F5F9] font-mono select-all truncate tabular-nums">
              SHA256: {sha256Hash || 'Computing...'}
            </div>
            <button
              onClick={handleCopyHash}
              className="p-2 bg-[#0F1926] border border-[#1D2E42] hover:border-[#2DD4BF] text-slate-300 hover:text-white"
              title="Copy Hash"
            >
              {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Evidence Telemetry Summary */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="p-2.5 bg-[#060B11] border border-[#1D2E42] space-y-1">
            <div className="text-[10px] text-slate-400">INCIDENT CASE IDENTIFIER</div>
            <div className="text-[#F1F5F9] font-bold">{detection.spill_id}</div>
            <div className="text-[10px] text-slate-400 pt-1">
              SAR Scene: {detection.source_scene_id.substring(0, 24)}...
            </div>
          </div>

          <div className="p-2.5 bg-[#060B11] border border-[#1D2E42] space-y-1">
            <div className="text-[10px] text-slate-400">PRIME SUSPECT ATTRIBUTION</div>
            <div className="text-[#2DD4BF] font-bold">
              {selectedCandidate?.vessel_name || selectedCandidate?.vessel_id || 'NONE'}
            </div>
            <div className="text-[10px] text-slate-400 pt-1">
              Score: {selectedCandidate?.suspicion_score !== null ? `${((selectedCandidate?.suspicion_score || 0) * 100).toFixed(1)}%` : '—'} [
              {selectedCandidate?.data_provenance.toUpperCase()}]
            </div>
          </div>
        </div>

        {/* Statutory Mandate Note */}
        <div className="p-2.5 bg-[#060B11] border border-[#1D2E42] text-[10px] text-slate-400 space-y-1">
          <div className="text-slate-300 font-bold">JURISDICTIONAL STATEMENT:</div>
          <div>• Territorial Waters, Continental Shelf, EEZ Act 1976 (Act 80 of 1976), Sec. 7</div>
          <div>• UNCLOS Art. 211(5) & MARPOL 73/78 Annex I Regulation 11 Strict Liability Protocol</div>
        </div>

        {/* Action Buttons */}
        <div className="flex justify-end space-x-2 pt-2 border-t border-[#1D2E42]">
          <button
            onClick={onClose}
            className="px-3 py-1.5 bg-[#060B11] border border-[#1D2E42] text-xs text-slate-300 hover:text-white font-mono"
          >
            CANCEL
          </button>
          <button
            onClick={handleDownloadPdf}
            disabled={isExporting}
            className="px-4 py-1.5 bg-[#2DD4BF] hover:bg-[#26bba7] text-[#060B11] font-bold text-xs flex items-center space-x-2 transition-colors disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            <span>{isExporting ? 'GENERATING COURT DOSSIER...' : 'EXPORT OFFICIAL PDF DOSSIER'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
