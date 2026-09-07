import React, { useState } from 'react';
import { Key, Check } from 'lucide-react';

interface MapboxKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentKey: string;
  onSave: (key: string) => void;
}

export const MapboxKeyModal: React.FC<MapboxKeyModalProps> = ({
  isOpen,
  onClose,
  currentKey,
  onSave,
}) => {
  const [tokenInput, setTokenInput] = useState(currentKey);

  if (!isOpen) return null;

  const handleSave = () => {
    onSave(tokenInput.trim());
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 select-none">
      <div className="w-full max-w-md bg-[#0A121C] border border-[#1D2E42] p-6 shadow-2xl font-mono text-xs">
        <div className="flex items-center justify-between pb-3 border-b border-[#1D2E42]">
          <div className="flex items-center space-x-2 text-[#2DD4BF] font-bold">
            <Key className="w-4 h-4" />
            <span>MAPBOX API KEY CONFIGURATION</span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">✕</button>
        </div>

        <div className="py-4 space-y-3 text-slate-300">
          <p className="leading-relaxed">
            By default, OilTrace uses <strong>ESRI World Imagery</strong> and <strong>ESRI Ocean Bathymetry</strong>, which are 100% free and have zero watermarks.
          </p>
          <p className="leading-relaxed text-slate-400 text-[11px]">
            If you have a Mapbox Public Access Token (<code className="text-[#2DD4BF]">pk.eyJ1...</code>), you can paste it below to enable Mapbox Satellite Streets and high-res vector tiles:
          </p>

          <div>
            <label className="block text-[10px] text-slate-400 uppercase tracking-wider mb-1">Mapbox Public Token</label>
            <input
              type="text"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="pk.eyJ1..."
              className="w-full bg-[#060B11] border border-[#1D2E42] px-3 py-2 text-slate-100 font-mono text-xs focus:border-[#2DD4BF] focus:outline-none"
            />
          </div>
        </div>

        <div className="flex justify-end space-x-2 pt-3 border-t border-[#1D2E42]">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-[#1D2E42] text-slate-400 hover:text-white"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-5 py-2 bg-[#2DD4BF] text-[#060B11] font-bold flex items-center space-x-1.5 hover:bg-[#26bba7]"
          >
            <Check className="w-3.5 h-3.5" />
            <span>Save & Apply</span>
          </button>
        </div>
      </div>
    </div>
  );
};
