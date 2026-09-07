import React, { useEffect, useState, useRef } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import { ScenarioItem } from '../../types';
import {
  Plus, Search, Grid, List, Layers, Ship, Droplet, AlertCircle, ArrowRight, X,
  Upload, MapPin, Calendar, ChevronRight, Star
} from 'lucide-react';

// Offline-ready scenario cards with local tactical previews
const SCENARIO_IMAGES: Record<string, string> = {
  mumbai_gulf_flagship: '/sar_enhanced.png',
  gulf_of_kutch_crude: '/sar_enhanced.png',
  chennai_ennore_port: '/sar_enhanced.png',
  arabian_sea_dark_vessel: '/sar_enhanced.png',
};

const FALLBACK_IMAGE = '/sar_enhanced.png';

interface CreateModalState {
  isOpen: boolean;
  file: File | null;
  name: string;
  lon: string;
  lat: string;
  isDragging: boolean;
  isCreating: boolean;
  error: string | null;
}

export const ScenarioPickerScreen: React.FC = () => {
  const { availableScenarios, isLoadingScenarios, loadScenario, refreshScenarios, createCustomScenario } = useOilTraceStore();
  const [activeTab, setActiveTab] = useState<'all' | 'recent' | 'training' | 'custom'>('all');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [searchQuery, setSearchQuery] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [createModal, setCreateModal] = useState<CreateModalState>({
    isOpen: false, file: null, name: 'Custom SAR Incident', lon: '71.61', lat: '18.42',
    isDragging: false, isCreating: false, error: null,
  });

  useEffect(() => {
    refreshScenarios();
  }, [refreshScenarios]);

  // Filter logic
  const filteredScenarios = availableScenarios.filter((s) => {
    const q = searchQuery.toLowerCase();
    const matchesSearch = !q || s.name.toLowerCase().includes(q) || s.location_name?.toLowerCase().includes(q) || s.description?.toLowerCase().includes(q);
    const matchesTab =
      activeTab === 'all' ||
      (activeTab === 'custom' && s.tags?.includes('CUSTOM SCENARIO')) ||
      (activeTab === 'training' && (s.tags?.includes('CAUSAL VETO') || s.spill_area_km2 && s.spill_area_km2 < 6)) ||
      activeTab === 'recent';
    return matchesSearch && matchesTab;
  });

  // Drag handlers for create modal
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setCreateModal((prev) => ({ ...prev, isDragging: true }));
  };
  const handleDragLeave = () => setCreateModal((prev) => ({ ...prev, isDragging: false }));
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      setCreateModal((prev) => ({ ...prev, file: droppedFile, isDragging: false, name: droppedFile.name.replace(/\.[^/.]+$/, '') }));
    }
  };

  const handleCreateSubmit = async () => {
    if (!createModal.file) return;
    const lon = parseFloat(createModal.lon);
    const lat = parseFloat(createModal.lat);
    if (isNaN(lon) || isNaN(lat)) {
      setCreateModal((prev) => ({ ...prev, error: 'Invalid coordinates.' }));
      return;
    }
    setCreateModal((prev) => ({ ...prev, isCreating: true, error: null }));
    try {
      await createCustomScenario(createModal.file, createModal.name, lon, lat);
      setCreateModal({ isOpen: false, file: null, name: 'Custom SAR Incident', lon: '71.61', lat: '18.42', isDragging: false, isCreating: false, error: null });
    } catch (err: any) {
      setCreateModal((prev) => ({ ...prev, isCreating: false, error: err.message || 'Creation failed.' }));
    }
  };

  const getPriorityBadge = (s: ScenarioItem) => {
    if (s.tags?.includes('FLAGSHIP')) return { label: 'High Priority', color: 'bg-rose-500 text-white' };
    if (s.tags?.includes('DARK VESSEL')) return { label: 'Dark Vessel', color: 'bg-amber-500 text-[#060B11]' };
    if (s.tags?.includes('CAUSAL VETO')) return { label: 'Training', color: 'bg-sky-500 text-white' };
    return { label: 'Normal', color: 'bg-slate-600 text-white' };
  };

  const getStatusChip = (s: ScenarioItem) => {
    if (s.tags?.includes('FLAGSHIP')) return { label: 'Oil Slick Detected', color: 'text-[#2DD4BF] border-[#2DD4BF]/40' };
    if (s.tags?.includes('DARK VESSEL')) return { label: 'Under Analysis', color: 'text-amber-300 border-amber-400/40' };
    return { label: 'Slick Detected', color: 'text-[#2DD4BF] border-[#2DD4BF]/40' };
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#060B11] text-[#F1F5F9] overflow-hidden">
      {/* Hero header with world map overlay */}
      <div className="relative border-b border-[#1D2E42] bg-[#0A121C] overflow-hidden shrink-0">
        {/* Background decorative world map dots */}
        <div className="absolute inset-0 opacity-5 bg-[radial-gradient(circle_at_50%_50%,#2DD4BF_1px,transparent_1px)] bg-[length:20px_20px]" />
        <div className="relative p-6 pb-4">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-bold text-slate-100 mb-1">Select a Scenario</h1>
              <p className="text-sm text-slate-400">Choose a region and incident to start investigation</p>
              <div className="absolute top-4 right-6 text-[10px] text-[#2DD4BF] font-mono tracking-wider font-bold">
                NTRO MDA // SPATIO-TEMPORAL MARITIME FORENSICS
              </div>
            </div>
          </div>

          {/* Tab bar + search + sort + view */}
          <div className="flex items-center justify-between mt-4">
            <div className="flex items-center bg-[#060B11] border border-[#1D2E42] p-0.5">
              {(['all', 'recent', 'training', 'custom'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-1.5 text-xs font-mono font-bold capitalize transition-all ${
                    activeTab === tab
                      ? 'bg-[#2DD4BF] text-[#060B11]'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {tab === 'all' ? 'All Scenarios' : tab.charAt(0).toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </div>

            <div className="flex items-center space-x-2">
              {/* Sort dropdown */}
              <div className="flex items-center space-x-2 bg-[#060B11] border border-[#1D2E42] px-3 py-1.5 text-xs font-mono">
                <span className="text-slate-400">Sort by:</span>
                <span className="text-slate-200">Newest</span>
              </div>

              {/* View toggle */}
              <div className="flex bg-[#060B11] border border-[#1D2E42]">
                <button
                  onClick={() => setViewMode('grid')}
                  className={`p-1.5 transition-colors ${viewMode === 'grid' ? 'bg-[#2DD4BF] text-[#060B11]' : 'text-slate-400 hover:text-white'}`}
                >
                  <Grid className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setViewMode('list')}
                  className={`p-1.5 transition-colors ${viewMode === 'list' ? 'bg-[#2DD4BF] text-[#060B11]' : 'text-slate-400 hover:text-white'}`}
                >
                  <List className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Grid of scenario cards */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoadingScenarios ? (
          <div className="flex items-center justify-center h-40 text-slate-400 font-mono text-sm">
            <div className="animate-spin w-5 h-5 border-2 border-[#2DD4BF] border-t-transparent rounded-full mr-3" />
            Loading scenarios...
          </div>
        ) : (
          <div className={viewMode === 'grid'
            ? 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5'
            : 'flex flex-col space-y-3'
          }>
            {filteredScenarios.map((s) => {
              const badge = getPriorityBadge(s);
              const status = getStatusChip(s);
              const imgSrc = SCENARIO_IMAGES[s.scenario_id] || FALLBACK_IMAGE;

              if (viewMode === 'grid') {
                return (
                  <button
                    key={s.scenario_id}
                    onClick={() => loadScenario(s)}
                    className="group relative overflow-hidden border border-[#1D2E42] bg-[#0A121C] hover:border-[#2DD4BF] transition-all text-left"
                    style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.5)' }}
                  >
                    {/* Card image with tactical radar crosshairs and scanning sweep */}
                    <div className="relative h-44 overflow-hidden border-b border-[#1D2E42]">
                      <img
                        src={imgSrc}
                        alt={s.name}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500 opacity-80 group-hover:opacity-100"
                        loading="lazy"
                        onError={(e) => { (e.target as HTMLImageElement).src = FALLBACK_IMAGE; }}
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-[#0A121C] via-[#0A121C]/30 to-transparent" />

                      {/* Tactical HUD Crosshairs */}
                      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-30 group-hover:opacity-60 transition-opacity">
                        <div className="w-full h-[1px] bg-[#2DD4BF] absolute" />
                        <div className="h-full w-[1px] bg-[#2DD4BF] absolute" />
                        <div className="w-10 h-10 border border-[#2DD4BF] rounded-full absolute" />
                      </div>

                      {/* Scanning Sweep Line */}
                      <div className="absolute inset-0 pointer-events-none overflow-hidden opacity-0 group-hover:opacity-100 transition-opacity">
                        <div className="w-full h-[2px] bg-[#2DD4BF]/70 shadow-[0_0_8px_#2DD4BF] animate-[pulse_2s_ease-in-out_infinite]" />
                      </div>

                      {/* Priority badge */}
                      {s.tags?.includes('FLAGSHIP') && (
                        <div className="absolute top-2.5 left-2.5 flex items-center space-x-1 bg-[#2DD4BF] text-[#060B11] text-[9px] font-bold px-2 py-0.5 font-mono tracking-wider rounded-sm">
                          <Star className="w-2.5 h-2.5 fill-current" />
                          <span>NTRO PRIMARY</span>
                        </div>
                      )}
                      {s.tags?.includes('DARK VESSEL') && (
                        <div className="absolute top-2.5 left-2.5 flex items-center space-x-1 bg-rose-500 text-white text-[9px] font-bold px-2 py-0.5 font-mono tracking-wider rounded-sm animate-pulse">
                          <AlertCircle className="w-2.5 h-2.5" />
                          <span>DARK TARGET</span>
                        </div>
                      )}

                      {/* Hindcast status badge */}
                      <div className="absolute top-2.5 right-2.5 text-[9px] font-mono font-bold px-2 py-0.5 bg-[#060B11]/90 border border-[#1D2E42] text-[#2DD4BF] rounded-sm">
                        {s.has_drift_ensemble ? 'HINDCAST READY' : 'LIVE COMPUTE'}
                      </div>
                    </div>

                    {/* Card content */}
                    <div className="p-4 flex flex-col justify-between flex-1">
                      <div>
                        <h3 className="text-sm font-bold text-slate-100 group-hover:text-[#2DD4BF] transition-colors leading-tight font-mono">
                          {s.name}
                        </h3>
                        {s.location_name && (
                          <p className="text-[11px] text-slate-400 mt-1 flex items-center space-x-1">
                            <MapPin className="w-3 h-3 text-[#2DD4BF]/70 shrink-0" />
                            <span className="truncate">{s.location_name}</span>
                          </p>
                        )}

                        <div className="flex items-center space-x-1.5 mt-2 text-[10px] text-slate-400 font-mono">
                          <Calendar className="w-3 h-3 text-slate-500" />
                          <span>{s.detected_at?.replace('T', ' ').substring(0, 16) || '—'} UTC</span>
                        </div>
                      </div>

                      {/* Stats telemetry row */}
                      <div className="mt-3 pt-3 border-t border-[#1D2E42] grid grid-cols-3 gap-2 text-[10px] font-mono">
                        <div className="p-1.5 bg-[#060B11] border border-[#1D2E42]/60 text-center rounded-sm">
                          <div className="text-[8px] text-slate-500 uppercase">AREA</div>
                          <div className="font-bold text-[#2DD4BF]">{s.spill_area_km2 ? `${s.spill_area_km2} km²` : '—'}</div>
                        </div>
                        <div className="p-1.5 bg-[#060B11] border border-[#1D2E42]/60 text-center rounded-sm">
                          <div className="text-[8px] text-slate-500 uppercase">SUSPECTS</div>
                          <div className="font-bold text-slate-200">{s.suspect_count ?? 3} AIS</div>
                        </div>
                        <div className="p-1.5 bg-[#060B11] border border-[#1D2E42]/60 text-center rounded-sm">
                          <div className="text-[8px] text-slate-500 uppercase">STATUS</div>
                          <div className="font-bold text-amber-400 truncate">{badge.label}</div>
                        </div>
                      </div>

                      {/* High-contrast action button */}
                      <div className="mt-3.5 w-full bg-[#1E2C3F] group-hover:bg-[#2DD4BF] text-[#2DD4BF] group-hover:text-[#060B11] text-[10px] font-mono font-bold py-2 px-3 rounded-sm flex items-center justify-center space-x-2 transition-all">
                        <span>LAUNCH INVESTIGATION</span>
                        <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
                      </div>
                    </div>
                  </button>
                );
              }

              // List view
              return (
                <button
                  key={s.scenario_id}
                  onClick={() => loadScenario(s)}
                  className="group w-full flex items-center space-x-4 border border-[#1D2E42] bg-[#0A121C] hover:border-[#2DD4BF] p-4 transition-all text-left"
                >
                  <div className="w-20 h-16 shrink-0 overflow-hidden">
                    <img src={imgSrc} alt={s.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-2">
                      <h3 className="text-sm font-bold text-slate-100 group-hover:text-[#2DD4BF] transition-colors">{s.name}</h3>
                      {s.tags?.includes('FLAGSHIP') && <span className="text-[9px] bg-amber-500 text-[#060B11] px-1.5 py-0.5 font-bold">FLAGSHIP</span>}
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">{s.location_name} · {s.detected_at?.split('T')[0]}</div>
                    <div className="text-[10px] text-slate-500 mt-1 truncate">{s.description}</div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-500 group-hover:text-[#2DD4BF] transition-colors shrink-0" />
                </button>
              );
            })}

            {/* Custom Scenario Card — always last */}
            <button
              onClick={() => setCreateModal((prev) => ({ ...prev, isOpen: true }))}
              className="group relative border-2 border-dashed border-[#1D2E42] hover:border-[#2DD4BF] bg-[#0A121C] transition-all text-left flex flex-col"
              style={{ minHeight: viewMode === 'grid' ? '280px' : 'auto' }}
            >
              {viewMode === 'grid' ? (
                <div className="flex-1 flex flex-col items-center justify-center p-8 space-y-4">
                  <div className="w-14 h-14 border-2 border-dashed border-[#1D2E42] group-hover:border-[#2DD4BF] flex items-center justify-center text-slate-500 group-hover:text-[#2DD4BF] transition-colors">
                    <Plus className="w-7 h-7" />
                  </div>
                  <div className="text-center">
                    <h3 className="text-base font-bold text-slate-300 group-hover:text-[#2DD4BF] transition-colors">Custom Scenario</h3>
                    <p className="text-xs text-slate-500 mt-1">Create and configure your own scenario</p>
                  </div>
                  <div className="px-6 py-2.5 border border-[#2DD4BF]/50 text-[#2DD4BF] text-xs font-bold hover:bg-[#2DD4BF]/10 transition-colors flex items-center space-x-2">
                    <Plus className="w-3.5 h-3.5" />
                    <span>Create New Scenario</span>
                  </div>
                </div>
              ) : (
                <div className="flex items-center space-x-4 p-4">
                  <div className="w-20 h-16 border border-dashed border-[#1D2E42] flex items-center justify-center">
                    <Plus className="w-6 h-6 text-slate-500 group-hover:text-[#2DD4BF] transition-colors" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-300 group-hover:text-[#2DD4BF] transition-colors">Custom Scenario</h3>
                    <p className="text-xs text-slate-500">Create and configure your own scenario</p>
                  </div>
                </div>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Bottom help bar */}
      <div className="p-3 border-t border-[#1D2E42] bg-[#0A121C] flex items-center justify-between text-[10px] text-slate-500 font-mono shrink-0">
        <div className="flex items-center space-x-2">
          <AlertCircle className="w-3 h-3" />
          <span>Need help choosing a scenario?</span>
          <button className="text-[#2DD4BF] hover:underline">View User Guide</button>
        </div>
        <span>OILTRACE v2.1.0 | NTRO MDA</span>
      </div>

      {/* ── Create New Scenario Modal ── */}
      {createModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-[#0A121C] border border-[#1D2E42] shadow-2xl">
            {/* Modal header */}
            <div className="p-4 border-b border-[#1D2E42] flex items-center justify-between">
              <div>
                <div className="text-[10px] text-[#2DD4BF] font-mono font-bold tracking-wider mb-0.5">SCENARIO BUILDER</div>
                <h2 className="text-sm font-bold text-slate-100">Create New Custom Scenario</h2>
              </div>
              <button
                onClick={() => setCreateModal((prev) => ({ ...prev, isOpen: false }))}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* Drag-and-drop zone */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed p-6 text-center cursor-pointer transition-all ${
                  createModal.isDragging
                    ? 'border-[#2DD4BF] bg-[#2DD4BF]/5'
                    : createModal.file
                    ? 'border-emerald-500 bg-emerald-500/5'
                    : 'border-[#1D2E42] hover:border-[#2DD4BF]/50 hover:bg-[#060B11]'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".tif,.tiff,.png,.jpg,.jpeg"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) setCreateModal((prev) => ({ ...prev, file: f, name: f.name.replace(/\.[^/.]+$/, '') }));
                  }}
                />
                {createModal.file ? (
                  <div>
                    <div className="text-emerald-400 text-2xl mb-1">✓</div>
                    <div className="text-sm font-bold text-emerald-300">{createModal.file.name}</div>
                    <div className="text-xs text-slate-400 mt-0.5">{(createModal.file.size / 1024 / 1024).toFixed(1)} MB · Click to change</div>
                  </div>
                ) : (
                  <div>
                    <Upload className="w-8 h-8 text-slate-500 mx-auto mb-2" />
                    <div className="text-sm font-bold text-slate-300">Drop SAR image here or click to upload</div>
                    <div className="text-xs text-slate-500 mt-1">Supports .tif, .tiff, .png, .jpg (Sentinel-1 GeoTIFF preferred)</div>
                  </div>
                )}
              </div>

              {/* Name */}
              <div>
                <label className="block text-[10px] text-slate-400 font-mono uppercase tracking-wider mb-1">Scenario Name</label>
                <input
                  type="text"
                  value={createModal.name}
                  onChange={(e) => setCreateModal((prev) => ({ ...prev, name: e.target.value }))}
                  className="w-full bg-[#060B11] border border-[#1D2E42] px-3 py-2 text-sm text-slate-100 font-mono focus:border-[#2DD4BF] focus:outline-none"
                  placeholder="Custom SAR Incident"
                />
              </div>

              {/* Coordinates */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] text-slate-400 font-mono uppercase tracking-wider mb-1">
                    <MapPin className="w-3 h-3 inline mr-1" />Longitude (°E)
                  </label>
                  <input
                    type="number"
                    value={createModal.lon}
                    onChange={(e) => setCreateModal((prev) => ({ ...prev, lon: e.target.value }))}
                    step="0.001"
                    className="w-full bg-[#060B11] border border-[#1D2E42] px-3 py-2 text-sm text-slate-100 font-mono focus:border-[#2DD4BF] focus:outline-none"
                    placeholder="71.610"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-slate-400 font-mono uppercase tracking-wider mb-1">
                    <MapPin className="w-3 h-3 inline mr-1" />Latitude (°N)
                  </label>
                  <input
                    type="number"
                    value={createModal.lat}
                    onChange={(e) => setCreateModal((prev) => ({ ...prev, lat: e.target.value }))}
                    step="0.001"
                    className="w-full bg-[#060B11] border border-[#1D2E42] px-3 py-2 text-sm text-slate-100 font-mono focus:border-[#2DD4BF] focus:outline-none"
                    placeholder="18.420"
                  />
                </div>
              </div>

              {createModal.error && (
                <div className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/30 px-3 py-2">
                  ⚠ {createModal.error}
                </div>
              )}

              <div className="text-[10px] text-slate-500 font-mono leading-relaxed">
                The uploaded image will be processed by the AI detection cascade (ResNet-34 → Wide U-Net segmenter).
                For non-TIFF files, a georeferenced slick polygon will be computed from the provided coordinates.
                <span className="text-[#2DD4BF] ml-1">Data provenance will be marked honestly.</span>
              </div>
            </div>

            {/* Modal footer */}
            <div className="p-4 border-t border-[#1D2E42] flex justify-end space-x-3">
              <button
                onClick={() => setCreateModal((prev) => ({ ...prev, isOpen: false }))}
                className="px-4 py-2 text-xs font-mono border border-[#1D2E42] text-slate-400 hover:text-white hover:border-slate-400 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateSubmit}
                disabled={!createModal.file || createModal.isCreating}
                className="px-6 py-2 text-xs font-mono font-bold bg-[#2DD4BF] hover:bg-[#26bba7] text-[#060B11] flex items-center space-x-2 disabled:opacity-50 transition-colors"
              >
                {createModal.isCreating ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-[#060B11]/30 border-t-[#060B11] rounded-full animate-spin" />
                    <span>PROCESSING...</span>
                  </>
                ) : (
                  <>
                    <Layers className="w-3.5 h-3.5" />
                    <span>CREATE & DETECT</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
