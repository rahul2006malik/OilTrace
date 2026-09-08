import React, { useState, useCallback, useEffect } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import { useMapLibreInstance } from './useMapLibreInstance';
import { useMaritimeBoundariesLayer } from './layers/useMaritimeBoundariesLayer';
import { useSlickLayer } from './layers/useSlickLayer';
import { useOriginConeLayer } from './layers/useOriginConeLayer';
import { useStreamlinesLayer } from './layers/useStreamlinesLayer';
import { useVesselTracksLayer } from './layers/useVesselTracksLayer';
import { useMetoceanVectorsLayer } from './layers/useMetoceanVectorsLayer';
import { usePhysicsProbeLayer } from './layers/usePhysicsProbeLayer';
import { MapControls } from './controls/MapControls';
import { MapboxKeyModal } from './controls/MapboxKeyModal';
import { ActiveLayersState } from './types';

export const TacticalMap: React.FC = () => {
  const detection = useOilTraceStore((s) => s.detection);
  const driftRun = useOilTraceStore((s) => s.driftRun);
  const attribution = useOilTraceStore((s) => s.attribution);
  const selectedCandidateId = useOilTraceStore((s) => s.selectedCandidateId);
  const selectCandidate = useOilTraceStore((s) => s.selectCandidate);
  const fetchPhysics = useOilTraceStore((s) => s.fetchPhysics);
  const togglePhysicsInspector = useOilTraceStore((s) => s.togglePhysicsInspector);
  const activeMapTab = useOilTraceStore((s) => s.activeMapTab);
  const activeScenarioId = useOilTraceStore((s) => s.activeScenarioId);
  const availableScenarios = useOilTraceStore((s) => s.availableScenarios);

  const {
    mapContainer,
    mapRef,
    mapLoaded,
    currentBasemap,
    switchBasemap,
    cursorCoords,
    mapboxToken,
    setMapboxToken,
  } = useMapLibreInstance();

  const [showKeyModal, setShowKeyModal] = useState<boolean>(false);
  const [activeLayers, setActiveLayers] = useState<ActiveLayersState>({
    slick: true,
    cones: true,
    streamlines: true,
    vessels: true,
    routes: true,
    wind: true,
    eez: true,
  });

  const activeScenario = availableScenarios.find((s) => s.scenario_id === activeScenarioId);
  const activeRegionLabel = activeScenario?.region ? activeScenario.region.toUpperCase() : 'MARITIME AOI';

  // Toggle active layer state
  const handleToggleLayer = useCallback((key: keyof ActiveLayersState) => {
    setActiveLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // Synchronize Tab selection with layers
  useEffect(() => {
    if (activeMapTab === 'Ocean Currents' && !activeLayers.streamlines) {
      setActiveLayers((prev) => ({ ...prev, streamlines: true }));
    } else if (activeMapTab === 'Wind' && !activeLayers.wind) {
      setActiveLayers((prev) => ({ ...prev, wind: true }));
    } else if (activeMapTab === 'Vessel Traffic') {
      setActiveLayers((prev) => ({ ...prev, vessels: true, routes: true }));
    }
  }, [activeMapTab]);

  // Layer Controllers
  const map = mapRef.current;
  useMaritimeBoundariesLayer(map, mapLoaded, activeLayers.eez);
  useSlickLayer(map, mapLoaded, detection, driftRun, activeLayers.slick);
  useOriginConeLayer(map, mapLoaded, driftRun, detection, activeLayers.cones);
  useStreamlinesLayer(map, mapLoaded, driftRun, activeLayers.streamlines);
  useVesselTracksLayer(
    map,
    mapLoaded,
    attribution,
    detection,
    selectedCandidateId,
    selectCandidate,
    activeLayers.vessels,
    activeLayers.routes
  );
  useMetoceanVectorsLayer(map, mapLoaded, detection, activeLayers.wind);
  usePhysicsProbeLayer(map, mapLoaded, detection, fetchPhysics, togglePhysicsInspector);

  // Mapbox Key Save Handler
  const handleSaveMapboxKey = (token: string) => {
    setMapboxToken(token);
    localStorage.setItem('oiltrace_mapbox_token', token);
    setShowKeyModal(false);
    if (token && map) {
      switchBasemap('mapbox');
    }
  };

  return (
    <div className="relative w-full h-full bg-[#060B11] overflow-hidden select-none">
      {/* MapLibre WebGL Canvas */}
      <div ref={mapContainer} className="w-full h-full" />

      {/* Modular HUD Controls & Overlays */}
      <MapControls
        map={map}
        currentBasemap={currentBasemap}
        switchBasemap={(style) => switchBasemap(style, () => setShowKeyModal(true))}
        mapboxToken={mapboxToken}
        onOpenKeyModal={() => setShowKeyModal(true)}
        activeLayers={activeLayers}
        onToggleLayer={handleToggleLayer}
        cursorCoords={cursorCoords}
        centroid={detection.centroid}
        regionLabel={activeRegionLabel}
      />

      {/* Mapbox Token Configuration Modal */}
      <MapboxKeyModal
        isOpen={showKeyModal}
        onClose={() => setShowKeyModal(false)}
        currentKey={mapboxToken}
        onSave={handleSaveMapboxKey}
      />
    </div>
  );
};
