import React, { useState } from 'react';
import maplibregl from 'maplibre-gl';
import {
  Layers, Crosshair, ZoomIn, ZoomOut, Compass, Globe,
  Eye, EyeOff, Shield, Key, ChevronDown
} from 'lucide-react';
import { BasemapStyle, ActiveLayersState, CursorCoords } from '../types';

interface MapControlsProps {
  map: maplibregl.Map | null;
  currentBasemap: BasemapStyle;
  switchBasemap: (style: BasemapStyle) => void;
  mapboxToken: string;
  onOpenKeyModal: () => void;
  activeLayers: ActiveLayersState;
  onToggleLayer: (key: keyof ActiveLayersState) => void;
  cursorCoords: CursorCoords | null;
  centroid: [number, number];
  regionLabel: string;
}

export const MapControls: React.FC<MapControlsProps> = ({
  map,
  currentBasemap,
  switchBasemap,
  mapboxToken,
  onOpenKeyModal,
  activeLayers,
  onToggleLayer,
  cursorCoords,
  centroid,
  regionLabel,
}) => {
  const [isLayerPanelOpen, setIsLayerPanelOpen] = useState(false);

  return (
    <>
      {/* ── TOP RIGHT: Basemap Style Switcher (Satellite | Bathymetry | Dark | Key) ── */}
      <div className="absolute top-3 right-3 bg-[#0D1522]/95 border border-[#1E2C3F] p-1 font-mono text-[10px] flex items-center space-x-1 backdrop-blur-md shadow-xl z-20 rounded-sm select-none">
        <button
          onClick={() => switchBasemap('satellite')}
          className={`px-2.5 py-1 flex items-center space-x-1.5 font-bold transition-all rounded-sm ${
            currentBasemap === 'satellite'
              ? 'bg-[#2DD4BF] text-[#060B11]'
              : 'text-slate-300 hover:text-white hover:bg-[#1E2C3F]'
          }`}
          title="Ultra-high resolution true-color satellite imagery + place labels (ESRI)"
        >
          <Globe className="w-3.5 h-3.5" />
          <span>SATELLITE</span>
        </button>

        <button
          onClick={() => switchBasemap('ocean')}
          className={`px-2.5 py-1 flex items-center space-x-1.5 font-bold transition-all rounded-sm ${
            currentBasemap === 'ocean'
              ? 'bg-[#2DD4BF] text-[#060B11]'
              : 'text-slate-300 hover:text-white hover:bg-[#1E2C3F]'
          }`}
          title="Marine bathymetric depth gradients, trenches, and coastal contours (ESRI Ocean)"
        >
          <Compass className="w-3.5 h-3.5" />
          <span>BATHYMETRY</span>
        </button>

        <button
          onClick={() => switchBasemap('dark')}
          className={`px-2.5 py-1 flex items-center space-x-1.5 font-bold transition-all rounded-sm ${
            currentBasemap === 'dark'
              ? 'bg-[#2DD4BF] text-[#060B11]'
              : 'text-slate-300 hover:text-white hover:bg-[#1E2C3F]'
          }`}
          title="Clean tactical dark gray canvas without watermarks (ESRI Dark)"
        >
          <Shield className="w-3.5 h-3.5" />
          <span>DARK HUD</span>
        </button>

        {mapboxToken && (
          <button
            onClick={() => switchBasemap('mapbox')}
            className={`px-2 py-1 flex items-center space-x-1 font-bold transition-all rounded-sm ${
              currentBasemap === 'mapbox'
                ? 'bg-[#2DD4BF] text-[#060B11]'
                : 'text-slate-400 hover:text-white hover:bg-[#1E2C3F]'
            }`}
            title="Custom Mapbox Satellite Streets"
          >
            <span>MAPBOX</span>
          </button>
        )}

        <button
          onClick={onOpenKeyModal}
          className="p-1 text-slate-400 hover:text-[#2DD4BF] hover:bg-[#1E2C3F] transition-colors border-l border-[#1E2C3F] rounded-sm"
          title="Configure Mapbox API Token (Optional)"
        >
          <Key className="w-3 h-3" />
        </button>
      </div>

      {/* ── TOP LEFT: Collapsible Tactical Layer Controls ── */}
      <div className="absolute top-3 left-3 font-mono text-[10px] z-20 select-none">
        <button
          onClick={() => setIsLayerPanelOpen((prev) => !prev)}
          className="flex items-center space-x-2 bg-[#0D1522]/95 border border-[#1E2C3F] hover:border-[#2DD4BF] px-3 py-1.5 text-slate-200 backdrop-blur-md shadow-xl transition-all rounded-sm"
          title="Toggle Tactical Layer Visibility"
        >
          <Layers className="w-3.5 h-3.5 text-[#2DD4BF]" />
          <span className="font-bold tracking-wider">LAYERS</span>
          <span className="text-[9px] px-1 py-0.2 bg-[#2DD4BF]/10 text-[#2DD4BF] border border-[#2DD4BF]/30 font-bold rounded-sm">
            {Object.values(activeLayers).filter(Boolean).length}/7
          </span>
          <ChevronDown className={`w-3 h-3 text-slate-400 transition-transform ${isLayerPanelOpen ? 'rotate-180' : ''}`} />
        </button>

        {isLayerPanelOpen && (
          <div className="mt-1.5 bg-[#0D1522]/98 border border-[#1E2C3F] p-3 space-y-2 backdrop-blur-md shadow-2xl w-64 rounded-sm animate-in fade-in duration-150">
            <div className="flex items-center justify-between border-b border-[#1E2C3F] pb-1.5">
              <span className="text-slate-400 font-bold uppercase text-[9px] tracking-wider">TACTICAL OVERLAYS</span>
              <button
                onClick={() => setIsLayerPanelOpen(false)}
                className="text-slate-500 hover:text-white text-xs px-1"
              >
                ✕
              </button>
            </div>

            <div className="space-y-1 text-slate-300">
              <button
                onClick={() => onToggleLayer('slick')}
                className={`w-full flex items-center justify-between px-2 py-1 text-left transition-colors rounded-sm ${
                  activeLayers.slick ? 'bg-[#2DD4BF]/10 text-slate-100 font-semibold' : 'text-slate-500 opacity-60 hover:opacity-100'
                }`}
              >
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 bg-[#2DD4BF] border border-white" />
                  <span>SAR Slick Outline (10m)</span>
                </div>
                {activeLayers.slick ? <Eye className="w-3 h-3 text-[#2DD4BF]" /> : <EyeOff className="w-3 h-3" />}
              </button>

              <button
                onClick={() => onToggleLayer('cones')}
                className={`w-full flex items-center justify-between px-2 py-1 text-left transition-colors rounded-sm ${
                  activeLayers.cones ? 'bg-[#818CF8]/10 text-slate-100 font-semibold' : 'text-slate-500 opacity-60 hover:opacity-100'
                }`}
              >
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 bg-[#818CF8]/40 border border-[#818CF8] border-dashed" />
                  <span>Drift Origin KDE (50/75/90%)</span>
                </div>
                {activeLayers.cones ? <Eye className="w-3 h-3 text-[#818CF8]" /> : <EyeOff className="w-3 h-3" />}
              </button>

              <button
                onClick={() => onToggleLayer('streamlines')}
                className={`w-full flex items-center justify-between px-2 py-1 text-left transition-colors rounded-sm ${
                  activeLayers.streamlines ? 'bg-[#38BDF8]/10 text-slate-100 font-semibold' : 'text-slate-500 opacity-60 hover:opacity-100'
                }`}
              >
                <div className="flex items-center space-x-2">
                  <span className="w-3 h-0.5 bg-[#38BDF8]" />
                  <span>25-Member RK4 Streamlines</span>
                </div>
                {activeLayers.streamlines ? <Eye className="w-3 h-3 text-[#38BDF8]" /> : <EyeOff className="w-3 h-3" />}
              </button>

              <button
                onClick={() => onToggleLayer('routes')}
                className={`w-full flex items-center justify-between px-2 py-1 text-left transition-colors rounded-sm ${
                  activeLayers.routes ? 'bg-amber-500/10 text-slate-100 font-semibold' : 'text-slate-500 opacity-60 hover:opacity-100'
                }`}
              >
                <div className="flex items-center space-x-2">
                  <span className="w-3 h-0.5 border-t border-dashed border-[#F59E0B]" />
                  <span>4D Reconstructed Route</span>
                </div>
                {activeLayers.routes ? <Eye className="w-3 h-3 text-[#F59E0B]" /> : <EyeOff className="w-3 h-3" />}
              </button>

              <button
                onClick={() => onToggleLayer('vessels')}
                className={`w-full flex items-center justify-between px-2 py-1 text-left transition-colors rounded-sm ${
                  activeLayers.vessels ? 'bg-slate-800 text-slate-100 font-semibold' : 'text-slate-500 opacity-60 hover:opacity-100'
                }`}
              >
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#2DD4BF] border border-white" />
                  <span>Candidate Vessels (AIS)</span>
                </div>
                {activeLayers.vessels ? <Eye className="w-3 h-3 text-[#2DD4BF]" /> : <EyeOff className="w-3 h-3" />}
              </button>

              <button
                onClick={() => onToggleLayer('eez')}
                className={`w-full flex items-center justify-between px-2 py-1 text-left transition-colors rounded-sm ${
                  activeLayers.eez ? 'bg-amber-500/10 text-slate-100 font-semibold' : 'text-slate-500 opacity-60 hover:opacity-100'
                }`}
              >
                <div className="flex items-center space-x-2">
                  <span className="w-3 h-0.5 border-t border-dashed border-[#F59E0B]" />
                  <span>Indian EEZ (200 NM)</span>
                </div>
                {activeLayers.eez ? <Eye className="w-3 h-3 text-[#F59E0B]" /> : <EyeOff className="w-3 h-3" />}
              </button>

              <button
                onClick={() => onToggleLayer('wind')}
                className={`w-full flex items-center justify-between px-2 py-1 text-left transition-colors rounded-sm ${
                  activeLayers.wind ? 'bg-[#2DD4BF]/10 text-slate-100 font-semibold' : 'text-slate-500 opacity-60 hover:opacity-100'
                }`}
                title="Metocean Vectors: Teal = Ocean Surface Current (100% advection), Amber = Surface Wind (3% leeway), Purple = Resultant Net Oil Drift"
              >
                <div className="flex items-center space-x-2">
                  <div className="flex -space-x-1">
                    <span className="w-2 h-2 rounded-full bg-[#2DD4BF] ring-1 ring-[#0D1522]" title="Teal: Ocean Current (100% advection)" />
                    <span className="w-2 h-2 rounded-full bg-[#F59E0B] ring-1 ring-[#0D1522]" title="Amber: Surface Wind (3% leeway)" />
                    <span className="w-2 h-2 rounded-full bg-[#A855F7] ring-1 ring-[#0D1522]" title="Purple: Net Drift Vector" />
                  </div>
                  <span>Vectors (Current/Wind/Drift)</span>
                </div>
                {activeLayers.wind ? <Eye className="w-3 h-3 text-[#2DD4BF]" /> : <EyeOff className="w-3 h-3" />}
              </button>
            </div>

            <div className="pt-2 border-t border-[#1E2C3F] text-[9px] text-[#2DD4BF] flex items-center justify-between">
              <span>CLICK MAP TO QUERY FORCING</span>
              <Compass className="w-3 h-3" />
            </div>
          </div>
        )}
      </div>

      {/* ── BOTTOM RIGHT: Cursor Coordinates HUD & Zoom Controls ── */}
      <div className="absolute bottom-6 right-4 flex items-end space-x-3 z-20 select-none">
        {cursorCoords && (
          <div className="bg-[#0A121C]/95 border border-[#1D2E42] px-3 py-2 font-mono text-[10px] text-slate-300 backdrop-blur-md shadow-lg hidden md:block">
            <div className="flex items-center space-x-3">
              <div>
                <span className="text-slate-500 mr-1">LON:</span>
                <span className="text-slate-100 font-bold">{cursorCoords.lon.toFixed(4)}° E</span>
              </div>
              <div>
                <span className="text-slate-500 mr-1">LAT:</span>
                <span className="text-slate-100 font-bold">{cursorCoords.lat.toFixed(4)}° N</span>
              </div>
              <div className="border-l border-[#1D2E42] pl-2 text-[#2DD4BF] uppercase">
                {regionLabel}
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-col space-y-1">
          <button
            onClick={() => map?.zoomIn()}
            className="w-8 h-8 bg-[#0A121C] border border-[#1D2E42] hover:border-[#2DD4BF] text-slate-200 flex items-center justify-center font-mono text-sm transition-colors"
            title="Zoom In"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={() => map?.zoomOut()}
            className="w-8 h-8 bg-[#0A121C] border border-[#1D2E42] hover:border-[#2DD4BF] text-slate-200 flex items-center justify-center font-mono text-sm transition-colors"
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            onClick={() => map?.flyTo({ center: [centroid[0], centroid[1]], zoom: 8.5, pitch: 25 })}
            className="w-8 h-8 bg-[#0A121C] border border-[#1D2E42] hover:border-[#2DD4BF] text-[#2DD4BF] flex items-center justify-center transition-colors"
            title="Recenter on Spill Origin"
          >
            <Crosshair className="w-4 h-4" />
          </button>
        </div>
      </div>
    </>
  );
};
